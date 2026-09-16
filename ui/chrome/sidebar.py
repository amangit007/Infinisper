import math

from PySide6.QtCore import QRectF, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (
    QAbstractButton,
    QButtonGroup,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.assets.mark import mark_pixmap
from ui.theme import MONO_FONT_FAMILY
from ui.widgets.mic_level_meter import MicLevelMeter

_BRAND_MARK_SIZE = 30

_WIDTH = 222
_NAV_ITEMS = [
    ("dashboard", "Dashboard"),
    ("models", "Models & providers"),
    ("language", "Language"),
    ("history", "History"),
]


class _NavRow(QAbstractButton):
    def __init__(self, nav_id: str, label: str, parent=None):
        super().__init__(parent)
        self.nav_id = nav_id
        self._label = label
        self.setCheckable(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(36)
        self._hover = False
        self._bg_selected = QColor("#5b8def").lighter(0)
        self._bg_hover = QColor(0, 0, 0, 0)
        self._fg_selected = QColor("#5b8def")
        self._fg_default = QColor("#b3bac6")

    def apply_theme(self, tokens: dict):
        self._bg_selected = _parse_rgba(tokens["accent_soft"])
        self._fg_selected = QColor(tokens["accent"])
        self._fg_default = QColor(tokens["text2"])
        self._bg_hover = QColor(tokens["panel2"])
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(self.rect())
        if self.isChecked():
            painter.setBrush(self._bg_selected)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 7, 7)
        elif self._hover:
            painter.setBrush(self._bg_hover)
            painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 7, 7)

        fg = self._fg_selected if self.isChecked() else self._fg_default

        bullet_size = 6
        bullet_x = 11
        bullet_y = (rect.height() - bullet_size) / 2
        painter.setBrush(fg)
        painter.setOpacity(0.85)
        painter.drawRoundedRect(QRectF(bullet_x, bullet_y, bullet_size, bullet_size), 2, 2)
        painter.setOpacity(1.0)

        painter.setPen(fg)
        text_rect = rect.adjusted(bullet_x + bullet_size + 10, 0, -11, 0)
        painter.drawText(text_rect, Qt.AlignVCenter | Qt.AlignLeft, self._label)


def _parse_rgba(rgba: str) -> QColor:
    # "rgba(r, g, b, a)" with a already in 0..255, as produced by theme.oklch_to_rgba.
    parts = rgba[rgba.index("(") + 1 : rgba.index(")")].split(",")
    r, g, b, a = (int(p.strip()) for p in parts)
    return QColor(r, g, b, a)


