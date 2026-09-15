import collections
import math

from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import QWidget

_BAR_COUNT = 14
_REST_HEIGHT_FRACTION = 0.18  # matches the mockup's scaleY(.18) idle floor


class MicLevelMeter(QWidget):
    """Real mic-level bars for the sidebar.

    Unlike the mockup (a CSS keyframe loop that "breathes" whether or not anyone is
    talking), this only ever reflects real audio: `audio.capture` only calls
    `update_audio_level` while actively recording, so the bars sit at a flat rest
    floor the rest of the time instead of faking activity.
    """

    _level_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(26)
        self._levels = collections.deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
        self._color = QColor("#5ec386")
        self._level_changed.connect(self._on_level_changed)

    def set_color(self, hex_color: str):
        self._color = QColor(hex_color)
        self.update()

    def update_audio_level(self, level: float):
        """Called from the audio callback thread while listening -- Qt signals queue
        safely across threads, so this is the only way this method may touch state,
        same pattern as ui.chip.ChipWindow.update_audio_level.
        """
        self._level_changed.emit(level)

    def set_listening(self, listening: bool):
        if not listening:
            self._levels = collections.deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
            self.update()

    def current_level(self) -> float:
        return self._levels[-1] if self._levels else 0.0

    def _on_level_changed(self, level: float):
        self._levels.append(level)
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()
        gap = 2.0
        bar_w = (rect.width() - gap * (_BAR_COUNT - 1)) / _BAR_COUNT
        max_h = rect.height()
        min_h = max_h * _REST_HEIGHT_FRACTION

        painter.setPen(Qt.NoPen)
        painter.setBrush(self._color)
        x = 0.0
        for level in self._levels:
            # Raw mic RMS for normal speaking volume is usually well under 0.2; sqrt
            # compresses the range so quiet speech still moves the bars (same
            # normalization ui.chip.ChipWindow uses for its listening waveform).
            normalized = min(1.0, math.sqrt(max(level, 0.0)) * 2.2)
            bar_h = min_h + normalized * (max_h - min_h)
            y = (rect.height() - bar_h) / 2
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 1, 1)
            x += bar_w + gap
