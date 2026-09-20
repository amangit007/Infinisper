from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QApplication,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from audio import capture as audio_capture
from history.store import HistoryStore
from ui.assets.mark import BRAND_HEX, mark_icon
from ui.chrome.sidebar import Sidebar
from ui.chrome.titlebar import TitleBar
from ui.tabs.dashboard_tab import DashboardTab
from ui.tabs.history_tab import HistoryTab
from ui.tabs.language_tab import LanguageTab
from ui.tabs.models_tab import ModelsTab
from ui.theme import DARK, THEMES, build_stylesheet
from utils.windows import HOTKEY_PRESETS

# Default window dimensions and shadow margins.
_CONTENT_SIZE = (1320, 864)
_SHADOW_MARGIN = 24
_MIN_SIZE = (760, 560)
_RADIUS = 10


def _device_caption(device_index) -> str:
    if device_index is not None:
        for name, index in audio_capture.list_input_devices():
            if index == device_index:
                return name
        return "System default"
    default_name = audio_capture.default_input_device_name()
    return f"System default — {default_name}" if default_name else "System default"


def _cursor_for_edges(edges: Qt.Edges) -> Qt.CursorShape:
    top = bool(edges & Qt.Edge.TopEdge)
    bottom = bool(edges & Qt.Edge.BottomEdge)
    left = bool(edges & Qt.Edge.LeftEdge)
    right = bool(edges & Qt.Edge.RightEdge)
    if (top and left) or (bottom and right):
        return Qt.SizeFDiagCursor
    if (top and right) or (bottom and left):
        return Qt.SizeBDiagCursor
    if left or right:
        return Qt.SizeHorCursor
    if top or bottom:
        return Qt.SizeVerCursor
    return Qt.ArrowCursor


class _ShadowLayer(QWidget):
    """A static, non-interactive rounded rect that exists purely to give
    QGraphicsDropShadowEffect something cheap to blur.

    Qt effects re-rasterize their *entire* widget subtree to an offscreen buffer and
    reblur it on every single repaint any descendant asks for. The old layout put the
    effect directly on RootFrame -- which contains the scroll area, the flowing pipeline
    animation and the breathing status dot -- so every scroll step and every animation
    tick forced a full-window blur at radius 60. This widget has no children and only
    repaints on resize/move, so the expensive part now only reruns when the window
    actually changes shape.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.setCursor(Qt.ArrowCursor)
        self._color = QColor(DARK["bg"])
        self._radius = _RADIUS

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def set_radius(self, radius: int):
        self._radius = radius
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        painter.drawRoundedRect(self.rect(), self._radius, self._radius)


class _ResizableContainer(QWidget):
    """The window's central widget. Manually positions two children -- a static
    _ShadowLayer behind, RootFrame (the real, animated content) in front -- inset by a
    margin that doubles as a resize grip -- frameless windows get no native resize
    border, so this is the same technique the titlebar already uses for drag-to-move
    (startSystemMove), just for the four edges/corners. The margin (and the shadow)
    collapses to 0 while maximized.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMouseTracking(True)
        self._shadow_layer: QWidget | None = None
        self._root_frame: QWidget | None = None
        self._margin = _SHADOW_MARGIN

    def set_content(self, shadow_layer: QWidget, root_frame: QWidget):
        self._shadow_layer = shadow_layer
        self._root_frame = root_frame
        self._layout_children()

    def set_margin(self, margin: int):
        self._margin = margin
        self._layout_children()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_children()

    def _layout_children(self):
        if self._root_frame is None:
            return
        rect = self.rect().adjusted(self._margin, self._margin, -self._margin, -self._margin)
        self._shadow_layer.setGeometry(rect)
        self._root_frame.setGeometry(rect)

    def _edges_at(self, pos) -> Qt.Edges:
        margin = self._margin
        if margin <= 0:
            return Qt.Edges()
        w, h = self.width(), self.height()
        edges = Qt.Edges()
        if pos.x() <= margin:
            edges |= Qt.Edge.LeftEdge
        elif pos.x() >= w - margin:
            edges |= Qt.Edge.RightEdge
        if pos.y() <= margin:
            edges |= Qt.Edge.TopEdge
        elif pos.y() >= h - margin:
            edges |= Qt.Edge.BottomEdge
        return edges

    def mouseMoveEvent(self, event):
        self.setCursor(_cursor_for_edges(self._edges_at(event.position().toPoint())))
        super().mouseMoveEvent(event)

    def leaveEvent(self, event):
        # Without this, the last cursor shape set above (e.g. SizeVer) stays applied to
        # this widget even after the pointer leaves it -- and since child widgets that
        # never set their own cursor inherit their parent's, that shape then shows
        # everywhere over RootFrame's content until something else overrides it.
        self.unsetCursor()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            edges = self._edges_at(event.position().toPoint())
            if edges:
                handle = self.window().windowHandle()
                if handle is not None:
                    handle.startSystemResize(edges)
                    event.accept()
                    return
        super().mousePressEvent(event)


