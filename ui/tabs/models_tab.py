import threading
from datetime import datetime

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from asr import catalog as asr_catalog
from config import load_config, save_config
from credentials import delete_api_key, get_api_key, set_api_key
from multimodal.catalog import (
    CURATED_PROVIDERS,
    DEFAULT_OLLAMA_BASE_URL,
    PROVIDERS_REQUIRING_BASE_URL,
    list_models_for_provider,
    probe_ollama,
)
from multimodal.engine import TIMEOUT_SECONDS
from multimodal.testing import AUDIO_DECLARED, AUDIO_UNKNOWN, test_provider_model
from ui.widgets.asr_engine_card import EngineTableRow
from ui.widgets.model_card import ModelCard
from ui.widgets.provider_card import ProviderCard

_LABELS_BY_ID = dict(CURATED_PROVIDERS)


class ProviderDialog(QDialog):
    """Add/edit dialog for one multimodal provider. The API key is masked by
    default with an eye-icon toggle to reveal it -- per this project's own
    design decision, keys are stored securely via keyring and can be revealed
    in plaintext inside the app's own UI, but stay masked until asked for.
    See credentials.py.
    """

    def __init__(self, existing: dict | None, parent=None):
        super().__init__(parent)
        self._existing = existing
        self.result_provider: dict | None = None

        self.result_delete = False

        self.setWindowTitle("Edit provider" if existing else "Add provider")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.type_combo = QComboBox()
        for provider_id, label in CURATED_PROVIDERS:
            self.type_combo.addItem(label, provider_id)
        self.custom_type_edit = QLineEdit()
        self.custom_type_edit.setPlaceholderText("LiteLLM provider prefix, e.g. deepseek")

        if existing:
            # The type can't change after creation -- the provider's id is
            # derived from it (used as the keyring username and the key models
            # reference it by).
            self.type_combo.setEnabled(False)
            idx = self.type_combo.findData(existing["id"])
            if idx < 0:
                idx = self.type_combo.findData("other")
                self.custom_type_edit.setText(existing["id"])
                self.custom_type_edit.setEnabled(False)
            self.type_combo.setCurrentIndex(idx)

        form.addRow("Provider:", self.type_combo)
        form.addRow("Custom type:", self.custom_type_edit)

        self.display_name_edit = QLineEdit(existing["display_name"] if existing else "")
        form.addRow("Display name:", self.display_name_edit)

        self.key_edit = QLineEdit()
        self.key_edit.setEchoMode(QLineEdit.Password)
        if existing:
            current_key = get_api_key(existing["id"])
            if current_key:
                self.key_edit.setText(current_key)
        self.toggle_key_button = QPushButton("\U0001F441")  # eye emoji
        self.toggle_key_button.setFixedWidth(32)
        self.toggle_key_button.setCheckable(True)
        self.toggle_key_button.setToolTip("Show/hide API key")
        self.toggle_key_button.toggled.connect(self._on_toggle_key_visibility)
        key_row = QHBoxLayout()
        key_row.addWidget(self.key_edit)
        key_row.addWidget(self.toggle_key_button)
        form.addRow("API key:", key_row)

        self.base_url_edit = QLineEdit((existing or {}).get("base_url") or "")
        form.addRow("Base URL:", self.base_url_edit)

        self.detect_button = QPushButton("Detect installed models (Ollama)")
        self.detect_button.clicked.connect(self._on_detect)
        form.addRow("", self.detect_button)

        self.type_combo.currentIndexChanged.connect(self._on_type_changed)
        self._on_type_changed()

        buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        if existing:
            delete_button = buttons.addButton("Delete provider", QDialogButtonBox.DestructiveRole)
            delete_button.clicked.connect(self._on_delete)
        buttons.accepted.connect(self._on_save)
        buttons.rejected.connect(self.reject)
        form.addRow(buttons)

    def _on_delete(self):
        self.result_delete = True
        self.accept()

    def _on_toggle_key_visibility(self, checked: bool):
        self.key_edit.setEchoMode(QLineEdit.Normal if checked else QLineEdit.Password)

    def _current_provider_type(self) -> str:
        provider_id = self.type_combo.currentData()
        if provider_id == "other":
            return self.custom_type_edit.text().strip()
        return provider_id

    def _on_type_changed(self):
        provider_id = self.type_combo.currentData()
        self.custom_type_edit.setVisible(provider_id == "other")
        requires_url = provider_id in PROVIDERS_REQUIRING_BASE_URL
        self.detect_button.setVisible(provider_id == "ollama")
        if provider_id == "ollama":
            # A placeholder hint only -- never auto-filled as real text, so it
            # disappears the instant the user types their own value, and an
            # empty field still falls back to this default on save (see _on_save).
            self.base_url_edit.setPlaceholderText(f"default: {DEFAULT_OLLAMA_BASE_URL}")
        elif requires_url:
            self.base_url_edit.setPlaceholderText("required")
        else:
            self.base_url_edit.setPlaceholderText("optional")

    def _on_detect(self):
        base_url = self.base_url_edit.text().strip() or DEFAULT_OLLAMA_BASE_URL
        QApplication.setOverrideCursor(Qt.WaitCursor)
        try:
            models = probe_ollama(base_url)
        except Exception as exc:
            QApplication.restoreOverrideCursor()
            QMessageBox.warning(
                self, "Detect failed", f"Could not reach Ollama at {base_url}:\n{exc}"
            )
            return
        QApplication.restoreOverrideCursor()
        if models:
            QMessageBox.information(
                self, "Detect", f"Found {len(models)} installed model(s):\n" + "\n".join(models)
            )
        else:
            QMessageBox.information(self, "Detect", "Reached Ollama, but no models are installed.")

    def _on_save(self):
        provider_type = self._current_provider_type()
        if not provider_type:
            QMessageBox.warning(
                self, "Provider required", "Pick a provider, or enter a custom provider type."
            )
            return

        base_url = self.base_url_edit.text().strip() or None
        if provider_type == "ollama" and not base_url:
            base_url = DEFAULT_OLLAMA_BASE_URL
        elif provider_type in PROVIDERS_REQUIRING_BASE_URL and not base_url:
            QMessageBox.warning(self, "Base URL required", f"{provider_type} needs a base URL.")
            return

        display_name = (
            self.display_name_edit.text().strip() or _LABELS_BY_ID.get(provider_type, provider_type)
        )
        key = self.key_edit.text().strip()

        if key:
            set_api_key(provider_type, key)
        elif self._existing is not None:
            delete_api_key(provider_type)

        self.result_provider = {"id": provider_type, "display_name": display_name, "base_url": base_url}
        self.accept()


