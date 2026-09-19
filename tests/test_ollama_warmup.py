"""When the app loads the Ollama model in the background, and when it leaves it alone."""

import pytest

import app

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


@pytest.fixture
def warm(monkeypatch):
    calls = []
    monkeypatch.setattr(app.threading, "Thread", ImmediateThread)
    monkeypatch.setattr(app.cleanup_engine, "warm_up_ollama", lambda *a, **kw: calls.append(a) or True)
    monkeypatch.setattr(app, "_cleanup_providers", PROVIDERS)
    monkeypatch.setattr(app, "_cleanup_models", [OLLAMA_MODEL, GEMINI_MODEL])
    monkeypatch.setattr(app, "_use_cleanup", True)
    monkeypatch.setattr(app, "_ollama_keep_alive", "30m")
    monkeypatch.setattr(app, "_active_cleanup_model_id", OLLAMA_MODEL["id"])
    monkeypatch.setattr(app, "_last_warmed", None)
    return calls


def test_loads_the_active_ollama_model(warm):
    app._warm_active_ollama_model()
    assert warm == [("ollama/gemma4:e4b", "http://127.0.0.1:11434", "30m")]


def test_does_nothing_when_cleanup_is_off(warm, monkeypatch):
    monkeypatch.setattr(app, "_use_cleanup", False)
    app._warm_active_ollama_model()
    assert warm == []


def test_does_nothing_when_the_user_kept_ollamas_default(warm, monkeypatch):
    monkeypatch.setattr(app, "_ollama_keep_alive", None)
    app._warm_active_ollama_model()
    assert warm == []


def test_never_touches_a_hosted_model(warm, monkeypatch):
    monkeypatch.setattr(app, "_active_cleanup_model_id", GEMINI_MODEL["id"])
    app._warm_active_ollama_model()
    assert warm == []


def test_does_nothing_without_an_active_model(warm, monkeypatch):
    monkeypatch.setattr(app, "_active_cleanup_model_id", None)
    app._warm_active_ollama_model()
    assert warm == []


def test_repeated_saves_do_not_reload_it_every_time(warm):
    app._warm_active_ollama_model()
    app._warm_active_ollama_model()
    assert len(warm) == 1


def test_a_different_keep_alive_loads_it_again(warm, monkeypatch):
    app._warm_active_ollama_model()
    monkeypatch.setattr(app, "_ollama_keep_alive", "2h")
    app._warm_active_ollama_model()
    assert [call[2] for call in warm] == ["30m", "2h"]
