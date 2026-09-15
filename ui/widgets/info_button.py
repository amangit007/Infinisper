from PySide6.QtCore import Qt
from PySide6.QtWidgets import QToolButton


class InfoButton(QToolButton):
    """A small round "i" button whose hover tooltip carries rich HTML content
    (e.g. a pros/cons list). Qt shows a widget's tooltip on hover natively --
    no custom popup/event handling needed.
    """

    def __init__(self, info_html: str, parent=None):
        super().__init__(parent)
        self.setText("i")
        self.setToolTip(info_html)
        self.setCursor(Qt.WhatsThisCursor)
        self.setFixedSize(18, 18)
        self.setStyleSheet(
            "QToolButton {"
            "  border-radius: 9px;"
            "  border: 1px solid palette(mid);"
            "  font-weight: bold;"
            "  font-size: 11px;"
            "  color: palette(mid);"
            "}"
            "QToolButton:hover {"
            "  background: palette(highlight);"
            "  color: palette(highlighted-text);"
            "  border-color: palette(highlight);"
            "}"
        )
