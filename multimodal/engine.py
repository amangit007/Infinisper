import base64
import io
import logging
import os
import wave
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from pathlib import Path

import litellm
import numpy as np
from dotenv import load_dotenv

from multimodal.prompts import (
    CLEANUP_PROMPT_ADVANCED,
    CLEANUP_PROMPT_BASIC,
    ENGLISH_TRANSLITERATION_RULE,
    TRANSCRIBE_PROMPT_ADVANCED,
    TRANSCRIBE_PROMPT_BASIC,
    custom_dictionary_rule,
)
from multimodal.errors import describe_error
from timing import timed

load_dotenv(Path(__file__).parent.parent / ".env")

# Benign: litellm always logs this when an audio message has no non-empty text
# part, even though we intentionally send an empty one (confirmed correct -- see
# the comment at the call site). It is log noise, not a sign of malfunction.
logging.getLogger("LiteLLM").setLevel(logging.ERROR)

TIMEOUT_SECONDS = 60  # default; the app's Multimodal correction card lets the user override this

# litellm's `timeout=` kwarg is not reliably honored for every provider path --
# observed failures against the Gemini/AI-Studio path report "Connection timed
# out after None seconds", meaning the configured timeout never reached the
# actual HTTP client. A hard deadline here is enforced independently, from
# outside litellm, for every provider, so a stuck network call can never block
# the hotkey/dictation loop past this.
_executor = ThreadPoolExecutor(max_workers=2)

MIN_LENGTH_RATIO = 0.4
MAX_LENGTH_RATIO = 2.5

# Stage-3 interim: until the Providers/Models UI (a later stage) exists,
# multimodal correction still only ever resolves to a Gemini key from .env,
# exactly like before this refactor -- app.py checks has_gemini_env_key() and
# passes GEMINI_ENV_MODEL + get_gemini_env_key() into the functions below,
# which otherwise no longer know anything about "Gemini" specifically. Once the
# Models tab lands, active-model resolution reads config.json + credentials.py
# instead, and this becomes just the migration fallback for an existing key.
GEMINI_ENV_MODEL = "gemini/gemini-3.5-flash-lite"


def has_gemini_env_key() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY"))


def get_gemini_env_key() -> str | None:
    return os.environ.get("GEMINI_API_KEY")


@dataclass
class RefineResult:
    text: str
    used_multimodal: bool
    detail: str = ""  # why it fell back, e.g. "no active model", "timeout", "error: ..."


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
    model: str, api_key: str | None, base_url: str | None, timeout_seconds: int = TIMEOUT_SECONDS
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
    if base_url and "11434" in str(base_url) and not actual_model.startswith("ollama/"):
        actual_model = f"ollama/{actual_model}"

    kwargs = {"model": actual_model, "timeout": timeout_seconds, "num_retries": 0}
    if api_key:
        kwargs["api_key"] = api_key
    if base_url:
        kwargs["api_base"] = base_url
    return kwargs


