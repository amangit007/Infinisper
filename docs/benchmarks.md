# Benchmarks

Measured, not estimated. Every number on this page comes from the scripts in
[`benchmarks/`](../benchmarks), so you can run them on your own machine:

```cmd
python benchmarks/engines.py           # speech engines
python benchmarks/pipeline.py          # AI cleanup + full pipeline, with your configured providers
python benchmarks/ollama_cold_hot.py   # local models: first request vs. loaded
python benchmarks/audio_pipeline.py    # audio cleanup chain
```

**Test machine:** AMD Ryzen 7 (8 cores), 16 GB RAM, Windows 11. 

- **Speech Recognition (ASR):** Runs **100% on the CPU only** across all tests (no GPU used).
- **Optional Local AI Cleanup (Ollama):** Timed with Ollama utilizing an NVIDIA laptop GPU. On CPU-only systems, using a lightweight 0.5B–1.5B model takes ~0.4–0.8s, keeping overall latency well under a second.
- **Whisper model:** Tested with Whisper `base`. Every engine runs using the application's default settings.

---

## How long you wait after you stop talking

Transcription time for continuous English speech, measured after the last word. Lower is
better.

| Speech length | Whisper | Qwen3-ASR | Nemotron (batch) | **Nemotron (streaming)** |
|---|---|---|---|---|
| 5 s | 1.49 s | 1.89 s | 1.16 s | **0.24 s** |
| 10 s | 1.62 s | 3.29 s | 1.77 s | **0.24 s** |
| 30 s | 3.02 s | 7.55 s | 4.70 s | **0.25 s** |
| 60 s | 4.91 s | 14.50 s | 12.32 s | — |

The last column is the reason Nemotron streams. For the streaming test, audio is fed in 50 ms
chunks **at real-time speed**, the same way the microphone delivers it. Only the time after
the final chunk is counted. That time stays at about a quarter of a second **however long you
speak**, because the decoding happened while you were talking.

In the app, the audio cleanup and paste add about 60 ms on top of these figures.

A fair note: in pure batch mode, Whisper `base` is the fastest engine on long takes. It gets
that speed by being the least accurate, as the next section shows.

---

## Memory and startup

| Engine | Memory for the model | Load time | Download |
|---|---|---|---|
| Whisper base | 166 MB | 1.6 s | ~140 MB, fetched on first launch |
| Nemotron 3.5 | 785 MB | 2.9 s | ~650 MB |
| Qwen3-ASR | 1,146 MB | 5.7 s | ~980 MB |

The memory column counts the model only, measured after warm-up with the runtimes already
loaded. Load time is with the model files already in the disk cache; the first launch after a
reboot takes longer. Models load once at startup and stay loaded, so this cost is never paid
during dictation.

---

## The whole pipeline: speech engine + AI cleanup

This is what you actually wait for with AI cleanup turned on. The test speaks the 7-second
English sample at real-time speed into streaming Nemotron, then sends the transcript to each
model at the **Advanced** cleanup level. The time runs from key release to cleaned text; the
paste adds about 10 ms more. Median of 3.

| Cleanup model | Where it runs | Key release → cleaned text |
|---|---|---|
| *None — Nemotron alone* | *local* | *0.24 s* |
| qwen2.5 0.5B | local, Ollama | **0.56 s** |
| qwen3.5 0.8B | local, Ollama | **0.58 s** |
| gemma4 e4b | local, Ollama | 0.73 s |
| GPT-OSS 120B | Groq | 0.78 s |
| Gemini 3.5 Flash Lite | Google | 1.02 s |

**With a small local model, speech-to-polished-text takes about half a second, with nothing
leaving the machine.**

### Cleanup on its own, and how good the output is

