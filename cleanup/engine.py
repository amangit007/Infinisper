import base64
import io
import logging
import os
import re
import wave
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path

import httpx
import litellm
import numpy as np
from dotenv import load_dotenv

from cleanup.prompts import (
    CLEANUP_PROMPT_ADVANCED,
    CLEANUP_PROMPT_BASIC,
    ENGLISH_TRANSLITERATION_RULE,
    TRANSCRIBE_PROMPT_ADVANCED,
    TRANSCRIBE_PROMPT_BASIC,
    custom_dictionary_rule,
    language_guidance_rule,
    translation_rule,
)
from cleanup.breaker import CircuitBreaker, is_overload_error
from cleanup.catalog import normalize_local_url
from cleanup.errors import describe_error
from timing import timed

load_dotenv(Path(__file__).parent.parent / ".env")

# Benign: litellm always logs this when an audio message has no non-empty text
# part, even though we intentionally send an empty one (confirmed correct -- see
# the comment at the call site). It is log noise, not a sign of malfunction.
logging.getLogger("LiteLLM").setLevel(logging.ERROR)
litellm.drop_params = True

TIMEOUT_SECONDS = 60  # default; the app's AI cleanup card lets the user override this

# Thread pool executor to enforce request timeouts across providers.
_executor = ThreadPoolExecutor(max_workers=2)

MIN_LENGTH_RATIO = 0.4
MAX_LENGTH_RATIO = 2.5

# Remembers which models are overloaded right now, so a take doesn't wait 8-24 s for a
# provider to say "503" again. See cleanup/breaker.py.
_breaker = CircuitBreaker()

# Default model fallback.
GEMINI_ENV_MODEL = "gemini/gemini-3.5-flash-lite"


def has_gemini_env_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def get_gemini_env_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


@dataclass
class RefineResult:
    text: str
    used_model: bool
    detail: str = ""  # why it fell back, e.g. "no active model", "timeout", "error: ..."


def _skipped_detail(model: str) -> str:
    seconds = max(1, round(_breaker.retry_in(model)))
    return f"{model} is overloaded right now; skipping it for about {seconds} s"


def audio_to_wav_base64(audio: np.ndarray, sample_rate: int) -> str:
    pcm16 = (np.clip(audio, -1.0, 1.0) * 32767).astype(np.int16)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(sample_rate)
        wav_file.writeframes(pcm16.tobytes())
    return base64.b64encode(buffer.getvalue()).decode("ascii")


def completion_kwargs(
    model: str,
    api_key: str | None,
    base_url: str | None,
    timeout_seconds: int = TIMEOUT_SECONDS,
    keep_alive: str | None = None,
) -> dict:
    # num_retries=0: litellm otherwise falls back to the OpenAI SDK's default of 2
    # retries per call (openai.DEFAULT_MAX_RETRIES), all happening silently *inside*
    # a single future.result(timeout=...) window above -- a failing or slow request
    # was being retried up to 3 times before anything got reported, which both
    # multiplied real-world latency and swallowed the actual first-attempt error
    # behind a generic timeout once our own deadline cut the retries off mid-flight.
    # This app already has its own recovery strategy one layer up (fall back to
    # local Whisper) -- same-provider retries underneath it just hide problems.
    actual_model = model
    actual_base_url = None
    if base_url:
        actual_base_url = normalize_local_url(base_url)
        if "11434" in actual_base_url or "ollama" in actual_model:
            os.environ["OLLAMA_API_BASE"] = actual_base_url
    elif "ollama" in actual_model:
        os.environ.setdefault("OLLAMA_API_BASE", "http://127.0.0.1:11434")

    if actual_base_url and "11434" in actual_base_url and not actual_model.startswith("ollama/"):
        actual_model = f"ollama/{actual_model}"

    kwargs = {
        "model": actual_model,
        "timeout": timeout_seconds,
        "num_retries": 0,
        "temperature": 0.0,
    }
    if api_key:
        kwargs["api_key"] = api_key
    if actual_base_url:
        kwargs["api_base"] = actual_base_url

    # For Ollama models, disable thinking tokens by default to minimize latency.
    # Reasoning models (like Qwen 3.5) think for tens of seconds unless disabled.
    # LiteLLM maps reasoning_effort="none" directly to {"think": False} in Ollama request payload.
    if "ollama" in actual_model or (actual_base_url and "11434" in actual_base_url):
        kwargs["reasoning_effort"] = "none"
        if keep_alive:
            # How long Ollama keeps the model in memory after this request (its own
            # default is 5 minutes). litellm drops a plain keep_alive kwarg, but forwards
            # extra_body into the request -- checked against a live daemon.
            kwargs["extra_body"] = {"keep_alive": keep_alive}

    return kwargs


