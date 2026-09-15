import numpy as np
from faster_whisper.vad import VadOptions, collect_chunks, get_speech_timestamps

# Silero VAD ships inside faster-whisper, so running it here costs no new dependency
# and no extra download -- sherpa-onnx bundles the same model again if this ever needs
# to move off faster-whisper.
#
# These are the exact parameters the Whisper path already passed to faster-whisper's
# own vad_filter, so lifting VAD out in front of every engine leaves Whisper behaving
# as before. What changes is that Qwen3 and Nemotron stop receiving raw takes --
# pre-roll silence, trailing pauses and all -- which is what they got previously.
DEFAULT_OPTIONS = VadOptions(
    threshold=0.35,
    min_speech_duration_ms=100,
    min_silence_duration_ms=1500,
    speech_pad_ms=400,
)

SUPPORTED_SAMPLE_RATE = 16000


def warm_up() -> None:
    """Loads the Silero model ahead of the first dictation.

    faster-whisper loads it lazily on first use, measured at ~490 ms against ~10 ms
    once warm. Left to itself that lands on the user's first take after launch, where
    it reads as the app being slow; called during the splash it is invisible.
    """
    try:
        trim_to_speech(np.zeros(SUPPORTED_SAMPLE_RATE, dtype=np.float32), SUPPORTED_SAMPLE_RATE)
    except Exception as exc:
        print(f"VAD warm-up failed ({exc}); it will load on first use instead.")


def trim_to_speech(
    audio: np.ndarray, sample_rate: int = SUPPORTED_SAMPLE_RATE, options: VadOptions | None = None
) -> np.ndarray:
    """Returns `audio` with non-speech regions dropped and the speech concatenated.

    Returns the input unchanged whenever trimming cannot be done safely -- the VAD
    finding nothing, an unexpected sample rate, or the model failing to load. A take
    the caller already decided was worth transcribing must never be emptied here; the
    safer failure is to hand the engine the untrimmed audio and let it report nothing.
    """
    if audio is None or len(audio) == 0:
        return audio
    if sample_rate != SUPPORTED_SAMPLE_RATE:
        return audio  # the bundled Silero model is 16 kHz only; the app only captures 16 kHz

    try:
        chunks = get_speech_timestamps(audio, options or DEFAULT_OPTIONS, sampling_rate=sample_rate)
        if not chunks:
            return audio
        segments, _ = collect_chunks(audio, chunks, sampling_rate=sample_rate)
    except Exception as exc:
        print(f"VAD failed ({exc}), transcribing the untrimmed take.")
        return audio

    if not segments:
        return audio
    return np.concatenate(segments)
