from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QWidget

from ui.assets.mark import mark_pixmap
from ui.widgets.icon_button import IconButton

_HEIGHT = 38
_BUTTON_SIZE = (34, 24)
_MARK_SIZE = 16


class _MarkGlyph(QLabel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_MARK_SIZE, _MARK_SIZE)

    def set_color(self, hex_color: str):
        self.setPixmap(mark_pixmap(hex_color, _MARK_SIZE))


class TitleBar(QWidget):
    """Frameless window titlebar supporting drag-to-move and window controls."""

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

        self._minimize_btn = self._make_button("minus", "TitleBarButton")
        self._minimize_btn.clicked.connect(self._on_minimize)
        layout.addWidget(self._minimize_btn)

        self._maximize_btn = self._make_button("square", "TitleBarButton", size=11)
        self._maximize_btn.clicked.connect(self._on_maximize_restore)
        layout.addWidget(self._maximize_btn)

        self._close_btn = self._make_button("x", "TitleBarCloseButton")
        self._close_btn.clicked.connect(self.close_requested.emit)
        layout.addWidget(self._close_btn)

    def _make_button(self, icon_name: str, object_name: str, size: int = 14) -> IconButton:
        button = IconButton(icon_name, size=size, stroke_width=2.0)
        button.setObjectName(object_name)
        button.setFixedSize(*_BUTTON_SIZE)
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
