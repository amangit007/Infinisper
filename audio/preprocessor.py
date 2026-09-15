import numpy as np

# Minimum RMS below which audio is pure silence / room noise (at 16 kHz float32)
# Lowered from the old 0.005 to 0.001 to support soft voices and whispered dictation.
MIN_SPEECH_RMS = 0.001

# Pre-emphasis factor to boost high frequencies (consonant clarity: /s/, /t/, /k/, /th/)
PRE_EMPHASIS_COEFF = 0.95

# Target RMS for normalisation (~ -20 dBFS), the conventional operating level for
# speech fed into a neural ASR encoder.
TARGET_RMS = 0.1

# Normalisation must not drive the loud end of the take past this.
CEILING = 0.99

# Both the ceiling check and the click detector measure "how loud is this take" at a
# high percentile rather than at max(|x|). A single sample -- one hotkey click, one
# desk bump -- must never stand in for the level of the whole recording.
LOUD_PERCENTILE = 99.9

# Ceiling on normalisation gain, so a take of pure static is not amplified to it.
MAX_GAIN = 100.0

# Click detector: how far either side of the pre-roll boundary to look, how much of
# the signal to attenuate once found, and how far above LOUD_PERCENTILE a sample must
# sit before it counts as a transient rather than as speech.
CLICK_SEARCH_MS = 60.0
CLICK_NOTCH_MS = 24.0
CLICK_PROMINENCE = 2.5

# high_pass_filter evaluates its recurrence in blocks this size; see the note there.
_HPF_BLOCK = 1024


def remove_dc_offset(audio: np.ndarray) -> np.ndarray:
    """Removes DC bias and microphone baseline drift."""
    if len(audio) == 0:
        return audio
    return audio - np.mean(audio)


def high_pass_filter(audio: np.ndarray, sample_rate: int = 16000, cutoff_hz: float = 80.0) -> np.ndarray:
    """Simple 1-pole high-pass filter (IIR) to remove low-frequency mechanical
    rumble, desk vibrations, and AC/fan hum below 80 Hz.

    Same recurrence a per-sample loop would evaluate -- y[n] = a*(y[n-1] + x[n] -
    x[n-1]) -- but computed with numpy. Expanding it gives y[n] = a**n * cumsum(b[k] *
    a**-k), except a**-k overflows float64 somewhere past 22000 samples, so the sum is
    taken in blocks with y carried across the seam. The loop version cost 208 ms on a
    30 s take, which is a third of the app's entire latency budget spent inside one
    filter; this is the same filter at a few hundred microseconds.
    """
    if len(audio) == 0:
        return audio
    # RC filter coefficient: alpha = RC / (RC + dt)
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)

    x = audio.astype(np.float64, copy=False)

    # Drives the recurrence: b[0] is what makes y[0] == x[0], and thereafter
    # b[n] = a*(x[n] - x[n-1]) is the per-step input to y[n] = a*y[n-1] + b[n].
    b = np.empty(len(x), dtype=np.float64)
    b[0] = x[0]
    np.subtract(x[1:], x[:-1], out=b[1:])
    b[1:] *= alpha

    powers = alpha ** np.arange(_HPF_BLOCK)
    inverse = 1.0 / powers

    filtered = np.empty(len(x), dtype=np.float64)
    carry = 0.0  # y[n-1] crossing in from the previous block
    for start in range(0, len(x), _HPF_BLOCK):
        block = b[start : start + _HPF_BLOCK]
        count = len(block)
        scale = powers[:count]
        segment = scale * np.cumsum(block * inverse[:count])
        segment += (carry * alpha) * scale
        filtered[start : start + count] = segment
        carry = segment[-1]

    return filtered.astype(audio.dtype, copy=False)


def apply_pre_emphasis(audio: np.ndarray, coeff: float = PRE_EMPHASIS_COEFF) -> np.ndarray:
    """Applies a first-order FIR pre-emphasis filter: y[t] = x[t] - coeff * x[t-1].
    
    In slow or whispered speech, vowel fundamentals swamp higher-frequency formants.
    Pre-emphasis restores the consonant-to-vowel energy ratio so acoustic models
    can distinguish subtle consonants like /p/, /t/, /k/, /ch/, /s/.
    """
    if len(audio) <= 1:
        return audio
    return np.append(audio[0], audio[1:] - coeff * audio[:-1])


