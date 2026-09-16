import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass

import litellm
import numpy as np

from multimodal.catalog import get_model_capabilities
from multimodal.engine import TIMEOUT_SECONDS, audio_to_wav_base64, completion_kwargs
from multimodal.errors import describe_error

_executor = ThreadPoolExecutor(max_workers=2)

# How the audio probe turned out. The distinction that matters is between the model
# refusing audio and the probe never getting an answer -- collapsing those two into a
# single False is what made every model added through the dialog come out text-only.
AUDIO_SUPPORTED = "supported"      # the model accepted an audio message
AUDIO_DECLARED = "declared"        # probe inconclusive, but litellm's catalog says it accepts audio
AUDIO_UNSUPPORTED = "unsupported"  # the model actively rejected audio
AUDIO_UNKNOWN = "unknown"          # probe inconclusive and nothing else to go on

_AUDIO_PROBE_ATTEMPTS = 3
_AUDIO_PROBE_BACKOFF_SECONDS = 2.0

# Every one of these means "this request did not get through", never "this model
# cannot accept audio". completion_kwargs sets num_retries=0, which is right for the
# dictation path (it has a local Whisper fallback underneath it) but wrong here: a
# capability answer gets written to config.json and never revisited, so one transient
# 503 from a busy provider would brand a perfectly capable model text-only forever.
def _litellm_errors(*names):
    return tuple(e for e in (getattr(litellm, n, None) for n in names) if isinstance(e, type))


_TRANSIENT_ERRORS = _litellm_errors(
    "ServiceUnavailableError", "Timeout", "APIConnectionError", "InternalServerError"
)
_TRANSIENT_STATUS_CODES = {408, 500, 502, 503, 504}

# The request was refused for reasons that have nothing to do with the model's
# capabilities -- quota, rate limit, bad key -- and that a retry a few seconds later
# will not fix. Deliberately NOT transient: a daily free-tier quota was being retried
# into the same 429 twice more. And deliberately NOT a capability rejection either,
# or an exhausted quota on the audio probe would brand the model text-only again.
_BLOCKED_ERRORS = _litellm_errors("RateLimitError", "AuthenticationError", "PermissionDeniedError")
_BLOCKED_STATUS_CODES = {401, 403, 429}


@dataclass
class TestResult:
    passed: bool  # True if the model can be saved at all (the text call worked)
    text_ok: bool
    audio_ok: bool  # unlocks the audio-transcription path specifically
    detail: str = ""
    audio_status: str = AUDIO_UNKNOWN


def _is_transient(exc: Exception) -> bool:
    if _is_blocked(exc):
        return False
    if isinstance(exc, _TRANSIENT_ERRORS):
        return True
    return getattr(exc, "status_code", None) in _TRANSIENT_STATUS_CODES


def _is_blocked(exc: Exception) -> bool:
    if isinstance(exc, _BLOCKED_ERRORS):
        return True
    return getattr(exc, "status_code", None) in _BLOCKED_STATUS_CODES


CALL_OK = "ok"                  # the provider answered
CALL_REJECTED = "rejected"      # the provider answered, refusing this request
CALL_BLOCKED = "blocked"        # refused for quota, rate limit or key -- says nothing about the model
CALL_UNREACHABLE = "unreachable"  # no answer, after retries


def _probe(label: str, messages: list, model: str, api_key: str | None, base_url: str | None):
    """Runs one probe call against `model`, retrying transient failures.

    Returns (CALL_*, detail). The distinction that matters is REJECTED (the provider
    answered and said no) versus UNREACHABLE (it never answered) -- collapsing those
    into one failure is what made a busy provider look like an incapable model.
    """
    detail = ""
    for attempt in range(1, _AUDIO_PROBE_ATTEMPTS + 1):
        try:
            future = _executor.submit(
                litellm.completion, messages=messages, **completion_kwargs(model, api_key, base_url)
            )
            future.result(timeout=TIMEOUT_SECONDS)
            return CALL_OK, ""
        except FutureTimeoutError as exc:
            detail = describe_error(exc)
        except Exception as exc:
            # litellm prints its own generic "Give Feedback / Get Help" boilerplate on
            # every mapped exception, but never the actual descriptive message -- that
            # only lives in the exception object, so print the raw form here for
            # debugging. What goes back to the dialog is describe_error's one sentence.
            print(f"Multimodal provider test ({label} call) failed: {exc}")
            if _is_blocked(exc):
                return CALL_BLOCKED, describe_error(exc)
            if not _is_transient(exc):
                return CALL_REJECTED, describe_error(exc)
            detail = describe_error(exc)

        if attempt < _AUDIO_PROBE_ATTEMPTS:
            print(
                f"{label.capitalize()} probe attempt {attempt}/{_AUDIO_PROBE_ATTEMPTS} hit a "
                f"transient error, retrying..."
            )
            time.sleep(_AUDIO_PROBE_BACKOFF_SECONDS * attempt)

    return CALL_UNREACHABLE, detail


