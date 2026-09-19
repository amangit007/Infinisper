"""Speed, memory and multilingual spot-check for the three speech engines.

Run from the repo root with the models already downloaded:

    python benchmarks/engines.py            # all engines
    python benchmarks/engines.py nemotron   # one engine

Each engine runs in its own process so memory figures don't bleed into each other.
Uses the sample clips that ship with the Nemotron download (models/nemotron-3.5-asr/test_wavs).
"""

import ctypes
import ctypes.wintypes as wt
import json
import os
import subprocess
import sys
import time
import wave

sys.path.insert(0, os.getcwd())
import numpy as np

CLIPS = "models/nemotron-3.5-asr/test_wavs/"
ENGINES = ("whisper", "nemotron", "qwen3")
LANGUAGES = ("fr", "de", "es", "zh", "ja")


class _MemoryCounters(ctypes.Structure):
    _fields_ = [("cb", wt.DWORD), ("PageFaultCount", wt.DWORD)] + [
        (name, ctypes.c_size_t)
        for name in ("PeakWorkingSetSize", "WorkingSetSize", "a", "b", "c", "d",
                     "PagefileUsage", "PeakPagefileUsage")
    ]


def working_set_mb() -> float:
    kernel32, psapi = ctypes.windll.kernel32, ctypes.windll.psapi
    kernel32.GetCurrentProcess.restype = wt.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(_MemoryCounters), wt.DWORD]
    counters = _MemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    psapi.GetProcessMemoryInfo(kernel32.GetCurrentProcess(), ctypes.byref(counters), counters.cb)
    return counters.WorkingSetSize / 2**20


def load_wav(path: str) -> np.ndarray:
    with wave.open(path) as w:
        rate, channels = w.getframerate(), w.getnchannels()
        audio = np.frombuffer(w.readframes(w.getnframes()), dtype=np.int16).astype(np.float32) / 32768
    if channels > 1:
        audio = audio.reshape(-1, channels).mean(axis=1)
    if rate != 16000:
        # Linear resample -- crude, but no extra dependency, and the clips are only a spot check.
        times = np.arange(0, len(audio) / rate, 1 / 16000)
        audio = np.interp(times, np.arange(len(audio)) / rate, audio).astype(np.float32)
    return audio


def speech_of_length(seconds: float, sample: np.ndarray) -> np.ndarray:
    """Repeats the English sample with half-second gaps until it's `seconds` long."""
    gap = np.zeros(8000, np.float32)
    unit = np.concatenate([sample, gap])
    reps = int(np.ceil(seconds * 16000 / len(unit)))
    return np.concatenate([unit] * reps)[: int(seconds * 16000)]


def load_engine(name: str):
    import faster_whisper  # noqa: F401 -- import runtimes first so memory reflects the model
    import sherpa_onnx  # noqa: F401

    if name == "whisper":
        from faster_whisper import WhisperModel
        model = WhisperModel("base", device="cpu", compute_type="int8")

        def transcribe(audio, language=None):
            segments, _ = model.transcribe(audio, language=language, beam_size=5,
                                           temperature=0.0, vad_filter=False)
            return "".join(s.text for s in segments).strip()
        return model, transcribe
    if name == "nemotron":
        from asr.nemotron_asr import NemotronAsrEngine
        model = NemotronAsrEngine()
        return model, lambda audio, language="en": model.transcribe(audio, 16000, language=language or "en")
    from asr.qwen_asr import Qwen3AsrEngine
    model = Qwen3AsrEngine()
    return model, lambda audio, language=None: model.transcribe(audio, 16000)


def run_one(name: str) -> dict:
    english = load_wav(CLIPS + "en.wav")
    baseline = working_set_mb()
    started = time.perf_counter()
    model, transcribe = load_engine(name)
    result = {"engine": name, "load_s": round(time.perf_counter() - started, 2)}
    transcribe(english[:16000])  # warm-up
    result["model_mb"] = round(working_set_mb() - baseline)

    result["batch_s"] = {}
    for seconds in (5, 10, 30, 60):
        audio = speech_of_length(seconds, english)
        runs = 3 if seconds <= 10 else 1
        times = []
        for _ in range(runs):
            t = time.perf_counter()
            transcribe(audio)
            times.append(time.perf_counter() - t)
        result["batch_s"][seconds] = round(min(times), 3)

    if name == "nemotron":
        # Feed audio at real-time pace in 50 ms chunks, exactly as the microphone does,
        # then time only what's left after "key release".
        result["stream_finalize_s"] = {}
        for seconds in (5, 10, 30):
            audio = speech_of_length(seconds, english)
            session = model.start_stream(16000, "en")
            step, t0 = 800, time.perf_counter()
            for i in range(0, len(audio), step):
                session.feed_chunk(audio[i : i + step].copy())
                wait = t0 + (i + step) / 16000 - time.perf_counter()
                if wait > 0:
                    time.sleep(wait)
            t = time.perf_counter()
            session.finish(timeout=30)
            result["stream_finalize_s"][seconds] = round(time.perf_counter() - t, 3)

    result["transcripts"] = {"en": transcribe(english)}
    for lang in LANGUAGES:
        audio = load_wav(CLIPS + f"{lang}.wav")
        result["transcripts"][lang] = transcribe(audio, lang if name == "nemotron" else None)
    return result


if __name__ == "__main__":
    if len(sys.argv) > 2 and sys.argv[1] == "--one":
        print("RESULT" + json.dumps(run_one(sys.argv[2]), ensure_ascii=False))
        sys.exit()

    wanted = sys.argv[1:] or ENGINES
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for name in wanted:
        proc = subprocess.run([sys.executable, __file__, "--one", name], capture_output=True,
                              text=True, encoding="utf-8", env=env)
        line = next((l for l in proc.stdout.splitlines() if l.startswith("RESULT")), None)
        if line is None:
            print(f"{name}: failed\n{proc.stderr[-800:]}")
            continue
        print(json.dumps(json.loads(line[6:]), ensure_ascii=False, indent=2))
