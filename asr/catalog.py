import os
import shutil
from pathlib import Path

from asr import nemotron_asr, qwen_asr
from utils.paths import get_bundle_dir, get_models_dir

ENGINE_ORDER = ["whisper", "nemotron", "qwen3"]

WHISPER_SIZES = ["tiny", "base", "small", "medium", "large-v3-turbo", "large-v3"]

MODELS = {
    "whisper-tiny": {
        "engine_id": "whisper",
        "size": "tiny",
        "label": "Whisper Tiny",
        "subtitle": "local, ultra-fast, minimal RAM",
        "size_label": "~75 MB",
        "expected_bytes": 75 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-tiny",
        "deletable": True,
        "color": "#38BDF8",  # Sky Blue
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Smallest Whisper model (~75 MB)<br>"
            "&bull; Fastest CPU inference with lowest RAM footprint<br>"
            "<br><b>Cons</b><br>"
            "&bull; Lower accuracy on accents and noisy audio"
        ),
    },
    "whisper-base": {
        "engine_id": "whisper",
        "size": "base",
        "label": "Whisper Base",
        "subtitle": "local, balanced speed & accuracy",
        "size_label": "~145 MB",
        "expected_bytes": 145 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-base",
        "deletable": True,
        "color": "#0078D4",  # Windows Accent Blue
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Excellent balance of speed and everyday accuracy<br>"
            "&bull; Lightweight download (~145 MB)<br>"
            "<br><b>Cons</b><br>"
            "&bull; May mishear niche technical terminology"
        ),
    },
    "whisper-small": {
        "engine_id": "whisper",
        "size": "small",
        "label": "Whisper Small",
        "subtitle": "local, higher accuracy",
        "size_label": "~460 MB",
        "expected_bytes": 460 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-small",
        "deletable": True,
        "color": "#818CF8",  # Indigo
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Significantly higher accuracy across multiple languages<br>"
            "&bull; Better punctuation and capitalization<br>"
            "<br><b>Cons</b><br>"
            "&bull; Moderate CPU usage (~460 MB download)"
        ),
    },
    "whisper-medium": {
        "engine_id": "whisper",
        "size": "medium",
        "label": "Whisper Medium",
        "subtitle": "local, high accuracy",
        "size_label": "~1.5 GB",
        "expected_bytes": 1500 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-medium",
        "deletable": True,
        "color": "#A855F7",  # Purple
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Strong Whisper accuracy on diverse speakers and terminology<br>"
            "<br><b>Cons</b><br>"
            "&bull; Large download (~1.5 GB), noticeably slower on older CPUs"
        ),
    },
    "whisper-large-v3-turbo": {
        "engine_id": "whisper",
        "size": "large-v3-turbo",
        "label": "Whisper Large v3 Turbo",
        "subtitle": "local, near-Large accuracy at 4x speed",
        "size_label": "~1.6 GB",
        "expected_bytes": 1600 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-large-v3-turbo",
        "deletable": True,
        "color": "#EC4899",  # Pink
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; OpenAI's optimized 4-layer decoder architecture<br>"
            "&bull; Retains ~95%+ accuracy of Large-v3 with 4x-6x faster CPU decode<br>"
            "<br><b>Cons</b><br>"
            "&bull; Requires ~2.5 GB RAM and ~1.6 GB storage"
        ),
    },
    "whisper-large-v3": {
        "engine_id": "whisper",
        "size": "large-v3",
        "label": "Whisper Large v3",
        "subtitle": "local, maximum accuracy benchmark",
        "size_label": "~3.1 GB",
        "expected_bytes": 3100 * 1024 * 1024,
        "languages": "~99 languages",
        "repo_id": "Systran/faster-whisper-large-v3",
        "deletable": True,
        "color": "#F43F5E",  # Rose
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Absolute highest Whisper benchmark accuracy on tough audio<br>"
            "&bull; Best handling of heavy accents and background noise<br>"
            "<br><b>Cons</b><br>"
            "&bull; Very large download (~3.1 GB)<br>"
            "&bull; High CPU and RAM usage (~4-5 GB RAM); slow on non-GPU systems"
        ),
    },
    "nemotron": {
        "engine_id": "nemotron",
        "size": "0.6b",
        "label": "Nemotron 3.5 ASR (0.6B streaming)",
        "subtitle": "local, real-time live streaming",
        "size_label": "~650 MB",
        "expected_bytes": 650 * 1024 * 1024,
        "languages": "Multilingual, incl. Hindi",
        "repo_id": "csukuangfj2/sherpa-onnx-nemotron-3.5-asr-streaming-0.6b-1120ms-int8-2026-06-11",
        "deletable": True,
        "module": nemotron_asr,
        "color": "#10B981",  # Emerald
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Fastest decode (~2s for a 7.2s clip)<br>"
            "&bull; Live background streaming decodes audio in real time as you speak<br>"
            "&bull; Broad multilingual coverage including Hindi<br>"
            "<br><b>Cons</b><br>"
            "&bull; Fixed language auto-detection"
        ),
    },
    "qwen3": {
        "engine_id": "qwen3",
        "size": "0.6b",
        "label": "Qwen3-ASR (0.6B int8)",
        "subtitle": "local, highly accurate multilingual",
        "size_label": "~980 MB",
        "expected_bytes": 980 * 1024 * 1024,
        "languages": "Multilingual",
        "repo_id": "cattle12/sherpa-onnx-qwen3-asr-0.6B-int8-2026-03-25",
        "deletable": True,
        "module": qwen_asr,
        "color": "#F59E0B",  # Amber
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Highly accurate multilingual transcription<br>"
            "&bull; Clean punctuation and casing<br>"
            "<br><b>Cons</b><br>"
            "&bull; Largest download (~980 MB)<br>"
            "&bull; Autoregressive decode is slower on older CPUs"
        ),
    },
}

