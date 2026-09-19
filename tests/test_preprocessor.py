import time

import numpy as np
import pytest

from audio import preprocessor as p

SR = 16000
PREROLL = 0.5


def reference_high_pass(audio, sample_rate=16000, cutoff_hz=80.0):
    """The original per-sample loop, kept here as the definition of correct. The
    vectorised implementation must agree with it."""
    rc = 1.0 / (2.0 * np.pi * cutoff_hz)
    dt = 1.0 / sample_rate
    alpha = rc / (rc + dt)
    out = np.empty_like(audio)
    out[0] = audio[0]
    for i in range(1, len(audio)):
        out[i] = alpha * (out[i - 1] + audio[i] - audio[i - 1])
    return out


def speech_like(seconds=2.0, amplitude=0.08, sample_rate=SR):
    """A voiced-sounding signal: a 140 Hz fundamental with harmonics, amplitude
    modulated at 3 Hz so it has syllable-scale envelope rather than a flat tone."""
    t = np.arange(int(seconds * sample_rate)) / sample_rate
    tone = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in (1, 2, 3, 4))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 3 * t)
    return (tone * envelope * amplitude).astype(np.float32)


def take_with_click(speech, click_amplitude=0.8, preroll=PREROLL, sample_rate=SR):
    """A realistic take: pre-roll silence, the hotkey click at the boundary where
    recording starts, then speech."""
    pre = (np.random.default_rng(0).normal(0, 0.0004, int(preroll * sample_rate))).astype(np.float32)
    audio = np.concatenate([pre, speech])
    audio[len(pre)] = click_amplitude
    audio[len(pre) + 1] = -click_amplitude * 0.7
    return audio, len(pre)


# --- fix 3: vectorised high-pass filter ------------------------------------------


@pytest.mark.parametrize("seconds", [0.05, 0.5, 3.0])
def test_high_pass_matches_reference_loop(seconds):
    audio = speech_like(seconds)
    assert np.allclose(p.high_pass_filter(audio, SR), reference_high_pass(audio, SR), atol=1e-6)


def test_high_pass_matches_reference_across_block_seam():
    # Long enough to span several _HPF_BLOCK boundaries, which is where a carry bug
    # between blocks would show up and a single-block test would miss it.
    audio = speech_like(1.0)
    assert len(audio) > p._HPF_BLOCK * 3
    assert np.allclose(p.high_pass_filter(audio, SR), reference_high_pass(audio, SR), atol=1e-6)


def test_high_pass_attenuates_below_cutoff_and_passes_above():
    t = np.arange(SR) / SR
    low = np.sin(2 * np.pi * 20 * t).astype(np.float32)   # 20 Hz, well below the 80 Hz corner
    high = np.sin(2 * np.pi * 1000 * t).astype(np.float32)  # 1 kHz, well above it

    def rms(x):
        return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))

    assert rms(p.high_pass_filter(low, SR)) < 0.3 * rms(low)
    assert rms(p.high_pass_filter(high, SR)) > 0.9 * rms(high)


def test_high_pass_is_fast_enough_for_a_long_take():
    audio = speech_like(30.0)
    start = time.perf_counter()
    p.high_pass_filter(audio, SR)
    elapsed_ms = (time.perf_counter() - start) * 1000
    # The per-sample loop took ~134 ms here and this takes ~6 ms. The limit is loose enough
    # for a slow CI runner, and still well under what the loop would cost on one.
    assert elapsed_ms < 60, f"high_pass_filter took {elapsed_ms:.1f} ms on a 30 s take"


def test_high_pass_handles_empty_and_single_sample():
    assert len(p.high_pass_filter(np.array([], dtype=np.float32), SR)) == 0
    assert p.high_pass_filter(np.array([0.5], dtype=np.float32), SR)[0] == pytest.approx(0.5)


def test_high_pass_preserves_dtype():
    assert p.high_pass_filter(speech_like(0.2), SR).dtype == np.float32


