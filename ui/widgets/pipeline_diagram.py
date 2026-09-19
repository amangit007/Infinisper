from PySide6.QtCore import QRectF, QTimer, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QWidget

from ui.theme import DARK

# Diagram dimensions and node bounding boxes.
_CANVAS_SIZE = (916, 212)
_MIC_CENTER = (48, 100)
_MIC_RADIUS = 28
_ASR_BOX = QRectF(168, 62, 216, 76)
_CLEANUP_BOX = QRectF(456, 62, 216, 76)
_OUT_BOX = QRectF(744, 62, 172, 76)

_FLOW_DASH = [9, 63]
_STATIC_DASH = [4, 5]
_SHORT_FLOW_MS_PER_CYCLE = 1900
_LONG_FLOW_MS_PER_CYCLE = 2800
_FLOW_TICK_MS = 50


def _straight(x1, y1, x2, y2) -> QPainterPath:
    path = QPainterPath()
    path.moveTo(x1, y1)
    path.lineTo(x2, y2)
    return path


def _bypass_path() -> QPainterPath:
    # Mic -> curves under the ASR box -> into the AI cleanup box's bottom edge.
    path = QPainterPath()
    path.moveTo(48, 128)
    path.lineTo(48, 168)
    path.quadTo(48, 178, 58, 178)
    path.lineTo(554, 178)
    path.quadTo(564, 178, 564, 168)
    path.lineTo(564, 138)
    return path


def _skip_path() -> QPainterPath:
    # ASR box's top edge -> arcs over the AI cleanup box -> into the output box's top edge.
    path = QPainterPath()
    path.moveTo(276, 62)
    path.lineTo(276, 44)
    path.quadTo(276, 34, 286, 34)
    path.lineTo(820, 34)
    path.quadTo(830, 34, 830, 44)
    path.lineTo(830, 62)
    return path


