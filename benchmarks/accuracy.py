"""Accuracy on clips you recorded with record_clips.py, scored against what you actually said.

    python benchmarks/accuracy.py hi

Reports character error rate (CER) -- the standard measure for Hindi and other languages
where word boundaries are less reliable than characters. Lower is better; 0% is perfect.
Audio goes through the same cleanup the app applies before transcription.
"""

import json
import os
import re
import sys
import time
import unicodedata
import wave
from pathlib import Path

sys.path.insert(0, os.getcwd())
import numpy as np

from audio import preprocessor, vad
from config import load_config
from credentials import get_api_key
from cleanup import engine as cleanup

CLIPS = Path(__file__).parent / "clips"


def load(path: Path) -> np.ndarray:
    with wave.open(str(path)) as w:
        pcm = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16)
    audio = pcm.astype(np.float32) / 32768
    audio = preprocessor.clean_speech_audio(audio, 16000, click_at_seconds=0)
    return preprocessor.normalize_audio(vad.trim_to_speech(audio, 16000))


def normalise(text: str) -> str:
    text = unicodedata.normalize("NFC", text).lower()
    text = "".join(" " if unicodedata.category(c).startswith("P") else c for c in text)
    return re.sub(r"\s+", " ", text).strip()


def edit_distance(a, b) -> int:
    prev = list(range(len(b) + 1))
    for i, x in enumerate(a, 1):
        cur = [i]
        for j, y in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (x != y)))
        prev = cur
    return prev[-1]


def cer(reference: str, hypothesis: str) -> float:
    ref, hyp = normalise(reference), normalise(hypothesis)
    return edit_distance(ref, hyp) / max(len(ref), 1)


def audio_model():
    config = load_config()
    models = [m for m in config.get("cleanup_models", []) if m.get("supports_audio")]
    chosen = next((m for m in models if "flash-lite" in m["model"]), models[0] if models else None)
    if chosen is None:
        return None
    provider = next(p for p in config["cleanup_providers"] if p["id"] == chosen["provider_id"])
    return {"model": chosen["model"], "api_key": get_api_key(provider["id"]), "base_url": provider.get("base_url")}


# Pause between hosted-model requests, to stay under free-tier rate limits. It happens
# after the clip is timed, so it doesn't count toward the seconds reported.
CLOUD_PAUSE_SECONDS = 4


def build_systems(lang: str):
    from faster_whisper import WhisperModel
    from asr.nemotron_asr import NemotronAsrEngine
    from asr.qwen_asr import Qwen3AsrEngine

    whisper = WhisperModel("base", device="cpu", compute_type="int8")
    nemotron = NemotronAsrEngine()
    qwen = Qwen3AsrEngine()
    gemini = audio_model()

    def run_whisper(audio, language):
        segments, _ = whisper.transcribe(audio, language=language, beam_size=5, temperature=0.0, vad_filter=False)
        return "".join(s.text for s in segments).strip()

    systems = {
        "Whisper, language auto-detected": lambda a: run_whisper(a, None),
        f"Whisper, language set to {lang}": lambda a: run_whisper(a, lang),
        "Nemotron": lambda a: nemotron.transcribe(a, 16000, language=lang),
        "Qwen3-ASR": lambda a: qwen.transcribe(a, 16000),
    }
    if gemini:
        name = gemini["model"].split("/")[-1]

        def gemini_audio(a):
            r = cleanup.transcribe_audio_with_model(
                a, 16000, level="basic", dictation_language=lang, timeout_seconds=60, **gemini)
            return r.text if r.used_model else f"[failed: {r.detail}]"

        def qwen_then_gemini(a):
            raw = qwen.transcribe(a, 16000)
            r = cleanup.refine_text_with_model(
                raw, level="basic", dictation_language=lang, timeout_seconds=60, **gemini)
            return r.text if r.used_model else raw

        systems[f"{name}, audio sent directly"] = gemini_audio
        systems[f"Qwen3-ASR + {name} cleanup"] = qwen_then_gemini
    return systems, {label for label in systems if "gemini" in label.lower()}


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "hi"
    scored_dir, mixed_dir = CLIPS / lang, CLIPS / f"{lang}-mixed"
    if not (scored_dir / "references.json").exists():
        sys.exit(f"No clips in {scored_dir}. Record some first: python benchmarks/record_clips.py {lang}")

    systems, cloud = build_systems(lang.split("-")[0])
    report = {"language": lang, "systems": {}}
    for label, run in systems.items():
        print(f"-- {label}", flush=True)
        entry = {"clips": [], "mixed": []}
        for folder, key in ((scored_dir, "clips"), (mixed_dir, "mixed")):
            refs_path = folder / "references.json"
            if not refs_path.exists():
                continue
            for name, reference in json.loads(refs_path.read_text(encoding="utf-8")).items():
                audio = load(folder / name)
                t = time.perf_counter()
                text = run(audio)
                item = {"clip": name, "reference": reference, "output": text,
                        "seconds": round(time.perf_counter() - t, 2)}
                if label in cloud:
                    time.sleep(CLOUD_PAUSE_SECONDS)
                if key == "clips":
                    item["cer"] = round(cer(reference, text), 4)
                entry[key].append(item)
        cers = [c["cer"] for c in entry["clips"]]
        entry["mean_cer"] = round(sum(cers) / len(cers), 4) if cers else None
        entry["median_seconds"] = float(np.median([c["seconds"] for c in entry["clips"]])) if entry["clips"] else None
        report["systems"][label] = entry
        print(f"   CER {entry['mean_cer']:.1%}   median {entry['median_seconds']} s", flush=True)

    out = Path(__file__).parent / f"accuracy_{lang}.json"
    out.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\nFull outputs written to {out}")


if __name__ == "__main__":
    main()