def test_streaming_high_pass_matches_batch_filter():
    audio = speech_like(5.0)
    ref = p.high_pass_filter(audio, SR)

    for chunk_size in [128, 800, 1024, 1500]:
        flt = p.StreamingHighPassFilter(SR, cutoff_hz=80.0)
        chunks = [audio[i : i + chunk_size] for i in range(0, len(audio), chunk_size)]
        filtered = [flt.process(c) for c in chunks]
        assembled = np.concatenate(filtered)
        assert np.allclose(assembled, ref, atol=1e-5), f"Failed for chunk_size {chunk_size}"


def test_streaming_high_pass_reset():
    flt = p.StreamingHighPassFilter(SR)
    flt.process(speech_like(0.5))
    assert flt.initialized is True
    flt.reset()
    assert flt.initialized is False
    assert flt.x_prev == 0.0
    assert flt.y_prev == 0.0


def test_streaming_high_pass_empty_and_none():
    flt = p.StreamingHighPassFilter(SR)
    assert flt.process(None) is None
    assert len(flt.process(np.array([], dtype=np.float32))) == 0


# --- fix 1: click suppression at the pre-roll boundary ---------------------------


def test_click_at_preroll_boundary_is_suppressed():
    audio, click_index = take_with_click(speech_like(1.0))
    before = abs(float(audio[click_index]))
    after = abs(float(p.suppress_transient_click(audio, SR, click_at_seconds=PREROLL)[click_index]))
    assert before > 0.7
    assert after < before * 0.05, f"click only fell from {before:.3f} to {after:.3f}"


def test_click_suppression_preserves_speech_outside_the_notch():
    speech = speech_like(1.0)
    audio, click_index = take_with_click(speech)
    result = p.suppress_transient_click(audio, SR, click_at_seconds=PREROLL)

    # Everything beyond the notch half-width must be untouched.
    guard = int(SR * p.CLICK_NOTCH_MS / 1000.0)
    assert np.allclose(result[click_index + guard :], audio[click_index + guard :])
    assert np.allclose(result[: click_index - guard], audio[: click_index - guard])


def test_clean_take_without_a_click_is_left_alone():
    speech = speech_like(1.0)
    pre = np.zeros(int(PREROLL * SR), dtype=np.float32)
    audio = np.concatenate([pre, speech])
    assert np.array_equal(p.suppress_transient_click(audio, SR, click_at_seconds=PREROLL), audio)


def test_loud_speech_is_not_mistaken_for_a_click():
    loud = speech_like(1.0, amplitude=0.5)
    pre = (np.random.default_rng(1).normal(0, 0.0004, int(PREROLL * SR))).astype(np.float32)
    audio = np.concatenate([pre, loud])
    assert np.array_equal(p.suppress_transient_click(audio, SR, click_at_seconds=PREROLL), audio)


def test_click_suppression_follows_a_short_preroll():
    """The first take after launch has a partial pre-roll, so the click is not at the
    nominal 0.5 s. Targeting the wrong offset is the bug this whole fix was about."""
    short = 0.15
    audio, click_index = take_with_click(speech_like(1.0), preroll=short)
    suppressed = p.suppress_transient_click(audio, SR, click_at_seconds=short)
    assert abs(float(suppressed[click_index])) < 0.05

    # Aimed at the old, wrong offset the click survives -- which is what used to happen.
    missed = p.suppress_transient_click(audio, SR, click_at_seconds=PREROLL)
    assert abs(float(missed[click_index])) == pytest.approx(abs(float(audio[click_index])))


def test_click_suppression_handles_out_of_range_positions():
    audio = speech_like(0.2)
    assert np.array_equal(p.suppress_transient_click(audio, SR, click_at_seconds=99.0), audio)
    assert np.array_equal(p.suppress_transient_click(audio, SR, click_at_seconds=0.0), audio)
    empty = np.array([], dtype=np.float32)
    assert len(p.suppress_transient_click(empty, SR, click_at_seconds=PREROLL)) == 0


