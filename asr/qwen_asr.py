
import numpy as np
import sherpa_onnx
from huggingface_hub import snapshot_download

import queue
import threading

from audio import preprocessor as audio_preprocessor
from audio import vad
from utils.paths import get_models_dir

REPO_ID = "cattle12/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
MODEL_DIR = get_models_dir() / "qwen3-asr"
REQUIRED_FILES = ["conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx"]

MIN_STREAM_CHUNK_SECONDS = 3.0
MAX_STREAM_CHUNK_SECONDS = 12.0
PAUSE_TAIL_SECONDS = 0.4


class Qwen3StreamSession:
    """Manages an active recording session for Qwen3-ASR with dynamic catch-up batching.
    
    Consumes live audio chunks during recording, detects natural phrase breath pauses,
    and dispatches speech segments to a background worker. If speech chunks accumulate
    faster than the model can decode, queued chunks are pulled together and decoded in
    a single batched call via `decode_streams()`.
    """

    def __init__(self, recognizer: sherpa_onnx.OfflineRecognizer, sample_rate: int = 16000):
        self._recognizer = recognizer
        self._sample_rate = sample_rate
        self._queue: queue.Queue[np.ndarray | None] = queue.Queue()
        self._buffer: list[np.ndarray] = []
        self._buffered_samples = 0
        self._last_eval_samples = 0
        self._lock = threading.Lock()
        self._hpf = audio_preprocessor.StreamingHighPassFilter(sample_rate=sample_rate, cutoff_hz=80.0)
        self._results: list[str] = []
        self._error: Exception | None = None
        self._aborted = False

        self._worker = threading.Thread(target=self._run, daemon=True)
        self._worker.start()

    def feed_chunk(self, chunk: np.ndarray):
        """Thread-safe chunk consumer called by the audio capture stream."""
        if chunk is None or self._aborted:
            return
        if chunk.ndim > 1:
            chunk = chunk.flatten()
        if chunk.dtype != np.float32:
            chunk = chunk.astype(np.float32)
        chunk = self._hpf.process(chunk)

        with self._lock:
            self._buffer.append(chunk)
            self._buffered_samples += len(chunk)

            # Evaluate segmentation every ~250ms once buffer exceeds MIN_STREAM_CHUNK_SECONDS
            eval_interval_samples = int(self._sample_rate * 0.25)
            if (
                self._buffered_samples >= int(MIN_STREAM_CHUNK_SECONDS * self._sample_rate)
                and (self._buffered_samples - self._last_eval_samples) >= eval_interval_samples
            ):
                self._last_eval_samples = self._buffered_samples
                self._check_and_dispatch_segment()

    def _check_and_dispatch_segment(self):
        """Checks if the accumulated buffer ends with a natural pause or reached max duration."""
        if not self._buffer:
            return

        combined = np.concatenate(self._buffer)
        duration = len(combined) / self._sample_rate
        tail_len = int(PAUSE_TAIL_SECONDS * self._sample_rate)

        # 1. Natural speech pause detection at tail
        if len(combined) > tail_len:
            tail = combined[-tail_len:]
            speech_body = combined[:-tail_len]
            # If tail is silence and preceding body contains speech, cut the segment
            if not audio_preprocessor.has_speech(tail, self._sample_rate) and audio_preprocessor.has_speech(
                speech_body, self._sample_rate
            ):
                self._queue.put(speech_body)
                self._buffer = [tail]
                self._buffered_samples = len(tail)
                self._last_eval_samples = len(tail)
                return

        # 2. Maximum duration reached without pause: force split at lowest energy window
        if duration >= MAX_STREAM_CHUNK_SECONDS:
            sub_chunks = vad.chunk_speech_audio(
                combined, sample_rate=self._sample_rate, max_chunk_duration=MAX_STREAM_CHUNK_SECONDS * 0.6
            )
            if len(sub_chunks) > 1:
                for sc in sub_chunks[:-1]:
                    if audio_preprocessor.has_speech(sc, self._sample_rate):
                        self._queue.put(sc)
                last = sub_chunks[-1]
                self._buffer = [last]
                self._buffered_samples = len(last)
                self._last_eval_samples = len(last)

    def _run(self):
        recognizer = self._recognizer
        sample_rate = self._sample_rate
        try:
            while True:
                chunk = self._queue.get()
                if chunk is None or self._aborted:
                    break

                # Dynamic catch-up batching: gather any additional chunks that
                # queued up while decoding the previous batch.
                batch = [chunk]
                while not self._queue.empty():
                    try:
                        nxt = self._queue.get_nowait()
                        if nxt is None:
                            self._queue.put(None)
                            break
                        batch.append(nxt)
                    except queue.Empty:
                        break

                if len(batch) > 1 and hasattr(recognizer, "decode_streams"):
                    streams = []
                    for b in batch:
                        s = recognizer.create_stream()
                        s.accept_waveform(sample_rate, b)
                        streams.append(s)
                    recognizer.decode_streams(streams)
                    for s in streams:
                        text = s.result.text.strip()
                        if text:
                            self._results.append(text)
                else:
                    for b in batch:
                        s = recognizer.create_stream()
                        s.accept_waveform(sample_rate, b)
                        recognizer.decode_stream(s)
                        text = s.result.text.strip()
                        if text:
                            self._results.append(text)
        except Exception as exc:
            self._error = exc

    def finish(self, timeout: float = 10.0) -> str:
        """Flushes remaining audio, waits for decoding to complete, and returns stitched text."""
        with self._lock:
            if self._buffer:
                remaining = np.concatenate(self._buffer)
                self._buffer = []
                self._buffered_samples = 0
                if audio_preprocessor.has_speech(remaining, self._sample_rate):
                    self._queue.put(remaining)
            self._queue.put(None)

        self._worker.join(timeout=timeout)
        if self._error is not None:
            raise self._error
        return stitch_transcription_chunks(self._results)

    def abort(self):
        """Aborts transcription immediately, discarding pending chunks."""
        self._aborted = True
        with self._lock:
            self._buffer = []
            self._buffered_samples = 0
        while not self._queue.empty():
            try:
                self._queue.get_nowait()
            except queue.Empty:
                break
        self._queue.put(None)


