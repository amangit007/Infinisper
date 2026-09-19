import copy
import json

from utils.paths import get_config_path

CONFIG_PATH = get_config_path()

DEFAULT_CONFIG = {
    "model_size": "base",
    "input_device": None,  # None = system default
    "use_asr": True,
    "asr_engine": "whisper",  # "whisper" | "qwen3" | "nemotron"
    "use_cleanup": False,
    "cleanup_level": "basic",  # "basic" | "advanced"
    "cleanup_timeout_seconds": 60,
    "fallback_to_whisper": True,
    "force_english_transliteration": False,
    "cleanup_output_mode": "original",  # "original" | "transliterate" | "translate"
    "translation_target_language": "en",  # e.g. "en", "es", "fr", "hi", etc.
    "dictation_language": "en",  # "en", "auto", or any supported ISO code
    "custom_words": [],
    "hotkey": "ctrl+win",
    # How long Ollama keeps the AI model in memory after a request: "30m", "2h", "-1"
    # (until Ollama quits) or None for Ollama's own default of 5 minutes. A model that is
    # already loaded answers in ~1 s; a cold one can take 10 s. Held memory is the cost.
    "ollama_keep_alive": "30m",
    # Ollama ships pre-configured so a user who already runs it only has to pick a model.
    # 127.0.0.1, not "localhost": on Windows "localhost" tries IPv6 first and Ollama only
    # listens on IPv4, which costs ~2 s on every new connection.
    "cleanup_providers": [
        {"id": "ollama", "display_name": "Ollama (local)", "base_url": "http://127.0.0.1:11434"}
    ],  # [{"id", "display_name", "base_url"}]
    "cleanup_models": [],  # [{"id", "provider_id", "model", "display_name",
    #                             "supports_audio", "last_tested", "test_passed"}]
    "active_cleanup_model_id": None,
}


# Keys as they were named while this step was called "Multimodal". Read from old
# config.json files and written back under the new names on the next save.
LEGACY_KEYS = {
    "use_multimodal": "use_cleanup",
    "multimodal_level": "cleanup_level",
    "multimodal_timeout_seconds": "cleanup_timeout_seconds",
    "multimodal_output_mode": "cleanup_output_mode",
    "multimodal_providers": "cleanup_providers",
    "multimodal_models": "cleanup_models",
    "active_multimodal_model_id": "active_cleanup_model_id",
}


def _migrate_legacy_keys(data: dict) -> dict:
    migrated = dict(data)
    for old, new in LEGACY_KEYS.items():
        if old in migrated:
            value = migrated.pop(old)
            migrated.setdefault(new, value)
    return migrated


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return copy.deepcopy(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = _migrate_legacy_keys(json.load(f))
    except Exception:
        return copy.deepcopy(DEFAULT_CONFIG)

    config = copy.deepcopy(DEFAULT_CONFIG)
    config.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})

    # Migration / sync: if legacy force_english_transliteration is set and output_mode wasn't saved,
    # map it to "transliterate". Keep force_english_transliteration in sync with output_mode.
    if data.get("force_english_transliteration") and "cleanup_output_mode" not in data:
        config["cleanup_output_mode"] = "transliterate"
    config["force_english_transliteration"] = (config["cleanup_output_mode"] == "transliterate")

    return config


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
