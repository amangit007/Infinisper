from PySide6.QtCore import QRectF, Qt, Signal
from PySide6.QtGui import QColor, QPainter, QPen
from PySide6.QtWidgets import (
    QButtonGroup,
    QCheckBox,
    QComboBox,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QRadioButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from asr import catalog as asr_catalog
from audio import capture as audio_capture
from config import load_config
from ui.theme import DARK
from ui.widgets.info_button import InfoButton
from ui.widgets.pipeline_diagram import PipelineDiagram
from ui.widgets.toggle_switch import ToggleSwitch

_ENGINE_DISPLAY_NAMES = {
    "whisper": "Whisper",
    "qwen3": "Qwen3-ASR 0.6B",
    "nemotron": "Nemotron 3.5 ASR",
}


def _parse_rgba(rgba: str) -> QColor:
    # "rgba(r, g, b, a)" with a already in 0..255, as produced by theme.oklch_to_rgba.
    parts = rgba[rgba.index("(") + 1 : rgba.index(")")].split(",")
    r, g, b, a = (int(p.strip()) for p in parts)
    return QColor(r, g, b, a)


class _EngineRow(QWidget):
    """Clickable, radio-selectable ASR engine selection row."""

    def __init__(self, engine_id: str, meta: dict, parent=None):
        super().__init__(parent)
        self.engine_id = engine_id
        self.setObjectName("EngineRow")
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self._tokens = DARK
        self._dimmed = False
        self._hover = False

        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 8, 11, 8)
        layout.setSpacing(11)

        self.radio = QRadioButton()
        layout.addWidget(self.radio)

        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        self.name_label = QLabel(meta["label"])
        self.name_label.setObjectName("EngineRowName")
        self.name_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        self.sub_label = QLabel(meta["subtitle"])
        self.sub_label.setObjectName("EngineRowSubtitle")
        self.sub_label.setAttribute(Qt.WA_TransparentForMouseEvents)
        text_col.addWidget(self.name_label)
        text_col.addWidget(self.sub_label)
        layout.addLayout(text_col, 1)

        layout.addWidget(InfoButton(meta["info_html"]))

        self.radio.toggled.connect(self._on_toggled)
        self._selected = self.radio.isChecked()

    def apply_theme(self, tokens: dict):
        self._tokens = tokens
        self.update()

    def set_dimmed(self, dimmed: bool):
        self._dimmed = dimmed
        self.update()

    def _on_toggled(self, checked: bool):
        self._selected = checked
        self.update()

    def paintEvent(self, event):
        # Painted directly with QPainter, not driven by a `[selected="true"]`
        # dynamic-property QSS selector or even a locally-set stylesheet string --
        # both were confirmed (via real interactive testing, not just this app's own
        # screenshot tooling) to not reliably repaint here after the state changed at
        # runtime. Every OTHER dynamic-state widget in this app (nav row highlight,
        # toggle switches, mic meter) already paints itself directly and has never had
        # this problem, so selection highlighting moves to the same proven approach.
        if not self._dimmed and (self._selected or self._hover):
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            painter.setPen(Qt.NoPen)
            if self._selected:
                painter.setBrush(_parse_rgba(self._tokens["accent_soft"]))
            else:
                painter.setBrush(QColor(self._tokens["panel2"]))
            painter.drawRoundedRect(QRectF(self.rect()), 8, 8)
        super().paintEvent(event)

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.radio.setChecked(True)
        super().mousePressEvent(event)


