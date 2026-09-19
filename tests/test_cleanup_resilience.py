"""Overloaded models, Ollama warm-up and keep-alive, and how local endpoints are recognised."""

import types

import httpx
import litellm
import pytest

from cleanup import catalog
from cleanup import engine as cleanup_engine
from cleanup.breaker import CircuitBreaker, is_overload_error


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


# --- circuit breaker ---------------------------------------------------------------

def test_breaker_opens_after_repeated_failures_then_recovers():
    clock = FakeClock()
    breaker = CircuitBreaker(threshold=2, cooldown_seconds=60, clock=clock)

    breaker.record_failure("m")
    assert not breaker.is_open("m")  # one failure is not a pattern
    breaker.record_failure("m")
    assert breaker.is_open("m")
    assert 59 <= breaker.retry_in("m") <= 60

    clock.now += 61
    assert not breaker.is_open("m")  # cooled down: one request may go through


def test_breaker_success_resets_the_count():
    breaker = CircuitBreaker(threshold=2)
    breaker.record_failure("m")
    breaker.record_success("m")
    breaker.record_failure("m")
    assert not breaker.is_open("m")


def test_breaker_tracks_models_separately():
    breaker = CircuitBreaker(threshold=1)
    breaker.record_failure("busy")
    assert breaker.is_open("busy")
    assert not breaker.is_open("fine")


def _status_error(code):
    exc = Exception("boom")
    exc.status_code = code
    return exc


@pytest.mark.parametrize("code", [429, 500, 502, 503, 504])
def test_overload_statuses_count(code):
    assert is_overload_error(_status_error(code))


@pytest.mark.parametrize("code", [400, 401, 403, 404])
def test_configuration_errors_do_not_count(code):
    assert not is_overload_error(_status_error(code))


def test_timeouts_count():
    assert is_overload_error(litellm.Timeout("slow", model="m", llm_provider="p"))


def test_a_repeatedly_overloaded_model_is_skipped_without_a_network_call(monkeypatch):
    calls = []

    def overloaded(**kwargs):
        calls.append(kwargs["model"])
        raise _status_error(503)

    monkeypatch.setattr(cleanup_engine, "_breaker", CircuitBreaker(threshold=2, cooldown_seconds=60))
    monkeypatch.setattr(cleanup_engine.litellm, "completion", overloaded)

    for _ in range(2):
        result = cleanup_engine.refine_text_with_model("hello there", model="gemini/busy")
        assert not result.used_model and result.text == "hello there"
    assert len(calls) == 2

    skipped = cleanup_engine.refine_text_with_model("hello there", model="gemini/busy")
    assert len(calls) == 2, "the third take must not wait on a model that just said 503"
    assert skipped.text == "hello there"
    assert "overloaded" in skipped.detail


def test_a_wrong_api_key_is_never_skipped(monkeypatch):
    calls = []

    def unauthorised(**kwargs):
        calls.append(1)
        raise _status_error(401)

    monkeypatch.setattr(cleanup_engine, "_breaker", CircuitBreaker(threshold=2))
    monkeypatch.setattr(cleanup_engine.litellm, "completion", unauthorised)

    for _ in range(4):
        cleanup_engine.refine_text_with_model("hello there", model="gemini/m")
    assert len(calls) == 4


def test_success_keeps_the_model_available(monkeypatch):
    message = types.SimpleNamespace(content="Hello there.")
    reply = types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])
    monkeypatch.setattr(cleanup_engine, "_breaker", CircuitBreaker(threshold=1))
    monkeypatch.setattr(cleanup_engine.litellm, "completion", lambda **kw: reply)

    result = cleanup_engine.refine_text_with_model("hello there", model="gemini/ok")
    assert result.used_model and result.text == "Hello there."
    assert not cleanup_engine._breaker.is_open("gemini/ok")


# --- Ollama request shape ----------------------------------------------------------

