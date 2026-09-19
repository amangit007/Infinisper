import numpy as np

import config
import languages
from cleanup import engine as cleanup_engine
from cleanup.prompts import (
    language_guidance_rule,
    translation_rule,
)


def test_language_names_and_lookup():
    assert languages.get_language_name("en") == "English"
    assert languages.get_language_name("hi") == "Hindi"
    assert languages.get_language_name("auto") == "Auto-detect"
    assert languages.get_language_name("xyz") == "xyz"
    assert len(languages.LANGUAGE_NAMES) >= 95
    assert len(languages.PRIMARY_DICTATION_LANGUAGES) >= 95
    assert len(languages.TRANSLATION_TARGET_LANGUAGES) >= 95


def test_language_guidance_rule():
    # Audio guidance
    rule_en_audio = language_guidance_rule("en", is_audio=True)
    assert "The speaker is speaking in English (en)" in rule_en_audio
    assert "Transcribe strictly in English" in rule_en_audio

    # Text guidance
    rule_hi_text = language_guidance_rule("hi", is_audio=False)
    assert "The input text is in Hindi (hi)" in rule_hi_text
    assert "Clean up and polish the text strictly in Hindi" in rule_hi_text

    # Auto and None should return empty string
    assert language_guidance_rule("auto", is_audio=True) == ""
    assert language_guidance_rule(None, is_audio=True) == ""


def test_translation_rule():
    rule_es = translation_rule("es")
    assert "translate the dictated content entirely into Spanish" in rule_es
    assert "Output ONLY the translated text in Spanish" in rule_es


def test_cleanup_engine_translation_audio_prompt(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here -- prompt captured")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)

    cleanup_engine.transcribe_audio_with_model(
        np.zeros(16000, dtype=np.float32),
        16000,
        model="test/model",
        output_mode="translate",
        target_language="fr",
        dictation_language="en",
        timeout_seconds=5,
    )

    system_prompt = captured["messages"][0]["content"]
    assert "translate the dictated content entirely into French" in system_prompt


def test_cleanup_engine_transliteration_audio_prompt(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here -- prompt captured")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)

    cleanup_engine.transcribe_audio_with_model(
        np.zeros(16000, dtype=np.float32),
        16000,
        model="test/model",
        output_mode="transliterate",
        dictation_language="hi",
        timeout_seconds=5,
    )

    system_prompt = captured["messages"][0]["content"]
    assert "The speaker is speaking in Hindi (hi)" in system_prompt
    assert "write every non-English word using English (Latin) letters" in system_prompt


def test_cleanup_engine_refine_text_translation(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here -- prompt captured")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)

    cleanup_engine.refine_text_with_model(
        "Bonjour tout le monde",
        model="test/model",
        output_mode="translate",
        target_language="en",
        timeout_seconds=5,
    )

    system_prompt = captured["messages"][0]["content"]
    assert "translate the dictated content entirely into English" in system_prompt


def test_config_migration_and_defaults(tmp_path, monkeypatch):
    fake_config_file = tmp_path / "config.json"
    monkeypatch.setattr(config, "CONFIG_PATH", fake_config_file)

    # 1. Default config load
    cfg = config.load_config()
    assert cfg["cleanup_output_mode"] == "original"
    assert cfg["translation_target_language"] == "en"
    assert cfg["force_english_transliteration"] is False

    # 2. Migration from legacy force_english_transliteration
    import json
    with open(fake_config_file, "w", encoding="utf-8") as f:
        json.dump({"force_english_transliteration": True}, f)

    migrated_cfg = config.load_config()
    assert migrated_cfg["cleanup_output_mode"] == "transliterate"
    assert migrated_cfg["force_english_transliteration"] is True