class _LevelCard(QWidget):
    """One half of the Basic/Advanced correction-level picker -- a clickable card
    pair, exclusive selection managed by the two siblings directly (there's no
    native input here to group, just two boxes)."""

    clicked = Signal()

    def __init__(self, title: str, description: str, parent=None):
        super().__init__(parent)
        self.setCursor(Qt.PointingHandCursor)
        self.setAttribute(Qt.WA_Hover, True)
        self.setMinimumHeight(64)
        self._title = title
        self._description = description
        self._tokens = DARK
        self._selected = False
        self._dimmed = False
        self._hover = False

    def apply_theme(self, tokens: dict):
        self._tokens = tokens
        self.update()

    def set_selected(self, selected: bool):
        self._selected = selected
        self.update()

    def set_dimmed(self, dimmed: bool):
        self._dimmed = dimmed
        self.update()

    def enterEvent(self, event):
        self._hover = True
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        self.update()
        super().leaveEvent(event)

    def mousePressEvent(self, event):
        if event.button() == Qt.LeftButton:
            self.clicked.emit()
        super().mousePressEvent(event)

    def paintEvent(self, event):
        # Fully self-painted with QPainter -- no QSS involved at all, including for
        # text. This card's selection state relied on QSS (first a `[selected="true"]`
        # dynamic-property selector, then a per-widget setStyleSheet() call) through
        # two rounds of fixes, and real interactive testing showed neither one actually
        # rendered the change. Every other dynamic-state widget in this app already
        # paints itself directly and has never had this problem, so this one now does
        # too -- eliminates the whole class of bug rather than guessing at a third QSS
        # variant.
        t = self._tokens
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        if self._dimmed:
            border_color = QColor(t["line"])
            bg = QColor(Qt.transparent)
            title_color = QColor(t["dim"])
            desc_color = QColor(t["dim"])
        elif self._selected:
            border_color = QColor(t["accent"])
            bg = _parse_rgba(t["accent_soft"])
            title_color = QColor(t["text"])
            desc_color = QColor(t["dim"])
        else:
            border_color = QColor(t["accent"]) if self._hover else QColor(t["line2"])
            bg = QColor(Qt.transparent)
            title_color = QColor(t["text"])
            desc_color = QColor(t["dim"])

        rect = QRectF(self.rect()).adjusted(0.5, 0.5, -0.5, -0.5)
        painter.setPen(QPen(border_color, 1))
        painter.setBrush(bg)
        painter.drawRoundedRect(rect, 8, 8)

        pad_x, pad_top = 11, 10
        title_font = self.font()
        title_font.setPointSizeF(9.5)
        title_font.setBold(True)
        painter.setFont(title_font)
        painter.setPen(title_color)
        title_rect = QRectF(pad_x, pad_top, self.width() - pad_x * 2, 16)
        painter.drawText(title_rect, Qt.AlignLeft | Qt.AlignVCenter, self._title)

        desc_font = self.font()
        desc_font.setPointSizeF(8.3)
        painter.setFont(desc_font)
        painter.setPen(desc_color)
        desc_rect = QRectF(
            pad_x, pad_top + 18, self.width() - pad_x * 2, self.height() - pad_top - 18 - 8
        )
        painter.drawText(desc_rect, int(Qt.AlignLeft | Qt.TextWordWrap), self._description)