def suppress_transient_click(
    audio: np.ndarray,
    sample_rate: int = 16000,
    click_at_seconds: float = 0.5,
    search_ms: float = CLICK_SEARCH_MS,
    notch_ms: float = CLICK_NOTCH_MS,
) -> np.ndarray:
    """Attenuates the mechanical hotkey click made by pressing the dictation combo,
    so a sharp transient cannot corrupt a streaming transducer's initial cache states
    or pin the level normalisation that runs after it.

    The click lands where the pre-roll buffer ends and live recording begins, NOT at
    sample 0: capture.start_recording() seeds each take with up to PREROLL_SECONDS of
    already-buffered audio, so at the default 0.5 s pre-roll the keypress sits around
    sample 8000. Pass the pre-roll length actually used -- it is shorter than the
    nominal 0.5 s for the first take after launch, before the ring buffer has filled.

    An earlier version faded the first 80 ms instead, which only ever attenuated
    pre-roll silence and left the click itself completely untouched; the surviving
    click then capped peak normalisation, cancelling the gain that quiet speech
    needed. Fires only when the boundary really does hold a transient, so a quiet
    keyboard costs no audio.
    """
    if len(audio) == 0 or click_at_seconds <= 0:
        return audio

    center = int(click_at_seconds * sample_rate)
    if center >= len(audio):
        return audio

    search = int(sample_rate * search_ms / 1000.0)
    low = max(0, center - search)
    high = min(len(audio), center + search)
    if high <= low:
        return audio

    magnitude = np.abs(audio)
    reference = float(np.percentile(magnitude, LOUD_PERCENTILE))
    window = magnitude[low:high]
    offset = int(np.argmax(window))
    if reference < 1e-9 or float(window[offset]) < reference * CLICK_PROMINENCE:
        return audio  # nothing at the boundary stands out as a transient

    peak = low + offset
    half = max(1, int(sample_rate * notch_ms / 1000.0) // 2)
    start = max(0, peak - half)
    end = min(len(audio), peak + half)
    if end - start < 2:
        return audio

    # Raised cosine: unity at both edges, zero at the transient itself. A rectangular
    # gate would remove the click and introduce two discontinuities of its own.
    ramp = np.linspace(0.0, 1.0, end - start)
    notch = 0.5 * (1.0 + np.cos(2.0 * np.pi * ramp))

    result = audio.copy()
    result[start:end] *= notch.astype(audio.dtype, copy=False)
    return result


def normalize_audio(
    audio: np.ndarray,
    target_rms: float = TARGET_RMS,
    max_gain: float = MAX_GAIN,
    ceiling: float = CEILING,
) -> np.ndarray:
    """Brings the take to a consistent speech level (~ -20 dBFS RMS) so a quiet or
    whispered voice sits inside the model's active range instead of down at the noise
    floor.

    Driven by RMS, not by max(|x|). Dividing by the peak let one transient decide the
    gain for the entire take: measured on a quiet recording with a single hotkey click
    in it, the speech received 1.2x where it needed 48x -- so the app's "robust on low
    voices" behaviour was being cancelled by the very click it had failed to remove.
    RMS barely moves for a handful of samples. The ceiling check uses a high
    percentile for the same reason; a lone sample above it is clipped, which is the
    intent, rather than being allowed to hold the whole take down.

    Best called after the audio has been trimmed to speech, so the level is measured
    over speech rather than over speech plus silence.
    """
    if len(audio) == 0:
        return audio

    rms = float(np.sqrt(np.mean(audio.astype(np.float64) ** 2)))
    if rms < 1e-7:
        return audio

    gain = min(target_rms / rms, max_gain)

    loud = float(np.percentile(np.abs(audio), LOUD_PERCENTILE))
    if loud > 1e-9 and loud * gain > ceiling:
        gain = ceiling / loud

    return np.clip(audio * gain, -1.0, 1.0).astype(audio.dtype, copy=False)


def has_speech(audio: np.ndarray, sample_rate: int = 16000, threshold: float = MIN_SPEECH_RMS) -> bool:
    """Returns True if any short 100ms window exceeds the minimum speech threshold.
    
    Uses 100ms windows so short utterances ("Yes", "OK") aren't averaged out by
    surrounding silence/pre-roll.
    """
    if len(audio) == 0:
        return False
    window = max(1, int(sample_rate * 0.1))
    if len(audio) <= window:
        return float(np.sqrt(np.mean(np.square(audio)))) >= threshold
    trimmed = audio[: len(audio) - (len(audio) % window)]
    window_rms = np.sqrt(np.mean(np.square(trimmed.reshape(-1, window)), axis=1))
    return float(window_rms.max()) >= threshold


def clean_speech_audio(
    audio: np.ndarray, sample_rate: int = 16000, click_at_seconds: float = 0.5
) -> np.ndarray:
    """Everything that should happen before the take is trimmed to speech:
    1. Remove DC bias
    2. High-pass filter (>80 Hz) to eliminate desk/fan rumble
    3. Suppress the mechanical hotkey click at the pre-roll boundary

    Level normalisation is deliberately NOT here -- it belongs after trimming, so the
    level is measured over speech rather than over speech plus silence.
    """
    if audio is None or len(audio) == 0:
        return audio

    clean = remove_dc_offset(audio)
    clean = high_pass_filter(clean, sample_rate=sample_rate, cutoff_hz=80.0)
    return suppress_transient_click(
        clean, sample_rate=sample_rate, click_at_seconds=click_at_seconds
    )


def preprocess_speech_audio(
    audio: np.ndarray, sample_rate: int = 16000, click_at_seconds: float = 0.5
) -> np.ndarray:
    """clean_speech_audio() plus normalisation, for callers that are not doing their
    own speech trimming in between the two."""
    if audio is None or len(audio) == 0:
        return audio
    return normalize_audio(
        clean_speech_audio(audio, sample_rate=sample_rate, click_at_seconds=click_at_seconds)
    )
