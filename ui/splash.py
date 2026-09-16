import math

from PySide6.QtCore import QByteArray, QRectF, Qt, QTimer
from PySide6.QtGui import QColor, QPainter
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtWidgets import QApplication, QHBoxLayout, QLabel, QVBoxLayout, QWidget

from ui.assets.mark import BRAND_ACCENT_DARK_HEX
from ui.theme import DARK

_WIDTH, _HEIGHT = 460, 300
_MARK_SIZE = 82
_TICK_MS = 33
_RADIUS = 14

_VIEWBOX = "5.25 -0.6 56.5 56.5"
_SVG_WRAPPER = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="' + _VIEWBOX + '" fill="none" '
    'stroke="{color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)

# Same path data as ui/assets/mark.py's FULL_MARK_SVG, split into the layers the
# splash animates independently (clipboard, bubble, tail, three waves) -- kept
# here rather than importing pieces out of mark.py's single combined template,
# since that template is deliberately one indivisible SVG for the static-icon
# use case (window/tray/titlebar), where there's nothing to animate.
_CLIPBOARD_BODY = (
    '<path d="M25 21.35 V11.5 Q25 8 28.5 8 H33"/>'
    '<path d="M49 8 H53.5 Q57 8 57 11.5 V50.5 Q57 54 53.5 54 H28.5 Q25 54 25 50.5 V46.65"/>'
    '<rect x="34" y="4.8" width="14" height="6.4" rx="1.8" fill="{color}" stroke="none"/>'
    '<circle cx="41" cy="3.1" r="2.4" stroke-width="2.1"/>'
)
_BUBBLE_BODY = '<path d="M28.49 45.78 A13 13 0 1 1 28.49 22.22"/>'
_TAIL_BODY = '<path d="M13.81 43.19 C10.8 47.6, 9.9 49.6, 10.5 50.1 C11.1 50.6, 14.4 49.2, 18.55 46.22"/>'
_WAVE_BODIES = (
    '<path d="M27.59 27.45 A8 8 0 0 1 27.59 40.55"/>',
    '<path d="M31.84 25.16 A12.5 12.5 0 0 1 31.84 42.84"/>',
    '<path d="M35.02 21.98 A17 17 0 0 1 35.02 46.02"/>',
)


def _layer(body: str, color: str) -> QSvgRenderer:
    svg = _SVG_WRAPPER.format(color=color, body=body.format(color=color))
    return QSvgRenderer(QByteArray(svg.encode("utf-8")))


class AnimatedMark(QWidget):
    """Animated brand mark loading indicator."""

    def __init__(self, color: str, size: int = _MARK_SIZE, parent=None):
        super().__init__(parent)
        self.setFixedSize(size, size)
        self._clipboard = _layer(_CLIPBOARD_BODY, color)
        self._bubble = _layer(_BUBBLE_BODY, color)
        self._tail = _layer(_TAIL_BODY, color)
        self._waves = [_layer(body, color) for body in _WAVE_BODIES]

        self._frame = 0
        self._clip_opacity = 0.0
        self._clip_anim_frames = max(1, int(700 / _TICK_MS))

        self._timer = QTimer(self)
        self._timer.setInterval(_TICK_MS)
        self._timer.timeout.connect(self._tick)
        self._timer.start()

    def _tick(self):
        self._frame += 1
        if self._clip_opacity < 1.0:
            self._clip_opacity = min(1.0, self._frame / self._clip_anim_frames)
        self.update()

    def _elapsed_ms(self) -> float:
        return self._frame * _TICK_MS

    def _oscillate(self, period_ms: float) -> float:
        t = (self._elapsed_ms() % period_ms) / period_ms
        return (1 - math.cos(2 * math.pi * t)) / 2

    def _wave_opacity(self, index: int) -> float:
        # Pops in over the first 18% of a 2.8s cycle, each wave staggered ~390ms
        # after the last, then holds at full opacity for the rest of the cycle --
        # matches the brand doc's w1/w2/w3 keyframes (0%->18%,100%, then loop).
        period, stagger = 2800, 390
        reveal_ms = period * 0.18
        t = (self._elapsed_ms() - index * stagger) % period
        return min(1.0, t / reveal_ms)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(0, 0, self.width(), self.height())

        painter.setOpacity(self._clip_opacity)
        self._clipboard.render(painter, rect)

        painter.setOpacity(0.9 + self._oscillate(3400) * 0.1)
        self._bubble.render(painter, rect)

        painter.setOpacity(1.0)
        self._tail.render(painter, rect)

        for i, wave in enumerate(self._waves):
            painter.setOpacity(self._wave_opacity(i))
            wave.render(painter, rect)


