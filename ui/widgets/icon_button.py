from PySide6.QtCore import Property, QSize, Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import QPushButton

from ui.assets.icons import icon
from ui.theme import DARK


class IconButton(QPushButton):
    """A flat button showing a line icon (ui/assets/icons.py).

    Its colors are Qt properties, so the app stylesheet sets them per theme:

        QPushButton#GhostGlyphButton { qproperty-iconColor: <text2>; qproperty-hoverIconColor: <text>; }

    That is what makes a button created later -- a model card added after the theme was
    applied -- pick up the right color without anyone having to call apply_theme on it.
    """

    def __init__(self, icon_name: str, size: int = 14, stroke_width: float = 2.0, parent=None):
        super().__init__(parent)
        self._icon_name = icon_name
        self._icon_size = size
        self._stroke_width = stroke_width
        self._color = QColor(DARK["text2"])
        self._hover_color = QColor(DARK["text"])
        self._hovered = False
        self.setFlat(True)
        self.setCursor(Qt.PointingHandCursor)
        self.setIconSize(QSize(size, size))
        self._refresh()

    def set_icon_name(self, icon_name: str):
        self._icon_name = icon_name
        self._refresh()

    def _refresh(self):
        color = self._hover_color if self._hovered else self._color
        self.setIcon(icon(self._icon_name, color.name(), self._icon_size, self._stroke_width))

    def _get_icon_color(self) -> QColor:
        return self._color

    def _set_icon_color(self, color: QColor):
        self._color = QColor(color)
        self._refresh()

    def _get_hover_icon_color(self) -> QColor:
        return self._hover_color

    def _set_hover_icon_color(self, color: QColor):
        self._hover_color = QColor(color)
        self._refresh()

    iconColor = Property(QColor, _get_icon_color, _set_icon_color)
    hoverIconColor = Property(QColor, _get_hover_icon_color, _set_hover_icon_color)

    def enterEvent(self, event):
        self._hovered = True
        self._refresh()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hovered = False
        self._refresh()
        super().leaveEvent(event)
