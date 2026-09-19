import json
import re
from concurrent.futures import TimeoutError as FutureTimeoutError

import litellm

from cleanup.catalog import CURATED_PROVIDERS

_PROVIDER_LABELS = dict(CURATED_PROVIDERS)
_MAX_DETAIL_CHARS = 220
_URL = re.compile(r"https?://\S+")


def _provider_label(exc: Exception) -> str:
    provider = getattr(exc, "llm_provider", None) or ""
    return _PROVIDER_LABELS.get(provider, provider.capitalize() or "The provider")


def _provider_body(exc: Exception) -> dict | None:
    """The provider's own JSON error body, if there is one.

    litellm has no user-facing formatter: str(exc) is the provider's raw response body
    pasted behind a "litellm.RateLimitError: litellm.RateLimitError: geminiException - "
    prefix, which is what used to be dumped into the Add-model dialog verbatim.
    """
    response = getattr(exc, "response", None)
    try:
        body = response.json() if response is not None else None
        if isinstance(body, dict):
            return body
    except Exception:
        pass

    message = str(getattr(exc, "message", "") or exc)
    start = message.find("{")
    if start == -1:
        return None
    try:
        body = json.loads(message[start:])
    except ValueError:
        return None
    return body if isinstance(body, dict) else None


def _inner_message(exc: Exception, body: dict | None) -> str:
    """The provider's human sentence, stripped of wrapper prefixes, links and noise."""
    text = ""
    if body:
        error = body.get("error")
        if isinstance(error, dict):
            text = str(error.get("message") or "")
        elif isinstance(error, str):
            text = error
        text = text or str(body.get("message") or "")
    if not text:
        text = str(getattr(exc, "message", "") or exc)
        text = re.sub(r"^(litellm\.\w+:\s*)+", "", text)
        text = re.sub(r"^\w+Exception\s*-\s*", "", text)

    text = _URL.sub("", text.splitlines()[0] if text.strip() else "")
    # "For more information on this error, head to: ." once the link itself is gone.
    text = re.sub(r"[^.]*head to:\s*\.?", "", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    if len(text) > _MAX_DETAIL_CHARS:
        text = text[: _MAX_DETAIL_CHARS - 1].rstrip() + "…"
    return text


def _quota_description(label: str, model: str, raw: str) -> str:
    limit = re.search(r"limit:\s*(\d+)", raw)
    period = "per day" if "PerDay" in raw else "per minute" if "PerMinute" in raw else ""
    tier = "free-tier " if "free_tier" in raw.lower() else ""

    parts = [f"{label} quota exceeded for {model}" if model else f"{label} quota exceeded"]
    if limit:
        parts[0] += f" ({tier}limit: {limit.group(1)} requests{' ' + period if period else ''})"
    advice = "Check your plan and billing"
    retry = re.search(r"retry in\s*([\d.]+)\s*s", raw, re.IGNORECASE)
    if retry:
        advice += f", or retry in about {max(1, round(float(retry.group(1))))} s"
    return f"{parts[0]}. {advice}."


def describe_error(exc: BaseException) -> str:
    """One readable sentence for a failed provider call, suitable for showing a user.

    Built from the structured fields litellm does carry (status_code, llm_provider,
    model) plus the provider's own message, rather than the raw exception text. Keep
    printing the raw exception to the console wherever this is used -- this is for
    people, not for debugging.
    """
    if isinstance(exc, FutureTimeoutError):
        return "The provider did not respond in time."

    label = _provider_label(exc)
    model = getattr(exc, "model", None) or ""
    status = getattr(exc, "status_code", None)
    body = _provider_body(exc)
    inner = _inner_message(exc, body)
    raw = json.dumps(body) if body else str(exc)

    if isinstance(exc, litellm.Timeout) or status == 408:
        return f"{label} did not respond in time."
    if isinstance(exc, litellm.APIConnectionError) and status is None:
        return f"Could not reach {label}. Check your internet connection or the provider's base URL."
    if status == 429:
        if "quota" in raw.lower() or "RESOURCE_EXHAUSTED" in raw:
            return _quota_description(label, model, raw)
        return f"{label} is rate-limiting requests right now. Wait a moment and try again."
    if status in (401, 403):
        return f"{label} rejected the API key (HTTP {status}). Check the key saved for this provider."
    if status == 404:
        return f"{label} does not recognise the model '{model}'." if model else f"{label}: {inner}."
    if status in (500, 502, 503, 504):
        reason = f" ({inner})" if inner else ""
        return f"{label} is temporarily unavailable{reason}. Try again shortly."
    return f"{label}: {inner}." if inner else f"{label} request failed."
