import pyperclip
from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QMessageBox,
    QPushButton,
    QTableView,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from history.models import HistoryEntry
from history.store import HistoryStore
from ui.widgets.timing_bars import TimingBarsWidget

_STATUS_LABELS = {
    "pasted": "Pasted",
    "skipped_short": "Too short",
    "skipped_silence": "No speech detected",
    "skipped_quick": "Too quick",
    "error": "Error",
}

_PREVIEW_MAX_CHARS = 80


class HistoryTableModel(QAbstractTableModel):
    HEADERS = ["Time", "Engine", "Total latency", "Result", "Status"]

    def __init__(self, entries: list[HistoryEntry], parent=None):
        super().__init__(parent)
        self._entries = entries  # newest first

    def rowCount(self, parent=QModelIndex()):
        return len(self._entries)

    def columnCount(self, parent=QModelIndex()):
        return len(self.HEADERS)

    def headerData(self, section, orientation, role=Qt.DisplayRole):
        if role == Qt.DisplayRole and orientation == Qt.Horizontal:
            return self.HEADERS[section]
        return None

    def data(self, index, role=Qt.DisplayRole):
        if role != Qt.DisplayRole or not index.isValid():
            return None
        entry = self._entries[index.row()]
        col = index.column()
        if col == 0:
            return entry.timestamp
        if col == 1:
            return entry.engine or "-"
        if col == 2:
            return f"{entry.total_ms:.0f} ms"
        if col == 3:
            preview = entry.text or entry.error or ""
            preview = preview.replace("\n", " ")
            if len(preview) > _PREVIEW_MAX_CHARS:
                preview = preview[:_PREVIEW_MAX_CHARS] + "..."
            return preview
        if col == 4:
            return _STATUS_LABELS.get(entry.outcome, entry.outcome)
        return None

    def entry_at(self, row: int) -> HistoryEntry:
        return self._entries[row]

    def set_entries(self, entries: list[HistoryEntry]):
        self.beginResetModel()
        self._entries = entries
        self.endResetModel()

    def prepend(self, entry: HistoryEntry):
        self.beginInsertRows(QModelIndex(), 0, 0)
        self._entries.insert(0, entry)
        self.endInsertRows()

    def remove_entry(self, entry: HistoryEntry) -> int:
        """Removes by identity, matching HistoryStore.delete_entry. Returns the
        removed row index, or -1 if the entry wasn't found (e.g. already gone)."""
        for row, existing in enumerate(self._entries):
            if existing is entry:
                self.beginRemoveRows(QModelIndex(), row, row)
                del self._entries[row]
                self.endRemoveRows()
                return row
        return -1


class HistoryTab(QWidget):
    """Structured, persisted replacement for the console's timing/error/text
    output -- see HistoryStore for the disk-backed data behind this."""

    def __init__(self, store: HistoryStore, parent=None):
        super().__init__(parent)
        self._store = store
        self._current_entry: HistoryEntry | None = None
        self.setObjectName("HistoryPage")
        self.setAttribute(Qt.WA_StyledBackground, True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(26, 20, 26, 26)

        self.model = HistoryTableModel(store.entries())
        self.table = QTableView()
        self.table.setModel(self.model)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.setEditTriggers(QTableView.NoEditTriggers)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setVisible(False)
        self.table.selectionModel().currentRowChanged.connect(self._on_row_changed)
        layout.addWidget(self.table, 1)

        self.detail = QTextEdit()
        self.detail.setReadOnly(True)
        self.detail.setMaximumHeight(110)
        self.detail.setPlaceholderText("Select a row to see the full text.")
        layout.addWidget(self.detail)

        self.timing_bars = TimingBarsWidget()
        layout.addWidget(self.timing_bars)

        button_row = QHBoxLayout()
        self.copy_button = QPushButton("Copy text")
        self.copy_button.setEnabled(False)
        self.copy_button.clicked.connect(self._on_copy)
        button_row.addWidget(self.copy_button)

        self.delete_button = QPushButton("Delete entry")
        self.delete_button.setEnabled(False)
        self.delete_button.clicked.connect(self._on_delete)
        button_row.addWidget(self.delete_button)

        button_row.addStretch()
        self.clear_button = QPushButton("Clear history")
        self.clear_button.clicked.connect(self._on_clear)
        button_row.addWidget(self.clear_button)
        layout.addLayout(button_row)

        store.entry_added.connect(self._on_entry_added)
        store.entry_deleted.connect(self._on_entry_deleted)
        store.cleared.connect(self._on_cleared)

    def apply_theme(self, tokens: dict):
        self.timing_bars.apply_theme(tokens)

    def _on_entry_added(self, entry: HistoryEntry):
        self.model.prepend(entry)

    def _on_entry_deleted(self, entry: HistoryEntry):
        row = self.model.remove_entry(entry)
        if row == -1:
            return
        if entry is self._current_entry:
            self._show_entry(None)

    def _on_cleared(self):
        self.model.set_entries([])
        self._show_entry(None)

    def _on_row_changed(self, current: QModelIndex, previous: QModelIndex):
        if not current.isValid():
            self._show_entry(None)
            return
        self._show_entry(self.model.entry_at(current.row()))

    def _show_entry(self, entry: HistoryEntry | None):
        self._current_entry = entry
        self.copy_button.setEnabled(entry is not None)
        self.delete_button.setEnabled(entry is not None)
        if entry is None:
            self.detail.clear()
            self.timing_bars.set_steps([])
            return
        self.detail.setPlainText(entry.text or entry.error or "(nothing)")
        self.timing_bars.set_steps(entry.steps)

    def _on_copy(self):
        if self._current_entry is None:
            return
        pyperclip.copy(self._current_entry.text or self._current_entry.error or "")

    def _on_delete(self):
        if self._current_entry is None:
            return
        reply = QMessageBox.question(
            self,
            "Delete entry",
            "Delete this history entry? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._store.delete_entry(self._current_entry)

    def _on_clear(self):
        reply = QMessageBox.question(
            self,
            "Clear history",
            "Delete all saved history entries? This cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self._store.clear()
