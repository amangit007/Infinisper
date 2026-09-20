from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QProgressBar,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from ui.widgets.info_button import InfoButton


class EngineTableRow(QWidget):
    """Row widget representing an on-device speech recognition model in the models table."""

    activate_requested = Signal(str)  # model_id
    download_requested = Signal(str)  # model_id
    delete_requested = Signal(str)  # model_id
    cancel_requested = Signal(str)  # model_id

    def __init__(
        self,
        model_id: str,
        meta: dict,
        *,
        is_active: bool,
        downloaded: bool,
        busy: bool,
        parent=None,
    ):
        super().__init__(parent)
        self.model_id = model_id
        self.meta = meta
        self._is_active = is_active
        self._downloaded = downloaded
        self._busy = busy

        self.setObjectName("EngineTableRowActive" if is_active else "EngineTableRow")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(18, 12, 18, 12)
        layout.setSpacing(16)

        # 1. Model Name & Subtitle
        name_col = QVBoxLayout()
        name_col.setSpacing(3)
        name_row = QHBoxLayout()
        name_row.setSpacing(6)

        name_label = QLabel(meta["label"])
        name_label.setObjectName("ListRowTitle")
        bold_font = name_label.font()
        bold_font.setBold(True)
        name_label.setFont(bold_font)
        name_row.addWidget(name_label)

        if "info_html" in meta:
            name_row.addWidget(InfoButton(meta["info_html"]))
        name_row.addStretch()
        name_col.addLayout(name_row)

        sub_label = QLabel(meta.get("subtitle", ""))
        sub_label.setObjectName("MutedValueLabel")
        name_col.addWidget(sub_label)
        layout.addLayout(name_col, 1)

        # 2. Size Column
        size_widget = QWidget()
        size_widget.setFixedWidth(100)
        size_layout = QVBoxLayout(size_widget)
        size_layout.setContentsMargins(0, 0, 0, 0)
        size_label = QLabel(meta.get("size_label", "Local"))
        size_label.setObjectName("MonoValueLabel")
        size_layout.addWidget(size_label)
        layout.addWidget(size_widget)

        # 3. Languages Column
        lang_label = QLabel(meta.get("languages", "Multilingual"))
        lang_label.setObjectName("MutedValueLabel")
        lang_label.setFixedWidth(110)
        lang_label.setWordWrap(True)
        layout.addWidget(lang_label)

        # 4. Action & Status Column
        self.status_container = QWidget()
        self.status_container.setFixedWidth(260)
        self.status_layout = QHBoxLayout(self.status_container)
        self.status_layout.setContentsMargins(0, 0, 0, 0)
        self.status_layout.setSpacing(8)

        # Progress widgets (hidden initially)
        self.progress_col = QVBoxLayout()
        self.progress_col.setSpacing(3)
        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setFixedHeight(6)
        self.progress_bar.setTextVisible(False)
        self.progress_bar.setStyleSheet("""
            QProgressBar {
                background: rgba(255, 255, 255, 0.08);
                border: none;
                border-radius: 3px;
            }
            QProgressBar::chunk {
                background: #0078D4;
                border-radius: 3px;
            }
        """)
        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #94A3B8; font-size: 7.5pt; font-family: monospace;")
        self.progress_col.addWidget(self.progress_bar)
        self.progress_col.addWidget(self.progress_label)

        self.progress_widget = QWidget()
        self.progress_widget.setLayout(self.progress_col)
        self.progress_widget.setVisible(False)
        self.status_layout.addWidget(self.progress_widget, 1)

        self._render_buttons()
        layout.addWidget(self.status_container)

    def _render_buttons(self):
        # Clear existing button widgets except progress_widget
        for i in reversed(range(self.status_layout.count())):
            item = self.status_layout.itemAt(i)
            w = item.widget()
            if w and w != self.progress_widget:
                w.setParent(None)
                w.deleteLater()

        self.status_layout.insertStretch(0)

        if self._is_active:
            pill = QLabel("Loading..." if self._busy else "Active")
            pill.setObjectName("StatusActivePill")
            self.status_layout.addWidget(pill)

            if self.meta.get("deletable", True) and self._downloaded:
                delete_btn = QPushButton("Delete")
                delete_btn.setObjectName("DangerPillButton")
                delete_btn.setEnabled(not self._busy)
                delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.model_id))
                self.status_layout.addWidget(delete_btn)

        elif self._downloaded:
            activate_btn = QPushButton("Activate")
            activate_btn.setObjectName("PillButton")
            activate_btn.setEnabled(not self._busy)
            activate_btn.clicked.connect(lambda: self.activate_requested.emit(self.model_id))
            self.status_layout.addWidget(activate_btn)

            if self.meta.get("deletable", True):
                delete_btn = QPushButton("Delete")
                delete_btn.setObjectName("DangerPillButton")
                delete_btn.setEnabled(not self._busy)
                delete_btn.clicked.connect(lambda: self.delete_requested.emit(self.model_id))
                self.status_layout.addWidget(delete_btn)

        else:
            # Not downloaded
            size_str = self.meta.get("size_label", "")
            btn_text = f"Download ({size_str})" if size_str else "Download"
            download_btn = QPushButton(btn_text)
            download_btn.setObjectName("PrimaryPillButton")
            download_btn.setCursor(Qt.PointingHandCursor)
            download_btn.setEnabled(not self._busy)
            download_btn.setStyleSheet("""
                QPushButton#PrimaryPillButton {
                    background-color: #0078D4;
                    color: white;
                    border: none;
                    border-radius: 14px;
                    padding: 5px 14px;
                    font-size: 8.5pt;
                    font-weight: bold;
                }
                QPushButton#PrimaryPillButton:hover {
                    background-color: #106EBE;
                }
                QPushButton#PrimaryPillButton:disabled {
                    background-color: rgba(255, 255, 255, 0.1);
                    color: rgba(255, 255, 255, 0.3);
                }
            """)
            download_btn.clicked.connect(lambda: self.download_requested.emit(self.model_id))
            self.status_layout.addWidget(download_btn)

    def set_downloading(self, downloading: bool):
        """Toggles between progress bar display and standard button row."""
        self.progress_widget.setVisible(downloading)
        if downloading:
            # Hide action buttons while downloading
            for i in range(self.status_layout.count()):
                w = self.status_layout.itemAt(i).widget()
                if w and w != self.progress_widget:
                    w.setVisible(False)
        else:
            self._render_buttons()

    def update_progress(self, percent: float, speed_str: str, status_str: str):
        """Updates the progress bar and readout during download."""
        if not self.progress_widget.isVisible():
            self.set_downloading(True)
        self.progress_bar.setValue(int(percent))
        label_text = f"{percent:.0f}%"
        if speed_str:
            label_text += f" • {speed_str}"
        self.progress_label.setText(label_text)