def warm_up_ollama(model: str, base_url: str | None, keep_alive: str, timeout_seconds: int = 120) -> bool:
    """Loads an Ollama model into memory so the first dictation isn't the one that pays for
    it (measured: gemma4:e4b 10.1 s cold vs 1.2 s loaded). An empty request is Ollama's
    documented way to load a model without generating anything. Returns False, quietly, if
    Ollama isn't reachable -- warming is a convenience, never something to interrupt on."""
    name = model.removeprefix("ollama/")
    url = (normalize_local_url(base_url) or "http://127.0.0.1:11434").rstrip("/") + "/api/generate"
    try:
        response = httpx.post(url, json={"model": name, "keep_alive": keep_alive}, timeout=timeout_seconds)
        return response.status_code == 200
    except Exception:
        return False


_PREAMBLE_RE = re.compile(
    r"^(?:here (?:is|are) (?:the )?(?:cleaned|corrected|transcribed|polished)?\s*(?:text|transcript|version)?:?"
    r"|cleaned text:?"
    r"|corrected text:?"
    r"|transcription:?"
    r"|transcript:?"
    r"|the user is asking:?"
    r"|user is asking:?"
    r"|user said:?)\s*",
    re.IGNORECASE,
)


def _sanitize_model_text(text: str) -> str:
    """Cleans up leaked prompt delimiters, conversational preambles, and enclosing quotes
    frequently produced by small local models (like Qwen 0.5B / 0.8B)."""
    if not text:
        return ""
    cleaned = text.strip()
    # Strip enclosing angle brackets (<<<text>>>, <<text>>, <text>)
    cleaned = re.sub(r"^<+\s*", "", cleaned)
    cleaned = re.sub(r"\s*>+$", "", cleaned).strip()

    # Strip conversational preambles (e.g. "Here is the cleaned text:", "User is asking:")
    cleaned = _PREAMBLE_RE.sub("", cleaned).strip()

    # In case angle brackets were wrapped inside/around the preamble
    cleaned = re.sub(r"^<+\s*", "", cleaned)
    cleaned = re.sub(r"\s*>+$", "", cleaned).strip()

    # Strip surrounding quotes if the model wrapped the entire output in quotes
    if (cleaned.startswith('"') and cleaned.endswith('"')) or (cleaned.startswith("'") and cleaned.endswith("'")):
        cleaned = cleaned[1:-1].strip()

    return cleaned


def transcribe_audio_with_model(
    audio: np.ndarray,
    sample_rate: int,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    level: str = "basic",
    force_english_transliteration: bool = False,
    dictation_language: str | None = None,
    output_mode: str = "original",
    target_language: str = "en",
    timeout_seconds: int = TIMEOUT_SECONDS,
    steps: list | None = None,
    custom_words: list[str] | None = None,
    keep_alive: str | None = None,
) -> RefineResult:
    """Sends raw audio directly to `model` (a LiteLLM model string, e.g.
    "gemini/gemini-3.5-flash-lite") for transcription, replacing Whisper
    entirely for this take. Returns used_model=False on any failure so the
    caller can fall back to local Whisper -- this path uploads the user's
    actual voice recording, so a failure must cost a slower local retry, never
    a lost take.

    level="basic" only fixes obvious ASR-style mistakes (nonsensical mishearings,
    number/time formatting); level="advanced" also removes filler words and
    formats detected lists as bullet points.

    output_mode controls linguistic transformation:
    - "original": Transcribe in the spoken language using native script.
    - "transliterate": Romanize into Latin alphabet (Hinglish, etc.).
    - "translate": Translate into target_language (e.g. "en").
    """
    if _breaker.is_open(model):
        return RefineResult("", used_model=False, detail=_skipped_detail(model))

    prompt = TRANSCRIBE_PROMPT_ADVANCED if level == "advanced" else TRANSCRIBE_PROMPT_BASIC
    prompt += custom_dictionary_rule(custom_words or [])

    effective_mode = output_mode
    if effective_mode == "original" and force_english_transliteration:
        effective_mode = "transliterate"

    if effective_mode == "translate":
        prompt += translation_rule(target_language)
    elif effective_mode == "transliterate":
        prompt += language_guidance_rule(dictation_language, is_audio=True)
        prompt += ENGLISH_TRANSLITERATION_RULE
    else:
        prompt += language_guidance_rule(dictation_language, is_audio=True)

    try:
        with timed("WAV encode + base64", steps):
            audio_b64 = audio_to_wav_base64(audio, sample_rate)
        future = _executor.submit(
            litellm.completion,
            messages=[
                {"role": "system", "content": prompt},
                {
                    "role": "user",
                    "content": [
                        # A blank text part, not an instruction -- litellm requires at least
                        # one text part alongside audio or the request is rejected, but any
                        # actual wording here (e.g. "transcribe this") measurably biases the
                        # model toward inventing speech in silent/non-speech audio instead of
                        # correctly reporting none. Confirmed by testing both against a pure
                        # sine tone: worded prompt hallucinated a sentence, blank text did not.
                        {"type": "text", "text": ""},
                        {
                            "type": "input_audio",
                            "input_audio": {"data": audio_b64, "format": "wav"},
                        },
                    ],
                },
            ],
            **completion_kwargs(model, api_key, base_url, timeout_seconds, keep_alive),
        )
        with timed("AI audio transcribe (network)", steps):
            response = future.result(timeout=timeout_seconds)
        text = _sanitize_model_text(response.choices[0].message.content or "")
    except FutureTimeoutError:
        _breaker.record_failure(model)
        print(f"AI transcription timed out after {timeout_seconds}s, falling back to local Whisper.")
        return RefineResult("", used_model=False, detail=f"timeout after {timeout_seconds}s")
    except Exception as exc:
        if is_overload_error(exc):
            _breaker.record_failure(model)
        print(f"AI transcription failed ({exc}), falling back to local Whisper.")
        return RefineResult("", used_model=False, detail=describe_error(exc))

    _breaker.record_success(model)
    if not text:
        return RefineResult("", used_model=False, detail="empty response")

    return RefineResult(text, used_model=True)


