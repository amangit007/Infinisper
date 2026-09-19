import queue
import time
import numpy as np
import pytest

from asr import qwen_asr
from audio import capture as audio_capture
from dictation import paste
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings


class FakeStreamResult:
    def __init__(self, text: str):
        self.text = text


class FakeStream:
    def __init__(self, text_to_return: str):
        self.text_to_return = text_to_return
        self.result = FakeStreamResult(text_to_return)
        self.waveforms: list[np.ndarray] = []

    def accept_waveform(self, sample_rate: int, chunk: np.ndarray):
        self.waveforms.append(chunk)


class MockRecognizerWithBatching:
    def __init__(self, texts: list[str]):
        self.texts = list(texts)
        self.stream_count = 0
        self.decoded_single_streams: list[FakeStream] = []
        self.decoded_batches: list[list[FakeStream]] = []

    def create_stream(self):
        text = self.texts[min(self.stream_count, len(self.texts) - 1)]
        self.stream_count += 1
        return FakeStream(text)

    def decode_stream(self, stream: FakeStream):
        self.decoded_single_streams.append(stream)

    def decode_streams(self, streams: list[FakeStream]):
        self.decoded_batches.append(list(streams))


def test_qwen_stream_session_lifecycle():
    rec = MockRecognizerWithBatching(["Hello world."])
    session = qwen_asr.Qwen3StreamSession(rec, sample_rate=16000)

    # Synthetic tone (speech-like energy) 16000 samples (1s)
    t = np.linspace(0, 1.0, 16000, dtype=np.float32)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)

    session.feed_chunk(tone)
    text = session.finish(timeout=3.0)

    assert text == "Hello world."
    assert not session._worker.is_alive()


def test_qwen_stream_session_dynamic_catchup_batching():
    """Verifies that when multiple chunks accumulate in the queue,
    the worker executes them in a single batch using decode_streams."""
    rec = MockRecognizerWithBatching(["First part.", "Second part."])
    session = qwen_asr.Qwen3StreamSession(rec, sample_rate=16000)

    t = np.linspace(0, 1.0, 16000, dtype=np.float32)
    tone1 = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    tone2 = (0.2 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)

    # Enqueue two chunks at once to simulate backlog
    session._queue.put(tone1)
    session._queue.put(tone2)

    text = session.finish(timeout=3.0)
    assert len(rec.decoded_batches) >= 1
    # Verify the batch contained multiple streams
    assert len(rec.decoded_batches[0]) == 2
    assert "First part. Second part." in text


def test_qwen_stream_session_abort():
    rec = MockRecognizerWithBatching(["Should be cancelled."])
    session = qwen_asr.Qwen3StreamSession(rec, sample_rate=16000)

    t = np.linspace(0, 1.0, 16000, dtype=np.float32)
    tone = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    session.feed_chunk(tone)

    session.abort()
    session._worker.join(timeout=2.0)
    assert not session._worker.is_alive()


def test_pipeline_qwen_streaming_integration(monkeypatch):
    """Verifies that the pipeline starts and finalizes a Qwen3 stream session."""
    fake_chip = type("C", (), {"set_state": lambda s, state: None, "update_audio_level": lambda s, lvl: None})()
    fake_tray = type("T", (), {"set_status": lambda s, status: None})()

    monkeypatch.setattr(paste, "paste_text", lambda text, steps: None)

    class FakeQwen3Engine:
        def __init__(self):
            self.session_started = False

        def start_stream(self, sample_rate=16000):
            self.session_started = True
            rec = MockRecognizerWithBatching(["Transcribed via stream."])
            return qwen_asr.Qwen3StreamSession(rec, sample_rate=sample_rate)

        def transcribe(self, audio, sample_rate):
            return "Transcribed via fallback buffer."

    qwen_engine = FakeQwen3Engine()
    pipeline = Pipeline(
        Settings(use_asr=True, use_cleanup=False),
        Runtime(active_engine="qwen3", qwen3=qwen_engine),
    )

    # 1. Start recording
    pipeline.start_recording(fake_chip, fake_tray)
    assert qwen_engine.session_started is True
    assert pipeline.runtime.stream_session is not None
    assert audio_capture._chunk_listener is not None

    # Feed a simulated chunk with speech energy through listener
    t = np.linspace(0, 0.5, 8000, dtype=np.float32)
    tone_chunk = (0.2 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    audio_capture._audio_callback(tone_chunk, len(tone_chunk), None, None)

    # 2. Stop recording
    audio = pipeline.stop_recording()
    assert audio_capture._chunk_listener is None

    # 3. Run ASR
    outcome = pipeline.run_asr(audio)
    assert outcome.source == "Qwen3"
    assert outcome.text == "Transcribed via stream."
    assert pipeline.runtime.stream_session is None
