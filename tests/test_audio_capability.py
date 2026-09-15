"""Covers how the Add-model dialog decides whether a model accepts audio.

The bug these exist for: completion_kwargs sets num_retries=0, which is correct for
the dictation path but was also being inherited by the capability probe. One transient
503 from a busy provider -- reproduced live against gemini/gemini-3.8-flash, which
answered 200 then 503 moments later -- permanently recorded supports_audio=False into
config.json, and nothing ever revisited it.
"""

import litellm
import pytest

from multimodal import testing
from multimodal.testing import (
    AUDIO_DECLARED,
    AUDIO_SUPPORTED,
    AUDIO_UNKNOWN,
    AUDIO_UNSUPPORTED,
)

# Aliased: pytest would otherwise collect the imported test_provider_model as a test
# case and fail trying to fill its `model` argument from a fixture.
from multimodal.testing import test_provider_model as run_provider_test

MODEL = "gemini/gemini-3.8-flash"


@pytest.fixture(autouse=True)
def no_backoff(monkeypatch):
    """The real probe sleeps between retries; the tests should not."""
    monkeypatch.setattr(testing, "_AUDIO_PROBE_BACKOFF_SECONDS", 0.0)


def fake_completion_sequence(*outcomes):
    """Returns a litellm.completion stand-in that yields `outcomes` in order. An
    outcome is either an exception to raise or None to succeed."""
    calls = {"n": 0}

    def fake(**kwargs):
        index = min(calls["n"], len(outcomes) - 1)
        calls["n"] += 1
        outcome = outcomes[index]
        if isinstance(outcome, Exception):
            raise outcome
        return {"choices": [{"message": {"content": "OK"}}]}

    fake.calls = calls
    return fake


def service_unavailable():
    return litellm.ServiceUnavailableError(
        message="model is experiencing high demand", model=MODEL, llm_provider="gemini"
    )


def bad_request():
    return litellm.BadRequestError(
        message="this model does not support audio input", model=MODEL, llm_provider="gemini"
    )


# --- the regression --------------------------------------------------------------


def test_a_single_transient_503_no_longer_marks_a_model_text_only(monkeypatch):
    """The exact failure the user hit. Text call succeeds, first audio call 503s,
    a retry succeeds -- the model must come out audio-capable."""
    monkeypatch.setattr(
        litellm, "completion", fake_completion_sequence(None, service_unavailable(), None)
    )
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.audio_ok is True
    assert result.audio_status == AUDIO_SUPPORTED


def test_the_audio_probe_is_retried(monkeypatch):
    fake = fake_completion_sequence(None, service_unavailable(), service_unavailable(), None)
    monkeypatch.setattr(litellm, "completion", fake)
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.audio_ok is True
    # 1 text call + 3 audio attempts
    assert fake.calls["n"] == 4


def test_persistent_transient_failure_falls_back_to_catalog_metadata(monkeypatch):
    """Provider unreachable for every attempt. litellm's catalog lists this model as
    audio-capable, and trusting it is the cheaper mistake: a wrong yes costs one take
    that falls back to Whisper, a wrong no locks audio dictation off permanently."""
    monkeypatch.setattr(
        litellm, "completion", fake_completion_sequence(None, service_unavailable())
    )
    assert litellm.model_cost[MODEL]["supports_audio_input"] is True

    result = run_provider_test(MODEL, "key", None, provider_id="gemini")
    assert result.audio_ok is True
    assert result.audio_status == AUDIO_DECLARED
    assert "catalog" in result.detail


def test_a_real_rejection_is_still_recorded_as_text_only(monkeypatch):
    """A model that genuinely refuses audio must not be retried into a false positive."""
    fake = fake_completion_sequence(None, bad_request())
    monkeypatch.setattr(litellm, "completion", fake)
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.audio_ok is False
    assert result.audio_status == AUDIO_UNSUPPORTED
    assert fake.calls["n"] == 2, "a hard rejection should not be retried"


