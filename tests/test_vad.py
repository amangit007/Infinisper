import numpy as np
import pytest

from audio import vad

SR = 16000


def speech_like(seconds=2.0, amplitude=0.08):
    t = np.arange(int(seconds * SR)) / SR
    tone = sum(np.sin(2 * np.pi * 140 * k * t) / k for k in (1, 2, 3, 4))
    envelope = 0.6 + 0.4 * np.sin(2 * np.pi * 3 * t)
    return (tone * envelope * amplitude).astype(np.float32)


def test_silence_around_speech_is_trimmed_away():
    silence = np.zeros(int(1.5 * SR), dtype=np.float32)
    take = np.concatenate([silence, speech_like(2.0), silence])

    trimmed = vad.trim_to_speech(take, SR)

    assert 0 < len(trimmed) < len(take)
    # The 3 s of silence must be gone; allow for speech_pad_ms either side.
    assert len(trimmed) < len(take) - int(2.0 * SR)


def test_a_take_of_pure_silence_is_returned_unchanged():
    """The caller already decided this take was worth transcribing. Emptying it here
    would lose it outright, so finding no speech must mean 'hand it over untouched'."""
    silence = np.zeros(3 * SR, dtype=np.float32)
    assert np.array_equal(vad.trim_to_speech(silence, SR), silence)


def test_non_speech_noise_is_returned_unchanged():
    noise = (np.random.default_rng(0).normal(0, 0.05, 3 * SR)).astype(np.float32)
    assert np.array_equal(vad.trim_to_speech(noise, SR), noise)


def test_unsupported_sample_rate_is_passed_through():
    audio = speech_like(1.0)
    assert np.array_equal(vad.trim_to_speech(audio, 8000), audio)
    assert np.array_equal(vad.trim_to_speech(audio, 44100), audio)


def test_empty_and_none_inputs_are_safe():
    empty = np.array([], dtype=np.float32)
    assert len(vad.trim_to_speech(empty, SR)) == 0
    assert vad.trim_to_speech(None, SR) is None


def test_output_is_never_longer_than_input():
    take = np.concatenate([np.zeros(SR, dtype=np.float32), speech_like(1.5)])
    assert len(vad.trim_to_speech(take, SR)) <= len(take)


def test_vad_failure_falls_back_to_the_untrimmed_take(monkeypatch):
    """A broken or missing VAD model must cost the transcription quality, not the take."""
    def boom(*args, **kwargs):
        raise RuntimeError("silero exploded")

    monkeypatch.setattr(vad, "get_speech_timestamps", boom)
    audio = speech_like(1.0)
    assert np.array_equal(vad.trim_to_speech(audio, SR), audio)


def test_warm_up_is_safe_to_call():
    vad.warm_up()
    # Still working afterwards, and now without the first-call model load.
    assert len(vad.trim_to_speech(speech_like(0.5), SR)) > 0


def test_options_match_the_parameters_whisper_already_used():
    """These were faster-whisper's vad_parameters on the Whisper path. Keeping them
    identical is what makes moving VAD in front of every engine a no-op for Whisper."""
    assert vad.DEFAULT_OPTIONS.threshold == pytest.approx(0.35)
    assert vad.DEFAULT_OPTIONS.min_speech_duration_ms == 100
    assert vad.DEFAULT_OPTIONS.min_silence_duration_ms == 1500
    assert vad.DEFAULT_OPTIONS.speech_pad_ms == 400


def test_chunk_speech_audio_short_take_is_unchanged():
    audio = speech_like(5.0)
    chunks = vad.chunk_speech_audio(audio, SR, max_chunk_duration=18.0)
    assert len(chunks) == 1
    assert np.array_equal(chunks[0], audio)


def test_chunk_speech_audio_empty_and_none():
    assert vad.chunk_speech_audio(None, SR) == []
    assert vad.chunk_speech_audio(np.array([], dtype=np.float32), SR) == []


def test_chunk_speech_audio_long_take_splits_within_duration():
    # 40s of speech-like audio
    long_audio = np.tile(speech_like(2.0), 20)
    chunks = vad.chunk_speech_audio(long_audio, SR, max_chunk_duration=18.0)
    assert len(chunks) > 1
    max_samples = int(18.0 * SR)
    for c in chunks:
        assert len(c) <= max_samples
        assert len(c) > 0


def test_chunk_speech_audio_fallback_on_vad_failure(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("VAD boom")

    monkeypatch.setattr(vad, "get_speech_timestamps", boom)
    long_audio = np.tile(speech_like(2.0), 15)  # 30s
    chunks = vad.chunk_speech_audio(long_audio, SR, max_chunk_duration=18.0)
    assert len(chunks) > 1
    for c in chunks:
        assert len(c) <= int(18.0 * SR)