class _BreathingDot(QWidget):
    """Status indicator dot with subtle breathing animation."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(7, 7)
        self._color = QColor("#5ec386")
        self._frame = 0
        self._timer = QTimer(self)
        self._timer.setInterval(140)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def _tick(self):
        self._frame += 1
        self.update()

    def paintEvent(self, event):
        # 0.06, not 0.03 -- the timer interval doubled (70ms -> 140ms) to cut repaint
        # frequency, so the phase step doubles too to keep the breathing rate itself
        # unchanged rather than making it look twice as slow.
        phase = self._frame * 0.06
        pulse = (math.sin(phase) + 1) / 2  # 0..1
        opacity = 0.45 + pulse * 0.45
        scale = 1.0 + pulse * 0.12

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setPen(Qt.NoPen)
        painter.setOpacity(opacity)
        painter.setBrush(self._color)
        cx, cy = self.rect().width() / 2, self.rect().height() / 2
        r = (self.rect().width() / 2) * scale
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))


class Sidebar(QWidget):
    nav_changed = Signal(str)
    theme_toggle_requested = Signal()

    _status_changed = Signal(str)
    _level_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("Sidebar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedWidth(_WIDTH)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(12, 18, 12, 12)
        outer.setSpacing(0)

        brand_row = QHBoxLayout()
        brand_row.setContentsMargins(8, 0, 8, 18)
        brand_row.setSpacing(10)
        self._brand_mark = QLabel()
        self._brand_mark.setFixedSize(_BRAND_MARK_SIZE, _BRAND_MARK_SIZE)
        brand_row.addWidget(self._brand_mark)
        brand_box = QVBoxLayout()
        brand_box.setSpacing(3)
        brand = QLabel("Infinisper")
        brand.setObjectName("SidebarBrand")
        subtitle = QLabel("local-first dictation")
        subtitle.setObjectName("SidebarSubtitle")
        subtitle.setStyleSheet(f"font-family: {MONO_FONT_FAMILY};")
        brand_box.addWidget(brand)
        brand_box.addWidget(subtitle)
        brand_row.addLayout(brand_box)
        brand_row.addStretch()
        outer.addLayout(brand_row)

        nav_box = QVBoxLayout()
        nav_box.setSpacing(2)
        self._rows: dict[str, _NavRow] = {}
        self._group = QButtonGroup(self)
        self._group.setExclusive(True)
        for nav_id, label in _NAV_ITEMS:
            row = _NavRow(nav_id, label)
            row.clicked.connect(lambda checked, nid=nav_id: self._on_row_clicked(nid))
            self._group.addButton(row)
            self._rows[nav_id] = row
            nav_box.addWidget(row)
        outer.addLayout(nav_box)

        outer.addStretch()

        self._mic_panel = QWidget()
        self._mic_panel.setObjectName("SidebarMicPanel")
        self._mic_panel.setAttribute(Qt.WA_StyledBackground, True)
        mic_layout = QVBoxLayout(self._mic_panel)
        mic_layout.setContentsMargins(12, 11, 12, 11)
        mic_layout.setSpacing(9)

        mic_header = QHBoxLayout()
        mic_title = QLabel("INPUT LEVEL")
        mic_title.setObjectName("SidebarMicLabel")
        mic_header.addWidget(mic_title)
        mic_header.addStretch()
        self._db_label = QLabel("—")
        self._db_label.setObjectName("SidebarDbLabel")
        mic_header.addWidget(self._db_label)
        mic_layout.addLayout(mic_header)

        self.mic_meter = MicLevelMeter()
        mic_layout.addWidget(self.mic_meter)

        self._device_label = QLabel("System default")
        self._device_label.setObjectName("SidebarDeviceLabel")
        self._device_label.setWordWrap(True)
        mic_layout.addWidget(self._device_label)

        outer.addWidget(self._mic_panel)
        outer.addSpacing(12)

        bottom_row = QHBoxLayout()
        bottom_row.setSpacing(8)
        self._status_dot = _BreathingDot()
        bottom_row.addWidget(self._status_dot)
        self._status_label = QLabel("Ready")
        self._status_label.setObjectName("SidebarStatusText")
        bottom_row.addWidget(self._status_label)
        self._hotkey_label = QLabel("Ctrl+Win")
        self._hotkey_label.setObjectName("SidebarHotkeyText")
        bottom_row.addWidget(self._hotkey_label)
        bottom_row.addStretch()
        self._theme_button = QPushButton("◑")
        self._theme_button.setObjectName("ThemeToggleButton")
        self._theme_button.setFixedSize(26, 26)
        self._theme_button.setCursor(Qt.PointingHandCursor)
        self._theme_button.setFlat(True)
        self._theme_button.setToolTip("Toggle theme")
        self._theme_button.clicked.connect(self.theme_toggle_requested.emit)
        bottom_row.addWidget(self._theme_button)
        outer.addLayout(bottom_row)

        self._status_changed.connect(self._apply_status)
        self._level_changed.connect(self._update_db_readout)

        self.set_active("dashboard")

    def _on_row_clicked(self, nav_id: str):
        self.nav_changed.emit(nav_id)

    def set_active(self, nav_id: str):
        row = self._rows.get(nav_id)
        if row is not None:
            row.setChecked(True)

    def set_status(self, text: str):
        """Safe to call from any thread -- queues across via the Qt signal, same
        pattern as ui.tray.TrayIcon.set_status."""
        self._status_changed.emit(text)

    def _apply_status(self, text: str):
        self._status_label.setText(text)

    def set_device_caption(self, text: str):
        self._device_label.setText(text)

    def set_listening(self, listening: bool):
        self.mic_meter.set_listening(listening)
        if not listening:
            self._db_label.setText("—")

    def update_audio_level(self, level: float):
        """Duck-typed to match ui.chip.ChipWindow.update_audio_level so both can be
        wired to audio.capture.set_chip() through the same fan-out. Called from the
        audio callback thread -- forwards to the mic meter (thread-safe internally)
        and marshals the dB readout across via _level_changed.
        """
        self.mic_meter.update_audio_level(level)
        self._level_changed.emit(level)

    def _update_db_readout(self, level: float):
        if level <= 0.0:
            self._db_label.setText("—")
            return
        db = 20 * math.log10(min(1.0, level))
        self._db_label.setText(f"{db:.0f} dB")

    def apply_theme(self, tokens: dict):
        for row in self._rows.values():
            row.apply_theme(tokens)
        self.mic_meter.set_color(tokens["good"])
        self._status_dot.set_color(tokens["good"])
        self._brand_mark.setPixmap(mark_pixmap(tokens["accent"], _BRAND_MARK_SIZE))