def test_keep_alive_is_forwarded_to_ollama_only():
    local = cleanup_engine.completion_kwargs("ollama/gemma4:e4b", None, "http://127.0.0.1:11434", keep_alive="30m")
    assert local["extra_body"] == {"keep_alive": "30m"}

    hosted = cleanup_engine.completion_kwargs("gemini/gemini-3.5-flash-lite", "key", None, keep_alive="30m")
    assert "extra_body" not in hosted


def test_no_keep_alive_means_ollama_keeps_its_own_default():
    kwargs = cleanup_engine.completion_kwargs("ollama/gemma4:e4b", None, "http://127.0.0.1:11434")
    assert "extra_body" not in kwargs


def test_ollama_requests_disable_thinking_and_avoid_localhost():
    kwargs = cleanup_engine.completion_kwargs("ollama/qwen3.5:0.8b", None, "http://localhost:11434")
    assert kwargs["reasoning_effort"] == "none"
    assert kwargs["api_base"] == "http://127.0.0.1:11434"
    assert kwargs["temperature"] == 0.0 and kwargs["num_retries"] == 0


def test_warm_up_sends_an_empty_generate_request(monkeypatch):
    seen = {}

    def fake_post(url, json, timeout):
        seen.update(url=url, json=json)
        return types.SimpleNamespace(status_code=200)

    monkeypatch.setattr(cleanup_engine.httpx, "post", fake_post)
    assert cleanup_engine.warm_up_ollama("ollama/gemma4:e4b", "http://localhost:11434", "30m")
    assert seen["url"] == "http://127.0.0.1:11434/api/generate"
    assert seen["json"] == {"model": "gemma4:e4b", "keep_alive": "30m"}
    assert "prompt" not in seen["json"]  # loads the model, generates nothing


def test_warm_up_is_quiet_when_ollama_is_not_running(monkeypatch):
    def refuse(*args, **kwargs):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(cleanup_engine.httpx, "post", refuse)
    assert cleanup_engine.warm_up_ollama("ollama/x", None, "30m") is False


# --- where a model runs ------------------------------------------------------------

@pytest.mark.parametrize("model,url,local", [
    ("ollama/gemma4:e4b", None, True),
    ("ollama/gemma4:e4b", "http://127.0.0.1:11434", True),
    ("gpt-4o", "http://localhost:8000/v1", True),
    ("gemini/gemini-3.5-flash-lite", None, False),
    ("groq/openai/gpt-oss-120b", None, False),
    ("openai/gpt-4o", "https://api.openai.com/v1", False),
    ("ollama/x", "http://192.168.1.20:11434", False),
])
def test_is_local_endpoint(model, url, local):
    assert catalog.is_local_endpoint(model, url) is local


def test_localhost_is_rewritten_for_probing(monkeypatch):
    seen = {}

    def fake_get(url, timeout):
        seen["url"] = url
        return types.SimpleNamespace(raise_for_status=lambda: None, json=lambda: {"models": [{"name": "a:1b"}]})

    monkeypatch.setattr(catalog.httpx, "get", fake_get)
    assert catalog.probe_ollama("http://localhost:11434") == ["a:1b"]
    assert seen["url"] == "http://127.0.0.1:11434/api/tags"


# --- what the user is told when Ollama isn't ready ---------------------------------

def _raise(exc):
    def probe(url):
        raise exc

    return probe


def test_status_when_ollama_is_not_running(monkeypatch):
    monkeypatch.setattr(catalog, "probe_ollama", _raise(httpx.ConnectError("refused")))
    status = catalog.ollama_status()
    assert status.models == [] and "isn't running" in status.problem
    assert status.show_install_link


def test_status_when_ollama_has_no_models(monkeypatch):
    monkeypatch.setattr(catalog, "probe_ollama", lambda url: [])
    status = catalog.ollama_status()
    assert "no models" in status.problem and "ollama pull" in status.problem
    assert not status.show_install_link  # already installed -- don't send them to the download page


def test_status_when_ready(monkeypatch):
    monkeypatch.setattr(catalog, "probe_ollama", lambda url: ["gemma4:e4b"])
    status = catalog.ollama_status()
    assert status.models == ["gemma4:e4b"] and status.problem is None
