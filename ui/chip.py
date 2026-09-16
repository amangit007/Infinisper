import collections
import ctypes
import math

from PySide6.QtCore import QEasingCurve, QPropertyAnimation, QRect, QRectF, QTimer, Qt, Signal
from PySide6.QtGui import QColor, QLinearGradient, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QApplication, QWidget

from ui.theme import oklch_to_hex

# Qt's WindowStaysOnTopHint sets WS_EX_TOPMOST once, but that flag is not a strict
# ordering -- Windows lets multiple windows claim topmost, and among them the one
# that most recently re-asserted it wins the actual top spot in the z-order. Some
# VDI clients (observed with Citrix Workspace's fullscreen Desktop Viewer) reclaim
# topmost themselves periodically, which silently buries any other topmost window
# underneath their remote-session surface -- the chip keeps running (state changes,
# repaints) but nothing shows on screen. _reassert_topmost() re-wins that fight on a
# timer instead of trusting the flag to hold, the same trick push-to-talk overlays
# and screen-annotation tools use to coexist with other topmost/fullscreen apps.
_HWND_TOPMOST = -1
_SWP_NOMOVE = 0x0002
_SWP_NOSIZE = 0x0001
_SWP_NOACTIVATE = 0x0010
_TOPMOST_REASSERT_MS = 1500


def _tinted(l: float, c: float, h_deg: float, alpha255: int) -> QColor:
    color = QColor(oklch_to_hex(l, c, h_deg))
    color.setAlpha(alpha255)
    return color


# State styling and tint colors for the status chip.
_TINT_DEFAULT = QColor(75, 78, 95, 175)  # rgba(75,78,95,.686)
_STROKE_DEFAULT = QColor(255, 255, 255, 160)  # rgba(255,255,255,.63)
_TINT_PASTED = _tinted(0.46, 0.075, 155, 184)  # oklch(0.46 0.075 155 / 0.72)
_STROKE_PASTED = _tinted(0.80, 0.10, 155, 184)  # oklch(0.80 0.10 155 / 0.72)
_TINT_FAILED = _tinted(0.44, 0.10, 25, 184)  # oklch(0.44 0.10 25 / 0.72)
_STROKE_FAILED = _tinted(0.78, 0.11, 25, 184)  # oklch(0.78 0.11 25 / 0.72)
_INK = QColor(255, 255, 255, 235)  # rgba(255,255,255,.92)

_COLORS = {
    "pasted": (_TINT_PASTED, _STROKE_PASTED),
    "failed": (_TINT_FAILED, _STROKE_FAILED),
}

_BORDER_WIDTH = 1.2

# Idle/paused are a minimal barely-there sliver; every other state grows to a size
# that can actually fit a waveform, spinner or glyph. Transitions between these
# animate via _GEO_ANIM_MS, growing/shrinking from a fixed center point rather than
# resizing in place -- resizing in place anchored at the bottom made it look like the
# pill was crawling upward out of the ground instead of expanding.
_SIZES = {
    "idle": (48, 6),
    "paused": (48, 6),
    "listening": (96, 24),
    "transcribing": (96, 24),
    "polishing": (96, 24),
    "pasted": (96, 24),
    "nospeech": (96, 24),
    "failed": (96, 24),
}

# States that flash a result and then revert themselves back to idle -- the duration
# is presentation detail owned by the chip, not the pipeline code that requests the
# state. A new set_state() call (e.g. a fresh recording starting) cancels any pending
# revert, same as it cancels any in-flight geometry animation.
_AUTO_REVERT_MS = {
    "pasted": 450,
    "nospeech": 600,
    "failed": 1200,
}

# States whose glyph animates on the shared tick timer. "listening" is driven by real
# mic levels instead (see update_audio_level); "paused"/"pasted"/"nospeech"/"failed"
# are static glyphs that only need one paint.
_TICKING_STATES = {"idle", "transcribing", "polishing"}

# Distance from the bottom of the screen to the pill's (fixed) center point.
_ANCHOR_BOTTOM_OFFSET = 45

