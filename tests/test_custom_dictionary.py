import numpy as np
import pytest

from config import DEFAULT_CONFIG
from dictation import controller as controller_module
from dictation.controller import SettingsController
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings
from cleanup import engine as cleanup_engine
from cleanup.prompts import (
    CLEANUP_PROMPT_BASIC,
    TRANSCRIBE_PROMPT_BASIC,
    custom_dictionary_rule,
)

WORDS = ["Kubernetes", "Nemotron", "Aman", "OKR"]


# --- the rule itself -------------------------------------------------------------


def test_no_dictionary_adds_nothing_to_the_prompt():
    assert custom_dictionary_rule([]) == ""
    assert custom_dictionary_rule(None or []) == ""


def test_every_term_reaches_the_prompt():
    rule = custom_dictionary_rule(WORDS)
    for word in WORDS:
        assert word in rule


def test_the_rule_tells_the_model_not_to_insert_unspoken_terms():
    """Naming words in a prompt makes a model want to use them. Inserting a term the
    speaker never said is worse than mis-spelling one they did."""
    rule = custom_dictionary_rule(WORDS).lower()
    assert "never insert" in rule
    assert "did not say" in rule


def test_the_rule_appends_cleanly_to_both_prompt_families():
    for base in (TRANSCRIBE_PROMPT_BASIC, CLEANUP_PROMPT_BASIC):
        combined = base + custom_dictionary_rule(WORDS)
        assert combined.startswith(base)
        assert "Kubernetes" in combined


# --- config plumbing -------------------------------------------------------------


def test_custom_words_is_a_real_config_key():
    assert DEFAULT_CONFIG["custom_words"] == []


def test_saving_from_the_ui_persists_and_takes_effect_immediately(monkeypatch):
    """The Language tab emits a list; the controller must both write it to config.json and
    update the live settings the next take will read."""
    saved = {}
    monkeypatch.setattr(controller_module, "load_config", lambda: dict(DEFAULT_CONFIG))
    monkeypatch.setattr(controller_module, "save_config", lambda cfg: saved.update(cfg))
    pipeline = Pipeline(Settings(), Runtime())

    SettingsController(pipeline, None, None).apply_custom_words(["Kubernetes", "Nemotron"])

    assert saved["custom_words"] == ["Kubernetes", "Nemotron"]
    assert pipeline.settings.custom_words == ["Kubernetes", "Nemotron"]


def test_saving_an_empty_dictionary_clears_it(monkeypatch):
    saved = {}
    monkeypatch.setattr(controller_module, "load_config", lambda: dict(DEFAULT_CONFIG, custom_words=["old"]))
    monkeypatch.setattr(controller_module, "save_config", lambda cfg: saved.update(cfg))
    pipeline = Pipeline(Settings(custom_words=["old"]), Runtime())

    SettingsController(pipeline, None, None).apply_custom_words([])

    assert saved["custom_words"] == []
    assert pipeline.settings.custom_words == []


# --- Whisper hotwords ------------------------------------------------------------


class FakeSegment:
    def __init__(self, text):
        self.text = text


class FakeInfo:
    language = "en"
    language_probability = 0.99


class FakeWhisper:
    """Records the kwargs it was called with, so the test can assert on what the app
    actually asked faster-whisper for."""

    def __init__(self):
        self.kwargs = None

    def transcribe(self, audio, **kwargs):
        self.kwargs = kwargs
        return [FakeSegment("transcribed text")], FakeInfo()


class WhisperHarness:
    """A pipeline whose Whisper is the fake, plus a way to run it."""

    def __init__(self):
        self.model = FakeWhisper()
        self.settings = Settings(dictation_language="en")
        self.pipeline = Pipeline(self.settings, Runtime(whisper=self.model))

    @property
    def kwargs(self):
        return self.model.kwargs

    def run(self):
        self.pipeline.run_whisper(np.zeros(16000, dtype=np.float32))


@pytest.fixture
def whisper():
    return WhisperHarness()


def test_custom_words_are_passed_to_whisper_as_hotwords(whisper):
    whisper.settings.custom_words = WORDS
    whisper.run()
    assert whisper.kwargs["hotwords"] == "Kubernetes Nemotron Aman OKR"


def test_an_empty_dictionary_sends_no_hotwords(whisper):
    """faster-whisper treats an empty string differently from None; it must get None."""
    whisper.run()
    assert whisper.kwargs["hotwords"] is None


def test_whisper_no_longer_runs_its_own_vad(whisper):
    """audio.vad already trimmed the take with these exact parameters. Doing it again
    inside faster-whisper would just re-pay the cost."""
    whisper.run()
    assert whisper.kwargs["vad_filter"] is False


def test_auto_language_is_sent_as_none(whisper):
    whisper.settings.dictation_language = "auto"
    whisper.run()
    assert whisper.kwargs["language"] is None


# --- AI cleanup plumbing ---------------------------------------------------------


def test_cleanup_text_cleanup_sends_the_dictionary(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here -- the prompt is all this test needs")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)
    cleanup_engine.refine_text_with_model(
        "some dictated text", model="test/model", custom_words=WORDS, timeout_seconds=5
    )

    system_prompt = captured["messages"][0]["content"]
    assert "Kubernetes" in system_prompt


def test_cleanup_cleanup_without_a_dictionary_is_unchanged(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)
    cleanup_engine.refine_text_with_model(
        "some dictated text", model="test/model", custom_words=[], timeout_seconds=5
    )

    assert captured["messages"][0]["content"] == CLEANUP_PROMPT_BASIC


def test_cleanup_audio_transcribe_sends_the_dictionary(monkeypatch):
    captured = {}

    def fake_completion(**kwargs):
        captured.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr(cleanup_engine.litellm, "completion", fake_completion)
    cleanup_engine.transcribe_audio_with_model(
        np.zeros(16000, dtype=np.float32),
        16000,
        model="test/model",
        custom_words=WORDS,
        timeout_seconds=5,
    )

    assert "Nemotron" in captured["messages"][0]["content"]
