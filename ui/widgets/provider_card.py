from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from cleanup.catalog import CURATED_PROVIDERS

_LABELS_BY_ID = dict(CURATED_PROVIDERS)


class ProviderCard(QWidget):
    """Row widget representing a configured AI provider."""

    edit_requested = Signal(str)  # provider id

    def __init__(self, provider: dict, parent=None):
        super().__init__(parent)
        self.provider_id = provider["id"]
        self.setObjectName("ListRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 14, 18, 14)
        layout.setSpacing(12)

        col = QVBoxLayout()
        col.setSpacing(3)
        name_label = QLabel(provider["display_name"])
        name_label.setObjectName("ListRowTitle")
        col.addWidget(name_label)

        type_label = _LABELS_BY_ID.get(self.provider_id, self.provider_id)
        detail_bits = [f"{type_label}"]
        if provider.get("base_url"):
            detail_bits.append(provider["base_url"])
        else:
            detail_bits.append("key in Credential Manager")
        detail = QLabel(" · ".join(detail_bits))
        detail.setObjectName("ListRowMono")
        col.addWidget(detail)
        layout.addLayout(col, 1)

        edit_button = QPushButton("Edit")
        edit_button.setObjectName("PillButton")
        edit_button.clicked.connect(lambda: self.edit_requested.emit(self.provider_id))
        layout.addWidget(edit_button)
