from PySide6.QtCore import Property, QEasingCurve, QPropertyAnimation, QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

_WIDTH = 38
_HEIGHT = 22
_PADDING = 2
_KNOB = _HEIGHT - _PADDING * 2


class ToggleSwitch(QWidget):
    """Pill-shaped on/off switch matching the mockup's track+knob control."""

    toggled = Signal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(_WIDTH, _HEIGHT)
        self.setCursor(Qt.PointingHandCursor)
        self._checked = False
        self._knob_x = _PADDING
        self._on_color = QColor("#5b8def")
        self._off_color = QColor("#3b414b")

        self._anim = QPropertyAnimation(self, b"knob_x", self)
        self._anim.setDuration(140)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)

    def set_colors(self, on_hex: str, off_hex: str):
        self._on_color = QColor(on_hex)
        self._off_color = QColor(off_hex)
        self.update()

    def isChecked(self) -> bool:
        return self._checked

    def setChecked(self, checked: bool, animate: bool = True):
        """Matches QCheckBox/QRadioButton convention: emits toggled on any actual
        change, whether triggered by a click or set programmatically -- callers
        that construct a switch already checked should pass animate=False and
        connect signals afterward if they don't want the initial emission.
        """
        if checked == self._checked:
            return
        self._checked = checked
        target = _WIDTH - _PADDING - _KNOB if checked else _PADDING
        if animate:
            self._anim.stop()
            self._anim.setStartValue(self._knob_x)
            self._anim.setEndValue(target)
            self._anim.start()
        else:
            self.knob_x = target
        self.toggled.emit(self._checked)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.LeftButton and self.rect().contains(event.pos()):
            self.setChecked(not self._checked)
        super().mouseReleaseEvent(event)

    def _get_knob_x(self) -> float:
        return self._knob_x

    def _set_knob_x(self, value: float):
        self._knob_x = value
        self.update()

    knob_x = Property(float, _get_knob_x, _set_knob_x)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        track_color = self._on_color if self._checked else self._off_color
        painter.setPen(Qt.NoPen)
        painter.setBrush(track_color)
        painter.drawRoundedRect(self.rect(), _HEIGHT / 2, _HEIGHT / 2)

        shadow_rect = QRectF(self._knob_x, _PADDING + 1, _KNOB, _KNOB)
        painter.setBrush(QColor(0, 0, 0, 60))
        painter.drawEllipse(shadow_rect)

        knob_rect = QRectF(self._knob_x, _PADDING, _KNOB, _KNOB)
        painter.setBrush(QColor("#ffffff"))
        painter.drawEllipse(knob_rect)
