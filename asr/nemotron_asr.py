import queue
import threading

import numpy as np
import sherpa_onnx
from huggingface_hub import snapshot_download

from audio import preprocessor as audio_preprocessor
from utils.paths import get_models_dir

REPO_ID = "csukuangfj2/sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8-2026-06-11"
MODEL_DIR = get_models_dir() / "nemotron-3.5-asr"
REQUIRED_FILES = ["tokens.txt", "encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx"]

# Trailing silence padding to ensure the final chunk is fully decoded.
TAIL_PADDING_SECONDS = 1.2


class NemotronStreamSession:
    """Manages an active real-time streaming recognition session on a background thread.
    Consumes incoming audio chunks via a thread-safe queue so the PortAudio thread is never blocked."""

    def __init__(self, recognizer: sherpa_onnx.OnlineRecognizer, sample_rate: int = 16000, language: str = "en"):
        self._recognizer = recognizer
        self._sample_rate = sample_rate
        self._stream = recognizer.create_stream()
        if language:
            try:
                self._stream.set_option("language", language)
            except Exception:
                pass
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._hpf = audio_preprocessor.StreamingHighPassFilter(sample_rate=sample_rate, cutoff_hz=80.0)
        self._result = ""
        self._error: Exception | None = None
        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def feed_chunk(self, chunk: np.ndarray):
        """Thread-safe, non-blocking chunk enqueue."""
        if chunk is not None:
            if chunk.ndim > 1:
                chunk = chunk.flatten()
            self._queue.put(chunk)

    def _run(self):
        recognizer = self._recognizer
        stream = self._stream
        sample_rate = self._sample_rate
        try:
            while True:
                chunk = self._queue.get()
                if chunk is None:
                    break
                if chunk.ndim > 1:
                    chunk = chunk.flatten()
                if chunk.dtype != np.float32:
                    chunk = chunk.astype(np.float32)
                chunk = self._hpf.process(chunk)
                stream.accept_waveform(sample_rate, chunk)
                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

            # Feed trailing silence to ensure the last 1120ms chunk completes
            # and final consonants/words are not clipped.
            chunk_size = max(1, int(sample_rate * 0.1))
            tail = np.zeros(int(TAIL_PADDING_SECONDS * sample_rate), dtype=np.float32)
            for i in range(0, len(tail), chunk_size):
                stream.accept_waveform(sample_rate, tail[i : i + chunk_size])
                while recognizer.is_ready(stream):
                    recognizer.decode_stream(stream)

            stream.input_finished()
            while recognizer.is_ready(stream):
                recognizer.decode_stream(stream)

            self._result = recognizer.get_result(stream).strip()
        except Exception as exc:
            self._error = exc

    def finish(self, timeout: float = 3.0) -> str:
        """Stops the stream, waits for the background worker to finish final decoding,
        and returns the transcribed text."""
        self._queue.put(None)
        self._worker.join(timeout=timeout)
        if self._error is not None:
            raise self._error
        return self._result

    def abort(self):
        """Discards the stream if the take was aborted."""
        self._queue.put(None)


def is_downloaded() -> bool:
    return all((MODEL_DIR / name).exists() for name in REQUIRED_FILES)


def download(progress_callback=None) -> None:
    """Fetches the ~650 MB Nemotron 3.5 ASR streaming int8 export from Hugging
    Face. Safe to call again if a previous download was interrupted --
    huggingface_hub resumes partial files rather than re-downloading from scratch.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback("Downloading Nemotron 3.5 ASR (~650 MB)...")
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(MODEL_DIR),
        allow_patterns=REQUIRED_FILES,
    )


class NemotronAsrEngine:
    def __init__(self):
        # num_threads=4 benchmarked as fastest on real speech audio for this
        # model (7.2s clip: 1t=3.9s, 2t=2.6s, 4t=2.0s) -- the pip-installed
        # sherpa_onnx is a CPU-only build, so provider="cuda" silently falls
        # back to cpu rather than erroring; real GPU support would need
        # building sherpa-onnx from source with CUDA.
        # feature_dim=128 and model_type='nemotron' are required by this
        # ONNX export's FastConformer-RNNT architecture.
        self._recognizer = sherpa_onnx.OnlineRecognizer.from_transducer(
            tokens=str(MODEL_DIR / "tokens.txt"),
            encoder=str(MODEL_DIR / "encoder.int8.onnx"),
            decoder=str(MODEL_DIR / "decoder.int8.onnx"),
            joiner=str(MODEL_DIR / "joiner.int8.onnx"),
            model_type="nemotron",
            feature_dim=128,
            sample_rate=16000,
            decoding_method="greedy_search",
            provider="cpu",
            num_threads=4,
        )

    def start_stream(self, sample_rate: int = 16000, language: str = "en") -> NemotronStreamSession:
        return NemotronStreamSession(self._recognizer, sample_rate=sample_rate, language=language)

    def transcribe(self, audio: np.ndarray, sample_rate: int, language: str = "en") -> str:
        stream = self._recognizer.create_stream()
        if language:
            try:
                stream.set_option("language", language)
            except Exception:
                pass

        # Stream audio in ~100ms chunks so the cache-aware encoder updates its
        # temporal state naturally as speech progresses.
        chunk_size = max(1, int(sample_rate * 0.1))
        for i in range(0, len(audio), chunk_size):
            chunk = audio[i : i + chunk_size]
            stream.accept_waveform(sample_rate, chunk)
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)

        # Feed trailing silence to ensure the last 1120ms chunk completes
        # and final consonants/words are not clipped.
        tail = np.zeros(int(TAIL_PADDING_SECONDS * sample_rate), dtype=np.float32)
        for i in range(0, len(tail), chunk_size):
            stream.accept_waveform(sample_rate, tail[i : i + chunk_size])
            while self._recognizer.is_ready(stream):
                self._recognizer.decode_stream(stream)

        stream.input_finished()
        while self._recognizer.is_ready(stream):
            self._recognizer.decode_stream(stream)
        return self._recognizer.get_result(stream).strip()
