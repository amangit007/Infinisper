"""Covers the order the dictation pipeline runs its stages in.

The individual stages are tested in test_preprocessor / test_vad. What is easy to get
wrong -- and invisible in a unit test of any one stage -- is the wiring: which pre-roll
offset the click suppressor is told about, and whether normalisation happens before or
after the take is trimmed to speech.
"""

import numpy as np
import pytest

import app

SR = 16000


class FakeChip:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


class FakeTray:
    def __init__(self):
        self.statuses = []

    def set_status(self, text):
        self.statuses.append(text)


def speech_like(seconds=2.0, amplitude=0.05):
    t = np.arange(int(seconds * SR)) / SR
    tone = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in (1, 2, 3, 4))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 3 * t)
    return (tone * envelope * amplitude).astype(np.float32)


@pytest.fixture
def pipeline(monkeypatch):
    """Runs the real pipeline with the engine, clipboard and history stubbed out,
    recording what each stage received."""
    seen = {}

    monkeypatch.setattr(app, "_history_store", None)
    monkeypatch.setattr(app, "pyperclip", type("P", (), {
        "paste": staticmethod(lambda: ""),
        "copy": staticmethod(lambda text: None),
    }))
    monkeypatch.setattr(app, "keyboard", type("K", (), {"send": staticmethod(lambda combo: None)}))
    monkeypatch.setattr(app, "_use_asr", True)
    monkeypatch.setattr(app, "_use_multimodal", False)

    real_clean = app.audio_preprocessor.clean_speech_audio
    real_trim = app.audio_vad.trim_to_speech
    real_normalize = app.audio_preprocessor.normalize_audio

    def clean(audio, sample_rate, click_at_seconds=0.5):
        seen["click_at_seconds"] = click_at_seconds
        seen["order"] = seen.get("order", []) + ["clean"]
        return real_clean(audio, sample_rate, click_at_seconds=click_at_seconds)

    def trim(audio, sample_rate=SR, options=None):
        seen["order"] = seen.get("order", []) + ["trim"]
        seen["length_into_trim"] = len(audio)
        return real_trim(audio, sample_rate, options)

    def normalize(audio, *args, **kwargs):
        seen["order"] = seen.get("order", []) + ["normalize"]
        seen["length_into_normalize"] = len(audio)
        return real_normalize(audio, *args, **kwargs)

    def run_asr(audio, steps=None):
        seen["audio_to_engine"] = audio
        return app.AsrOutcome("transcribed text", "FakeEngine")

    monkeypatch.setattr(app.audio_preprocessor, "clean_speech_audio", clean)
    monkeypatch.setattr(app.audio_vad, "trim_to_speech", trim)
    monkeypatch.setattr(app.audio_preprocessor, "normalize_audio", normalize)
    monkeypatch.setattr(app, "run_asr", run_asr)
    return seen


def run_take(audio, hold=1.0):
    chip, tray = FakeChip(), FakeTray()
    app.transcribe_and_paste(chip, tray, audio, hold)
    return chip, tray


def test_stages_run_in_the_right_order(pipeline):
    """Normalisation must come after trimming, so the level is measured over speech
    rather than over speech plus the silence around it."""
    take = np.concatenate([np.zeros(int(0.5 * SR), dtype=np.float32), speech_like(2.0)])
    run_take(take)
    assert pipeline["order"] == ["clean", "trim", "normalize"]


def test_click_suppressor_is_told_the_real_preroll_length(pipeline, monkeypatch):
    """The first take after launch has a partial pre-roll. Passing the nominal 0.5 s
    there would aim the notch at the wrong place -- the original bug."""
    monkeypatch.setattr(app.audio_capture, "preroll_seconds_used", lambda: 0.15)
    run_take(np.concatenate([np.zeros(int(0.15 * SR), dtype=np.float32), speech_like(2.0)]))
    assert pipeline["click_at_seconds"] == pytest.approx(0.15)


def test_trimming_actually_shortens_what_reaches_the_engine(pipeline):
    silence = np.zeros(int(1.5 * SR), dtype=np.float32)
    take = np.concatenate([silence, speech_like(2.0), silence])
    run_take(take)
    assert pipeline["length_into_normalize"] < pipeline["length_into_trim"]
    assert len(pipeline["audio_to_engine"]) < len(take)


def test_the_engine_receives_normalised_audio(pipeline):
    """A quiet take must arrive at the engine boosted, not at its original level."""
    quiet = np.concatenate([np.zeros(int(0.5 * SR), dtype=np.float32), speech_like(2.0, amplitude=0.01)])
    run_take(quiet)
    delivered = pipeline["audio_to_engine"]
    assert float(np.sqrt(np.mean(delivered.astype(np.float64) ** 2))) > 0.03


def test_a_too_short_take_never_reaches_preprocessing(pipeline):
    chip, _ = run_take(np.zeros(int(0.1 * SR), dtype=np.float32))
    assert "order" not in pipeline
    assert chip.states == ["nospeech"]


def test_a_too_quick_hold_never_reaches_preprocessing(pipeline):
    chip, _ = run_take(speech_like(2.0), hold=0.05)
    assert "order" not in pipeline
    assert chip.states == ["nospeech"]


def test_a_successful_take_ends_on_the_pasted_state(pipeline):
    take = np.concatenate([np.zeros(int(0.5 * SR), dtype=np.float32), speech_like(2.0)])
    chip, _ = run_take(take)
    assert chip.states[0] == "transcribing"
    assert chip.states[-1] == "pasted"