def test_unknown_model_with_no_metadata_stays_unknown(monkeypatch):
    monkeypatch.setattr(
        litellm, "completion", fake_completion_sequence(None, service_unavailable())
    )
    result = run_provider_test(
        "gemini/not-a-real-model-xyz", "key", None, provider_id="gemini"
    )
    assert result.audio_ok is False
    assert result.audio_status == AUDIO_UNKNOWN


# --- unchanged behaviour ---------------------------------------------------------


def test_a_failing_text_call_still_blocks_the_save(monkeypatch):
    monkeypatch.setattr(litellm, "completion", fake_completion_sequence(bad_request()))
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")
    assert result.passed is False


def test_the_text_call_is_retried_too(monkeypatch):
    """Observed live: gemini/gemini-3.8-flash 503'd on the text call as well, which
    blocked saving the model outright with an error implying the model or key was
    wrong."""
    monkeypatch.setattr(
        litellm, "completion", fake_completion_sequence(service_unavailable(), None, None)
    )
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")
    assert result.passed is True
    assert result.text_ok is True


def test_an_unreachable_provider_says_so_rather_than_blaming_the_model(monkeypatch):
    monkeypatch.setattr(litellm, "completion", fake_completion_sequence(service_unavailable()))
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")
    assert result.passed is False
    assert "did not respond" in result.detail


def test_ollama_is_still_never_probed_for_audio(monkeypatch):
    """LiteLLM/Ollama silently drops an audio payload instead of erroring, so probing
    it would mark every local text LLM as audio-capable."""
    fake = fake_completion_sequence(None)
    monkeypatch.setattr(litellm, "completion", fake)
    result = run_provider_test(
        "gemma3", "key", "http://localhost:11434", provider_id="ollama"
    )
    assert result.audio_status == AUDIO_UNSUPPORTED
    assert result.audio_ok is False
    assert fake.calls["n"] == 1, "only the text call should have run"


def test_transient_classification():
    assert testing._is_transient(service_unavailable()) is True
    assert testing._is_transient(bad_request()) is False
    assert testing._is_transient(Exception("something else")) is False
    assert testing._is_transient(quota_exceeded()) is False


# --- quota / rate limit / key ----------------------------------------------------


def quota_exceeded():
    return litellm.RateLimitError(
        message='geminiException - {"error": {"code": 429, "message": "You exceeded your current quota", '
        '"status": "RESOURCE_EXHAUSTED"}}',
        model=MODEL,
        llm_provider="gemini",
    )


def test_an_exhausted_quota_is_not_retried(monkeypatch):
    """A daily free-tier quota was being retried into the identical 429 twice more,
    with backoff -- slower, and no chance of a different answer."""
    fake = fake_completion_sequence(quota_exceeded())
    monkeypatch.setattr(litellm, "completion", fake)
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.passed is False
    assert fake.calls["n"] == 1


def test_a_failed_text_call_skips_the_audio_probe(monkeypatch):
    """Nothing is saved, so probing audio would only spend another request against an
    exhausted quota and show the same error twice."""
    fake = fake_completion_sequence(quota_exceeded())
    monkeypatch.setattr(litellm, "completion", fake)
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert fake.calls["n"] == 1
    assert result.detail.count("quota exceeded") == 1


def test_quota_hit_on_the_audio_probe_does_not_brand_the_model_text_only(monkeypatch):
    """Text call spends the last request of the quota, audio call gets a 429. That says
    nothing about the model's capabilities, so it must not be recorded as unsupported."""
    monkeypatch.setattr(litellm, "completion", fake_completion_sequence(None, quota_exceeded()))
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.audio_status == AUDIO_DECLARED  # catalog fallback, not UNSUPPORTED
    assert result.audio_ok is True


def test_failure_detail_is_readable_not_a_raw_dump(monkeypatch):
    monkeypatch.setattr(litellm, "completion", fake_completion_sequence(quota_exceeded()))
    result = run_provider_test(MODEL, "key", None, provider_id="gemini")

    assert result.detail.startswith("Google Gemini quota exceeded")
    assert "{" not in result.detail and "litellm." not in result.detail
