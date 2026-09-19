"""Record your own test clips, so accuracy is measured on your voice in your language.

    python benchmarks/record_clips.py hi

Shows one sentence at a time. Press Enter, read it aloud naturally, press Enter again.
Clips are saved to benchmarks/clips/<lang>/ with the sentences in references.json, which
is what benchmarks/accuracy.py scores against. Re-run to re-record.
"""

import json
import sys
import threading
import wave
from pathlib import Path

import numpy as np
import sounddevice as sd

SENTENCES = {
    "hi": [
        "आज मौसम बहुत अच्छा है, चलो शाम को पार्क में घूमने चलते हैं।",
        "कल सुबह दस बजे हमारी टीम की मीटिंग है, कृपया समय पर पहुँचें।",
        "मुझे बाज़ार से दो किलो आलू, एक दर्जन केले और थोड़ा दूध लाना है।",
        "भारत की राजधानी नई दिल्ली है और यहाँ की आबादी बहुत ज़्यादा है।",
        "मैंने नया लैपटॉप खरीदा है लेकिन उसकी बैटरी जल्दी खत्म हो जाती है।",
        "अगर तुम्हें कोई परेशानी हो तो मुझे फ़ोन कर देना, मैं मदद करूँगा।",
    ],
    # Code-mixed speech, the way many people actually dictate. Reported separately --
    # there's no single correct script for the English words, so it isn't scored.
    "hi-mixed": [
        "कल का deployment postpone हो गया क्योंकि production में एक bug मिला।",
        "मैंने meeting के notes Slack पर share कर दिए हैं, please एक बार check कर लेना।",
        "इस feature को next sprint में ले लेते हैं, अभी testing बाकी है।",
    ],
}

RATE = 16000


def record_until_enter() -> np.ndarray:
    frames, stop = [], threading.Event()

    def callback(indata, *_):
        frames.append(indata.copy())

    with sd.InputStream(samplerate=RATE, channels=1, dtype="float32", callback=callback):
        threading.Thread(target=lambda: (input(), stop.set()), daemon=True).start()
        stop.wait()
    return np.concatenate(frames).flatten() if frames else np.zeros(0, np.float32)


def main():
    lang = sys.argv[1] if len(sys.argv) > 1 else "hi"
    sets = [k for k in SENTENCES if k == lang or k.startswith(lang + "-")]
    if not sets:
        sys.exit(f"No sentences for '{lang}'. Available: {', '.join(SENTENCES)}")

    for key in sets:
        out = Path(__file__).parent / "clips" / key
        out.mkdir(parents=True, exist_ok=True)
        references = {}
        for i, sentence in enumerate(SENTENCES[key], 1):
            name = f"{i:02d}.wav"
            print(f"\n[{key} {i}/{len(SENTENCES[key])}]  {sentence}")
            input("  Enter to start recording...")
            print("  Recording -- read the sentence, then press Enter.")
            audio = record_until_enter()
            pcm = (np.clip(audio, -1, 1) * 32767).astype(np.int16)
            with wave.open(str(out / name), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(RATE)
                w.writeframes(pcm.tobytes())
            references[name] = sentence
            print(f"  Saved {len(audio) / RATE:.1f} s")
        (out / "references.json").write_text(json.dumps(references, ensure_ascii=False, indent=1),
                                             encoding="utf-8")
    print("\nDone. Now run: python benchmarks/accuracy.py", lang)


if __name__ == "__main__":
    main()