# --- fix 2: RMS normalisation robust to transients -------------------------------


def rms(x):
    return float(np.sqrt(np.mean(x.astype(np.float64) ** 2)))


def test_quiet_speech_is_brought_up_to_target_level():
    quiet = speech_like(2.0, amplitude=0.01)
    assert rms(p.normalize_audio(quiet)) == pytest.approx(p.TARGET_RMS, rel=0.15)


def test_one_click_no_longer_collapses_the_gain():
    """The regression this fix exists for. Peak normalisation gave quiet speech 1.2x
    where it needed 48x, purely because one click held the peak."""
    quiet = speech_like(2.0, amplitude=0.01)
    with_click = quiet.copy()
    with_click[100] = 0.8

    clean_gain = rms(p.normalize_audio(quiet)) / rms(quiet)
    clicked_gain = rms(p.normalize_audio(with_click)) / rms(with_click)
    assert clicked_gain > clean_gain * 0.5, (
        f"one transient still cut the gain from {clean_gain:.1f}x to {clicked_gain:.1f}x"
    )


def test_normalisation_respects_the_ceiling():
    quiet = speech_like(2.0, amplitude=0.005)
    out = p.normalize_audio(quiet)
    assert float(np.max(np.abs(out))) <= 1.0
    assert float(np.percentile(np.abs(out), p.LOUD_PERCENTILE)) <= p.CEILING + 1e-6


def test_normalisation_caps_gain_so_static_is_not_amplified():
    static = (np.random.default_rng(2).normal(0, 1e-6, SR)).astype(np.float32)
    out = p.normalize_audio(static)
    assert rms(out) / max(rms(static), 1e-12) <= p.MAX_GAIN * 1.01


def test_normalisation_leaves_digital_silence_alone():
    silence = np.zeros(SR, dtype=np.float32)
    assert np.array_equal(p.normalize_audio(silence), silence)
    assert len(p.normalize_audio(np.array([], dtype=np.float32))) == 0


def test_normalisation_does_not_reduce_already_loud_speech_below_target():
    loud = speech_like(2.0, amplitude=0.4)
    assert rms(p.normalize_audio(loud)) == pytest.approx(p.TARGET_RMS, rel=0.2)


# --- the three fixes together ----------------------------------------------------


def test_whispered_take_with_a_click_ends_up_audible():
    """End to end on the exact scenario that was broken: a whispered take whose
    hotkey click both survived suppression and then cancelled the gain."""
    whisper = speech_like(2.0, amplitude=0.008)
    audio, click_index = take_with_click(whisper, click_amplitude=0.8)

    out = p.preprocess_speech_audio(audio, SR, click_at_seconds=PREROLL)

    assert abs(float(out[click_index])) < 0.1, "click survived the pipeline"
    speech_region = out[click_index + int(0.1 * SR) :]
    assert rms(speech_region) > 0.03, f"speech left at RMS {rms(speech_region):.4f}, still too quiet"
    assert float(np.max(np.abs(out))) <= 1.0


def test_clean_speech_audio_does_not_normalise():
    """Normalisation belongs after VAD trimming, so this stage must leave level alone."""
    quiet = speech_like(1.0, amplitude=0.01)
    audio, _ = take_with_click(quiet)
    cleaned = p.clean_speech_audio(audio, SR, click_at_seconds=PREROLL)
    assert rms(cleaned) < 0.05, "clean_speech_audio should not be changing the level"


def test_pipeline_handles_empty_input():
    empty = np.array([], dtype=np.float32)
    assert len(p.preprocess_speech_audio(empty, SR)) == 0
    assert len(p.clean_speech_audio(empty, SR)) == 0
    assert p.preprocess_speech_audio(None, SR) is None