def transcribe_with_multimodal_model(
    audio: np.ndarray,
    sample_rate: int,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    level: str = "basic",
    force_english_transliteration: bool = False,
    timeout_seconds: int = TIMEOUT_SECONDS,
    steps: list | None = None,
    custom_words: list[str] | None = None,
) -> RefineResult:
    """Sends raw audio directly to `model` (a LiteLLM model string, e.g.
    "gemini/gemini-3.5-flash-lite") for transcription, replacing Whisper
    entirely for this take. Returns used_multimodal=False on any failure so the
    caller can fall back to local Whisper -- this path uploads the user's
    actual voice recording, so a failure must cost a slower local retry, never
    a lost take.

    level="basic" only fixes obvious ASR-style mistakes (nonsensical mishearings,
    number/time formatting); level="advanced" also removes filler words and
    formats detected lists as bullet points. force_english_transliteration
    romanizes non-English speech instead of writing it in its native script --
    see prompts.ENGLISH_TRANSLITERATION_RULE.
    """
    prompt = TRANSCRIBE_PROMPT_ADVANCED if level == "advanced" else TRANSCRIBE_PROMPT_BASIC
    prompt += custom_dictionary_rule(custom_words or [])
    if force_english_transliteration:
        prompt += ENGLISH_TRANSLITERATION_RULE

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
            **completion_kwargs(model, api_key, base_url, timeout_seconds),
        )
        with timed("Multimodal audio transcribe (network)", steps):
            response = future.result(timeout=timeout_seconds)
        text = (response.choices[0].message.content or "").strip()
    except FutureTimeoutError:
        print(f"Multimodal transcription timed out after {timeout_seconds}s, falling back to local Whisper.")
        return RefineResult("", used_multimodal=False, detail=f"timeout after {timeout_seconds}s")
    except Exception as exc:
        print(f"Multimodal transcription failed ({exc}), falling back to local Whisper.")
        return RefineResult("", used_multimodal=False, detail=describe_error(exc))

    if not text:
        return RefineResult("", used_multimodal=False, detail="empty response")

    return RefineResult(text, used_multimodal=True)


def refine_text_with_multimodal_model(
    text: str,
    model: str,
    api_key: str | None = None,
    base_url: str | None = None,
    level: str = "basic",
    force_english_transliteration: bool = False,
    timeout_seconds: int = TIMEOUT_SECONDS,
    steps: list | None = None,
    custom_words: list[str] | None = None,
) -> RefineResult:
    """Polishes text that an ASR engine already produced. Used only when both
    the ASR and Multimodal categories are enabled -- the ASR step already
    succeeded by the time this runs, so a failure here just means no polish
    happened; the caller keeps the original ASR text rather than losing it.

    level="basic" only fixes obvious ASR-style mistakes (nonsensical mishearings,
    number/time formatting); level="advanced" also removes filler words and
    formats detected lists as bullet points. force_english_transliteration
    romanizes non-English text instead of correcting it back to its native
    script -- see prompts.ENGLISH_TRANSLITERATION_RULE.
    """
    if not text.strip():
        return RefineResult(text, used_multimodal=False)

    prompt = CLEANUP_PROMPT_ADVANCED if level == "advanced" else CLEANUP_PROMPT_BASIC
    prompt += custom_dictionary_rule(custom_words or [])
    if force_english_transliteration:
        prompt += ENGLISH_TRANSLITERATION_RULE

    try:
        future = _executor.submit(
            litellm.completion,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": f"<<<{text}>>>"},
            ],
            **completion_kwargs(model, api_key, base_url, timeout_seconds),
        )
        with timed("Multimodal text cleanup (network)", steps):
            response = future.result(timeout=timeout_seconds)
        cleaned = response.choices[0].message.content.strip()
        # Belt-and-suspenders: the prompt tells the model not to echo the <<< >>>
        # delimiters, but observed it do so anyway on at least one real response.
        # Strip them if they slip through rather than pasting literal brackets.
        cleaned = cleaned.removeprefix("<<<").removesuffix(">>>").strip()
    except FutureTimeoutError:
        print(f"Multimodal cleanup timed out after {timeout_seconds}s, using unpolished ASR text.")
        return RefineResult(text, used_multimodal=False, detail=f"timeout after {timeout_seconds}s")
    except Exception as exc:
        print(f"Multimodal cleanup failed ({exc}), using unpolished ASR text.")
        return RefineResult(text, used_multimodal=False, detail=describe_error(exc))

    if not cleaned:
        return RefineResult(text, used_multimodal=False, detail="empty response")

    ratio = len(cleaned) / max(len(text), 1)
    if ratio < MIN_LENGTH_RATIO or ratio > MAX_LENGTH_RATIO:
        print("Multimodal cleanup output looked implausible (length mismatch), using unpolished ASR text.")
        return RefineResult(text, used_multimodal=False, detail="implausible output")

    return RefineResult(cleaned, used_multimodal=True)