class ModelDialog(QDialog):
    """Add dialog for one provider+model pairing. Save runs a real connection
    test (multimodal/testing.py) off the main thread and only accepts the
    dialog if it passes -- per this project's own gating design, "passes"
    means the text call succeeded, not that a (possibly quiet) test audio
    clip produced non-empty text.
    """

    _test_finished = Signal(object)  # TestResult

    def __init__(self, providers: list[dict], parent=None):
        super().__init__(parent)
        self._providers = providers
        self._pending = None
        self._closed = False
        self.result_model: dict | None = None
        self._test_finished.connect(self._on_test_finished)

        self.setWindowTitle("Add model")
        self.setMinimumWidth(420)
        form = QFormLayout(self)

        self.provider_combo = QComboBox()
        for provider in providers:
            self.provider_combo.addItem(provider["display_name"], provider["id"])
        self.provider_combo.currentIndexChanged.connect(self._refresh_model_options)
        form.addRow("Provider:", self.provider_combo)

        self.model_combo = QComboBox()
        self.model_combo.setEditable(True)
        form.addRow("Model:", self.model_combo)
        form.addRow("", QLabel("Pick from the list if one is shown, or type a model id."))

        self.display_name_edit = QLineEdit()
        form.addRow("Display name:", self.display_name_edit)

        self.status_label = QLabel("")
        self.status_label.setTextInteractionFlags(Qt.TextSelectableByMouse)
        # Without word-wrap, a real litellm failure message (often a full sentence
        # or more -- auth errors, "model not found" with the attempted model name,
        # etc.) got clipped by the dialog's fixed width instead of shown in full,
        # which is exactly the "got an error but can't see it" report this fixes.
        self.status_label.setWordWrap(True)
        form.addRow("", self.status_label)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 0)  # indeterminate/busy mode -- no known duration to show
        self.progress_bar.setVisible(False)
        form.addRow("", self.progress_bar)

        self.buttons = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        self.save_button = self.buttons.button(QDialogButtonBox.Save)
        self.save_button.setText("Test && Save")
        self.buttons.accepted.connect(self._on_save_clicked)
        self.buttons.rejected.connect(self.reject)
        form.addRow(self.buttons)

        self._refresh_model_options()

    def _current_provider(self) -> dict:
        provider_id = self.provider_combo.currentData()
        return next(p for p in self._providers if p["id"] == provider_id)

    def _refresh_model_options(self):
        provider = self._current_provider()
        self.model_combo.clear()

        if provider["id"] == "ollama":
            try:
                models = probe_ollama(provider.get("base_url") or DEFAULT_OLLAMA_BASE_URL)
            except Exception:
                models = []
        else:
            models = list_models_for_provider(provider["id"]) or []

        self.model_combo.addItems(models)
        self.model_combo.setCurrentText("")

    def _on_save_clicked(self):
        provider = self._current_provider()
        model = self.model_combo.currentText().strip()
        if not model:
            QMessageBox.warning(self, "Model required", "Pick a model, or type a model id.")
            return

        api_key = get_api_key(provider["id"])
        base_url = provider.get("base_url")

        provider_id = provider["id"]
        actual_model = model
        if provider_id == "ollama" or (base_url and "11434" in str(base_url)):
            if not actual_model.startswith("ollama/"):
                actual_model = f"ollama/{actual_model}"
        elif provider_id and provider_id not in ("other",) and "/" not in actual_model and not actual_model.startswith(f"{provider_id}/"):
            actual_model = f"{provider_id}/{actual_model}"

        self._pending = (provider, actual_model, model)

        self._set_busy(True)
        self._set_status(
            f"Testing connection (this can take up to ~{2 * TIMEOUT_SECONDS}s -- "
            "a text call, then an audio call)..."
        )

        def worker():
            result = test_provider_model(actual_model, api_key, base_url, provider_id=provider_id)
            self._test_finished.emit(result)

        threading.Thread(target=worker, daemon=True).start()

    def _set_status(self, text: str, error: bool = False):
        # This dialog is its own top-level window, so the app's stylesheet never reaches
        # it -- it paints with the system palette. The fixed palette(mid) grey used before
        # sat almost exactly on a dark dialog's background and made errors unreadable.
        # Colours are picked against whichever palette is actually in use.
        if error:
            dark = self.palette().color(QPalette.Window).lightness() < 128
            color = "#ff8b8b" if dark else "#b3261e"
        else:
            color = "palette(window-text)"
        self.status_label.setStyleSheet(f"color: {color};")
        self.status_label.setText(text)

    def _set_busy(self, busy: bool):
        self.progress_bar.setVisible(busy)
        self.save_button.setEnabled(not busy)
        self.provider_combo.setEnabled(not busy)
        self.model_combo.setEnabled(not busy)
        self.display_name_edit.setEnabled(not busy)
        if busy:
            QApplication.setOverrideCursor(Qt.WaitCursor)
        else:
            QApplication.restoreOverrideCursor()

    def reject(self):
        # A background test may still be running -- make sure the wait cursor
        # this dialog set never outlives it, and ignore a test result that
        # arrives after the user already cancelled.
        if self.progress_bar.isVisible():
            QApplication.restoreOverrideCursor()
        self._closed = True
        super().reject()

    def _on_test_finished(self, result):
        if self._closed:
            return
        self._set_busy(False)
        if not result.passed:
            self._set_status(f"Test failed. {result.detail}", error=True)
            return

        provider, actual_model, raw_model = self._pending
        display_name = self.display_name_edit.text().strip() or raw_model
        self.result_model = {
            "id": f"{provider['id']}::{actual_model}",
            "provider_id": provider["id"],
            "model": actual_model,
            "display_name": display_name,
            "supports_audio": result.audio_ok,
            "audio_status": result.audio_status,
            "last_tested": datetime.now().isoformat(timespec="seconds"),
            "test_passed": True,
        }
        if result.audio_status == AUDIO_DECLARED:
            self.status_label.setText(
                "Test passed. The audio check could not reach the provider, so audio "
                "support was taken from litellm's catalog -- re-add the model if audio "
                "dictation then fails."
            )
        elif result.audio_status == AUDIO_UNKNOWN:
            self.status_label.setText(
                "Test passed, but audio support could not be confirmed. Saved as text-only."
            )
        else:
            self.status_label.setText("Test passed.")
        self.accept()


