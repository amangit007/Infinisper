"""When the app loads the Ollama model in the background, and when it leaves it alone."""

import pytest

from dictation import pipeline as pipeline_module
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings

OLLAMA_MODEL = {"id": "ollama::ollama/gemma4:e4b", "provider_id": "ollama", "model": "ollama/gemma4:e4b"}
GEMINI_MODEL = {"id": "gemini::gemini/flash", "provider_id": "gemini", "model": "gemini/flash"}
PROVIDERS = [
    {"id": "ollama", "display_name": "Ollama", "base_url": "http://127.0.0.1:11434"},
    {"id": "gemini", "display_name": "Gemini", "base_url": None},
]


class ImmediateThread:
    """Runs the warm-up inline so the test can see what it did."""

    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


class Warmup:
    """The pipeline under test, and the model loads it asked Ollama for."""

    def __init__(self):
        self.calls = []
        self.settings = Settings(
            use_cleanup=True,
            ollama_keep_alive="30m",
            cleanup_providers=PROVIDERS,
            cleanup_models=[OLLAMA_MODEL, GEMINI_MODEL],
            active_cleanup_model_id=OLLAMA_MODEL["id"],
        )
        self.pipeline = Pipeline(self.settings, Runtime())

    def run(self):
        self.pipeline.warm_active_ollama_model()


@pytest.fixture
def warm(monkeypatch):
    warmup = Warmup()
    monkeypatch.setattr(pipeline_module.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(
        pipeline_module.cleanup_engine, "warm_up_ollama", lambda *a, **kw: warmup.calls.append(a) or True
    )
    return warmup


def test_loads_the_active_ollama_model(warm):
    warm.run()
    assert warm.calls == [("ollama/gemma4:e4b", "http://127.0.0.1:11434", "30m")]


def test_does_nothing_when_cleanup_is_off(warm):
    warm.settings.use_cleanup = False
    warm.run()
    assert warm.calls == []


def test_does_nothing_when_the_user_kept_ollamas_default(warm):
    warm.settings.ollama_keep_alive = None
    warm.run()
    assert warm.calls == []


def test_never_touches_a_hosted_model(warm):
    warm.settings.active_cleanup_model_id = GEMINI_MODEL["id"]
    warm.run()
    assert warm.calls == []


def test_does_nothing_without_an_active_model(warm):
    warm.settings.active_cleanup_model_id = None
    warm.run()
    assert warm.calls == []


def test_repeated_saves_do_not_reload_it_every_time(warm):
    warm.run()
    warm.run()
    assert len(warm.calls) == 1


def test_a_different_keep_alive_loads_it_again(warm):
    warm.run()
    warm.settings.ollama_keep_alive = "2h"
    warm.run()
    assert [call[2] for call in warm.calls] == ["30m", "2h"]
