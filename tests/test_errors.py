"""Tests for AI cleanup error message formatting."""

import json
from concurrent.futures import TimeoutError as FutureTimeoutError

import litellm

from cleanup.errors import describe_error

MODEL = "gemini-3.8-flash"

QUOTA_BODY = {
    "error": {
        "code": 429,
        "message": (
            "You exceeded your current quota, please check your plan and billing details. "
            "For more information on this error, head to: https://ai.google.dev/gemini-api/docs/rate-limits. "
            "To monitor your current usage, head to: https://ai.dev/rate-limit. \n"
            "* Quota exceeded for metric: generativelanguage.googleapis.com/"
            "generate_content_free_tier_requests, limit: 20, model: gemini-3.8-flash\n"
            "Please retry in 26.558707724s."
        ),
        "status": "RESOURCE_EXHAUSTED",
        "details": [
            {
                "@type": "type.googleapis.com/google.rpc.QuotaFailure",
                "violations": [
                    {"quotaId": "GenerateRequestsPerDayPerProjectPerModel-FreeTier", "quotaValue": "20"}
                ],
            }
        ],
    }
}


def wrapped(body):
    """The shape litellm actually produces: provider JSON behind its own prefixes."""
    return "litellm.RateLimitError: litellm.RateLimitError: geminiException - " + json.dumps(body, indent=2)


def quota_error():
    return litellm.RateLimitError(message=wrapped(QUOTA_BODY), model=MODEL, llm_provider="gemini")


def test_quota_error_becomes_one_readable_sentence():
    text = describe_error(quota_error())
    assert text == (
        "Google Gemini quota exceeded for gemini-3.8-flash (free-tier limit: 20 requests per day). "
        "Check your plan and billing, or retry in about 27 s."
    )


def test_output_never_contains_raw_json_links_or_litellm_prefixes():
    text = describe_error(quota_error())
    for noise in ("{", "}", "http", "litellm.", "geminiException", "RESOURCE_EXHAUSTED", "@type"):
        assert noise not in text
    assert len(text) < 200


def test_plain_rate_limit_without_quota_wording():
    body = {"error": {"code": 429, "message": "Too many requests, slow down."}}
    exc = litellm.RateLimitError(message=wrapped(body), model=MODEL, llm_provider="gemini")
    assert describe_error(exc) == "Google Gemini is rate-limiting requests right now. Wait a moment and try again."


def test_bad_api_key():
    exc = litellm.AuthenticationError(message="API key not valid", model=MODEL, llm_provider="gemini")
    assert describe_error(exc) == (
        "Google Gemini rejected the API key (HTTP 401). Check the key saved for this provider."
    )


def test_unknown_model():
    exc = litellm.NotFoundError(message="models/xyz is not found", model="xyz", llm_provider="gemini")
    assert describe_error(exc) == "Google Gemini does not recognise the model 'xyz'."


def test_provider_overloaded_keeps_the_providers_own_reason():
    body = {"error": {"code": 503, "message": "This model is currently experiencing high demand. "
                                               "Spikes in demand are usually temporary. Please try again later."}}
    exc = litellm.ServiceUnavailableError(message=wrapped(body), model=MODEL, llm_provider="gemini")
    text = describe_error(exc)
    assert text.startswith("Google Gemini is temporarily unavailable (This model is currently experiencing high demand")
    assert text.endswith("Try again shortly.")


def test_bad_request_passes_the_providers_message_through_cleanly():
    body = {"error": {"code": 400, "message": "Audio input is not supported for this model."}}
    exc = litellm.BadRequestError(message=wrapped(body), model=MODEL, llm_provider="gemini")
    assert describe_error(exc) == "Google Gemini: Audio input is not supported for this model."


def test_timeouts():
    assert describe_error(FutureTimeoutError()) == "The provider did not respond in time."
    exc = litellm.Timeout(message="Request timed out", model=MODEL, llm_provider="openai")
    assert describe_error(exc) == "OpenAI did not respond in time."


def test_unrecognised_provider_is_still_named_sensibly():
    exc = litellm.BadRequestError(message="nope", model="m", llm_provider="deepinfra")
    assert describe_error(exc).startswith("Deepinfra:")


def test_a_very_long_provider_message_is_truncated():
    body = {"error": {"code": 400, "message": "word " * 200}}
    exc = litellm.BadRequestError(message=wrapped(body), model=MODEL, llm_provider="gemini")
    assert len(describe_error(exc)) < 260


def test_a_non_litellm_exception_does_not_crash_the_formatter():
    assert describe_error(RuntimeError("socket closed"))