class EnginesSubTab(QWidget):
    """Sub-tab for viewing and managing on-device speech recognition engines."""

    activate_requested = Signal(str)  # engine_id
    delete_requested = Signal(str)  # engine_id
    model_size_changed = Signal(str)  # whisper only

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_engine = "whisper"
        self._busy = False
        self._model_size = load_config().get("model_size", "base")
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
        title = QLabel("Installed models")
        title.setObjectName("TableCardHeaderTitle")
        header_layout.addWidget(title)
        header_layout.addStretch()
        one_active_note = QLabel("One active at a time")
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
        for text, width in (("SIZE", 114), ("LANGUAGES", 104), ("STATUS", 194)):
            col_label = QLabel(text)
            col_label.setObjectName("ColumnHeaderLabel")
            col_label.setFixedWidth(width)
            if text == "STATUS":
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
            "Downloads are resumable and verified. Deleting the active model switches back to Whisper."
        )
        footer_note.setObjectName("TableCardFooterNote")
        footer_layout.addWidget(footer_note)
        footer_layout.addStretch()
        self.disk_label = QLabel()
        self.disk_label.setObjectName("DiskUsageLabel")
        footer_layout.addWidget(self.disk_label)
        outer.addWidget(footer)

        self.refresh(self._active_engine, self._busy)

    def refresh(self, active_engine: str, busy: bool):
        self._active_engine = active_engine
        self._busy = busy
        while self.list_container.count():
            item = self.list_container.takeAt(0)
            widget = item.widget()
            if widget:
                # setParent(None) detaches (and hides) it immediately;
                # deleteLater() alone leaves it as a visible, un-laid-out
                # child until the event loop's next turn, which paints as
                # stale rows overlapping the freshly built ones whenever
                # refresh() is called twice back-to-back.
                widget.setParent(None)
                widget.deleteLater()

        for engine_id in asr_catalog.ENGINE_ORDER:
            meta = asr_catalog.ENGINES[engine_id]
            row = EngineTableRow(
                engine_id,
                meta,
                is_active=(engine_id == active_engine),
                downloaded=asr_catalog.is_downloaded(engine_id),
                busy=busy,
                current_model_size=self._model_size,
            )
            row.activate_requested.connect(self.activate_requested.emit)
            row.delete_requested.connect(self.delete_requested.emit)
            row.model_size_changed.connect(self._on_model_size_changed)
            self.list_container.addWidget(row)

        self.disk_label.setText(f"{asr_catalog.disk_usage_bytes() / (1024 ** 3):.2f} GB on disk")

    def _on_model_size_changed(self, size: str):
        self._model_size = size
        self.model_size_changed.emit(size)

    def confirm_and_request_delete(self, engine_id: str, is_active: bool) -> bool:
        meta = asr_catalog.ENGINES[engine_id]
        directory = asr_catalog.model_dir(engine_id)
        message = (
            f"Delete {meta['label']} ({meta['size_label']} from {directory})?\n\n"
            "This permanently deletes the downloaded files, bypassing the Recycle Bin."
        )
        if is_active:
            message += "\n\nThis is your active engine -- Infinisper will switch to Whisper."
        reply = QMessageBox.question(
            self,
            "Delete model",
            message,
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        return reply == QMessageBox.Yes


class ProvidersSubTab(QWidget):
    """Card widget for managing multimodal provider configurations."""

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
                # setParent(None) detaches (and hides) it immediately;
                # deleteLater() alone leaves it as a visible, un-laid-out
                # child until the event loop's next turn, which paints as
                # stale rows overlapping the freshly built ones whenever
                # refresh() is called twice back-to-back.
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
        if dialog.exec() != QDialog.Accepted:
            return
        if dialog.result_delete:
            self._confirm_and_delete(provider_id)
        else:
            self._models_tab.save_provider(dialog.result_provider)

    def _confirm_and_delete(self, provider_id: str):
        used_by = [
            m["display_name"] for m in self._models_tab.models() if m["provider_id"] == provider_id
        ]
        message = "Delete this provider and its stored API key?"
        if used_by:
            message += "\n\nThis also removes the model(s) that depend on it: " + ", ".join(used_by)
        reply = QMessageBox.question(
            self, "Delete provider", message, QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.Yes:
            self._models_tab.delete_provider(provider_id)


class ModelsSubTab(QWidget):
    """Card widget for managing multimodal models."""

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
                # setParent(None) detaches (and hides) it immediately;
                # deleteLater() alone leaves it as a visible, un-laid-out
                # child until the event loop's next turn, which paints as
                # stale rows overlapping the freshly built ones whenever
                # refresh() is called twice back-to-back.
                widget.setParent(None)
                widget.deleteLater()

        active_id = load_config().get("active_multimodal_model_id")
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
            self,
            "Delete model",
            "Remove this model from Multimodal Models?",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._models_tab.delete_model(model_id)

    def _on_activate(self, model_id: str):
        self._models_tab.activate_model(model_id)


class ModelsTab(QWidget):
    """Models & providers tab for configuring speech recognition engines and multimodal models."""

    changed = Signal()  # providers/models/active-model changed -- app.py refreshes its runtime cache
    activate_engine_requested = Signal(str)  # engine_id
    delete_engine_requested = Signal(str)  # engine_id
    whisper_model_size_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("ModelsPage")
        self.setAttribute(Qt.WA_StyledBackground, True)

        self.engines_subtab = EnginesSubTab(self)
        self.engines_subtab.activate_requested.connect(self.activate_engine_requested.emit)
        self.engines_subtab.delete_requested.connect(self.delete_engine_requested.emit)
        self.engines_subtab.model_size_changed.connect(self.whisper_model_size_changed.emit)

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
            "Two independent subsystems — speech recognition on device, multimodal through a provider."
        )
        hint.setObjectName("PageHint")
        header_layout.addWidget(hint)
        header_layout.addStretch()
        self.disk_total_label = QLabel()
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
                "On-device models shipped with Infinisper. Nothing downloads without a click.",
            )
        )
        section1.addWidget(self.engines_subtab)
        content_layout.addLayout(section1)

        section2 = QVBoxLayout()
        section2.setSpacing(12)
        section2.addLayout(
            self._section_heading(
                "2  Multimodal", "Add a provider first, then the models you want to use from it."
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
        self.disk_total_label.setText(f"on disk {asr_catalog.disk_usage_bytes() / (1024 ** 3):.2f} GB")

    def confirm_and_request_delete_engine(self, engine_id: str, is_active: bool) -> bool:
        return self.engines_subtab.confirm_and_request_delete(engine_id, is_active)

    def providers(self) -> list[dict]:
        return load_config()["multimodal_providers"]

    def models(self) -> list[dict]:
        return load_config()["multimodal_models"]

    def provider_display_name(self, provider_id: str) -> str:
        for provider in self.providers():
            if provider["id"] == provider_id:
                return provider["display_name"]
        return provider_id

    def save_provider(self, provider: dict):
        config = load_config()
        others = [p for p in config["multimodal_providers"] if p["id"] != provider["id"]]
        config["multimodal_providers"] = others + [provider]
        save_config(config)
        self._after_change()

    def delete_provider(self, provider_id: str):
        config = load_config()
        config["multimodal_providers"] = [
            p for p in config["multimodal_providers"] if p["id"] != provider_id
        ]
        remaining_models = [
            m for m in config["multimodal_models"] if m["provider_id"] != provider_id
        ]
        config["multimodal_models"] = remaining_models
        if config.get("active_multimodal_model_id") not in {m["id"] for m in remaining_models}:
            config["active_multimodal_model_id"] = None
        delete_api_key(provider_id)
        save_config(config)
        self._after_change()

    def activate_model(self, model_id: str):
        config = load_config()
        config["active_multimodal_model_id"] = model_id
        save_config(config)
        self._after_change()

    def save_model(self, model_entry: dict):
        config = load_config()
        others = [m for m in config["multimodal_models"] if m["id"] != model_entry["id"]]
        config["multimodal_models"] = others + [model_entry]
        save_config(config)
        self._after_change()

    def delete_model(self, model_id: str):
        config = load_config()
        config["multimodal_models"] = [m for m in config["multimodal_models"] if m["id"] != model_id]
        if config.get("active_multimodal_model_id") == model_id:
            config["active_multimodal_model_id"] = None
        save_config(config)
        self._after_change()

    def rename_model(self, model_id: str, new_display_name: str):
        config = load_config()
        for model_entry in config["multimodal_models"]:
            if model_entry["id"] == model_id:
                model_entry["display_name"] = new_display_name
                break
        save_config(config)
        self._after_change()

    def _after_change(self):
        self.providers_subtab.refresh()
        self.models_subtab.refresh()
        self.changed.emit()
