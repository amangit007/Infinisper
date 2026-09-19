from pathlib import Path

import numpy as np
import sherpa_onnx
from huggingface_hub import snapshot_download

from audio import vad

REPO_ID = "cattle12/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25"
MODEL_DIR = Path(__file__).parent.parent / "models" / "qwen3-asr"
REQUIRED_FILES = ["conv_frontend.onnx", "encoder.int8.onnx", "decoder.int8.onnx"]


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

    def transcribe(self, audio: np.ndarray, sample_rate: int) -> str:
        chunks = vad.chunk_speech_audio(audio, sample_rate=sample_rate, max_chunk_duration=18.0)
        if not chunks:
            return ""

        if len(chunks) == 1:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, chunks[0])
            self._recognizer.decode_stream(stream)
            return stream.result.text.strip()

        results = []
        for chunk in chunks:
            stream = self._recognizer.create_stream()
            stream.accept_waveform(sample_rate, chunk)
            self._recognizer.decode_stream(stream)
            text = stream.result.text.strip()
            if text:
                results.append(text)

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