class SplashScreen(QWidget):
    """Cold-start splash shown while initializing models and audio capture."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setFixedSize(_WIDTH, _HEIGHT)
        self._bg = QColor(DARK["bg"])
        self._border = QColor(DARK["line2"])

        self._center_on_screen()

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 30, 0, 26)
        outer.setSpacing(16)
        outer.addStretch()

        mark_row = QHBoxLayout()
        mark_row.addStretch()
        mark_row.addWidget(AnimatedMark(BRAND_ACCENT_DARK_HEX))
        mark_row.addStretch()
        outer.addLayout(mark_row)

        title = QLabel("Infinisper")
        title.setAlignment(Qt.AlignCenter)
        title.setStyleSheet(
            f"color:{DARK['text']}; font-size:24px; font-weight:700; letter-spacing:-0.03em; "
            "background:transparent;"
        )
        outer.addWidget(title)

        self._subtitle = QLabel("starting…")
        self._subtitle.setAlignment(Qt.AlignCenter)
        self._subtitle.setStyleSheet(
            f"color:{DARK['dim']}; font-size:10.5px; letter-spacing:.1em; background:transparent;"
        )
        outer.addWidget(self._subtitle)

        outer.addStretch()

        bar_col = QVBoxLayout()
        bar_col.setContentsMargins(26, 0, 26, 0)
        bar_col.setSpacing(11)

        self._bar_track = QWidget()
        self._bar_track.setFixedHeight(3)
        self._bar_track.setStyleSheet(f"background:{DARK['panel3']}; border-radius:2px;")
        bar_track_layout = QHBoxLayout(self._bar_track)
        bar_track_layout.setContentsMargins(0, 0, 0, 0)
        self._bar_fill = QWidget(self._bar_track)
        self._bar_fill.setStyleSheet(f"background:{BRAND_ACCENT_DARK_HEX}; border-radius:2px;")
        self._bar_fill.setGeometry(0, 0, 0, 3)
        bar_col.addWidget(self._bar_track)

        self._step_label = QLabel("")
        self._step_label.setStyleSheet(
            f"color:{DARK['text2']}; font-size:11px; "
            "font-family:ui-monospace,'Cascadia Mono',Consolas,monospace; background:transparent;"
        )
        bar_col.addWidget(self._step_label)

        outer.addLayout(bar_col)

    def _center_on_screen(self):
        screen = QApplication.primaryScreen().availableGeometry()
        self.move(
            screen.x() + (screen.width() - _WIDTH) // 2,
            screen.y() + (screen.height() - _HEIGHT) // 2,
        )

    def set_step(self, label: str, index: int, total: int):
        """Called from app.py at each real boot step -- index is 1-based,
        total is the number of steps in *this* boot (varies: extra ASR engines
        add a step, multimodal setup does not).
        """
        self._step_label.setText(label)
        progress = index / total if total else 0.0
        self._bar_fill.setGeometry(0, 0, round(self._bar_track.width() * progress), 3)
        # Repaints immediately rather than waiting for the event loop -- app.py's
        # boot sequence does real blocking work (model load, mic open) between
        # steps, so without this the label/bar would only ever show their very
        # last state once everything was already done.
        QApplication.processEvents()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(self._border)
        painter.setBrush(self._bg)
        painter.drawRoundedRect(rect, _RADIUS, _RADIUS)
