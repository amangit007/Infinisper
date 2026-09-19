"""Accuracy with the AI cleanup step running on a local Ollama model, on your own clips.

    python benchmarks/accuracy_local_ollama.py hi
    python benchmarks/accuracy_local_ollama.py hi ollama/gemma4:e4b

Same clips and scoring as accuracy.py. Each clip is transcribed with Qwen3-ASR, then cleaned
up by the model through the app's own cleanup path (cleanup.engine.refine_text_with_model), so
the prompt, the thinking-disabled request and the output safety check are exactly what
dictation uses. Nothing leaves the machine. Ollama must already be running with the model
pulled; the model defaults to the first gemma model in your configured AI models.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, os.getcwd())
import numpy as np

from accuracy import CLIPS, cer, load
from cleanup import engine as cleanup
from config import load_config

OLLAMA_URL = "http://127.0.0.1:11434"  # not "localhost": see docs/benchmarks.md
FALLBACK_MODEL = "ollama/gemma4:e4b"


def default_model() -> str:
    models = [m["model"] for m in load_config().get("cleanup_models", []) if m["model"].startswith("ollama/")]
    return next((m for m in models if "gemma" in m), FALLBACK_MODEL)


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "hi"
    model = sys.argv[2] if len(sys.argv) > 2 else default_model()
    clips_dir = CLIPS / lang
    if not (clips_dir / "references.json").exists():
        sys.exit(f"No clips in {clips_dir}. Record some first: python benchmarks/record_clips.py {lang}")

    from asr.qwen_asr import Qwen3AsrEngine

    qwen = Qwen3AsrEngine()
    refs = json.loads((clips_dir / "references.json").read_text(encoding="utf-8"))
    print(f"Qwen3-ASR -> {model} at {OLLAMA_URL}, thinking disabled, {len(refs)} clips\n")

    # The first request pays for loading the model. The app does this at startup and keeps the
    # model loaded, so it is done here too rather than counted against the first clip.
    cleanup.warm_up_ollama(model, OLLAMA_URL, "30m")

    clips = []
    for name, reference in refs.items():
        audio = load(clips_dir / name)

        started = time.perf_counter()
        raw = qwen.transcribe(audio, 16000)
        asr_seconds = time.perf_counter() - started

        started = time.perf_counter()
        result = cleanup.refine_text_with_model(
            raw, model=model, api_key=None, base_url=OLLAMA_URL, level="basic",
            dictation_language=lang, timeout_seconds=60, keep_alive="30m")
        cleanup_seconds = time.perf_counter() - started

        text = result.text if result.used_model else raw
        clips.append({
            "clip": name, "reference": reference, "raw_asr": raw, "output": text,
            "cleanup_applied": result.used_model, "cleanup_detail": result.detail,
            "cer_raw": round(cer(reference, raw), 4), "cer": round(cer(reference, text), 4),
            "asr_seconds": round(asr_seconds, 2), "cleanup_seconds": round(cleanup_seconds, 2),
        })
        c = clips[-1]
        print(f"{name}  CER {c['cer_raw']:.1%} -> {c['cer']:.1%}   ASR {asr_seconds:.2f}s + cleanup {cleanup_seconds:.2f}s"
              + ("" if result.used_model else f"   [cleanup skipped: {result.detail}]"))

    report = {
        "language": lang,
        "pipeline": f"Qwen3-ASR + {model} cleanup (local, thinking disabled)",
        "mean_cer_raw": round(sum(c["cer_raw"] for c in clips) / len(clips), 4),
        "mean_cer": round(sum(c["cer"] for c in clips) / len(clips), 4),
        "median_cleanup_seconds": float(np.median([c["cleanup_seconds"] for c in clips])),
        "median_total_seconds": float(np.median([c["asr_seconds"] + c["cleanup_seconds"] for c in clips])),
        "clips": clips,
    }
    print(f"\nMean CER {report['mean_cer_raw']:.1%} -> {report['mean_cer']:.1%}   "
          f"median cleanup {report['median_cleanup_seconds']:.2f}s   median total {report['median_total_seconds']:.2f}s")

    out = Path(__file__).parent / f"accuracy_{lang}_ollama.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Full outputs written to {out}")


if __name__ == "__main__":
    main()
