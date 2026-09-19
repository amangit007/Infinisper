"""What the user asked for, and what is loaded right now.

`Settings` is the dictation loop's own copy of config.json, so a take never touches the disk.
`Runtime` is the other half: which engines are actually loaded and which microphone is open.
The two differ on purpose -- the config can say "qwen3" while Whisper is still the active
engine because Qwen3 is mid-download.

These used to be two dozen module-level globals in app.py.
"""

from dataclasses import dataclass, field
from typing import Any

from credentials import get_api_key


@dataclass
class Settings:
    use_asr: bool = True
    use_cleanup: bool = False
    cleanup_level: str = "basic"  # "basic" | "advanced"
    cleanup_timeout_seconds: int = 60
    fallback_to_whisper: bool = True
    hotkey: str = "ctrl+win"
    # None leaves Ollama's own keep-alive default alone.
    ollama_keep_alive: str | None = "30m"
    # Only applied when use_cleanup is on -- see cleanup/prompts.py's
    # ENGLISH_TRANSLITERATION_RULE and translation_rule. Set from the Language tab.
    force_english_transliteration: bool = False
    cleanup_output_mode: str = "original"  # "original" | "transliterate" | "translate"
    translation_target_language: str = "en"
    dictation_language: str = "en"
    # Names, acronyms and jargon the speaker uses that a general model mishears. Boosted
    # in Whisper's decoder via hotwords= and named to the AI model in its prompt.
    # Qwen3 and Nemotron are not covered: sherpa-onnx can bias a transducer, but only with
    # a BPE model file that neither of those exports ships.
    custom_words: list[str] = field(default_factory=list)
    # Cache of config.json's cleanup_* fields. Refreshed whenever the Models & providers
    # tab changes something or the Dashboard's Active model selection is saved.
    cleanup_providers: list[dict] = field(default_factory=list)
    cleanup_models: list[dict] = field(default_factory=list)
    active_cleanup_model_id: str | None = None

    @classmethod
    def from_config(cls, config: dict) -> "Settings":
        return cls(
            use_asr=config["use_asr"],
            use_cleanup=config["use_cleanup"],
            cleanup_level=config["cleanup_level"],
            cleanup_timeout_seconds=config["cleanup_timeout_seconds"],
            fallback_to_whisper=config["fallback_to_whisper"],
            hotkey=config.get("hotkey", "ctrl+win"),
            ollama_keep_alive=config.get("ollama_keep_alive", "30m"),
            force_english_transliteration=config["force_english_transliteration"],
            cleanup_output_mode=config.get("cleanup_output_mode", "original"),
            translation_target_language=config.get("translation_target_language", "en"),
            dictation_language=config.get("dictation_language", "en"),
            custom_words=[w.strip() for w in config.get("custom_words", []) if str(w).strip()],
            cleanup_providers=config["cleanup_providers"],
            cleanup_models=config["cleanup_models"],
            active_cleanup_model_id=config["active_cleanup_model_id"],
        )

    def apply_dashboard(self, new_config: dict) -> None:
        """Takes the fields the Dashboard's Save button owns."""
        self.use_asr = new_config["use_asr"]
        self.use_cleanup = new_config["use_cleanup"]
        self.cleanup_level = new_config["cleanup_level"]
        self.cleanup_timeout_seconds = new_config["cleanup_timeout_seconds"]
        self.fallback_to_whisper = new_config["fallback_to_whisper"]
        self.active_cleanup_model_id = new_config["active_cleanup_model_id"]
        self.hotkey = new_config.get("hotkey", "ctrl+win")
        self.ollama_keep_alive = new_config.get("ollama_keep_alive", self.ollama_keep_alive)

    def reload_cleanup_models(self, config: dict) -> None:
        """The Models & providers tab can null out active_cleanup_model_id (deleting the
        provider or model backing it), so that is re-read along with the two lists --
        otherwise this cache would keep pointing at a model that no longer exists."""
        self.cleanup_providers = config["cleanup_providers"]
        self.cleanup_models = config["cleanup_models"]
        self.active_cleanup_model_id = config["active_cleanup_model_id"]

    def resolve_active_cleanup(self) -> tuple[str, str | None, str | None, bool] | None:
        """(model, api_key, base_url, supports_audio) for the configured active AI model,
        or None if none is configured / the configured one no longer exists (its
        provider or model could have been deleted on the Models & providers tab
        since this was set active).
        """
        if not self.active_cleanup_model_id:
            return None
        model_entry = next(
            (m for m in self.cleanup_models if m["id"] == self.active_cleanup_model_id), None
        )
        if model_entry is None:
            return None
        provider_entry = next(
            (p for p in self.cleanup_providers if p["id"] == model_entry["provider_id"]), None
        )
        if provider_entry is None:
            return None
        return (
            model_entry["model"],
            get_api_key(provider_entry["id"]),
            provider_entry.get("base_url"),
            bool(model_entry.get("supports_audio", False)),
        )


@dataclass
class Runtime:
    whisper: Any = None  # faster_whisper.WhisperModel
    whisper_size: str = "base"
    qwen3: Any = None  # asr.qwen_asr.Qwen3AsrEngine
    nemotron: Any = None  # asr.nemotron_asr.NemotronAsrEngine
    active_engine: str = "whisper"  # "whisper" | "qwen3" | "nemotron" -- what's actually loaded and active
    stream_session: Any = None  # the open Nemotron streaming take, if any
    input_device: Any = None
    mic_stream: Any = None  # sounddevice.InputStream

    @classmethod
    def from_config(cls, config: dict) -> "Runtime":
        return cls(
            whisper_size=config["model_size"],
            active_engine=config["asr_engine"],
            input_device=config["input_device"],
        )