class DashboardTab(QWidget):
    settings_saved = Signal(dict)
    delete_model_requested = Signal(str)  # engine_id
    manage_models_requested = Signal()

    def __init__(self, current_config: dict, parent=None):
        super().__init__(parent)
        self._tokens = DARK
        self._initializing = True
        self._multimodal_level = current_config.get("multimodal_level", "basic")

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        outer.addWidget(self._build_header())

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.viewport().setObjectName("DashboardScrollViewport")
        scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)
        content = QWidget()
        content.setObjectName("DashboardScrollContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 20, 26, 26)
        content_layout.setSpacing(16)

        content_layout.addWidget(self._build_device_row(current_config))
        content_layout.addWidget(self._build_pipeline_card())

        controls_grid = QGridLayout()
        controls_grid.setSpacing(16)
        controls_grid.addWidget(self._build_asr_card(current_config), 0, 0)
        controls_grid.addWidget(self._build_multimodal_card(current_config), 0, 1)
        content_layout.addLayout(controls_grid)

        content_layout.addWidget(self._build_fallback_row(current_config))
        content_layout.addStretch()

        scroll.setWidget(content)
        outer.addWidget(scroll, 1)

        self._wire_auto_save()

        current_engine = current_config.get("asr_engine", "whisper")
        self.refresh_engine_statuses(current_engine, busy=False)
        self._on_asr_toggled(self.asr_toggle.isChecked())
        self._on_mm_toggled(self.mm_toggle.isChecked())
        self._apply_level_selection()

        self._initializing = False

    # ---- construction helpers -------------------------------------------------

    def _build_header(self) -> QWidget:
        header = QWidget()
        header.setObjectName("DashboardHeader")
        header.setFixedHeight(60)
        layout = QHBoxLayout(header)
        layout.setContentsMargins(26, 0, 26, 0)
        layout.setSpacing(14)

        title = QLabel("Dashboard")
        title.setObjectName("PageTitle")
        layout.addWidget(title)

        hint = QLabel("Hold Ctrl + Win, speak, release — the text lands where your cursor is.")
        hint.setObjectName("PageHint")
        layout.addWidget(hint)
        layout.addStretch()

        return header

    def _build_device_row(self, current_config: dict) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(10)

        label = QLabel("Microphone")
        label.setObjectName("SectionLabel")
        layout.addWidget(label)

        self.device_combo = QComboBox()
        self.device_combo.setObjectName("DeviceCombo")
        self.device_combo.addItem("System default", None)
        for name, index in audio_capture.list_input_devices():
            self.device_combo.addItem(name, index)
        self._select_device(current_config.get("input_device"))
        layout.addWidget(self.device_combo)
        layout.addStretch()
        return row

    def _build_pipeline_card(self) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(24, 18, 24, 18)
        layout.setSpacing(8)

        header = QHBoxLayout()
        title = QLabel("Pipeline")
        title.setObjectName("CardTitle")
        header.addWidget(title)
        self._route_label = QLabel("")
        self._route_label.setObjectName("RouteLabel")
        header.addWidget(self._route_label)
        header.addStretch()

        legend_in_use = QLabel("— IN USE")
        legend_in_use.setObjectName("LegendLabel")
        header.addWidget(legend_in_use)
        legend_available = QLabel("┄ AVAILABLE ROUTE")
        legend_available.setObjectName("LegendLabel")
        header.addWidget(legend_available)
        layout.addLayout(header)

        self.pipeline = PipelineDiagram()
        diagram_row = QHBoxLayout()
        diagram_row.addStretch()
        diagram_row.addWidget(self.pipeline)
        diagram_row.addStretch()
        layout.addLayout(diagram_row)

        return card

    def _build_asr_card(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("CardHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 15, 18, 15)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title = QLabel("Speech recognition")
        title.setObjectName("CardTitle")
        subtitle = QLabel("Runs on this machine. Audio never leaves.")
        subtitle.setObjectName("CardSubtitle")
        text_col.addWidget(title)
        text_col.addWidget(subtitle)
        header_layout.addLayout(text_col, 1)

        self.asr_toggle = ToggleSwitch()
        self.asr_toggle.setChecked(current_config.get("use_asr", True), animate=False)
        self.asr_toggle.toggled.connect(self._on_asr_toggled)
        header_layout.addWidget(self.asr_toggle)
        outer.addWidget(header)

        self._asr_body = QWidget()
        body_layout = QVBoxLayout(self._asr_body)
        body_layout.setContentsMargins(8, 8, 8, 8)
        body_layout.setSpacing(2)

        self._asr_group = QButtonGroup(self._asr_body)
        self.rows: dict[str, _EngineRow] = {}
        for engine_id in asr_catalog.ENGINE_ORDER:
            row = _EngineRow(engine_id, asr_catalog.ENGINES[engine_id])
            self._asr_group.addButton(row.radio)
            self.rows[engine_id] = row
            body_layout.addWidget(row)

        # Initial selection is applied later, via refresh_engine_statuses() at the end of
        # __init__ -- setting it here would fire _update_pipeline_preview() (through the
        # toggled signal above) before the multimodal card exists yet.
        outer.addWidget(self._asr_body)

        outer.addStretch()
        # Whisper's model-size picker and per-engine download/delete controls all live
        # in Models & providers now (Stage 4) -- this card only picks which engine runs.
        footer = QPushButton("Manage sizes, downloads and deletes in Models & providers →")
        footer.setObjectName("FooterLink")
        footer.setCursor(Qt.PointingHandCursor)
        footer.setFlat(True)
        footer.clicked.connect(self.manage_models_requested.emit)
        outer.addWidget(footer)

        # kept for external callers (asr_engine_card.py used to own this signal path)
        self.cards = self.rows
        return card

    def _build_multimodal_card(self, current_config: dict) -> QWidget:
        card = QWidget()
        card.setObjectName("Card")
        card.setAttribute(Qt.WA_StyledBackground, True)
        outer = QVBoxLayout(card)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("CardHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 15, 18, 15)
        text_col = QVBoxLayout()
        text_col.setSpacing(2)
        title_row = QHBoxLayout()
        title_row.setSpacing(7)
        title = QLabel("Multimodal correction")
        title.setObjectName("CardTitle")
        title_row.addWidget(title)
        privacy_info = InfoButton(
            "<b>Text leaves your machine</b><br>"
            "Transcripts go to your configured provider. Audio stays on device unless "
            "you route the mic straight to the model."
        )
        title_row.addWidget(privacy_info)
        title_row.addStretch()
        text_col.addLayout(title_row)
        subtitle = QLabel("Cleans up the text — or transcribes on its own.")
        subtitle.setObjectName("CardSubtitle")
        text_col.addWidget(subtitle)
        header_layout.addLayout(text_col, 1)

        self.mm_toggle = ToggleSwitch()
        self.mm_toggle.setChecked(current_config.get("use_multimodal", False), animate=False)
        self.mm_toggle.toggled.connect(self._on_mm_toggled)
        header_layout.addWidget(self.mm_toggle)
        outer.addWidget(header)

        self._mm_body = QWidget()
        body_layout = QVBoxLayout(self._mm_body)
        body_layout.setContentsMargins(18, 14, 18, 14)
        body_layout.setSpacing(14)

        model_col = QVBoxLayout()
        model_col.setSpacing(7)
        model_label = QLabel("ACTIVE MODEL")
        model_label.setObjectName("SectionLabel")
        model_col.addWidget(model_label)
        self.multimodal_model_combo = QComboBox()
        self.multimodal_model_combo.currentIndexChanged.connect(self._update_pipeline_preview)
        model_col.addWidget(self.multimodal_model_combo)
        self.refresh_multimodal_models(
            current_config.get("multimodal_models", []),
            current_config.get("active_multimodal_model_id"),
        )
        body_layout.addLayout(model_col)

        level_col = QVBoxLayout()
        level_col.setSpacing(7)
        level_label = QLabel("CORRECTION LEVEL")
        level_label.setObjectName("SectionLabel")
        level_col.addWidget(level_label)
        level_row = QHBoxLayout()
        level_row.setSpacing(8)
        self.basic_card = _LevelCard("Basic", "Fixes mishearings only")
        self.advanced_card = _LevelCard("Advanced", "Drops fillers, formats lists")
        self.basic_card.clicked.connect(lambda: self._on_level_picked("basic"))
        self.advanced_card.clicked.connect(lambda: self._on_level_picked("advanced"))
        level_row.addWidget(self.basic_card)
        level_row.addWidget(self.advanced_card)
        level_col.addLayout(level_row)
        body_layout.addLayout(level_col)

        self._multimodal_level = (
            "advanced" if current_config.get("multimodal_level", "basic") == "advanced" else "basic"
        )
        self._apply_level_selection()

        timeout_col = QVBoxLayout()
        timeout_col.setSpacing(7)
        timeout_label = QLabel("TIMEOUT (SECONDS)")
        timeout_label.setObjectName("SectionLabel")
        timeout_col.addWidget(timeout_label)
        timeout_row = QHBoxLayout()
        timeout_row.setSpacing(8)
        self.timeout_spinbox = QSpinBox()
        # 180s ceiling: generous headroom above the 60s default -- a newly added or
        # cold-starting model can genuinely need more than the default window without
        # the request actually being stuck.
        self.timeout_spinbox.setRange(10, 180)
        self.timeout_spinbox.setValue(current_config.get("multimodal_timeout_seconds", 60))
        self.timeout_spinbox.setSuffix("s")
        timeout_row.addWidget(self.timeout_spinbox)
        timeout_hint = QLabel("How long to wait for the multimodal model before falling back.")
        timeout_hint.setObjectName("CardSubtitle")
        timeout_hint.setWordWrap(True)
        timeout_row.addWidget(timeout_hint, 1)
        timeout_col.addLayout(timeout_row)
        body_layout.addLayout(timeout_col)

        outer.addWidget(self._mm_body)
        outer.addStretch()

        footer = QPushButton("Add providers and models in Models & providers →")
        footer.setObjectName("FooterLink")
        footer.setCursor(Qt.PointingHandCursor)
        footer.setFlat(True)
        footer.clicked.connect(self.manage_models_requested.emit)
        outer.addWidget(footer)

        return card

    def _build_fallback_row(self, current_config: dict) -> QWidget:
        row = QWidget()
        row.setObjectName("FallbackRow")
        row.setAttribute(Qt.WA_StyledBackground, True)
        row.setCursor(Qt.PointingHandCursor)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        self.fallback_checkbox = QCheckBox()
        self.fallback_checkbox.setChecked(current_config.get("fallback_to_whisper", True))
        layout.addWidget(self.fallback_checkbox)

        text = QLabel("Fall back to Whisper if the selected route fails")
        text.setObjectName("FallbackText")
        text.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(text)

        hint = QLabel("Applies to both stages — you get unpolished text rather than nothing.")
        hint.setObjectName("FallbackHint")
        hint.setAttribute(Qt.WA_TransparentForMouseEvents)
        layout.addWidget(hint)
        layout.addStretch()

        row.mousePressEvent = lambda event: self._toggle_fallback_row(event, row)
        return row

    def _toggle_fallback_row(self, event, row):
        if event.button() == Qt.LeftButton:
            self.fallback_checkbox.setChecked(not self.fallback_checkbox.isChecked())
        QWidget.mousePressEvent(row, event)

    # ---- auto-save & pipeline preview -----------------------------------------

    def _wire_auto_save(self):
        self.device_combo.currentIndexChanged.connect(self._on_control_changed)
        self.asr_toggle.toggled.connect(self._on_asr_toggled)
        self.mm_toggle.toggled.connect(self._on_mm_toggled)
        self.multimodal_model_combo.currentIndexChanged.connect(self._on_control_changed)
        self.timeout_spinbox.valueChanged.connect(self._on_control_changed)
        self.fallback_checkbox.toggled.connect(self._on_control_changed)
        for engine_id, row in self.rows.items():
            row.radio.toggled.connect(
                lambda checked, eid=engine_id: self._on_engine_radio_toggled(eid, checked)
            )

    def _on_control_changed(self, *_args):
        self._update_pipeline_preview()
        self._emit_settings_changed()

    def _on_engine_radio_toggled(self, engine_id: str, checked: bool):
        if not checked:
            return
        self._update_pipeline_preview()
        self._emit_settings_changed()

    def apply_theme(self, tokens: dict):
        self._tokens = tokens
        for row in self.rows.values():
            row.apply_theme(tokens)
        self.basic_card.apply_theme(tokens)
        self.advanced_card.apply_theme(tokens)
        self.asr_toggle.set_colors(tokens["accent"], tokens["line2"])
        self.mm_toggle.set_colors(tokens["accent"], tokens["line2"])
        self.pipeline.apply_theme(tokens)
        self._set_widget_active(self._asr_body, self.asr_toggle.isChecked())
        self._set_widget_active(self._mm_body, self.mm_toggle.isChecked())

    def _set_widget_active(self, widget: QWidget, active: bool):
        """Visually dims an "off" section without QWidget.setEnabled()."""
        t = self._tokens
        widget.setAttribute(Qt.WA_TransparentForMouseEvents, not active)
        for child in (widget, *widget.findChildren(QWidget)):
            if isinstance(child, (_LevelCard, _EngineRow)):
                child.set_dimmed(not active)
            elif isinstance(child, (QComboBox, QSpinBox)):
                child.setStyleSheet(
                    "" if active else f"color: {t['dim']}; background: {t['panel2']};"
                )
            elif isinstance(child, QLabel):
                child.setStyleSheet("" if active else f"color: {t['dim']};")

    def _active_model_supports_audio(self) -> bool:
        active_id = self.multimodal_model_combo.currentData()
        if not active_id:
            return False
        config = load_config()
        for m in config.get("multimodal_models", []):
            if m["id"] == active_id:
                return bool(m.get("supports_audio", False))
        return False

    def _on_asr_toggled(self, checked: bool):
        if not checked and self.mm_toggle.isChecked() and not self._active_model_supports_audio():
            model_name = self.multimodal_model_combo.currentText() or "The active model"
            QMessageBox.information(
                self,
                "Speech Recognition (ASR) Required",
                f"{model_name} is a text-only refinement model (it polishes transcripts, but cannot transcribe raw audio directly).\n\n"
                "Speech Recognition (ASR) must remain enabled so Nemotron, Whisper, or Qwen3 can capture your voice.",
            )
            self.asr_toggle.blockSignals(True)
            self.asr_toggle.setChecked(True)
            self.asr_toggle.blockSignals(False)
            return

        self._set_widget_active(self._asr_body, checked)
        self._update_pipeline_preview()
        self._emit_settings_changed()

    def _on_mm_toggled(self, checked: bool):
        self._set_widget_active(self._mm_body, checked)
        self._update_pipeline_preview()
        self._emit_settings_changed()

    def _on_level_picked(self, level: str):
        self._multimodal_level = level
        self._apply_level_selection()
        self._emit_settings_changed()

    def _apply_level_selection(self):
        self.basic_card.set_selected(self._multimodal_level == "basic")
        self.advanced_card.set_selected(self._multimodal_level == "advanced")

    def _update_pipeline_preview(self):
        use_asr = self.asr_toggle.isChecked()
        use_mm = self.mm_toggle.isChecked()
        selected_engine = "whisper"
        for engine_id, row in self.rows.items():
            if row.radio.isChecked():
                selected_engine = engine_id
                break
        asr_label = _ENGINE_DISPLAY_NAMES.get(selected_engine, selected_engine)
        mm_label = self.multimodal_model_combo.currentText() or "a multimodal model"
        route_label = self.pipeline.set_route(use_asr, use_mm, asr_label, mm_label)
        if use_mm and not use_asr and not self._active_model_supports_audio():
            route_label += " (⚠️ Model is text-only; enable ASR)"
        self._route_label.setText(route_label)

    # ---- public API used by app.py --------------------------------------------

    def _select_device(self, device_index):
        idx = self.device_combo.findData(device_index)
        if idx >= 0:
            self.device_combo.setCurrentIndex(idx)

    def refresh_engine_statuses(self, active_engine: str, busy: bool):
        """Keeps the active-engine radio selection in sync. Per-engine download
        status/delete now lives in the Models & providers engine table (Stage 4);
        this card only needs to track which one is active.
        """
        for engine_id, row in self.rows.items():
            is_target = (engine_id == active_engine)
            if row.radio.isChecked() != is_target:
                row.radio.blockSignals(True)
                row.radio.setChecked(is_target)
                row.radio.blockSignals(False)
        self._update_pipeline_preview()

    def set_active_engine_radio(self, engine_id: str):
        for eid, row in self.rows.items():
            is_target = (eid == engine_id)
            if row.radio.isChecked() != is_target:
                row.radio.blockSignals(True)
                row.radio.setChecked(is_target)
                row.radio.blockSignals(False)
        self._update_pipeline_preview()

    def refresh_multimodal_models(self, models: list[dict], active_id: str | None):
        self.multimodal_model_combo.blockSignals(True)
        self.multimodal_model_combo.clear()
        if not models:
            self.multimodal_model_combo.addItem("Configure a model in Models & providers", None)
            self._set_widget_active(self.multimodal_model_combo, False)
        else:
            self._set_widget_active(self.multimodal_model_combo, True)
            for model_entry in models:
                self.multimodal_model_combo.addItem(model_entry["display_name"], model_entry["id"])
            idx = self.multimodal_model_combo.findData(active_id)
            if idx >= 0:
                self.multimodal_model_combo.setCurrentIndex(idx)
        self.multimodal_model_combo.blockSignals(False)
        self._update_pipeline_preview()

    def _emit_settings_changed(self):
        if getattr(self, "_initializing", False):
            return

        selected_engine = "whisper"
        for engine_id, row in self.rows.items():
            if row.radio.isChecked():
                selected_engine = engine_id
                break

        self.settings_saved.emit(
            {
                "input_device": self.device_combo.currentData(),
                # Whisper's model size is managed from Models & providers,
                # read fresh from disk rather than caching.
                "model_size": load_config().get("model_size", "base"),
                "use_asr": self.asr_toggle.isChecked(),
                "asr_engine": selected_engine,
                "use_multimodal": self.mm_toggle.isChecked(),
                "multimodal_level": self._multimodal_level,
                "multimodal_timeout_seconds": self.timeout_spinbox.value(),
                "fallback_to_whisper": self.fallback_checkbox.isChecked(),
                "active_multimodal_model_id": self.multimodal_model_combo.currentData(),
            }
        )
