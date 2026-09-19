
from PySide6.QtCore import Qt
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QMessageBox,
    QPushButton,
)

from credentials import delete_api_key, get_api_key, set_api_key
from cleanup.catalog import (
    CURATED_PROVIDERS,
    DEFAULT_OLLAMA_BASE_URL,
    PROVIDERS_REQUIRING_BASE_URL,
    probe_ollama,
)
from ui.widgets.icon_button import IconButton

_LABELS_BY_ID = dict(CURATED_PROVIDERS)


class ProviderDialog(QDialog):
    """Add/edit dialog for one AI provider. The API key is masked by
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
        self.toggle_key_button = IconButton("eye", size=16)
        # This dialog is its own top-level window, so the app stylesheet doesn't reach it;
        # the icon takes the dialog's own text color instead.
        icon_color = self.palette().color(QPalette.WindowText)
        self.toggle_key_button.setProperty("iconColor", icon_color)
        self.toggle_key_button.setProperty("hoverIconColor", icon_color)
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
        self.toggle_key_button.set_icon_name("eye-off" if checked else "eye")

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
