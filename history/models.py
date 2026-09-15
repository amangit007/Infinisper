from dataclasses import dataclass, field

# error: the pipeline raised/reported a hard error, nothing was pasted
OUTCOMES = ("pasted", "skipped_short", "skipped_silence", "skipped_quick", "error")


@dataclass
class HistoryEntry:
    timestamp: str  # ISO 8601
    engine: str  # e.g. "Whisper", "Qwen3", "Nemotron", "... -> Multimodal", "" for skipped/error takes
    outcome: str  # one of OUTCOMES
    total_ms: float
    steps: list[tuple[str, float]] = field(default_factory=list)  # [(label, elapsed_ms), ...]
    text: str = ""
    error: str = ""

    def to_dict(self) -> dict:
        return {
            "timestamp": self.timestamp,
            "engine": self.engine,
            "outcome": self.outcome,
            "total_ms": self.total_ms,
            "steps": [list(step) for step in self.steps],
            "text": self.text,
            "error": self.error,
        }

    @staticmethod
    def from_dict(data: dict) -> "HistoryEntry":
        return HistoryEntry(
            timestamp=data.get("timestamp", ""),
            engine=data.get("engine", ""),
            outcome=data.get("outcome", "error"),
            total_ms=data.get("total_ms", 0.0),
            steps=[tuple(step) for step in data.get("steps", [])],
            text=data.get("text", ""),
            error=data.get("error", ""),
        )
