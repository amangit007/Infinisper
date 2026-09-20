from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from asr import catalog as asr_catalog
from asr.downloader import downloader, format_bytes
from config import load_config, save_config
from credentials import delete_api_key
from ui.dialogs.model_dialog import ModelDialog
from ui.dialogs.provider_dialog import ProviderDialog
from ui.widgets.asr_engine_card import EngineTableRow
from ui.widgets.disk_pie_chart import DiskPieChartPopover
from ui.widgets.model_card import ModelCard
from ui.widgets.provider_card import ProviderCard


class HoverableDiskLabel(QLabel):
    """Badge that presents an interactive storage breakdown doughnut chart on hover."""

    def __init__(self, text="", parent=None):
        super().__init__(text, parent)
        self.setCursor(Qt.PointingHandCursor)
        self._popover = None

    def enterEvent(self, event):
        if self._popover:
            self._popover.close()
            self._popover.deleteLater()
        self._popover = DiskPieChartPopover(self.window())
        self._popover.show_below(self)
        super().enterEvent(event)

    def leaveEvent(self, event):
        if self._popover:
            self._popover.hide()
        super().leaveEvent(event)


class EnginesSubTab(QWidget):
    """Sub-tab for viewing and managing on-device speech recognition models."""

    activate_requested = Signal(str)  # model_id
    download_requested = Signal(str)  # model_id
    delete_requested = Signal(str)  # model_id
    cancel_requested = Signal(str)  # model_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_engine = "whisper"
        self._busy = False
        self._model_size = load_config().get("model_size", "base")
        self._rows: dict[str, EngineTableRow] = {}
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("TableCardHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 13, 18, 13)
        title = QLabel("Speech Recognition Models")
        title.setObjectName("TableCardHeaderTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        one_active_note = QLabel("One active at a time • Hover disk badge for breakdown")
        one_active_note.setObjectName("TableCardHeaderNote")
        header_layout.addWidget(one_active_note)
        outer.addWidget(header)

        columns = QWidget()
        columns.setObjectName("ColumnHeaderRow")
        columns_layout = QHBoxLayout(columns)
        columns_layout.setContentsMargins(18, 9, 18, 9)
        columns_layout.setSpacing(16)
        model_col = QLabel("MODEL")
        model_col.setObjectName("ColumnHeaderLabel")
        columns_layout.addWidget(model_col, 1)

        for text, width in (("SIZE", 100), ("LANGUAGES", 110), ("STATUS & ACTIONS", 260)):
            col_label = QLabel(text)
            col_label.setObjectName("ColumnHeaderLabel")
            col_label.setFixedWidth(width)
            if "STATUS" in text:
                col_label.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            columns_layout.addWidget(col_label)
        outer.addWidget(columns)

        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(0)
        outer.addLayout(self.list_container)

        footer = QWidget()
        footer.setObjectName("TableCardFooter")
        footer.setAttribute(Qt.WA_StyledBackground, True)
        footer_layout = QHBoxLayout(footer)
        footer_layout.setContentsMargins(18, 11, 18, 11)
        footer_note = QLabel(
            "Download any model to activate. You can delete downloaded models at any time to reclaim space."
        )
        footer_note.setObjectName("TableCardFooterNote")
        footer_layout.addWidget(footer_note)
        footer_layout.addStretch()
        self.disk_label = HoverableDiskLabel()
        self.disk_label.setObjectName("DiskUsageLabel")
        footer_layout.addWidget(self.disk_label)
        outer.addWidget(footer)

        downloader.progress_updated.connect(self._on_download_progress)
        downloader.download_finished.connect(self._on_download_finished)

        self.refresh(self._active_engine, self._busy)

    def refresh(self, active_engine: str, busy: bool):
        self._active_engine = active_engine
        self._busy = busy
        self._rows.clear()

        while self.list_container.count():
            item = self.list_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        current_config = load_config()
        configured_whisper_size = current_config.get("model_size", "base")

        for model_id in asr_catalog.MODEL_ORDER:
            meta = asr_catalog.MODELS[model_id]
            is_active = False
            if active_engine == "whisper":
                is_active = (model_id == f"whisper-{configured_whisper_size}")
            else:
                is_active = (model_id == active_engine)

            downloaded = asr_catalog.is_downloaded(model_id)

            row = EngineTableRow(
                model_id,
                meta,
                is_active=is_active,
                downloaded=downloaded,
                busy=busy,
            )
            row.activate_requested.connect(self.activate_requested.emit)
            row.download_requested.connect(self.download_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            row.cancel_requested.connect(self.cancel_requested.emit)

            self._rows[model_id] = row
            self.list_container.addWidget(row)

        self.disk_label.setText(f"{format_bytes(asr_catalog.disk_usage_bytes())} on disk 📊")

    def _on_download_progress(self, model_id, dl_b, total_b, pct, speed_str, status_str):
        if model_id in self._rows:
            self._rows[model_id].update_progress(pct, speed_str, status_str)

    def _on_download_finished(self, model_id, success, err_msg):
        self.refresh(self._active_engine, self._busy)

    def confirm_and_request_delete(self, model_id: str, is_active: bool) -> bool:
        meta = asr_catalog.get_model_info(model_id)
        directory = asr_catalog.model_dir(model_id)
        size_label = meta.get("size_label", "")
        message = (
            f"Delete {meta['label']} ({size_label} from {directory})?\n\n"
            "This will permanently delete the downloaded model weights to reclaim disk space."
        )
        if is_active:
            message += "\n\nThis is currently your active speech model -- Infinisper will switch to another available model."
        reply = QMessageBox.question(
            self,
            "Delete model",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes


class ProvidersSubTab(QWidget):
    """Card widget for managing AI provider configurations."""

    def __init__(self, models_tab: "ModelsTab", parent=None):
        super().__init__(parent)
        self._models_tab = models_tab
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("TableCardHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 13, 18, 13)
        title = QLabel("Providers")
        title.setObjectName("TableCardHeaderTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        add_button = QPushButton("+ Add provider")
        add_button.setObjectName("AddPillButton")
        add_button.clicked.connect(self._on_add)
        header_layout.addWidget(add_button)
        outer.addWidget(header)

        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(0)
        outer.addLayout(self.list_container)
        self.empty_label = QLabel("No providers configured yet.")
        self.empty_label.setObjectName("MutedValueLabel")
        self.empty_label.setContentsMargins(18, 14, 18, 14)
        outer.addWidget(self.empty_label)
        outer.addStretch()

        footer_note = QLabel(
            "Ollama, OpenAI, Anthropic, OpenRouter and any LiteLLM-compatible gateway are supported."
        )
        footer_note.setObjectName("TableCardFooterNote")
        footer_note.setWordWrap(True)
        footer_note.setContentsMargins(18, 12, 18, 12)
        outer.addWidget(footer_note)

        self.refresh()

    def refresh(self):
        while self.list_container.count():
            item = self.list_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        providers = self._models_tab.providers()
        self.empty_label.setVisible(not providers)
        for provider in providers:
            card = ProviderCard(provider)
            card.edit_requested.connect(self._on_edit)
            self.list_container.addWidget(card)

    def _on_add(self):
        dialog = ProviderDialog(existing=None, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._models_tab.save_provider(dialog.result_provider)

    def _on_edit(self, provider_id: str):
        existing = next((p for p in self._models_tab.providers() if p["id"] == provider_id), None)
        if existing is None:
            return
        dialog = ProviderDialog(existing=existing, parent=self)
        if dialog.exec() == QDialog.Accepted:
            if dialog.deleted:
                self._models_tab.delete_provider(provider_id)
            else:
                self._models_tab.save_provider(dialog.result_provider)


class ModelsSubTab(QWidget):
    """Card widget for managing AI models."""

    def __init__(self, models_tab: "ModelsTab", parent=None):
        super().__init__(parent)
        self._models_tab = models_tab
        self.setObjectName("Card")
        self.setAttribute(Qt.WA_StyledBackground, True)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("TableCardHeader")
        header.setAttribute(Qt.WA_StyledBackground, True)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(18, 13, 18, 13)
        title = QLabel("Models")
        title.setObjectName("TableCardHeaderTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        add_button = QPushButton("+ Add model")
        add_button.setObjectName("AddPillButton")
        add_button.clicked.connect(self._on_add)
        header_layout.addWidget(add_button)
        outer.addWidget(header)

        self.list_container = QVBoxLayout()
        self.list_container.setSpacing(0)
        outer.addLayout(self.list_container)
        self.empty_label = QLabel("No models configured yet.")
        self.empty_label.setObjectName("MutedValueLabel")
        self.empty_label.setContentsMargins(18, 14, 18, 14)
        outer.addWidget(self.empty_label)
        outer.addStretch()

        footer_note = QLabel(
            "Every model is connection-tested before it is saved. Audio-capable models can also "
            "replace speech recognition entirely."
        )
        footer_note.setObjectName("TableCardFooterNote")
        footer_note.setWordWrap(True)
        footer_note.setContentsMargins(18, 12, 18, 12)
        outer.addWidget(footer_note)

        self.refresh()

    def refresh(self):
        while self.list_container.count():
            item = self.list_container.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)
                widget.deleteLater()

        active_id = load_config().get("active_cleanup_model_id")
        models = self._models_tab.models()
        self.empty_label.setVisible(not models)
        for model_entry in models:
            provider_name = self._models_tab.provider_display_name(model_entry["provider_id"])
            card = ModelCard(model_entry, provider_name, is_active=(model_entry["id"] == active_id))
            card.rename_requested.connect(self._on_rename)
            card.delete_requested.connect(self._on_delete)
            card.activate_requested.connect(self._on_activate)
            self.list_container.addWidget(card)

    def _on_add(self):
        providers = self._models_tab.providers()
        if not providers:
            QMessageBox.information(
                self,
                "Add a provider first",
                "Configure a provider in the Providers section before adding a model.",
            )
            return
        dialog = ModelDialog(providers, parent=self)
        if dialog.exec() == QDialog.Accepted:
            self._models_tab.save_model(dialog.result_model)

    def _on_rename(self, model_id: str):
        existing = next((m for m in self._models_tab.models() if m["id"] == model_id), None)
        if existing is None:
            return
        new_name, ok = QInputDialog.getText(
            self, "Rename model", "Display name:", text=existing["display_name"]
        )
        new_name = new_name.strip()
        if ok and new_name:
            self._models_tab.rename_model(model_id, new_name)

    def _on_delete(self, model_id: str):
        reply = QMessageBox.question(
            self, "Delete model", "Remove this model from your configuration?",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._models_tab.delete_model(model_id)

    def _on_activate(self, model_id: str):
        self._models_tab.activate_model(model_id)


class ModelsTab(QWidget):
    """Models & providers tab for configuring speech recognition engines and AI models."""

    changed = Signal()  # providers/models/active-model changed
    activate_engine_requested = Signal(str)  # model_id
    download_requested = Signal(str)  # model_id
    delete_engine_requested = Signal(str)  # model_id
    cancel_download_requested = Signal(str)  # model_id
    whisper_model_size_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelsPage")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.engines_subtab = EnginesSubTab(self)
        self.engines_subtab.activate_requested.connect(self.activate_engine_requested.emit)
        self.engines_subtab.download_requested.connect(self.download_requested.emit)
        self.engines_subtab.delete_requested.connect(self.delete_engine_requested.emit)
        self.engines_subtab.cancel_requested.connect(self.cancel_download_requested.emit)

        self.providers_subtab = ProvidersSubTab(self)
        self.models_subtab = ModelsSubTab(self)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        header = QWidget()
        header.setObjectName("DashboardHeader")
        header.setFixedHeight(60)
        header_layout = QHBoxLayout(header)
        header_layout.setContentsMargins(26, 0, 26, 0)
        header_layout.setSpacing(14)
        title = QLabel("Models & providers")
        title.setObjectName("PageTitle")
        header_layout.addWidget(title)
        hint = QLabel(
            "Speech recognition runs on this device. AI cleanup is optional."
        )
        hint.setObjectName("PageHint")
        header_layout.addWidget(hint)
        header_layout.addStretch()
        self.disk_total_label = HoverableDiskLabel()
        self.disk_total_label.setObjectName("DiskUsageLabel")
        header_layout.addWidget(self.disk_total_label)
        outer.addWidget(header)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.viewport().setObjectName("ModelsScrollViewport")
        scroll.viewport().setAttribute(Qt.WA_StyledBackground, True)

        content = QWidget()
        content.setObjectName("ModelsScrollContent")
        content.setAttribute(Qt.WA_StyledBackground, True)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(26, 22, 26, 26)
        content_layout.setSpacing(26)

        section1 = QVBoxLayout()
        section1.setSpacing(12)
        section1.addLayout(
            self._section_heading(
                "1  Speech recognition",
                "Hover disk badge on right for full storage breakdown.",
            )
        )
        section1.addWidget(self.engines_subtab)
        content_layout.addLayout(section1)

        section2 = QVBoxLayout()
        section2.setSpacing(12)
        section2.addLayout(
            self._section_heading(
                "2  AI cleanup", "Add a provider, then a model."
            )
        )
        grid = QHBoxLayout()
        grid.setSpacing(16)
        grid.addWidget(self.providers_subtab, 4)
        grid.addWidget(self.models_subtab, 5)
        section2.addLayout(grid)
        content_layout.addLayout(section2)

        content_layout.addStretch()
        scroll.setWidget(content)
        outer.addWidget(scroll)

        self._refresh_disk_total()

    def _section_heading(self, number_text: str, hint_text: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(12)
        number = QLabel(number_text)
        number.setObjectName("SectionNumberLabel")
        row.addWidget(number)
        hint = QLabel(hint_text)
        hint.setObjectName("SectionHintLabel")
        row.addWidget(hint)
        row.addStretch()
        return row

    def refresh_engine_statuses(self, active_engine: str, busy: bool):
        self.engines_subtab.refresh(active_engine, busy)
        self._refresh_disk_total()

    def _refresh_disk_total(self):
        self.disk_total_label.setText(f"on disk {format_bytes(asr_catalog.disk_usage_bytes())} 📊")

    def confirm_and_request_delete_engine(self, model_id: str, is_active: bool) -> bool:
        return self.engines_subtab.confirm_and_request_delete(model_id, is_active)

    def providers(self) -> list[dict]:
        return load_config()["cleanup_providers"]

    def models(self) -> list[dict]:
        return load_config()["cleanup_models"]

    def provider_display_name(self, provider_id: str) -> str:
        for provider in self.providers():
            if provider["id"] == provider_id:
                return provider["display_name"]
        return provider_id

    def save_provider(self, provider: dict):
        config = load_config()
        others = [p for p in config["cleanup_providers"] if p["id"] != provider["id"]]
        config["cleanup_providers"] = others + [provider]
        save_config(config)
        self._after_change()

    def delete_provider(self, provider_id: str):
        config = load_config()
        config["cleanup_providers"] = [
            p for p in config["cleanup_providers"] if p["id"] != provider_id
        ]
        remaining_models = [
            m for m in config["cleanup_models"] if m["provider_id"] != provider_id
        ]
        config["cleanup_models"] = remaining_models
        if config.get("active_cleanup_model_id") not in {m["id"] for m in remaining_models}:
            config["active_cleanup_model_id"] = None
        delete_api_key(provider_id)
        save_config(config)
        self._after_change()

    def activate_model(self, model_id: str):
        config = load_config()
        config["active_cleanup_model_id"] = model_id
        save_config(config)
        self._after_change()

    def save_model(self, model_entry: dict):
        config = load_config()
        others = [m for m in config["cleanup_models"] if m["id"] != model_entry["id"]]
        config["cleanup_models"] = others + [model_entry]
        save_config(config)
        self._after_change()

    def delete_model(self, model_id: str):
        config = load_config()
        config["cleanup_models"] = [m for m in config["cleanup_models"] if m["id"] != model_id]
        if config.get("active_cleanup_model_id") == model_id:
            config["active_cleanup_model_id"] = None
        save_config(config)
        self._after_change()

    def rename_model(self, model_id: str, new_display_name: str):
        config = load_config()
        for model_entry in config["cleanup_models"]:
            if model_entry["id"] == model_id:
                model_entry["display_name"] = new_display_name
                break
        save_config(config)
        self._after_change()

    def _after_change(self):
        self.providers_subtab.refresh()
        self.models_subtab.refresh()
        self.changed.emit()
