from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget


class ModelCard(QWidget):
    """One row in the Models list card on Models & providers. Matches the
    design mockup: name + provider/model-id detail line, an audio/text-only
    tag, and an Activate/Active pill -- plus small ghost-glyph rename/delete
    buttons the mockup doesn't show a slot for but this app still needs.
    """

    rename_requested = Signal(str)  # model id
    delete_requested = Signal(str)  # model id
    activate_requested = Signal(str)  # model id

    def __init__(self, model_entry: dict, provider_display_name: str, *, is_active: bool, parent=None):
        super().__init__(parent)
        self.model_id = model_entry["id"]
        self.setObjectName("ListRowActive" if is_active else "ListRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 13)
        layout.setSpacing(10)

        col = QVBoxLayout()
        col.setSpacing(3)
        name_label = QLabel(model_entry["display_name"])
        name_label.setObjectName("ListRowTitle")
        col.addWidget(name_label)
        detail = QLabel(f"{provider_display_name} · {model_entry['model']}")
        detail.setObjectName("ListRowMono")
        col.addWidget(detail)
        layout.addLayout(col, 1)

        supports_audio = model_entry.get("supports_audio")
        tag = QLabel("AUDIO + TEXT" if supports_audio else "TEXT ONLY")
        tag.setObjectName("TagGood" if supports_audio else "TagNeutral")
        # "declared" means the live audio probe never got an answer from the provider
        # and this came from litellm's catalog instead. Worth saying so on hover rather
        # than presenting a guess and a confirmed result identically.
        if model_entry.get("audio_status") == "declared":
            tag.setToolTip(
                "Audio support comes from litellm's model catalog -- the live check "
                "could not reach the provider when this model was added."
            )
        elif model_entry.get("audio_status") == "unknown":
            tag.setToolTip(
                "The live audio check could not reach the provider, and litellm has no "
                "capability metadata for this model. Re-add it to try the check again."
            )
        layout.addWidget(tag)

        if is_active:
            pill = QLabel("Active")
            pill.setObjectName("StatusActivePill")
            layout.addWidget(pill)
        else:
            activate_button = QPushButton("Activate")
            activate_button.setObjectName("PillButton")
            activate_button.clicked.connect(lambda: self.activate_requested.emit(self.model_id))
            layout.addWidget(activate_button)

        rename_button = QPushButton("✎")
        rename_button.setObjectName("GhostGlyphButton")
        rename_button.setFixedWidth(20)
        rename_button.setToolTip("Rename")
        rename_button.clicked.connect(lambda: self.rename_requested.emit(self.model_id))
        layout.addWidget(rename_button)

        delete_button = QPushButton("×")
        delete_button.setObjectName("DangerGhostGlyphButton")
        delete_button.setFixedWidth(20)
        delete_button.setToolTip("Delete")
        delete_button.clicked.connect(lambda: self.delete_requested.emit(self.model_id))
        layout.addWidget(delete_button)