MODEL_ORDER = [
    "whisper-tiny",
    "whisper-base",
    "whisper-small",
    "whisper-medium",
    "whisper-large-v3-turbo",
    "whisper-large-v3",
    "nemotron",
    "qwen3",
]

# Legacy engine metadata map kept for compatibility with existing settings & UI
ENGINES = {
    "whisper": {
        "label": "Whisper",
        "subtitle": "local, offline speech recognition",
        "module": None,
        "size_label": "Multiple sizes",
        "languages": "~99 languages",
        "deletable": True,
        "info_html": (
            "<b>Pros</b><br>"
            "&bull; Fully offline on this device<br>"
            "&bull; Multiple size presets (Tiny to Medium) to trade speed for accuracy<br>"
            "<br><b>Cons</b><br>"
            "&bull; Batch-only -- decodes upon releasing the hotkey"
        ),
    },
    "qwen3": MODELS["qwen3"],
    "nemotron": MODELS["nemotron"],
}


def whisper_model_dir(size: str) -> Path:
    """Directory where a specific Whisper model variant is stored."""
    return get_models_dir() / "whisper" / size


def _hf_cache_dir(size: str) -> Path | None:
    """Checks if model files exist in the global Hugging Face hub cache."""
    hf_hub = Path.home() / ".cache" / "huggingface" / "hub" / f"models--Systran--faster-whisper-{size}"
    snapshots = hf_hub / "snapshots"
    if snapshots.exists():
        for snap in snapshots.iterdir():
            if snap.is_dir() and ((snap / "model.bin").exists() or (snap / "model.safetensors").exists()):
                return snap
    return None


def get_whisper_model_path(size: str) -> str:
    """Returns the local path to the Whisper model files, or size fallback."""
    local_dir = whisper_model_dir(size)
    if local_dir.exists() and any(local_dir.iterdir()):
        return str(local_dir)

    cached = _hf_cache_dir(size)
    if cached is not None:
        return str(cached)

    return size


def get_model_info(model_or_engine_id: str) -> dict:
    """Returns metadata dictionary for a model or engine ID."""
    if model_or_engine_id in MODELS:
        return MODELS[model_or_engine_id]
    if model_or_engine_id in ENGINES:
        return ENGINES[model_or_engine_id]
    if model_or_engine_id in WHISPER_SIZES:
        return MODELS[f"whisper-{model_or_engine_id}"]
    raise KeyError(f"Unknown model or engine '{model_or_engine_id}'")


