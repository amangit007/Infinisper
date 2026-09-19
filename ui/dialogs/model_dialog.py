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
    QLabel,
    QLineEdit,
    QMessageBox,
    QProgressBar,
)

from credentials import get_api_key
from cleanup.catalog import (
    DEFAULT_OLLAMA_BASE_URL,
    OLLAMA_DOWNLOAD_URL,
    list_models_for_provider,
    ollama_status,
)
from cleanup.engine import TIMEOUT_SECONDS
from cleanup.testing import AUDIO_DECLARED, AUDIO_UNKNOWN, test_provider_model
from ui.theme import DARK, LIGHT

class ModelDialog(QDialog):
    """Add dialog for one provider+model pairing. Save runs a real connection
    test (cleanup/testing.py) off the main thread and only accepts the
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

        # Says what's wrong when Ollama isn't ready. It only ever explains -- installing
        # Ollama or pulling a model is the user's call, never something this app does.
        self.ollama_note = QLabel("")
        self.ollama_note.setWordWrap(True)
        self.ollama_note.setOpenExternalLinks(True)
        self.ollama_note.setVisible(False)
        form.addRow("", self.ollama_note)

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

        note = ""
        if provider["id"] == "ollama":
            status = ollama_status(provider.get("base_url") or DEFAULT_OLLAMA_BASE_URL)
            models = status.models
            if status.problem:
                note = status.problem
                if status.show_install_link:
                    note += f' <a href="{OLLAMA_DOWNLOAD_URL}">ollama.com/download</a>'
        else:
            models = list_models_for_provider(provider["id"]) or []
        self.ollama_note.setText(note)
        self.ollama_note.setVisible(bool(note))

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
            color = (DARK if dark else LIGHT)["danger_text"]
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
