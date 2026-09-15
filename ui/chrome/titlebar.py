from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QWidget

from ui.assets.mark import mark_pixmap

_HEIGHT = 38
_BUTTON_SIZE = (34, 24)
_MARK_SIZE = 16  # matches Infinisper Brand.html's own "in place" titlebar mockup


class _MarkGlyph(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_MARK_SIZE, _MARK_SIZE)

    def set_color(self, hex_color: str):
        self.setPixmap(mark_pixmap(hex_color, _MARK_SIZE))


class TitleBar(QWidget):
    """Frameless-window titlebar: drag-to-move, minimize/maximize/close.

    Windows' UIPI/focus rules don't come into play here -- unlike the chip (invariant 1),
    this window is a normal activatable app window, so startSystemMove() is safe to use
    directly instead of the ctypes fallbacks the chip needs.
    """

    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("TitleBar")
        self.setAttribute(Qt.WA_StyledBackground, True)
        self.setFixedHeight(_HEIGHT)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 0, 6, 0)
        layout.setSpacing(10)

        self._mark = _MarkGlyph()
        layout.addWidget(self._mark)

        self._label = QLabel("Infinisper")
        self._label.setObjectName("TitleBarLabel")
        layout.addWidget(self._label)

        layout.addStretch()

        self._minimize_btn = self._make_button("—", "TitleBarButton")
        self._minimize_btn.clicked.connect(self._on_minimize)
        layout.addWidget(self._minimize_btn)

        self._maximize_btn = self._make_button("□", "TitleBarButton")
        self._maximize_btn.clicked.connect(self._on_maximize_restore)
        layout.addWidget(self._maximize_btn)

        self._close_btn = self._make_button("✕", "TitleBarButton")
        self._close_btn.setObjectName("TitleBarCloseButton")
        self._close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self._close_btn)

    def _make_button(self, text: str, object_name: str) -> QPushButton:
        button = QPushButton(text)
        button.setObjectName(object_name)
        button.setFixedSize(*_BUTTON_SIZE)
        button.setCursor(Qt.PointingHandCursor)
        button.setFlat(True)
        return button

    def apply_theme(self, tokens: dict):
        self._mark.set_color(tokens["accent"])

    def _on_minimize(self):
        self.window().showMinimized()

    def _on_maximize_restore(self):
        window = self.window()
        if window.isMaximized():
            window.showNormal()
        else:
            window.showMaximized()

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            handle = self.window().windowHandle()
            if handle is not None:
                handle.startSystemMove()
                event.accept()
                return
        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.LeftButton:
            self._on_maximize_restore()
            return
        super().mouseDoubleClickEvent(event)
