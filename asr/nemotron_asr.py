from pathlib import Path

import numpy as np
import sherpa_onnx
from huggingface_hub import snapshot_download

REPO_ID = "csukuangfj2/sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8-2026-06-11"
MODEL_DIR = Path(__file__).parent.parent / "models" / "nemotron-3.5-asr"
REQUIRED_FILES = ["tokens.txt", "encoder.int8.onnx", "decoder.int8.onnx", "joiner.int8.onnx"]

# This export's cache-aware streaming encoder chunks audio in 1120ms windows (see
# the repo name and its README). The tail of a recording doesn't fill a full
# chunk, and without enough trailing silence to complete one, the last word(s)
# come back truncated (observed on a real clip: "...fifty pieces of co" with
# under a second of padding). Padded slightly above the model's own chunk size
# rather than sherpa-onnx's generic 0.66s example padding, which predates this
# specific chunk-size export and isn't guaranteed sufficient for it.
TAIL_PADDING_SECONDS = 1.2


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
