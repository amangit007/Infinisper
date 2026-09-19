"""How much slower is the first cleanup request when the Ollama model isn't loaded yet?

    python benchmarks/ollama_cold_hot.py

For every Ollama model configured in the app: unloads it, times the first request (cold),
then times requests while it stays loaded (hot). Repeated several times. Uses Ollama's own
timing fields to show where cold time goes -- loading the model vs. generating the text.

"Cold" here means unloaded from RAM/VRAM with the files still in the OS disk cache. Straight
after a reboot, the first load also has to read the model from disk and takes longer.
"""

import json
import os
import statistics
import sys
import time
import urllib.request

sys.path.insert(0, os.getcwd())

from config import load_config
from cleanup.prompts import CLEANUP_PROMPT_ADVANCED

CYCLES = 3
HOT_RUNS = 5
TEXT = (
    "so um I wanted to give you a quick update on the release uh we finished the migration "
    "yesterday and the tests are passing now but there's still like two things left one is the "
    "login page which is loading slowly on mobile and the other is the export button which "
    "sometimes fails for large files so I think we can ship on thursday if we fix those by "
    "wednesday evening let me know if that works for you"
)


def post(base: str, path: str, payload: dict) -> dict:
    req = urllib.request.Request(base + path, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=300) as r:
        return json.loads(r.read())


def cleanup(base: str, model: str) -> tuple[float, dict]:
    """Same request shape the app sends: advanced cleanup prompt, thinking off, temperature 0."""
    t = time.perf_counter()
    r = post(base, "/api/chat", {
        "model": model, "stream": False, "think": False,
        "options": {"temperature": 0},
        "messages": [{"role": "system", "content": CLEANUP_PROMPT_ADVANCED},
                     {"role": "user", "content": f"<<<{TEXT}>>>"}],
    })
    return time.perf_counter() - t, r


def unload(base: str, model: str):
    post(base, "/api/generate", {"model": model, "keep_alive": 0})
    for _ in range(50):  # wait until Ollama reports it gone
        with urllib.request.urlopen(base + "/api/ps", timeout=10) as r:
            if not any(m["name"] == model for m in json.loads(r.read()).get("models", [])):
                return
        time.sleep(0.2)


def main():
    config = load_config()
    providers = {p["id"]: p for p in config.get("cleanup_providers", [])}
    base = (providers.get("ollama", {}).get("base_url") or "http://127.0.0.1:11434").rstrip("/")
    base = base.replace("localhost", "127.0.0.1")
    models = [m["model"].removeprefix("ollama/") for m in config.get("cleanup_models", [])
              if m["provider_id"] == "ollama"]
    if not models:
        sys.exit("No Ollama models configured in the app.")

    results = []
    for model in models:
        print(f"-- {model}", flush=True)
        cold, load, hot = [], [], []
        for _ in range(CYCLES):
            unload(base, model)
            elapsed, r = cleanup(base, model)
            cold.append(elapsed)
            load.append(r.get("load_duration", 0) / 1e9)
            for _ in range(HOT_RUNS):
                elapsed, r = cleanup(base, model)
                hot.append(elapsed)
        row = {
            "model": model,
            "cold_s": round(statistics.median(cold), 3),
            "load_s": round(statistics.median(load), 3),
            "hot_s": round(statistics.median(hot), 3),
            "hot_p90_s": round(sorted(hot)[int(0.9 * (len(hot) - 1))], 3),
            "slowdown_x": round(statistics.median(cold) / statistics.median(hot), 1),
            "output": r["message"]["content"].strip(),
        }
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
    print("RESULTS" + json.dumps(results, ensure_ascii=False))


if __name__ == "__main__":
    main()