class PipelineDiagram(QWidget):
    """Visual pipeline diagram showing audio routing through ASR and AI cleanup processing."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(*_CANVAS_SIZE)

        self._edges = {
            "mic_asr": _straight(76, 100, 168, 100),
            "asr_cleanup": _straight(384, 100, 456, 100),
            "cleanup_out": _straight(672, 100, 744, 100),
            "bypass": _bypass_path(),
            "skip": _skip_path(),
        }
        self._edge_live = {name: False for name in self._edges}
        self._edge_is_long = {"bypass": True, "skip": True}

        self._use_asr = True
        self._use_cleanup = False
        self._asr_label = "Whisper"
        self._cleanup_label = "Off"
        self._cleanup_is_local = False

        self._colors: dict[str, QColor] = {}
        self.apply_theme(DARK)  # until the window applies the real theme

        self._flow_phase = 0.0
        self._timer = QTimer(self)
        self._timer.setInterval(_FLOW_TICK_MS)
        self._timer.timeout.connect(self._on_tick)
        # Not started here -- set_route() starts/stops it based on whether any edge is
        # actually live, so an idle pipeline (nothing enabled, or the dashboard just not
        # visible) isn't repainting 33x/sec forever for no visible effect.

    def apply_theme(self, tokens: dict):
        def rgba(key, alpha):
            c = QColor(tokens[key])
            return QColor(c.red(), c.green(), c.blue(), round(alpha * 255))

        self._colors["line2"] = QColor(tokens["line2"])
        self._colors["accent"] = QColor(tokens["accent"])
        self._colors["good"] = QColor(tokens["good"])
        self._colors["good_soft"] = rgba("good", 0.14)
        self._colors["warn"] = QColor(tokens["warn"])
        self._colors["warn_soft"] = rgba("warn", 0.14)
        self._colors["panel2"] = QColor(tokens["panel2"])
        self._colors["dim"] = QColor(tokens["dim"])
        self._colors["text"] = QColor(tokens["text"])
        self.update()

    def set_route(
        self,
        use_asr: bool,
        use_cleanup: bool,
        asr_label: str,
        cleanup_label: str,
        cleanup_is_local: bool = False,
    ) -> str:
        """Recomputes which edges are live and returns a one-line route summary.
        `cleanup_is_local` says whether the AI model runs on this machine (e.g. Ollama),
        which decides whether the summary can promise that nothing leaves it."""
        self._use_asr = use_asr
        self._use_cleanup = use_cleanup
        self._asr_label = asr_label
        self._cleanup_label = cleanup_label
        self._cleanup_is_local = cleanup_is_local

        both = use_asr and use_cleanup
        asr_only = use_asr and not use_cleanup
        cleanup_only = use_cleanup and not use_asr

        self._edge_live = {
            "mic_asr": both or asr_only,
            "asr_cleanup": both,
            "cleanup_out": both or cleanup_only,
            "bypass": cleanup_only,
            "skip": asr_only,
        }
        if any(self._edge_live.values()):
            if not self._timer.isActive():
                self._timer.start()
        else:
            self._timer.stop()
        self.update()

        if both:
            route = f"Mic → {asr_label} → {cleanup_label} → cursor"
            return route + (" · nothing leaves this machine" if cleanup_is_local else "")
        if asr_only:
            return f"Mic → {asr_label} → cursor · nothing leaves this machine"
        if cleanup_only:
            return f"Mic → {cleanup_label} → cursor" + (
                " · nothing leaves this machine" if cleanup_is_local else " · audio leaves this machine"
            )
        return "Nothing enabled — turn on a stage to dictate"

    def _on_tick(self):
        self._flow_phase += _FLOW_TICK_MS
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        self._paint_edges(painter)
        self._paint_mic(painter)
        self._paint_stage_box(
            painter, _ASR_BOX, "SPEECH RECOGNITION", self._asr_label, "DEVICE",
            self._colors["good"], self._colors["good_soft"], self._use_asr,
        )
        local = self._cleanup_is_local
        self._paint_stage_box(
            painter, _CLEANUP_BOX, "AI CLEANUP", self._cleanup_label, "LOCAL" if local else "CLOUD",
            self._colors["good" if local else "warn"], self._colors["good_soft" if local else "warn_soft"],
            self._use_cleanup,
        )
        self._paint_output_box(painter)
        self._paint_annotations(painter)

    def _paint_edges(self, painter: QPainter):
        for name, path in self._edges.items():
            live = self._edge_live[name]

            pen = QPen(self._colors["line2"])
            pen.setWidthF(1.5)
            pen.setDashPattern(_STATIC_DASH)
            painter.setOpacity(0.0 if live else 1.0)
            painter.setPen(pen)
            painter.drawPath(path)

            if not live:
                continue
            cycle = _LONG_FLOW_MS_PER_CYCLE if self._edge_is_long.get(name) else _SHORT_FLOW_MS_PER_CYCLE
            offset = -((self._flow_phase / cycle) * 72) % 72
            pen = QPen(self._colors["accent"])
            pen.setWidthF(2)
            pen.setCapStyle(Qt.RoundCap)
            pen.setDashPattern(_FLOW_DASH)
            pen.setDashOffset(offset)
            painter.setOpacity(1.0)
            painter.setPen(pen)
            painter.drawPath(path)

        painter.setOpacity(1.0)

    def _paint_mic(self, painter: QPainter):
        cx, cy = _MIC_CENTER
        r = _MIC_RADIUS
        good = self._colors["good"]
        good_soft = self._colors["good_soft"]

        painter.setPen(QPen(good, 1.5))
        painter.setBrush(good_soft)
        painter.drawEllipse(QRectF(cx - r, cy - r, r * 2, r * 2))

        painter.setPen(Qt.NoPen)
        painter.setBrush(good)
        painter.drawRoundedRect(QRectF(cx - 4.5, cy - 15, 9, 14), 4.5, 4.5)
        pen = QPen(good, 1.6)
        painter.setPen(pen)
        painter.setBrush(Qt.NoBrush)
        painter.drawArc(QRectF(cx - 8.5, cy - 6, 17, 16), 180 * 16, -180 * 16)
        painter.drawLine(int(cx), cy + 10, int(cx), cy + 14)

        painter.setPen(self._colors["text"])
        font = QFont()
        font.setPointSizeF(9.5)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(QRectF(cx - 48, cy + 36, 96, 16), Qt.AlignCenter, "Microphone")

    def _paint_stage_box(self, painter, rect, title, name, badge_text, badge_color, badge_bg, enabled):
        painter.setOpacity(1.0 if enabled else 0.38)

        painter.setPen(QPen(self._colors["line2"], 1))
        painter.setBrush(self._colors["panel2"])
        painter.drawRoundedRect(rect, 10, 10)

        pad = 13
        inner = rect.adjusted(pad, 11, -pad, -11)

        title_font = QFont()
        title_font.setPointSizeF(8.0)
        painter.setFont(title_font)
        painter.setPen(self._colors["dim"])
        title_rect = QRectF(inner.left(), inner.top(), inner.width() - 44, 14)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, title.upper())

        badge_rect = QRectF(inner.right() - 40, inner.top(), 40, 15)
        painter.setPen(Qt.NoPen)
        painter.setBrush(badge_bg)
        painter.drawRoundedRect(badge_rect, 4, 4)
        painter.setPen(badge_color)
        badge_font = QFont()
        badge_font.setPointSizeF(6.5)
        painter.setFont(badge_font)
        painter.drawText(badge_rect, Qt.AlignCenter, badge_text)

        name_font = QFont()
        name_font.setPointSizeF(9.5)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(self._colors["text"])
        name_rect = QRectF(inner.left(), inner.top() + 18, inner.width(), 18)
        elided = painter.fontMetrics().elidedText(name if enabled else "Off", Qt.ElideRight, int(inner.width()))
        painter.drawText(name_rect, Qt.AlignLeft | Qt.AlignVCenter, elided)

        detail_font = QFont()
        detail_font.setPointSizeF(7.5)
        painter.setFont(detail_font)
        painter.setPen(self._colors["dim"])
        detail_rect = QRectF(inner.left(), inner.top() + 38, inner.width(), 14)
        on_device = title.startswith("SPEECH") or self._cleanup_is_local
        detail = "runs on this device" if on_device else "cloud round trip"
        painter.drawText(detail_rect, Qt.AlignLeft | Qt.AlignVCenter, detail if enabled else "skipped")

        painter.setOpacity(1.0)

    def _paint_output_box(self, painter: QPainter):
        rect = _OUT_BOX
        painter.setOpacity(1.0)
        painter.setPen(QPen(self._colors["line2"], 1))
        painter.setBrush(self._colors["panel2"])
        painter.drawRoundedRect(rect, 10, 10)

        pad = 13
        inner = rect.adjusted(pad, 11, -pad, -11)

        title_font = QFont()
        title_font.setPointSizeF(8.0)
        painter.setFont(title_font)
        painter.setPen(self._colors["dim"])
        painter.drawText(QRectF(inner.left(), inner.top(), inner.width(), 14), Qt.AlignLeft, "OUTPUT")

        name_font = QFont()
        name_font.setPointSizeF(9.5)
        name_font.setBold(True)
        painter.setFont(name_font)
        painter.setPen(self._colors["text"])
        painter.drawText(
            QRectF(inner.left(), inner.top() + 18, inner.width(), 18),
            Qt.AlignLeft | Qt.AlignVCenter,
            "Your cursor",
        )

        detail_font = QFont()
        detail_font.setPointSizeF(7.5)
        painter.setFont(detail_font)
        painter.setPen(self._colors["dim"])
        painter.drawText(
            QRectF(inner.left(), inner.top() + 38, inner.width(), 14),
            Qt.AlignLeft | Qt.AlignVCenter,
            "paste to active window",
        )

    def _paint_annotations(self, painter: QPainter):
        font = QFont()
        font.setPointSizeF(7.5)
        painter.setFont(font)
        painter.setPen(self._colors["dim"])

        if self._edge_live["bypass"]:
            painter.drawText(
                QRectF(150, 164, 300, 14), Qt.AlignLeft,
                "audio straight to the model — skips speech recognition",
            )
        if self._edge_live["skip"]:
            painter.drawText(
                QRectF(354, 20, 300, 14), Qt.AlignLeft,
                "raw transcript — skips cleanup",
            )
