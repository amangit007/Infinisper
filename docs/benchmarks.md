# Benchmarks

Measured, not estimated. Every number on this page comes from the scripts in
[`benchmarks/`](../benchmarks), so you can run them on your own machine:

```cmd
python benchmarks/engines.py           # speech engines
python benchmarks/pipeline.py          # AI cleanup + full pipeline, with your configured providers
python benchmarks/ollama_cold_hot.py   # local models: first request vs. loaded
python benchmarks/audio_pipeline.py    # audio cleanup chain
```

**Test machine:** AMD Ryzen 7 250 (8 cores), 16 GB RAM, Windows 11. The speech engines run
**on the CPU only**. Ollama 0.33.3 ran its models entirely on the integrated Radeon 780M GPU,
which is a laptop chip, not a dedicated card. Whisper is the `base` model, and every engine
runs exactly as the app configures it.

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

## Two settings that matter more than the model

Both are already the default in Infinisper. They're measured here because they're the
difference between "instant" and "is it broken?".

**Thinking disabled.** qwen3.5 0.8B cleaning up the long passage:

| | Median of 3 |
|---|---|
| Thinking on | 23.58 s |
| Thinking off | **0.55 s — 43× faster** |

Reasoning models deliberate at length over a task this simple. Turning thinking off costs
nothing in quality here.

**`127.0.0.1` instead of `localhost`.** Median time to open a new connection to Ollama and
get a reply:

| Address | Time |
|---|---|
| `http://localhost:11434` | 2,048 ms |
| `http://127.0.0.1:11434` | **1.2 ms** |

On Windows, `localhost` resolves to the IPv6 address `::1` first. Ollama listens only on IPv4,
so every new connection waits two seconds for IPv6 to fail before falling back. The app now
rewrites `localhost` to `127.0.0.1` for you.

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

Qwen3 was the best of the three on four of the five. That matches everyday use: switch to
Qwen3 when you're not dictating in English. Spanish tripped up every engine. It's also the
lowest-quality recording of the set.

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
