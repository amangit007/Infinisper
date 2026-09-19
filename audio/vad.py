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

# Dedicated options for audio chunking: smaller silence window (300ms) detects
# natural sentence and phrase breath pauses as clean split points.
CHUNKING_VAD_OPTIONS = VadOptions(
    threshold=0.35,
    min_speech_duration_ms=100,
    min_silence_duration_ms=300,
    speech_pad_ms=200,
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


def chunk_speech_audio(
    audio: np.ndarray,
    sample_rate: int = SUPPORTED_SAMPLE_RATE,
    max_chunk_duration: float = 18.0,
    options: VadOptions | None = None,
) -> list[np.ndarray]:
    """Divides `audio` into speech chunks of at most `max_chunk_duration` seconds,
    splitting at natural speech pauses detected by VAD so words are not cut mid-syllable.
    Preserves all audio samples across the chunks.

    Returns `[audio]` immediately for takes under `max_chunk_duration`. Falls back to
    low-energy point splitting if VAD fails or if speech is continuous without pauses.
    """
    if audio is None or len(audio) == 0:
        return []

    max_samples = int(max_chunk_duration * sample_rate)
    if len(audio) <= max_samples:
        return [audio]

    candidate_splits = []
    if sample_rate == SUPPORTED_SAMPLE_RATE:
        try:
            timestamps = get_speech_timestamps(
                audio, options or CHUNKING_VAD_OPTIONS, sampling_rate=sample_rate
            )
            # Silence gaps between detected speech intervals are ideal split points
            for i in range(len(timestamps) - 1):
                gap_start = timestamps[i]["end"]
                gap_end = timestamps[i + 1]["start"]
                if gap_end > gap_start:
                    candidate_splits.append((gap_start + gap_end) // 2)
        except Exception as exc:
            print(f"VAD chunking fallback ({exc})")

    chunks = []
    current_start = 0
    window_samples = int(sample_rate * 0.05)  # 50ms window for energy search

    while len(audio) - current_start > max_samples:
        deadline = current_start + max_samples
        min_progress = current_start + int(max_samples * 0.5)

        # Look for the latest candidate pause in [min_progress, deadline]
        valid_candidates = [pt for pt in candidate_splits if min_progress <= pt <= deadline]

        if valid_candidates:
            split_at = valid_candidates[-1]
        else:
            # Fall back to finding the lowest RMS energy window in [min_progress, deadline]
            search_region = audio[min_progress:deadline]
            num_windows = max(1, (len(search_region) - window_samples) // window_samples)
            if num_windows > 1:
                truncated_len = num_windows * window_samples
                windows = search_region[:truncated_len].reshape(-1, window_samples)
                energies = np.sum(windows ** 2, axis=1)
                best_idx = int(np.argmin(energies))
                split_at = min_progress + (best_idx * window_samples) + (window_samples // 2)
            else:
                split_at = deadline

        chunks.append(audio[current_start:split_at])
        current_start = split_at

    if current_start < len(audio):
        chunks.append(audio[current_start:])

    return chunks