def refine_text_with_model(
    text: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    level: str = "basic",
    force_english_transliteration: bool = False,
    dictation_language: str | None = None,
    output_mode: str = "original",
    target_language: str = "en",
    timeout_seconds: int = TIMEOUT_SECONDS,
    steps: list | None = None,
    custom_words: list[str] | None = None,
    keep_alive: str | None = None,
) -> RefineResult:
    """Polishes text that an ASR engine already produced. Used only when both
    the ASR and AI cleanup categories are enabled -- the ASR step already
    succeeded by the time this runs, so a failure here just means no polish
    happened; the caller keeps the original ASR text rather than losing it.

    level="basic" only fixes obvious ASR-style mistakes (nonsensical mishearings,
    number/time formatting); level="advanced" also removes filler words and
    formats detected lists as bullet points.

    output_mode controls linguistic transformation:
    - "original": Polish in the original language and native script.
    - "transliterate": Romanize into Latin alphabet (Hinglish, etc.).
    - "translate": Translate into target_language (e.g. "en").
    """
    if not text.strip():
        return RefineResult(text, used_model=False)
    if _breaker.is_open(model):
        return RefineResult(text, used_model=False, detail=_skipped_detail(model))

    prompt = CLEANUP_PROMPT_ADVANCED if level == "advanced" else CLEANUP_PROMPT_BASIC
    prompt += custom_dictionary_rule(custom_words or [])

    effective_mode = output_mode
    if effective_mode == "original" and force_english_transliteration:
        effective_mode = "transliterate"

    if effective_mode == "translate":
        prompt += translation_rule(target_language)
    elif effective_mode == "transliterate":
        prompt += language_guidance_rule(dictation_language, is_audio=False)
        prompt += ENGLISH_TRANSLITERATION_RULE
    else:
        prompt += language_guidance_rule(dictation_language, is_audio=False)

    try:
        future = _executor.submit(
            litellm.completion,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"<<<{text}>>>"},
            ],
            **completion_kwargs(model, api_key, base_url, timeout_seconds, keep_alive),
        )
        with timed("AI text cleanup (network)", steps):
            response = future.result(timeout=timeout_seconds)
        cleaned = _sanitize_model_text(response.choices[0].message.content or "")
    except FutureTimeoutError:
        _breaker.record_failure(model)
        print(f"AI cleanup timed out after {timeout_seconds}s, using unpolished ASR text.")
        return RefineResult(text, used_model=False, detail=f"timeout after {timeout_seconds}s")
    except Exception as exc:
        if is_overload_error(exc):
            _breaker.record_failure(model)
        print(f"AI cleanup failed ({exc}), using unpolished ASR text.")
        return RefineResult(text, used_model=False, detail=describe_error(exc))

    _breaker.record_success(model)
    if not cleaned:
        return RefineResult(text, used_model=False, detail="empty response")

    ratio = len(cleaned) / max(len(text), 1)
    if ratio < MIN_LENGTH_RATIO or ratio > MAX_LENGTH_RATIO:
        print("AI cleanup output looked implausible (length mismatch), using unpolished ASR text.")
        return RefineResult(text, used_model=False, detail="implausible output")

    return RefineResult(cleaned, used_model=True)