Text in, text out, with the model already loaded. Median of 3. The short input is one
15-word sentence; the long one is a 75-word dictated update full of fillers ("so um… uh…
like…") containing two items that belong in a list.

| Model | Short | Long | How it handled the long passage |
|---|---|---|---|
| Gemini 3.5 Flash Lite | 0.74 s | 0.86 s | **Best.** Fillers gone, and the two items became a bulleted list |
| GPT-OSS 120B (Groq) | 0.72 s | 1.18 s | Clean prose, fillers gone, no list |
| gemma4 e4b (local) | 0.29 s | 1.25 s | Clean prose, one leftover "So," |
| qwen3.5 0.8B (local) | 0.18 s | 0.60 s | Kept "So, um," and changed "two things left" to "one thing" — **a meaning error** |
| qwen2.5 0.5B (local) | 0.08 s | — | Output **rejected by the app's safety check** in 3 of 3 runs |
| Gemini 3.7 Flash | — | — | Google returned "high demand" (503) on every request during testing |

Smaller models are faster, but they start to slip once the input gets long. Of the local
models tested, the ~4B gemma4 was the most reliable. The rejected 0.5B outputs show the
length check doing its job: the app pasted the unpolished transcript instead of a mangled one.

### Sending audio straight to the model

Gemini 3.5 Flash Lite, given the 7-second clip directly, took a **median of 2.25 s** and
transcribed it correctly. That's slower than Nemotron + Gemini text cleanup (1.02 s), because
uploading audio and having a large model listen to it costs more than a local transcription
plus a short text request.

---

## Local models: cold vs. hot

Ollama unloads a model from memory when it's been idle for a while. By default that's after 5
minutes. The next request has to load it again first. Measured on the long passage: 3 cold
starts per model, each followed by 5 requests with the model loaded.

| Model | Cold (first request) | …of which loading | Hot (already loaded) | Cold is |
|---|---|---|---|---|
| qwen2.5 0.5B | 1.46 s | 1.11 s | 0.24 s | 6× slower |
| qwen3.5 0.8B | 2.76 s | 2.17 s | 0.56 s | 5× slower |
| gemma4 e4b | 10.09 s | 8.31 s | 1.23 s | 8× slower |

Almost all of the cold penalty is loading, not thinking. After a break, the first dictation
pays it once, and every one after that is fast. Infinisper avoids it by loading your model at
startup and asking Ollama to keep it for 30 minutes (adjustable on the Dashboard).

"Cold" here means unloaded from memory, with the model files still cached by Windows. The
first load after a reboot has to read them from disk, and takes longer still.

---

## Performance defaults that matter

These optimizations are enabled by default in Infinisper:

- **Thinking disabled for local models:** Reasoning models deliberate over simple text cleanup tasks. Disabling thinking brings response time on `qwen3.5 0.8B` from **23.58 s** down to **0.55 s** (43× faster) with identical cleanup quality.
- **Fast IPv4 connection (`127.0.0.1`):** On Windows, `localhost` attempts IPv6 resolution first, which can delay connection establishment by ~2 seconds before failing over to Ollama. Infinisper automatically rewrites connection URLs to `127.0.0.1`, dropping connection time to **~1.2 ms**.

---

## Other languages: a spot check

This isn't a formal accuracy benchmark. It's five well-known sentences, one per language,
from the sample clips that come with the Nemotron download. Each engine's output was judged
against the sentence actually spoken. Full transcripts are below the table.

| Language | Whisper | Nemotron | Qwen3-ASR |
|---|---|---|---|
| French | ✗ "pays" → "PIPE" | ✓ minor punctuation | ✓ **exact** |
| German | ✓ exact | ✗ dropped first word | ✓ **exact** |
| Chinese | ✓ in Traditional script | ✓ | ✓ **exact, with punctuation** |
| Japanese | ✗ two wrong words | ✗ two wrong words | ✓ one small slip |
| Spanish | ✗ second half garbled | ✗ partly garbled | ✗ partly garbled |

Qwen3 was the best of the three on four of the five, so it's the one to try first for
French, German, Chinese and Japanese. Hindi, measured properly below, went the other way.
Spanish tripped up every engine. It's also the lowest-quality recording of the set.

### Hindi, measured on a real voice

The spot check above is five sentences from sample clips. For Hindi there's a proper test: six
sentences I read aloud into the laptop microphone, scored by **character error rate** (CER: the
share of characters that differ from what I actually said; 0% is perfect). Punctuation and
capitalisation are ignored. Audio goes through the same cleanup the app applies before
transcription. To run it on your own voice, record clips with
`python benchmarks/record_clips.py hi`, then `python benchmarks/accuracy.py hi`.

| System | CER ↓ | Median time per clip |
|---|---|---|
| Whisper base | 94.7% | 0.6 s |
| **Nemotron** | **1.9%** | **0.9 s** |
| Qwen3-ASR | 3.9% | 3.4 s |
| Gemini 3.5 Flash Lite, audio sent directly | 3.9% | 2.6 s |
| Qwen3-ASR + Gemini 3.5 Flash Lite cleanup | **1.7%** | 5.0 s |
| Qwen3-ASR + gemma4 e4b cleanup (local) | 3.5% | 0.4 s cleanup on top of Qwen3 |

- **Nemotron was the best single engine for Hindi**, more accurate than Qwen3-ASR and about
  four times faster, and it streams. That overturns my assumption that Qwen3 is the one to
  use outside English; for Hindi it isn't. Most of what it missed was spelling: "ँ" written as
  "ं", and the dot under "ज़" and "फ़" left out. There was one real slip, "की" heard as "को",
  which Qwen3 made too.
- **Whisper `base` doesn't really do Hindi.** Across the six clips it never wrote a single
  Devanagari character. It returned an English translation, Roman letters, or Urdu script, so
  the 95% is real, not a scoring quirk. Larger Whisper models are much better; `base` is the
  one the app starts with.
- **Cleanup helps, but only a little, and mostly by fixing spelling.** Gemini brought Qwen3
  from 3.9% to 1.7%. The local gemma4 e4b, through the app's real cleanup prompt, brought it
  from 3.9% to 3.5%, and it took 0.4 s per clip with thinking disabled. It fixed real
  mistakes ("क्रिप्या" → "कृपया", "को" → "की"). It also turned spoken numbers into digits
  ("दस" → "10"), which is what the cleanup prompt is meant to do but which counts against it
  here, since I spelled them out. And on one clip it dropped a word that Qwen3 had misheard,
  rather than fixing it.
- **Code-mixed Hindi and English** ("कल का deployment postpone हो गया…", three sentences) isn't
  scored, because there's no single correct spelling for the English words. Nemotron wrote
  them in Devanagari ("डिप्लॉयमेंट", "पोस्टपोन"); Qwen3 did too, with a couple of odd
  spellings ("डिप्लोमेंट"); Whisper `base` repeated one word dozens of times on the first
  sentence. Full outputs are in
  [`benchmarks/accuracy_hi.json`](../benchmarks/accuracy_hi.json).

**Limits of this test:** six sentences, one speaker, one microphone, so differences of a
percentage point or two are noise. The Gemini rows are timed on a hosted service, so they
vary with load. The local-cleanup row comes from a separate script,
[`accuracy_local_ollama.py`](../benchmarks/accuracy_local_ollama.py), which sends Qwen3's output
through Ollama; its ASR half ran slower (4 to 5 s per clip) because the app was open beside it.

<details>
<summary>Full transcripts</summary>

**French** — *Ne vous demandez pas ce que votre pays peut faire pour vous, demandez-vous plutôt ce que vous pouvez faire pour lui.*

| | |
|---|---|
| Whisper | Ne vous demandez pas ce que votre PIPE peut faire pour vous. Demandez-vous plutôt ce que vous pouvez faire pour lui. |
| Nemotron | Ne vous demandez pas ce que votre pays peut faire pour vous, demandez vous plutôt ce que vous pouvez faire pour lui |
| Qwen3 | Ne vous demandez pas ce que votre pays peut faire pour vous, demandez-vous plutôt ce que vous pouvez faire pour lui. |

**German** — *Alles hat ein Ende, nur die Wurst hat zwei.*

| | |
|---|---|
| Whisper | Alles hat ein Ende, nur die Wurst hat zwei. |
| Nemotron | hat ein Ende, nur die Wurst hat zwei |
| Qwen3 | Alles hat ein Ende, nur die Wurst hat zwei. |

**Chinese** — *不要问你的国家能为你做什么，而要问你能为你的国家做什么。*

| | |
|---|---|
| Whisper | 不要問你的國家能為你做什麼,而要問你能為你的國家做什麼。 |
| Nemotron | 不要问你的国家能为你做什么, 而要问你能为你的国家做什么 |
| Qwen3 | 不要问你的国家能为你做什么，而要问你能为你的国家做什么。 |

**Japanese** — *国があなたのために何ができるかを問うのではなく、あなたが国のために何ができるかを問うてください。*

| | |
|---|---|
| Whisper | 国が花灯のために何ができるかを遠くではなくあなたが国のために何ができるかを遠くなさい |
| Nemotron | 国が花とのために何ができるかを通のではなく、あなたが国のために何ができるかを通ってください |
| Qwen3 | 国があなたのために何ができるかを問うのではなく、あなたが国のために何ができるかを問ってください。 |

**Spanish** — *No preguntes qué puede hacer tu país por ti, pregunta qué puedes hacer tú por tu país.*

| | |
|---|---|
| Whisper | No preguntes que puede hacer tu país por ti, te aguanta que puedes hacer que un por tu paz. |
| Nemotron | preguntas que puede hacer tu país porti. Pregunta qué puedes hacer que por tu país |
| Qwen3 | Uno pregunta: ¿Qué puede hacer tu país por ti? Te pregunta: ¿Qué puedes hacer tu país por tu país? |

</details>

---

## The audio cleanup chain

What it costs to prepare a **30-second** take before transcription:

| Step | Time |
|---|---|
| DC removal + 80 Hz high-pass + click notch | 12 ms |
| Voice activity trim (Silero VAD) | 46 ms |
| Level normalisation | 6 ms |

The high-pass filter used to be a plain per-sample loop. The vectorized version, described in
[How it works](how-it-works.md#cleaning-the-audio), runs the same filter:

| | 30 s of audio |
|---|---|
| Per-sample loop | 134 ms |
| Vectorized, in blocks | 5.8 ms — **23× faster** |
| Largest difference between the two outputs | 0.000000065 |

The last row is the important one. It shows the faster version gives the same result, not an
approximation.

---

## In daily use

The numbers above are controlled tests. For medians from a week of real dictation — 259 takes, with Nemotron streaming
at 169 ms from key release to text, or about 1 s with AI cleanup — see the
[performance guide](performance-guide.md#measured-on-one-machine).