def is_downloaded(model_or_engine_id: str) -> bool:
    """Returns True if the specified model or engine is downloaded locally."""
    if model_or_engine_id == "whisper":
        return any(is_downloaded(f"whisper-{size}") for size in WHISPER_SIZES)

    if model_or_engine_id in WHISPER_SIZES:
        model_or_engine_id = f"whisper-{model_or_engine_id}"

    if model_or_engine_id.startswith("whisper-"):
        size = model_or_engine_id.removeprefix("whisper-")
        local_dir = whisper_model_dir(size)
        if local_dir.exists() and (
            (local_dir / "model.bin").exists()
            or (local_dir / "model.safetensors").exists()
            or (local_dir / "config.json").exists()
        ):
            return True
        return _hf_cache_dir(size) is not None

    if model_or_engine_id == "nemotron":
        return nemotron_asr.is_downloaded()

    if model_or_engine_id == "qwen3":
        return qwen_asr.is_downloaded()

    return False


def has_any_model_downloaded() -> bool:
    """True if at least one ASR speech model is installed on the machine."""
    return any(is_downloaded(m_id) for m_id in MODEL_ORDER)


def model_dir(model_or_engine_id: str) -> Path | None:
    """Returns local filesystem directory where model weights reside."""
    if model_or_engine_id in WHISPER_SIZES:
        model_or_engine_id = f"whisper-{model_or_engine_id}"

    if model_or_engine_id.startswith("whisper-"):
        size = model_or_engine_id.removeprefix("whisper-")
        local_path = whisper_model_dir(size)
        if local_path.exists() and any(local_path.iterdir()):
            return local_path
        cached = _hf_cache_dir(size)
        if cached is not None:
            return cached
        return local_path

    if model_or_engine_id == "nemotron":
        return nemotron_asr.MODEL_DIR

    if model_or_engine_id == "qwen3":
        return qwen_asr.MODEL_DIR

    return None


def get_model_size_bytes(model_or_engine_id: str) -> int:
    """Calculates disk space occupied by a model in bytes."""
    directory = model_dir(model_or_engine_id)
    if directory is not None and directory.exists():
        try:
            return sum(f.stat().st_size for f in directory.rglob("*") if f.is_file())
        except Exception:
            return 0
    return 0


def delete_model(model_or_engine_id: str) -> None:
    """Permanently deletes downloaded model files."""
    if model_or_engine_id in WHISPER_SIZES:
        model_or_engine_id = f"whisper-{model_or_engine_id}"

    if model_or_engine_id == "whisper":
        for size in WHISPER_SIZES:
            delete_model(f"whisper-{size}")
        return

    directory = model_dir(model_or_engine_id)
    if directory is not None and directory.exists():
        shutil.rmtree(directory, ignore_errors=True)

    # If it was also in HuggingFace cache for whisper, clean that snapshot too
    if model_or_engine_id.startswith("whisper-"):
        size = model_or_engine_id.removeprefix("whisper-")
        hf_cache = _hf_cache_dir(size)
        if hf_cache is not None and hf_cache.exists():
            shutil.rmtree(hf_cache.parent.parent, ignore_errors=True)


def disk_usage_bytes() -> int:
    """Total bytes used by all downloaded speech models."""
    total = 0
    for model_id in MODEL_ORDER:
        total += get_model_size_bytes(model_id)
    return total


def get_base_application_size_bytes() -> int:
    """Approximates base application executable/runtime footprint on disk."""
    from utils.paths import is_frozen

    if not is_frozen():
        return 145 * 1024 * 1024

    bundle = get_bundle_dir()
    models_root = get_models_dir()
    total = 0
    try:
        for root, dirs, files in os.walk(bundle):
            if Path(root).is_relative_to(models_root):
                continue
            for f in files:
                try:
                    total += (Path(root) / f).stat().st_size
                except Exception:
                    pass
    except Exception:
        pass
    return max(total, 140 * 1024 * 1024)


def get_disk_breakdown() -> list[dict]:
    """Provides a detailed breakdown of all disk usage components for the hover pie chart."""
    breakdown = []

    # 1. Base application files
    base_bytes = get_base_application_size_bytes()
    breakdown.append({
        "id": "base_app",
        "name": "Base Application",
        "category": "core",
        "size_bytes": base_bytes,
        "color": "#64748B",  # Slate
        "description": "App executable, Python runtime & Qt UI",
    })

    # 2. Downloaded models
    for model_id in MODEL_ORDER:
        meta = MODELS[model_id]
        size_bytes = get_model_size_bytes(model_id)
        if size_bytes > 0:
            breakdown.append({
                "id": model_id,
                "name": meta["label"],
                "category": "model",
                "size_bytes": size_bytes,
                "color": meta.get("color", "#0078D4"),
                "description": f"Speech model ({meta['size_label']})",
            })

    return breakdown
