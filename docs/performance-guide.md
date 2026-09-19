# Getting the best speed and accuracy

Practical advice from daily use — Infinisper is the author's main way of writing,
including long-form text. None of this is required; the defaults work. This is for when
you want to tune.

---

## Pick a setup

| You want | Speech engine | AI cleanup |
|---|---|---|
| **To start right now, lowest memory** | Whisper | Off |
| **Better accuracy, still low memory** | Whisper or Nemotron | Gemini 3.5 Flash Lite (free tier) |
| **Fully local, fast** — closest to Wispr Flow | Nemotron | A small Ollama model |
| **French, German, Chinese, Japanese** | Qwen3-ASR | Optional |
| **Hindi** | Nemotron | Optional; a hosted model fixes spelling best |

---

## The speech engines, honestly

**Nemotron is the everyday engine.** It's faster than Whisper *and* more accurate in
English. It transcribes while you speak, so there's almost nothing left to do when you
release the key. Its weak spot is other languages — outside English, results drop off
noticeably in some languages, though not in Hindi: on six sentences read aloud, it made
fewer mistakes than Qwen3-ASR and was four times faster
([the numbers](benchmarks.md#hindi-measured-on-a-real-voice)).

**Qwen3-ASR is the most accurate for most other languages, and the slowest.** In a spot
check it beat Nemotron and Whisper on French, German, Chinese and Japanese. The quality
feels closer to a large cloud model that takes audio directly than to a typical local
speech engine.

It handles long takes, but it works best if you **speak in shorter stretches** —
a sentence or two, release, continue. Long recordings are split at natural pauses and
transcribed piece by piece, which works, but short takes come back faster.

**Whisper** is the quick-start option. A small one-time download (about 140 MB, fetched on first launch), low memory. Fine to start with; most
people will want to move to Nemotron once they're dictating regularly.

### Measured on one machine

Median over real use from the author's history, CPU only. Your hardware will differ;
the ratios are what matter.

| Setup | Takes | Speech engine | Total, key-release to text |
|---|---|---|---|
| Nemotron (streaming) | 33 | 131 ms | **169 ms** |
| Nemotron + cloud cleanup | 128 | 127 ms | **1.06 s** |
| Qwen3-ASR | 17 | 1.74 s | 3.35 s |
| Qwen3-ASR + cloud cleanup | 55 | 2.43 s | 3.45 s |

For comparison, Nemotron *before* it streamed took a median 2.18 s to transcribe. Streaming
moved that work into the time you're talking. For controlled tests — speed by speech
length, memory, and a multilingual spot check — see [Benchmarks](benchmarks.md).

---

## AI cleanup

The speech engine gives you what you said. Cleanup fixes grammar and punctuation, and at the
**Advanced** level also drops filler words and formats spoken lists.

### Cloud: Gemini 3.5 Flash Lite

The best all-rounder if you're happy for **text** (or audio, in audio mode) to leave your
machine. Fast, accurate, works in most situations, and the free tier covers normal personal
use. It also accepts audio directly, so it can replace the local engine entirely.

Open-weight models such as **GPT-OSS 120B on Groq** are a close alternative. In testing it
was a little quicker end to end (0.78 s vs 1.02 s) but slower on long passages, and it wrote
clean prose without formatting spoken lists the way Gemini did. It's text-only, so it can
clean up a transcript but can't take your audio directly.

### Local: Ollama

For fully offline cleanup, a model between roughly **0.5B and 4B parameters** is enough —
this is a simple task, and bigger models only add latency. The trade-off within that range is
real, though: the smallest models are the fastest but start slipping on long passages, while
a ~4B model like `gemma4:e4b` stays reliable. Start small, and step up if you see mistakes.

Two things are already handled for you:

- **Thinking is turned off** for Ollama models. Reasoning models otherwise spend many
  seconds "thinking" about a job that doesn't need it.
- **Ollama is reached at `127.0.0.1`, not `localhost`.** On Windows, `localhost` tries IPv6
  first and can stall about two seconds per request before falling back. If you add Ollama
  yourself, use `http://127.0.0.1:11434`.

**A model that isn't loaded is slow to answer** — 1.5 s for a 0.5B model, about 10 s for a 4B
one — and 5–8× faster once loaded. Ollama unloads idle models after 5 minutes, so Infinisper
loads yours when it starts and asks Ollama to keep it for **30 minutes**. You can change that on
the Dashboard under **Keep model loaded** (2 hours, or until Ollama quits). It's a trade: a loaded
model holds its memory the whole time, so choose the shortest wait you can live with on a small
machine. Leave it on **Ollama default** and Infinisper won't touch it. A GPU, even an integrated
one, speeds Ollama up considerably.

**Nemotron + a small Ollama model gets you close to Wispr Flow — in both quality and speed
— entirely on your own machine.** Measured: about 0.6–0.7 s from releasing the key to
polished text. See [Benchmarks](benchmarks.md#the-whole-pipeline-speech-engine--ai-cleanup).

---

## Accuracy tips

**Set your dictation language** in the Language tab rather than leaving it on automatic.
This helps Whisper and the AI cleanup step noticeably — and with both of those together,
it's faster too, because nothing has to guess the language first.

**Add names and jargon** to the custom dictionary in the Language tab. This reaches Whisper
and the cleanup step, not Nemotron or Qwen3.

**Writing in one language but want another?** The Language tab can keep your words as
spoken, romanize them (for example Hindi as Hinglish), or translate them. This happens in the
cleanup step, so it needs cleanup turned on.

---

## GPUs and Qwen3-ASR

A GPU helps Ollama a lot. It does **not** help Qwen3-ASR as shipped here, and in some tests
it made it slower. Two reasons, as best understood so far:

- **The bundled speech runtime is CPU-only.** The `sherpa-onnx` package installed from pip is
  built without CUDA. Asking it for a GPU silently falls back to CPU.
- **The models are int8-quantized.** That's what keeps them small and quick on a CPU. Much of
  that int8 work has no GPU implementation in ONNX Runtime, so a GPU build keeps shuttling data
  between graphics memory and the CPU for those steps. For a small 0.6B model, that traffic can
  cost more than the GPU saves.

Getting real GPU speed means running an unquantized (FP16) model on a GPU-oriented runtime such
as vLLM. That's possible, but the CUDA runtime and its libraries run to many gigabytes — the
size comes from the runtime, not the model — which is why it isn't bundled.

If you have a capable GPU and want speed, put it to work on **Ollama** and run **Nemotron** on
the CPU. That combination is already fast.