def _test_text_call(model: str, api_key: str | None, base_url: str | None) -> tuple[bool, str]:
    """Confirms the model answers at all. Retried on transient failures for the same
    reason the audio probe is: a 503 from a provider under load was blocking the save
    outright, with an error implying the model or the key was wrong."""
    status, detail = _probe(
        "text",
        [{"role": "user", "content": "Reply with the single word: OK"}],
        model,
        api_key,
        base_url,
    )
    if status == CALL_UNREACHABLE:
        detail = f"{detail} It did not respond after {_AUDIO_PROBE_ATTEMPTS} attempts."
    return status == CALL_OK, detail


def _test_audio_call(model: str, api_key: str | None, base_url: str | None) -> tuple[str, str]:
    """Probe whether the model supports audio inputs."""
    audio = np.zeros(16000, dtype=np.float32)  # 1s of silence at 16kHz
    audio_b64 = audio_to_wav_base64(audio, 16000)
    status, detail = _probe(
        "audio",
        [
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": ""},
                    {"type": "input_audio", "input_audio": {"data": audio_b64, "format": "wav"}},
                ],
            }
        ],
        model,
        api_key,
        base_url,
    )
    return {
        CALL_OK: AUDIO_SUPPORTED,
        CALL_REJECTED: AUDIO_UNSUPPORTED,
        CALL_BLOCKED: AUDIO_UNKNOWN,
        CALL_UNREACHABLE: AUDIO_UNKNOWN,
    }[status], detail


def test_provider_model(
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    provider_id: str | None = None,
) -> TestResult:
    """Runs a minimal text call and a minimal audio call against `model`.
    A model that rejects audio entirely still gets `passed=True` (text_ok) so
    the caller can offer saving it as a text-only multimodal model -- usable at
    least for the ASR+Multimodal cleanup path, which is text-only anyway --
    rather than hard-blocking the save.
    """
    actual_model = model
    if (provider_id == "ollama" or (base_url and "11434" in str(base_url))) and not actual_model.startswith("ollama/"):
        actual_model = f"ollama/{actual_model}"
    elif provider_id and provider_id not in ("other",) and "/" not in actual_model and not actual_model.startswith(f"{provider_id}/"):
        actual_model = f"{provider_id}/{actual_model}"

    text_ok, text_detail = _test_text_call(actual_model, api_key, base_url)
    if not text_ok:
        # Nothing gets saved, so the audio result would be thrown away -- and running it
        # anyway costs another request against what is often an already-exhausted quota,
        # then repeats the same error a second time in the dialog.
        return TestResult(passed=False, text_ok=False, audio_ok=False, detail=text_detail)

    # Ollama is a text/vision LLM daemon; it does not support raw audio transcription.
    # When sent audio, LiteLLM/Ollama silently drops the audio payload instead of erroring,
    # which would falsely mark text LLMs as supporting audio input.
    if provider_id == "ollama" or (base_url and "11434" in str(base_url)):
        audio_status, audio_detail = AUDIO_UNSUPPORTED, ""
    else:
        audio_status, audio_detail = _test_audio_call(actual_model, api_key, base_url)

    # The probe never got an answer. Rather than record a guess as fact, fall back to
    # litellm's own catalog: it is the same metadata the model picker is built from,
    # and being wrong in this direction is the cheaper mistake -- a model wrongly
    # marked audio-capable fails one take and falls back to Whisper, where one wrongly
    # marked text-only can never be used for audio at all.
    if audio_status == AUDIO_UNKNOWN:
        capabilities = get_model_capabilities(actual_model) or {}
        if capabilities.get("supports_audio_input"):
            audio_status = AUDIO_DECLARED
            audio_detail = (
                f"audio probe was inconclusive ({audio_detail}), but litellm's catalog "
                f"lists this model as accepting audio input"
            )

    detail = "; ".join(d for d in (text_detail, audio_detail) if d)
    return TestResult(
        passed=text_ok,
        text_ok=text_ok,
        audio_ok=audio_status in (AUDIO_SUPPORTED, AUDIO_DECLARED),
        detail=detail,
        audio_status=audio_status,
    )
