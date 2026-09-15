from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QComboBox, QHBoxLayout, QLabel, QPushButton, QVBoxLayout, QWidget

from ui.widgets.info_button import InfoButton

MODEL_SIZES = ["tiny", "base", "small", "medium"]


class EngineTableRow(QWidget):
    """One row of the ASR engine table on Models & providers: Model / Size /
    Languages / Status, matching the design mockup's single combined Status
    column (a status pill plus whatever action buttons apply, right-aligned)
    rather than a separate Actions column.

    Built fresh on every refresh() call by the owning sub-tab rather than
    mutated in place -- this project's own dashboard work this session hit
    real, repeated cases where updating an existing widget's stylesheet or
    text at runtime did not reliably repaint; a freshly constructed widget
    always paints correctly, so that's the pattern here too.
    """

    activate_requested = Signal(str)  # engine_id
    delete_requested = Signal(str)  # engine_id
    model_size_changed = Signal(str)  # whisper only

    def __init__(
        self,
        engine_id: str,
        meta: dict,
        *,
        is_active: bool,
        downloaded: bool,
        busy: bool,
        current_model_size: str,
        parent=None,
    ):
        super().__init__(parent)
        self.engine_id = engine_id
        self.setObjectName("EngineTableRowActive" if is_active else "EngineTableRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 13, 18, 13)
        layout.setSpacing(16)

        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)
        # Plain text + a bold QFont, not "<b>...</b>" rich text: a QLabel with rich-text
        # content renders through an internal QTextDocument that uses QPalette colors
        # instead of the QSS `color` property, so it silently ignores the app's theme
        # (this codebase hit that exact bug -- it read fine in dark mode by coincidence
        # and was invisible in light mode).
        name_label = QLabel(meta["label"])
        name_label.setObjectName("ListRowTitle")
        bold_font = name_label.font()
        bold_font.setBold(True)
        name_label.setFont(bold_font)
        name_row.addWidget(name_label)
        name_row.addWidget(InfoButton(meta["info_html"]))
        name_row.addStretch()
        name_col.addLayout(name_row)
        sub_label = QLabel(meta["subtitle"])
        sub_label.setObjectName("MutedValueLabel")
        name_col.addWidget(sub_label)
        layout.addLayout(name_col, 1)

        size_widget = QWidget()
        size_widget.setFixedWidth(114)
        size_layout = QVBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        if engine_id == "whisper":
            size_combo = QComboBox()
            size_combo.setObjectName("SizeCombo")
            size_combo.addItems(MODEL_SIZES)
            if current_model_size in MODEL_SIZES:
                size_combo.setCurrentText(current_model_size)
            size_combo.setEnabled(not busy)
            size_combo.currentTextChanged.connect(self.model_size_changed.emit)
            size_layout.addWidget(size_combo)
        else:
            size_label = QLabel(meta["size_label"] or "bundled")
            size_label.setObjectName("MonoValueLabel")
            size_layout.addWidget(size_label)
        layout.addWidget(size_widget)

        lang_label = QLabel(meta["languages"])
        lang_label.setObjectName("MutedValueLabel")
        lang_label.setFixedWidth(104)
        lang_label.setWordWrap(True)
        layout.addWidget(lang_label)

        status = QWidget()
        status.setFixedWidth(194)
        status_layout = QHBoxLayout(status)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(7)
        status_layout.addStretch()

        if is_active:
            pill = QLabel("Loading..." if busy else "Active")
            pill.setObjectName("StatusActivePill")
            status_layout.addWidget(pill)
            if meta["deletable"]:
                delete_button = QPushButton("Delete")
                delete_button.setObjectName("DangerPillButton")
                delete_button.setEnabled(not busy)
                delete_button.clicked.connect(lambda: self.delete_requested.emit(engine_id))
                status_layout.addWidget(delete_button)
        else:
            activate_button = QPushButton("Activate")
            activate_button.setObjectName("PillButton")
            activate_button.setEnabled(not busy)
            activate_button.clicked.connect(lambda: self.activate_requested.emit(engine_id))
            status_layout.addWidget(activate_button)
            if not meta["deletable"]:
                badge = QLabel("Bundled")
                badge.setObjectName("BundledBadge")
                status_layout.addWidget(badge)
            elif downloaded:
                delete_button = QPushButton("Delete")
                delete_button.setObjectName("DangerPillButton")
                delete_button.setEnabled(not busy)
                delete_button.clicked.connect(lambda: self.delete_requested.emit(engine_id))
                status_layout.addWidget(delete_button)

        layout.addWidget(status)
