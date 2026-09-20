"""Disk Usage Pie Chart Widget and Popover Card.

Renders an anti-aliased, theme-aware doughnut/pie chart with high-DPI precision,
a central total readout, color-coded item breakdowns, and storage drive context.
"""

import shutil
from pathlib import Path

from PySide6.QtCore import QPoint, QRectF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsDropShadowEffect,
    QHBoxLayout,
    QLabel,
    QVBoxLayout,
    QWidget,
)

from asr import catalog as asr_catalog
from asr.downloader import format_bytes
from ui.theme import DARK


class DoughnutChartWidget(QWidget):
    """Custom paint widget rendering an anti-aliased doughnut chart with center readout."""

    def __init__(self, slices: list[dict], total_bytes: int, tokens: dict = DARK, parent=None):
        super().__init__(parent)
        self.slices = slices
        self.total_bytes = max(total_bytes, 1)
        self.tokens = tokens
        self.setFixedSize(140, 140)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        rect = QRectF(10, 10, 120, 120)
        hole_rect = QRectF(32, 32, 76, 76)

        start_angle = 90.0 * 16.0  # 12 o'clock in 1/16th degrees

        if not self.slices:
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(self.tokens.get("line2", self.tokens["panel2"])))
            painter.drawEllipse(rect)
            painter.setBrush(QColor(self.tokens.get("panel", self.tokens["bg"])))
            painter.drawEllipse(hole_rect)
            return

        # Draw slices
        for s in self.slices:
            frac = s["size_bytes"] / self.total_bytes
            span_angle = -(frac * 360.0 * 16.0)

            path = QPainterPath()
            path.arcMoveTo(rect, start_angle / 16.0)
            path.arcTo(rect, start_angle / 16.0, span_angle / 16.0)

            # Cut hole for doughnut
            inner_angle = (start_angle + span_angle) / 16.0
            path.arcTo(hole_rect, inner_angle, -span_angle / 16.0)
            path.closeSubpath()

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(s["color"]))
            painter.drawPath(path)

            start_angle += span_angle

        # Draw center hole background
        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(self.tokens.get("panel", self.tokens["bg"])))
        painter.drawEllipse(hole_rect)

        # Center text: "TOTAL" and amount
        painter.setPen(QColor(self.tokens.get("dim", self.tokens["text2"])))
        lbl_font = QFont("Segoe UI", 7)
        lbl_font.setBold(True)
        painter.setFont(lbl_font)
        painter.drawText(QRectF(32, 48, 76, 16), Qt.AlignCenter, "TOTAL")

        painter.setPen(QColor(self.tokens.get("text", self.tokens["text"])))
        val_font = QFont("Segoe UI", 8)
        val_font.setBold(True)
        painter.setFont(val_font)
        painter.drawText(QRectF(32, 64, 76, 20), Qt.AlignCenter, format_bytes(self.total_bytes))


class DiskPieChartPopover(QFrame):
    """Floating hover card presenting an interactive storage footprint breakdown."""

    def __init__(self, parent=None, tokens: dict = DARK):
        super().__init__(parent, Qt.ToolTip | Qt.FramelessWindowHint)
        self.tokens = tokens
        self.setAttribute(Qt.WA_ShowWithoutActivating, True)
        self.setAttribute(Qt.WA_TranslucentBackground, True)
        self.setObjectName("DiskPieChartPopover")

        # Shadow effect
        shadow = QGraphicsDropShadowEffect(self)
        shadow.setBlurRadius(20)
        shadow.setColor(QColor(0, 0, 0, 160))
        shadow.setOffset(0, 6)
        self.setGraphicsEffect(shadow)

        self._build_ui()

    def _build_ui(self):
        container = QWidget(self)
        container.setObjectName("PopoverContainer")
        bg_color = self.tokens.get("panel", self.tokens["bg"])
        border_color = self.tokens.get("line2", self.tokens["line"])
        text_color = self.tokens.get("text", self.tokens["text"])
        muted_color = self.tokens.get("dim", self.tokens["text2"])

        container.setStyleSheet(f"""
            QWidget#PopoverContainer {{
                background-color: {bg_color};
                border: 1px solid {border_color};
                border-radius: 12px;
            }}
        """)

        layout = QVBoxLayout(container)
        layout.setContentsMargins(18, 16, 18, 16)
        layout.setSpacing(12)

        # Header
        header = QHBoxLayout()
        title = QLabel("Storage Breakdown")
        title_font = title.font()
        title_font.setPointSize(10)
        title_font.setBold(True)
        title.setFont(title_font)
        title.setStyleSheet(f"color: {text_color};")
        header.addWidget(title)
        header.addStretch()
        layout.addLayout(header)

        # Content: Chart + Legend
        content = QHBoxLayout()
        content.setSpacing(18)

        slices = asr_catalog.get_disk_breakdown()
        total_bytes = sum(s["size_bytes"] for s in slices)

        self.chart = DoughnutChartWidget(slices, total_bytes, self.tokens, self)
        content.addWidget(self.chart)

        # Legend list
        legend_layout = QVBoxLayout()
        legend_layout.setSpacing(6)
        legend_layout.setAlignment(Qt.AlignVCenter)

        for s in slices:
            item = QHBoxLayout()
            item.setSpacing(8)

            dot = QLabel("●")
            dot.setStyleSheet(f"color: {s['color']}; font-size: 11px;")
            item.addWidget(dot)

            name = QLabel(s["name"])
            name.setStyleSheet(f"color: {text_color}; font-size: 9pt; font-weight: 500;")
            item.addWidget(name)

            item.addStretch()

            pct = (s["size_bytes"] / total_bytes) * 100.0 if total_bytes > 0 else 0
            size_lbl = QLabel(f"{format_bytes(s['size_bytes'])} ({pct:.0f}%)")
            size_lbl.setStyleSheet(f"color: {muted_color}; font-size: 8.5pt; font-family: monospace;")
            item.addWidget(size_lbl)

            legend_layout.addLayout(item)

        content.addLayout(legend_layout, 1)
        layout.addLayout(content)

        # Footer drive capacity context
        try:
            drive_root = Path(asr_catalog.get_models_dir()).anchor or "C:\\"
            usage = shutil.disk_usage(drive_root)
            free_str = format_bytes(usage.free)
            footer_text = f"Drive {drive_root} has {free_str} available."
        except Exception:
            footer_text = "Local storage footprint."

        footer = QLabel(footer_text)
        footer.setStyleSheet(f"color: {muted_color}; font-size: 8pt; border-top: 1px solid {border_color}; padding-top: 8px;")
        layout.addWidget(footer)

        outer_layout = QVBoxLayout(self)
        outer_layout.setContentsMargins(10, 10, 10, 10)
        outer_layout.addWidget(container)

    def show_below(self, target_widget: QWidget):
        """Positions and shows the popover card neatly below or above the target widget."""
        pos = target_widget.mapToGlobal(QPoint(0, target_widget.height() + 4))
        # Ensure it stays on screen
        self.adjustSize()
        self.move(pos.x() - self.width() + target_widget.width(), pos.y())
        self.show()
