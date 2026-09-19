"""End-to-end timings for AI cleanup: text-only, audio-direct, and speech engine + cleanup.

Uses whatever providers and models you've configured in the app (config.json + keys in
Windows Credential Manager). Run from the repo root:

    python benchmarks/pipeline.py

Sends the public English sample clip and two fixed text passages to each configured
provider -- nothing from your own history. Cloud requests are spaced out to stay inside
free-tier rate limits.
"""

import json
import os
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.getcwd())
sys.path.insert(0, os.path.dirname(__file__))

import litellm

from config import load_config
from credentials import get_api_key
from cleanup import engine
from engines import CLIPS, load_wav

LEVEL = "advanced"
RUNS = 3
CLOUD_GAP_S = 4.0

SHORT_TEXT = "the tribal chieftain called for the boy and presented him with fifty pieces of gold"
LONG_TEXT = (
    "so um I wanted to give you a quick update on the release uh we finished the migration "
    "yesterday and the tests are passing now but there's still like two things left one is the "
    "login page which is loading slowly on mobile and the other is the export button which "
    "sometimes fails for large files so I think we can ship on thursday if we fix those by "
    "wednesday evening let me know if that works for you"
)


def configured_models():
    config = load_config()
    providers = {p["id"]: p for p in config.get("cleanup_providers", [])}
    for m in config.get("cleanup_models", []):
        provider = providers.get(m["provider_id"])
        if provider is None:
            continue
        yield {
            "label": m["model"],
            "model": m["model"],
            "provider": m["provider_id"],
            "api_key": get_api_key(m["provider_id"]),
            "base_url": provider.get("base_url"),
            "audio": bool(m.get("supports_audio")),
        }


def unload_ollama(model: str, base_url: str):
    name = model.removeprefix("ollama/")
    body = json.dumps({"model": name, "keep_alive": 0}).encode()
    req = urllib.request.Request(base_url.rstrip("/") + "/api/generate", data=body,
                                 headers={"Content-Type": "application/json"})
    urllib.request.urlopen(req, timeout=30).read()
    time.sleep(1.0)


def timed_refine(m, text):
    t = time.perf_counter()
    r = engine.refine_text_with_model(
        text, model=m["model"], api_key=m["api_key"], base_url=m["base_url"], level=LEVEL,
        timeout_seconds=90)
    return time.perf_counter() - t, r


def timed_audio(m, audio):
    t = time.perf_counter()
    r = engine.transcribe_audio_with_model(
        audio, 16000, model=m["model"], api_key=m["api_key"], base_url=m["base_url"],
        level=LEVEL, timeout_seconds=90)
    return time.perf_counter() - t, r


def median_of(fn, pause):
    times, last, failures = [], None, 0
    for _ in range(RUNS):
        elapsed, result = fn()
        if result.used_model:
            times.append(elapsed)
            last = result.text
        else:
            failures += 1
            last = f"[fell back: {result.detail}]"
        time.sleep(pause)
    return (round(statistics.median(times), 3) if times else None), last, failures


def stream_nemotron(nemotron, audio):
    """Feeds audio at real-time pace like the microphone, returns (text, finalize_seconds)."""
    session = nemotron.start_stream(16000, "en")
    t0 = time.perf_counter()
    for i in range(0, len(audio), 800):
        session.feed_chunk(audio[i : i + 800].copy())
        wait = t0 + (i + 800) / 16000 - time.perf_counter()
        if wait > 0:
            time.sleep(wait)
    t = time.perf_counter()
    text = session.finish(timeout=30)
    return text, time.perf_counter() - t


def main():
    english = load_wav(CLIPS + "en.wav")
    models = list(configured_models())
    results = []

    from asr.nemotron_asr import NemotronAsrEngine
    nemotron = NemotronAsrEngine()
    nemotron.transcribe(english[:16000], 16000)

    for m in models:
        is_local = m["provider"] == "ollama"
        pause = 0.2 if is_local else CLOUD_GAP_S
        row = {"model": m["label"], "local": is_local}
        print(f"-- {m['label']}", flush=True)

        if is_local:
            unload_ollama(m["model"], m["base_url"])
            elapsed, r = timed_refine(m, SHORT_TEXT)
            row["cold_first_s"] = round(elapsed, 3) if r.used_model else None
        else:
            timed_refine(m, SHORT_TEXT)  # connection warm-up, not counted
            time.sleep(pause)

        row["text_short_s"], row["short_output"], f1 = median_of(lambda: timed_refine(m, SHORT_TEXT), pause)
        row["text_long_s"], row["long_output"], f2 = median_of(lambda: timed_refine(m, LONG_TEXT), pause)

        # Full pipeline: speak, release, Nemotron finalizes, cleanup runs. Paste (~10 ms) excluded.
        totals = []
        for _ in range(RUNS):
            raw, finalize = stream_nemotron(nemotron, english)
            elapsed, r = timed_refine(m, raw)
            if r.used_model:
                totals.append(finalize + elapsed)
            time.sleep(pause)
        row["pipeline_nemotron_s"] = round(statistics.median(totals), 3) if totals else None

        if m["audio"]:
            row["audio_direct_s"], row["audio_output"], f3 = median_of(lambda: timed_audio(m, english), pause)
        row["failures"] = f1 + f2
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)

    # Two claims from the performance guide, measured rather than asserted.
    extras = {}
    ollama = next((m for m in models if m["provider"] == "ollama" and "qwen3.5" in m["model"]), None)
    if ollama:
        def raw_call(base, think):
            kwargs = {"model": ollama["model"], "api_base": base, "timeout": 120, "num_retries": 0,
                      "temperature": 0.0,
                      "messages": [{"role": "system", "content": "Clean up this dictated text. Output only the text."},
                                   {"role": "user", "content": LONG_TEXT}]}
            if not think:
                kwargs["reasoning_effort"] = "none"
            t = time.perf_counter()
            litellm.completion(**kwargs)
            return time.perf_counter() - t
        raw_call("http://127.0.0.1:11434", False)  # make sure it's loaded
        extras["thinking_on_s"] = round(statistics.median(raw_call("http://127.0.0.1:11434", True) for _ in range(RUNS)), 3)
        extras["thinking_off_s"] = round(statistics.median(raw_call("http://127.0.0.1:11434", False) for _ in range(RUNS)), 3)
        extras["via_localhost_s"] = round(statistics.median(raw_call("http://localhost:11434", False) for _ in range(RUNS)), 3)
        extras["via_127_0_0_1_s"] = extras["thinking_off_s"]
        print("extras " + json.dumps(extras), flush=True)

    print("RESULTS" + json.dumps({"models": results, "extras": extras}, ensure_ascii=False))


if __name__ == "__main__":
    main()
