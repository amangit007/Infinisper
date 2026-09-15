import json
from pathlib import Path

from PySide6.QtCore import QObject, Signal

from history.models import HistoryEntry

HISTORY_PATH = Path(__file__).parent.parent / "history.json"
MAX_ENTRIES = 500  # oldest dropped first -- keeps the file from growing forever


class HistoryStore(QObject):
    entry_added = Signal(object)  # HistoryEntry -- lets history_tab update live, not by polling
    entry_deleted = Signal(object)  # HistoryEntry
    cleared = Signal()

    def __init__(self):
        super().__init__()
        self._entries: list[HistoryEntry] = self._load()

    def _load(self) -> list[HistoryEntry]:
        if not HISTORY_PATH.exists():
            return []
        try:
            with open(HISTORY_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
            return [HistoryEntry.from_dict(item) for item in data]
        except Exception:
            return []

    def _save(self):
        with open(HISTORY_PATH, "w", encoding="utf-8") as f:
            json.dump([entry.to_dict() for entry in self._entries], f, indent=2)

    def entries(self) -> list[HistoryEntry]:
        """Newest first."""
        return list(reversed(self._entries))

    def append(self, entry: HistoryEntry):
        self._entries.append(entry)
        if len(self._entries) > MAX_ENTRIES:
            self._entries = self._entries[-MAX_ENTRIES:]
        self._save()
        self.entry_added.emit(entry)

    def delete_entry(self, entry: HistoryEntry):
        """Removes one entry by identity (not value equality -- two entries could
        plausibly have identical field values, e.g. two empty "no speech
        detected" takes seconds apart)."""
        for index, existing in enumerate(self._entries):
            if existing is entry:
                del self._entries[index]
                break
        else:
            return
        self._save()
        self.entry_deleted.emit(entry)

    def clear(self):
        self._entries = []
        self._save()
        self.cleared.emit()
