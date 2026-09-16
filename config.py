import json
from pathlib import Path

CONFIG_PATH = Path(__file__).parent / "config.json"

DEFAULT_CONFIG = {
    "model_size": "base",
    "input_device": None,  # None = system default
    "use_asr": True,
    "asr_engine": "whisper",  # "whisper" | "qwen3" | "nemotron"
    "use_multimodal": False,
    "multimodal_level": "basic",  # "basic" | "advanced"
    "multimodal_timeout_seconds": 60,
    "fallback_to_whisper": True,
    "force_english_transliteration": False,
    "dictation_language": "en",  # "en", "auto", "hi", "es", "fr", "de", "ja", "zh"
    "custom_words": [],
    "multimodal_providers": [],  # [{"id", "base_url"}]
    "multimodal_models": [],  # [{"id", "provider_id", "model", "display_name",
    #                             "supports_audio", "last_tested", "test_passed"}]
    "active_multimodal_model_id": None,
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return dict(DEFAULT_CONFIG)
    try:
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return dict(DEFAULT_CONFIG)

    config = dict(DEFAULT_CONFIG)
    config.update({k: v for k, v in data.items() if k in DEFAULT_CONFIG})
    return config


def save_config(config: dict):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)