class MainWindow(QMainWindow):
    settings_saved = Signal(dict)
    delete_model_requested = Signal(str)
    download_model_requested = Signal(str)
    cleanup_changed = Signal()
    activate_engine_requested = Signal(str)
    whisper_model_size_changed = Signal(str)
    language_settings_changed = Signal(bool)  # force_english_transliteration
    cleanup_transformation_changed = Signal(str, str)  # output_mode, target_language
    dictation_language_changed = Signal(str)  # dictation_language (e.g. 'en', 'auto')
    custom_words_changed = Signal(list)  # custom_words
    engine_status_refresh_requested = Signal(str, bool)  # (active_engine, busy) thread-safe dispatch

    def __init__(self, current_config: dict, history_store: HistoryStore, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Infinisper")
        self.setWindowIcon(mark_icon(BRAND_HEX))
        self._theme_name = "dark"
        self._maximized = False
        self.engine_status_refresh_requested.connect(
            self.refresh_engine_statuses, Qt.QueuedConnection
        )

        self.setWindowFlags(Qt.FramelessWindowHint)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setMinimumSize(
            _MIN_SIZE[0] + _SHADOW_MARGIN * 2, _MIN_SIZE[1] + _SHADOW_MARGIN * 2
        )

        container = _ResizableContainer()
        container.setObjectName("WindowContainer")
        self.setCentralWidget(container)

        self._shadow_layer = _ShadowLayer(container)
        shadow = QGraphicsDropShadowEffect(self._shadow_layer)
        shadow.setBlurRadius(60)
        shadow.setOffset(0, 12)
        shadow.setColor(QColor(0, 0, 0, 130))
        self._shadow_layer.setGraphicsEffect(shadow)
        self._shadow_effect = shadow

        self._root_frame = QWidget(container)
        self._root_frame.setObjectName("RootFrame")
        self._root_frame.setAttribute(Qt.WA_StyledBackground, True)
        self._root_frame.setCursor(Qt.ArrowCursor)

        container.set_content(self._shadow_layer, self._root_frame)
        self._container = container

        root_layout = QVBoxLayout(self._root_frame)
        root_layout.setContentsMargins(0, 0, 0, 0)
        root_layout.setSpacing(0)

        self._titlebar = TitleBar()
        self._titlebar.close_requested.connect(self.close)
        root_layout.addWidget(self._titlebar)

        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        root_layout.addLayout(body)

        self.sidebar = Sidebar()
        self.sidebar.nav_changed.connect(self._on_nav_changed)
        self.sidebar.theme_toggle_requested.connect(self._on_theme_toggle)
        self.sidebar.set_device_caption(_device_caption(current_config.get("input_device")))
        init_hotkey = current_config.get("hotkey", "ctrl+win")
        self.sidebar.set_hotkey_caption(HOTKEY_PRESETS.get(init_hotkey, {}).get("display", "Ctrl + Win"))
        body.addWidget(self.sidebar)

        self._stack = QStackedWidget()
        body.addWidget(self._stack, stretch=1)

        self.dashboard_tab = DashboardTab(current_config)
        self.dashboard_tab.settings_saved.connect(self.settings_saved.emit)
        self.dashboard_tab.settings_saved.connect(self._on_settings_saved)
        self.dashboard_tab.delete_model_requested.connect(self.delete_model_requested.emit)
        self.dashboard_tab.download_model_requested.connect(self.download_model_requested.emit)
        self.dashboard_tab.manage_models_requested.connect(lambda: self._on_nav_requested("models"))
        self._stack.addWidget(self.dashboard_tab)

        self.models_tab = ModelsTab()
        self.models_tab.changed.connect(self.cleanup_changed.emit)
        self.models_tab.activate_engine_requested.connect(self.activate_engine_requested.emit)
        self.models_tab.download_requested.connect(self.download_model_requested.emit)
        self.models_tab.delete_engine_requested.connect(self.delete_model_requested.emit)
        self.models_tab.whisper_model_size_changed.connect(self.whisper_model_size_changed.emit)
        self._stack.addWidget(self.models_tab)

        self.language_tab = LanguageTab(current_config)
        self.language_tab.settings_changed.connect(self.language_settings_changed.emit)
        self.language_tab.transformation_changed.connect(self.cleanup_transformation_changed.emit)
        self.language_tab.language_changed.connect(self.dictation_language_changed.emit)
        self.language_tab.custom_words_changed.connect(self.custom_words_changed.emit)
        self._stack.addWidget(self.language_tab)

        self.history_tab = HistoryTab(history_store)
        self._stack.addWidget(self.history_tab)

        self._nav_pages = {
            "dashboard": self.dashboard_tab,
            "models": self.models_tab,
            "language": self.language_tab,
            "history": self.history_tab,
        }

        self._set_default_geometry()
        self._apply_theme()

    def _set_default_geometry(self):
        # Center window within available screen geometry.
        screen = QApplication.primaryScreen().availableGeometry()
        default_w = min(_CONTENT_SIZE[0] + _SHADOW_MARGIN * 2, screen.width() - 80)
        default_h = min(_CONTENT_SIZE[1] + _SHADOW_MARGIN * 2, screen.height() - 80)
        self.resize(default_w, default_h)
        self.move(
            screen.x() + (screen.width() - default_w) // 2,
            screen.y() + (screen.height() - default_h) // 2,
        )

    def _on_settings_saved(self, new_config: dict):
        self.sidebar.set_device_caption(_device_caption(new_config.get("input_device")))
        hotkey_id = new_config.get("hotkey", "ctrl+win")
        hotkey_display = HOTKEY_PRESETS.get(hotkey_id, {}).get("display", "Ctrl + Win")
        self.sidebar.set_hotkey_caption(hotkey_display)
        self.dashboard_tab.update_hotkey_hint(hotkey_display)

    def refresh_engine_statuses(self, active_engine: str, busy: bool):
        """Keeps both the Dashboard's active-engine radio picker and the Models &
        providers engine table in sync -- app.py calls this one entry point instead
        of reaching into either tab individually."""
        self.dashboard_tab.refresh_engine_statuses(active_engine, busy)
        self.models_tab.refresh_engine_statuses(active_engine, busy)

    def _on_nav_changed(self, nav_id: str):
        page = self._nav_pages.get(nav_id)
        if page is not None:
            self._stack.setCurrentWidget(page)

    def _on_nav_requested(self, nav_id: str):
        """Programmatic navigation (e.g. a card's 'manage in Models & providers ->'
        link) -- keeps the sidebar's own selection state in sync too."""
        self.sidebar.set_active(nav_id)
        self._on_nav_changed(nav_id)

    def _on_theme_toggle(self):
        self._theme_name = "light" if self._theme_name == "dark" else "dark"
        self._apply_theme()

    def _apply_theme(self):
        tokens = THEMES[self._theme_name]
        # Applied to RootFrame, not self -- self is the frameless QMainWindow itself and
        # doesn't need styling; RootFrame is the actual visible root every other widget
        # cascades from. `maximized` is passed as a real argument, not a QSS
        # `[maximized="true"]` dynamic-property selector -- see build_stylesheet's
        # docstring for why that pattern proved unreliable here.
        self._root_frame.setStyleSheet(build_stylesheet(tokens, maximized=self._maximized))
        self._shadow_layer.set_color(tokens["bg"])
        self._titlebar.apply_theme(tokens)
        self.sidebar.apply_theme(tokens)
        self.dashboard_tab.apply_theme(tokens)
        self.history_tab.apply_theme(tokens)

    def _apply_maximized_state(self, maximized: bool):
        if maximized == self._maximized:
            return
        self._maximized = maximized
        self._container.set_margin(0 if maximized else _SHADOW_MARGIN)
        self._shadow_layer.setVisible(not maximized)
        self._shadow_layer.set_radius(0 if maximized else _RADIUS)
        self._apply_theme()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.WindowStateChange:
            self._apply_maximized_state(self.isMaximized())
            # Frameless + WA_TranslucentBackground windows can come back from a minimize
            # without repainting on Windows -- force one so restoring doesn't leave a
            # blank window.
            if not self.isMinimized():
                self._root_frame.update()

    def show_dashboard(self):
        self.sidebar.set_active("dashboard")
        self._on_nav_changed("dashboard")
        self.show()
        self.raise_()
        self.activateWindow()
