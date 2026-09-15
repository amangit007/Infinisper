import shutil
from pathlib import Path

from asr import nemotron_asr, qwen_asr

ENGINE_ORDER = ["whisper", "qwen3", "nemotron"]

# Pros/cons text is grounded in this project's own benchmarking (see the
# comments in qwen_asr.py / nemotron_asr.py for the numbers this summarizes),
# not marketing copy -- keep it factual when editing.
ENGINES = {
    "whisper": {
        "label": "Whisper",
        "subtitle": "local, offline, default",
        "module": None,
        "size_label": None,  # lives in faster-whisper's own HF cache, not this app's models/
        "languages": "~99 languages",
        "deletable": False,
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Fully offline, no manual download step<br>"
            "&bull; Multiple size presets to trade speed for accuracy<br>"
            "&bull; Used as this app's safety-net fallback everywhere<br>"
            "<br><b>Cons</b><br>"
            "&bull; Batch-only -- no partial results while speaking<br>"
            "&bull; Larger sizes cost more CPU"
        ),
    },
    "qwen3": {
        "label": "Qwen3-ASR (0.6B int8)",
        "subtitle": "local, most accurate, larger",
        "module": qwen_asr,
        "size_label": "~980 MB",
        "languages": "Multilingual",
        "deletable": True,
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Most accurate of the three engines in this app's testing<br>"
            "&bull; Strong multilingual support<br>"
            "&bull; Clean punctuation and casing<br>"
            "<br><b>Cons</b><br>"
            "&bull; Largest download (~980 MB)<br>"
            "&bull; Autoregressive decoding is inherently slower "
            "(~72s to decode a dense clip, even at the benchmarked-optimal 4 threads)<br>"
            "&bull; Batch-only"
        ),
    },
    "nemotron": {
        "label": "Nemotron 3.5 ASR (0.6B streaming)",
        "subtitle": "local, fast + multilingual",
        "module": nemotron_asr,
        "size_label": "~650 MB",
        "languages": "Multilingual, incl. Hindi",
        "deletable": True,
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Fastest decode in this app's testing "
            "(~2s for a 7.2s clip at 4 threads)<br>"
            "&bull; Smallest download (~650 MB)<br>"
            "&bull; Broad multilingual coverage, including Hindi<br>"
            "<br><b>Cons</b><br>"
            "&bull; Fed as one full buffer rather than true live streaming today, "
            "so its latency advantage isn't fully exposed yet<br>"
            "&bull; Needs trailing-silence padding to avoid cutting off the last word "
            "(already handled)<br>"
            "&bull; Occasional language auto-detection misfires, with no way to force "
            "a language through the current integration"
        ),
    },
}


def is_downloaded(engine_id: str) -> bool:
    module = ENGINES[engine_id]["module"]
    if module is None:
        return True  # Whisper has no app-managed download step
    return module.is_downloaded()


def model_dir(engine_id: str) -> Path | None:
    module = ENGINES[engine_id]["module"]
    if module is None:
        return None
    return module.MODEL_DIR


def disk_usage_bytes() -> int:
    """Total bytes used by downloaded (deletable) engine weights -- Whisper is
    excluded, since its cache lives outside this app's own models/ folder."""
    total = 0
    for engine_id, meta in ENGINES.items():
        if not meta["deletable"]:
            continue
        directory = model_dir(engine_id)
        if directory is not None and directory.exists():
            total += sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
    return total


def delete_model(engine_id: str) -> None:
    """Permanently deletes engine_id's downloaded weights, bypassing the
    Recycle Bin. Whisper is not deletable here -- its weights live in
    faster-whisper's own Hugging Face cache, not this app's models/ folder.
    """
    if not ENGINES[engine_id]["deletable"]:
        raise ValueError(f"{engine_id} is not deletable")
    directory = model_dir(engine_id)
    if directory is not None and directory.exists():
        shutil.rmtree(directory)
