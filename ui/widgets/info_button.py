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
        # Colors come from the app stylesheet (ui/theme.py), so the button follows the
        # in-app light/dark switch rather than the Windows palette.
        self.setObjectName("InfoButton")
