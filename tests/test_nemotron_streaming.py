import time
import numpy as np
import pytest

from asr import nemotron_asr
from audio import capture as audio_capture
from dictation import paste
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings


def test_chunk_listener_lifecycle():
    """Verifies that audio_capture's chunk listener is called during recording and stops when cleared."""
    received = []

    def dummy_listener(chunk):
        received.append(chunk)

    audio_capture.set_chunk_listener(dummy_listener)
    
    # When not recording, _audio_callback should not dispatch to listener
    fake_chunk = np.zeros(audio_capture.BLOCK_SIZE, dtype=np.float32)
    audio_capture._audio_callback(fake_chunk, len(fake_chunk), None, None)
    assert len(received) == 0

    # Start recording
    audio_capture.start_recording()
    audio_capture._audio_callback(fake_chunk, len(fake_chunk), None, None)
    assert len(received) == 1

    # Stop recording should clear the listener automatically
    audio_capture.stop_recording()
    audio_capture._audio_callback(fake_chunk, len(fake_chunk), None, None)
    assert len(received) == 1

    # Clear manually test
    audio_capture.set_chunk_listener(dummy_listener)
    audio_capture.clear_chunk_listener()
    assert audio_capture._chunk_listener is None


@pytest.mark.skipif(not nemotron_asr.is_downloaded(), reason="Nemotron model not downloaded")
def test_nemotron_streaming_session_lifecycle():
    """Tests the real NemotronStreamSession with synthetic audio chunks."""
    engine = nemotron_asr.NemotronAsrEngine()
    session = engine.start_stream(sample_rate=16000, language="en")

    # Feed 10 chunks of 50ms silence with shape (800, 1) to match sounddevice format
    chunk_2d = np.zeros((800, 1), dtype=np.float32)
    for _ in range(10):
        session.feed_chunk(chunk_2d)

    t0 = time.perf_counter()
    result = session.finish(timeout=5.0)
    elapsed_ms = (time.perf_counter() - t0) * 1000

    # Verify result is string and finalization finishes quickly
    assert isinstance(result, str)
    assert elapsed_ms < 2000.0
    assert not session._worker.is_alive()


@pytest.mark.skipif(not nemotron_asr.is_downloaded(), reason="Nemotron model not downloaded")
def test_nemotron_streaming_session_abort():
    """Tests that aborting a NemotronStreamSession cleans up worker thread without error."""
    engine = nemotron_asr.NemotronAsrEngine()
    session = engine.start_stream(sample_rate=16000, language="en")

    session.feed_chunk(np.zeros(800, dtype=np.float32))
    session.abort()
    session._worker.join(timeout=2.0)
    assert not session._worker.is_alive()


def test_whisper_and_qwen_unaffected_by_streaming_hooks(monkeypatch):
    """Ensures Whisper and Qwen3 engines never activate or depend on the Nemotron streaming session."""
    monkeypatch.setattr(paste, "pyperclip", type("P", (), {
        "paste": staticmethod(lambda: ""),
        "copy": staticmethod(lambda text: None),
    }))
    monkeypatch.setattr(paste, "keyboard", type("K", (), {"send": staticmethod(lambda combo: None)}))
    pipeline = Pipeline(Settings(use_asr=True, use_cleanup=False), Runtime(active_engine="whisper"))

    # 1. Test Whisper mode
    fake_chip = type("C", (), {"set_state": lambda s, state: None})()
    fake_tray = type("T", (), {"set_status": lambda s, status: None})()

    pipeline.start_recording(fake_chip, fake_tray)
    assert pipeline.runtime.stream_session is None
    assert audio_capture._chunk_listener is None
    audio_capture.stop_recording()

    # 2. Test Qwen3 mode
    pipeline.runtime.active_engine = "qwen3"
    pipeline.runtime.qwen3 = type("Q", (), {})()
    pipeline.start_recording(fake_chip, fake_tray)
    assert pipeline.runtime.stream_session is None
    assert audio_capture._chunk_listener is None
    audio_capture.stop_recording()