def is_downloaded() -> bool:
    if not (MODEL_DIR / "tokenizer").exists():
        return False
    return all((MODEL_DIR / name).exists() for name in REQUIRED_FILES)


def download(progress_callback=None) -> None:
    """Fetches the ~980 MB Qwen3-ASR int8 export from Hugging Face. Only the
    files actually needed are pulled (not the repo's test_wavs/ etc). Safe to
    call again if a previous download was interrupted -- huggingface_hub
    resumes partial files rather than re-downloading from scratch.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if progress_callback:
        progress_callback("Downloading Qwen3-ASR (~980 MB)...")
    snapshot_download(
        repo_id=REPO_ID,
        local_dir=str(MODEL_DIR),
        allow_patterns=[*REQUIRED_FILES, "tokenizer/*"],
    )


class Qwen3AsrEngine:
    def __init__(self):
        # sherpa-onnx defaults num_threads to 1. Qwen3-ASR's decoder is
        # autoregressive (one token per forward pass, batch=1), so each step's
        # matmuls are tiny -- thread-pool sync overhead swamps the benefit past
        # a handful of threads. Confirmed by benchmarking real speech audio
        # (identical 256-token decode across thread counts, same machine):
        # 1->116s, 2->91s, 4->72s (fastest), 8->110s, 16->158s. More cores made
        # it *slower*, not faster. 4 is a fixed, benchmarked value, not
        # os.cpu_count() -- the optimum here is unrelated to core count.
        # Default max_total_len=512 caps prompt + audio-placeholder tokens + generated
        # tokens combined. A single ~10-15s dictation take can produce 500+ audio
        # tokens on its own, leaving no room for the prompt or the response -- sherpa-onnx
        # then silently truncates the audio and returns garbage (observed: a full sentence
        # collapsed to the single word "Language"). Raised well above what a dictation
        # take needs; confirmed this export isn't hard-capped at 512 (constructs and
        # decodes cleanly at 2048, with no meaningful latency cost). max_new_tokens raised
        # to match, since the default 128 leaves little room for longer dictated sentences
        # once audio tokens eat most of a small budget.
        self._recognizer = sherpa_onnx.OfflineRecognizer.from_qwen3_asr(
            conv_frontend=str(MODEL_DIR / "conv_frontend.onnx"),
            encoder=str(MODEL_DIR / "encoder.int8.onnx"),
            decoder=str(MODEL_DIR / "decoder.int8.onnx"),
            tokenizer=str(MODEL_DIR / "tokenizer"),
            provider="cpu",
            num_threads=4,
            max_total_len=2048,
            max_new_tokens=256,
        )

    def start_stream(self, sample_rate: int = 16000) -> Qwen3StreamSession:
        return Qwen3StreamSession(self._recognizer, sample_rate=sample_rate)

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        chunks = vad.chunk_speech_audio(audio, sample_rate=sample_rate, max_chunk_duration=18.0)
        if not chunks:
            return ""

        if len(chunks) == 1:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, chunks[0])
            self._recognizer.decode_stream(stream)
            return stream.result.text.strip()

        streams = []
        for chunk in chunks:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, chunk)
            streams.append(stream)

        if hasattr(self._recognizer, "decode_streams"):
            self._recognizer.decode_streams(streams)
        else:
            for s in streams:
                self._recognizer.decode_stream(s)

        results = [s.result.text.strip() for s in streams if s.result.text.strip()]
        return stitch_transcription_chunks(results)


def stitch_transcription_chunks(texts: list[str]) -> str:
    """Combines transcribed segments into a coherent sentence, handling spacing and
    avoiding accidental mid-sentence capitalization at chunk seams.
    """
    cleaned = [t.strip() for t in texts if t and t.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    result = cleaned[0]
    for nxt in cleaned[1:]:
        if not nxt:
            continue
        # If preceding text ended with sentence-terminal punctuation (. ! ?), keep capitalization
        ends_terminal = bool(result and result[-1] in ".!?")

        first_word = nxt.split()[0] if nxt.split() else ""
        # Lowercase the first word if it was mid-sentence, unless it's an acronym (e.g. NASA, API)
        # or the pronoun "I" / "I'm" / "I'll".
        should_lowercase = (
            not ends_terminal
            and len(first_word) > 1
            and not first_word.isupper()
            and first_word != "I"
            and not first_word.startswith("I'")
        )

        if should_lowercase:
            nxt_stitched = nxt[0].lower() + nxt[1:]
        else:
            nxt_stitched = nxt

        result = f"{result} {nxt_stitched}"

    return result