_GEO_ANIM_MS = 200
_TICK_MS = 33

_BAR_COUNT = 14


class ChipWindow(QWidget):
    _state_changed = Signal(str)
    _level_changed = Signal(float)

    # Public, fired from _apply_state (always on the main thread, after cross-thread
    # marshaling) -- lets other UI, e.g. the sidebar mic meter, mirror real chip state
    # without duplicating the idle/listening/transcribing bookkeeping.
    state_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self.setWindowFlags(Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground)
        self.setAttribute(Qt.WA_ShowWithoutActivating)
        self.setAttribute(Qt.WA_TransparentForMouseEvents)

        self._state = "idle"
        self.setGeometry(self._target_geometry("idle"))

        self._levels = collections.deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
        self._anim_frame = 0
        # Keyed by (w, h) -- the pill only ever takes one of two sizes, so this
        # caps out at 2 entries. Rebuilding a QPainterPath every single tick during
        # "polishing" was needless per-frame cost for a shape that never changes.
        self._clip_path_cache: dict[tuple[int, int], QPainterPath] = {}

        self._anim_timer = QTimer(self)
        self._anim_timer.setInterval(_TICK_MS)
        self._anim_timer.timeout.connect(self._on_anim_tick)

        # Fires once, _AUTO_REVERT_MS[state] after a flash state (pasted/nospeech/
        # failed) is entered, bringing the chip back to idle on its own.
        self._revert_timer = QTimer(self)
        self._revert_timer.setSingleShot(True)
        self._revert_timer.timeout.connect(lambda: self._apply_state("idle"))

        # Animates width/height/position together so the pill grows and shrinks
        # from a fixed center point instead of resizing in place from one corner
        # -- see _target_geometry.
        self._geo_anim = QPropertyAnimation(self, b"geometry", self)
        self._geo_anim.setDuration(_GEO_ANIM_MS)
        self._geo_anim.setEasingCurve(QEasingCurve.OutCubic)
        self._geo_anim.finished.connect(self._on_resize_finished)

        # True only while a real grow/shrink animation is in flight (idle/paused's
        # small size vs. every other state's large size -- see _SIZES). Suppresses
        # glyph painting during that window: the new state's glyph/color used to
        # switch the instant _apply_state was called, while the box was still 200ms
        # into resizing to fit it, so the final state's icon was visible sitting
        # inside a wrong-sized, still-animating pill -- the "final state before the
        # previous one finishes closing" effect. Painting only the morphing pill
        # shape (no glyph) until the resize actually completes, then snapping the
        # new glyph in at the correct final size, reads as a single clean motion
        # instead of two overlapping ones.
        self._resizing = False

        self._topmost_timer = QTimer(self)
        self._topmost_timer.setInterval(_TOPMOST_REASSERT_MS)
        self._topmost_timer.timeout.connect(self._reassert_topmost)
        self._topmost_timer.start()

        self._state_changed.connect(self._apply_state)
        self._level_changed.connect(self._on_level_changed)

        # Visible for the app's entire lifetime, not just while listening/transcribing
        # -- a small always-on indicator that the app is running and the hotkey isn't
        # currently held, same as e.g. Wispr Flow's persistent pill.
        self._apply_state("idle", animate=False)

    def _target_geometry(self, state: str) -> QRect:
        """The on-screen rect for `state`, centered on the same fixed anchor
        point regardless of size -- this is what makes transitions grow/shrink
        outward from the middle instead of from a corner.
        """
        screen = QApplication.primaryScreen().availableGeometry()
        cx = screen.x() + screen.width() // 2
        cy = screen.y() + screen.height() - _ANCHOR_BOTTOM_OFFSET
        w, h = _SIZES[state]
        return QRect(round(cx - w / 2), round(cy - h / 2), w, h)

    def set_state(self, state: str):
        self._state_changed.emit(state)

    def update_audio_level(self, level: float):
        """Called from the audio callback thread while listening -- Qt signals
        queue safely across threads, so this is the only way this method may
        touch chip state.
        """
        self._level_changed.emit(level)

    def _apply_state(self, state: str, animate: bool = True):
        self._revert_timer.stop()
        self._state = state
        target = self._target_geometry(state)

        if state == "listening":
            self._levels = collections.deque([0.0] * _BAR_COUNT, maxlen=_BAR_COUNT)
            self._anim_timer.stop()
        elif state in _TICKING_STATES:
            self._anim_frame = 0
            self._anim_timer.start()
        else:
            self._anim_timer.stop()

        # Most state changes (listening -> transcribing -> polishing -> pasted) don't
        # change size at all -- only a real resize needs the grow/shrink animation.
        # Starting a QPropertyAnimation with equal start/end values still ticks for
        # its full duration, repeatedly calling setGeometry() on a translucent
        # top-level window for no visual change: on every single state transition,
        # not just resizes, which is what made the whole chip feel laggy once there
        # were several same-size states in a row instead of the original three.
        if animate and self.isVisible() and target != self.geometry():
            self._geo_anim.stop()
            self._resizing = True
            self._geo_anim.setStartValue(self.geometry())
            self._geo_anim.setEndValue(target)
            self._geo_anim.start()
        else:
            self._geo_anim.stop()
            self._resizing = False
            self.setGeometry(target)

        self.show()
        self.update()
        self.state_changed.emit(state)

        if state in _AUTO_REVERT_MS:
            self._revert_timer.start(_AUTO_REVERT_MS[state])

    def _on_level_changed(self, level: float):
        if self._state != "listening":
            return
        self._levels.append(level)
        self.update()

    def _on_anim_tick(self):
        self._anim_frame += 1
        self.update()

    def _on_resize_finished(self):
        self._resizing = False
        self.update()

    def _reassert_topmost(self):
        # SWP_NOMOVE | SWP_NOSIZE | SWP_NOACTIVATE: only the z-order changes, so this
        # is cheap enough to run continuously (no repaint, resize or focus stealing).
        hwnd = int(self.winId())
        ctypes.windll.user32.SetWindowPos(
            hwnd, _HWND_TOPMOST, 0, 0, 0, 0, _SWP_NOMOVE | _SWP_NOSIZE | _SWP_NOACTIVATE
        )

    def _elapsed_ms(self) -> float:
        return self._anim_frame * _TICK_MS

    # -- painting --------------------------------------------------------

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = self.rect()

        # A translucent top-level window's backing store isn't guaranteed cleared
        # before each paint; SourceOver (the default) just blends new pixels on top
        # of whatever was already there, so the previous frame's glyph could still
        # be showing through underneath the new one for a frame or two -- most
        # visible right when a state changes. CompositionMode_Source replaces the
        # buffer outright instead of blending onto it.
        painter.setCompositionMode(QPainter.CompositionMode_Source)
        painter.fillRect(rect, Qt.transparent)
        painter.setCompositionMode(QPainter.CompositionMode_SourceOver)

        tint, stroke = _COLORS.get(self._state, (_TINT_DEFAULT, _STROKE_DEFAULT))

        # Inset by half the border width so the stroke isn't clipped at the
        # widget edge (QPainter centers strokes on the path by default).
        border_rect = QRectF(rect).adjusted(
            _BORDER_WIDTH / 2, _BORDER_WIDTH / 2, -_BORDER_WIDTH / 2, -_BORDER_WIDTH / 2
        )
        pen = QPen(stroke)
        pen.setWidthF(_BORDER_WIDTH)
        painter.setPen(pen)
        painter.setBrush(tint)
        painter.drawRoundedRect(border_rect, border_rect.height() / 2, border_rect.height() / 2)

        paint_glyph = {
            "idle": self._paint_idle,
            "paused": self._paint_paused,
            "listening": self._paint_bars,
            "transcribing": self._paint_transcribing,
            "polishing": self._paint_polishing,
            "pasted": self._paint_pasted,
            "nospeech": self._paint_nospeech,
            "failed": self._paint_failed,
        }.get(self._state)
        if paint_glyph and not self._resizing:
            paint_glyph(painter, rect)

    def _paint_idle(self, painter: QPainter, rect):
        """Draws a subtle pulsing dot for idle state."""
        cx, cy = rect.width() / 2, rect.height() / 2
        pulse = self._oscillate(4500)  # 0..1
        r = 1.5
        color = QColor(_INK)
        color.setAlpha(int(_INK.alpha() * (0.55 + pulse * 0.45)))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

    def _paint_paused(self, painter: QPainter, rect):
        """Two static stubs at idle-dot scale -- the pause glyph has to read
        inside the 6px sliver, so it isn't full-height pause bars."""
        cx, cy = rect.width() / 2, rect.height() / 2
        stub_w, stub_h, gap = 2.0, 3.2, 1.8
        total_w = stub_w * 2 + gap
        x = cx - total_w / 2
        color = QColor(_INK)
        color.setAlpha(int(_INK.alpha() * 0.6))
        painter.setPen(Qt.NoPen)
        painter.setBrush(color)
        for _ in range(2):
            painter.drawRoundedRect(QRectF(x, cy - stub_h / 2, stub_w, stub_h), 0.8, 0.8)
            x += stub_w + gap

    def _paint_bars(self, painter: QPainter, rect):
        bar_w = 3.0
        gap = (rect.width() - _BAR_COUNT * bar_w) / (_BAR_COUNT + 1)
        max_bar_h = rect.height() - 8
        min_bar_h = 3.0

        painter.setPen(Qt.NoPen)
        painter.setBrush(_INK)
        x = gap
        for level in self._levels:
            # Raw mic RMS for normal speaking volume is usually well under 0.2.
            # sqrt compresses the range so quiet speech still moves the bars
            # instead of flatlining near zero.
            normalized = min(1.0, math.sqrt(max(level, 0.0)) * 2.2)
            bar_h = min_bar_h + normalized * (max_bar_h - min_bar_h)
            y = (rect.height() - bar_h) / 2
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), bar_w / 2, bar_w / 2)
            x += bar_w + gap

    def _paint_transcribing(self, painter: QPainter, rect):
        self._paint_spinner(painter, rect)
        dot_d, gap, count = 4.8, 3.2, 3
        self._paint_pulsing_dots(
            painter, rect, count=count, dot_d=dot_d, gap=gap, left_x=47.6,
            period_ms=1150, stagger=0.16, offset=-0.32,
        )

    def _paint_spinner(self, painter: QPainter, rect):
        r = 6.0
        cx, cy = 18.0 + r, rect.height() / 2

        pen = QPen(_INK)
        pen.setWidthF(2.0)
        pen.setCapStyle(Qt.FlatCap)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)

        # Rotating arc spinner for transcription state.
        t = (self._elapsed_ms() % 850) / 850
        start_angle = t * 360
        span_angle = 270
        arc_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        painter.drawArc(arc_rect, -round(start_angle * 16), span_angle * 16)

    def _paint_polishing(self, painter: QPainter, rect):
        self._paint_sweep(painter, rect)
        dot_d, gap, count = 3.0, 4.4, 4
        total_w = count * dot_d + (count - 1) * gap
        left_x = rect.width() / 2 - total_w / 2
        self._paint_pulsing_dots(
            painter, rect, count=count, dot_d=dot_d, gap=gap, left_x=left_x,
            period_ms=1500, stagger=0.12, offset=-0.36,
        )

    def _pill_clip_path(self, rect) -> QPainterPath:
        key = (rect.width(), rect.height())
        cached = self._clip_path_cache.get(key)
        if cached is None:
            cached = QPainterPath()
            cached.addRoundedRect(QRectF(rect), rect.height() / 2, rect.height() / 2)
            self._clip_path_cache[key] = cached
        return cached

    def _paint_sweep(self, painter: QPainter, rect):
        """Draws a soft highlight sweep across the pill during cleanup."""
        band_w = rect.width() * 0.34
        eased = self._ease_in_out(1500)  # 0..1, single pass then snaps back
        x = -1.10 * band_w + eased * (3.20 * band_w)

        gradient = QLinearGradient(x, 0, x + band_w, 0)
        gradient.setColorAt(0.0, QColor(255, 255, 255, 0))
        gradient.setColorAt(0.5, QColor(255, 255, 255, 77))
        gradient.setColorAt(1.0, QColor(255, 255, 255, 0))

        painter.save()
        painter.setClipPath(self._pill_clip_path(rect))
        painter.setPen(Qt.NoPen)
        painter.setBrush(gradient)
        painter.drawRect(QRectF(x, 0, band_w, rect.height()))
        painter.restore()

    def _paint_pasted(self, painter: QPainter, rect):
        """A checkmark -- the only green the chip ever shows, and only for a
        moment (see _AUTO_REVERT_MS)."""
        cx, cy = rect.width() / 2, rect.height() / 2
        w, h = 9.0, 5.0
        path = QPainterPath()
        path.moveTo(cx - w / 2, cy - h * 0.1)
        path.lineTo(cx - w / 2 + w * 0.32, cy + h / 2)
        path.lineTo(cx + w / 2, cy - h / 2)

        pen = QPen(_INK)
        pen.setWidthF(1.8)
        pen.setCapStyle(Qt.RoundCap)
        pen.setJoinStyle(Qt.RoundJoin)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawPath(path)

    def _paint_nospeech(self, painter: QPainter, rect):
        """A flat line -- nothing above the noise floor, not an error."""
        cx, cy = rect.width() / 2, rect.height() / 2
        w, h = 44.0, 1.8
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 128))
        painter.drawRoundedRect(QRectF(cx - w / 2, cy - h / 2, w, h), h / 2, h / 2)

    def _paint_failed(self, painter: QPainter, rect):
        """An exclamation mark, opaque white (not the translucent ink used
        elsewhere) -- details wait for the user in History."""
        cx, cy = rect.width() / 2, rect.height() / 2
        bar_w, bar_h, gap, dot_d = 2.0, 8.0, 2.0, 2.0
        total_h = bar_h + gap + dot_d
        top = cy - total_h / 2

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(255, 255, 255, 255))
        painter.drawRoundedRect(QRectF(cx - bar_w / 2, top, bar_w, bar_h), bar_w / 2, bar_w / 2)
        painter.drawEllipse(QRectF(cx - dot_d / 2, top + bar_h + gap, dot_d, dot_d))

    def _paint_pulsing_dots(self, painter: QPainter, rect, *, count, dot_d, gap, left_x, period_ms, stagger, offset):
        """Draws pulsing dots with staggered phases."""
        dot_r = dot_d / 2
        cy = rect.height() / 2
        x = left_x + dot_r
        painter.setPen(Qt.NoPen)
        for i in range(count):
            delay_ms = (i * stagger + offset) * 1000
            pulse = self._oscillate(period_ms, phase_offset_ms=-delay_ms)
            color = QColor(_INK)
            color.setAlpha(int(255 * (0.4 + pulse * 0.6)))
            r = dot_r * (0.78 + pulse * 0.37)
            painter.setBrush(color)
            painter.drawEllipse(QRectF(x - r, cy - r, r * 2, r * 2))
            x += dot_d + gap

    def _oscillate(self, period_ms: float, phase_offset_ms: float = 0.0) -> float:
        """0..1..0 over `period_ms`, matching a CSS `0%,100%:0 50%:1`
        ease-in-out keyframe (chipbreath/mb/dotp are all this shape)."""
        t = ((self._elapsed_ms() + phase_offset_ms) % period_ms) / period_ms
        return (1 - math.cos(2 * math.pi * t)) / 2

    def _ease_in_out(self, period_ms: float) -> float:
        """0..1 once per `period_ms`, then snaps back to 0 -- for a value that
        travels from a start to an end and loops, rather than oscillating."""
        t = (self._elapsed_ms() % period_ms) / period_ms
        return (1 - math.cos(math.pi * t)) / 2
