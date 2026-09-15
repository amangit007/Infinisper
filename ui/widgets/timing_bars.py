from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

from ui.theme import DARK

_ROW_HEIGHT = 22
_LABEL_WIDTH = 150
_VALUE_WIDTH = 64
_BAR_HEIGHT = 10


class TimingBarsWidget(QWidget):
    """Per-step timing breakdown for one History entry: a proportional bar per
    step (relative to the slowest step), replacing the old plain-text list.

    Fully self-painted with QPainter, no QSS -- this app's own dashboard work
    hit real, repeated cases where dynamic *stylesheet* state didn't reliably
    repaint; plain Python attribute + self.update() (the technique every
    other dynamic-state widget here already uses successfully) has no such
    issue, so that's what this uses too.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._steps: list[tuple[str, float]] = []
        self._tokens = DARK

    def set_steps(self, steps: list[tuple[str, float]]):
        self._steps = steps
        self.setMinimumHeight(max(_ROW_HEIGHT, len(steps) * _ROW_HEIGHT) + 8)
        self.update()

    def apply_theme(self, tokens: dict):
        self._tokens = tokens
        self.update()

    def paintEvent(self, event):
        if not self._steps:
            return
        t = self._tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        max_ms = max((ms for _, ms in self._steps), default=1.0) or 1.0
        bar_x = _LABEL_WIDTH
        bar_w = max(30, self.width() - _LABEL_WIDTH - _VALUE_WIDTH - 12)

        label_font = self.font()
        label_font.setPointSizeF(8.5)
        value_font = self.font()
        value_font.setPointSizeF(8.5)

        y = 4.0
        for label, ms in self._steps:
            painter.setFont(label_font)
            painter.setPen(QColor(t["dim"]))
            painter.drawText(
                QRectF(0, y, _LABEL_WIDTH - 8, _ROW_HEIGHT),
                Qt.AlignLeft | Qt.AlignVCenter,
                label,
            )

            track_rect = QRectF(bar_x, y + (_ROW_HEIGHT - _BAR_HEIGHT) / 2, bar_w, _BAR_HEIGHT)
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(t["panel2"]))
            painter.drawRoundedRect(track_rect, 3, 3)

            frac = max(0.0, min(1.0, ms / max_ms))
            fill_rect = QRectF(bar_x, track_rect.y(), bar_w * frac, _BAR_HEIGHT)
            painter.setBrush(QColor(t["accent"]))
            painter.drawRoundedRect(fill_rect, 3, 3)

            painter.setFont(value_font)
            painter.setPen(QColor(t["text"]))
            painter.drawText(
                QRectF(bar_x + bar_w + 8, y, _VALUE_WIDTH, _ROW_HEIGHT),
                Qt.AlignLeft | Qt.AlignVCenter,
                f"{ms:.0f}ms",
            )
            y += _ROW_HEIGHT
