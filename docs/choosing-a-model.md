# Choosing a model

There are two separate decisions here, and they're independent:

1. **Which speech engine** turns your voice into text. Always runs on your machine.
2. **Whether an AI model polishes** that text afterwards. Optional, off by default.

You can use just the first. Most people should start there.

---

## Speech engines

All speech recognition runs 100% locally on your CPU. Your audio never leaves your computer. **No model is auto-downloaded on first launch** — you choose what to download and can delete models anytime to reclaim space.

| Model | Download | Memory (RAM) | Good for |
|---|---|---|---|
| **Whisper Tiny** | ~75 MB | ~120 MB | Minimum resource usage, ultra-fast CPU decode. Lower accuracy on heavy accents. |
| **Whisper Base** | ~145 MB | ~165 MB | **Recommended baseline.** Good everyday accuracy with lightweight RAM footprint. |
| **Whisper Small** | ~460 MB | ~480 MB | Balanced upgrade for higher punctuation and capitalization fidelity across ~99 languages. |
| **Whisper Medium** | ~1.5 GB | ~1.6 GB | High accuracy across diverse accents and specialized vocabulary. |
| **Whisper Large v3 Turbo** | ~1.6 GB | ~2.5 GB | Near Large-v3 accuracy at 4x-6x faster decode speed via OpenAI's 4-layer decoder design. |
| **Whisper Large v3** | ~3.1 GB | ~4.5 GB | Highest Whisper benchmark accuracy for tough audio, but heavy on CPU. |
| **Nemotron 3.5 ASR** | ~650 MB | ~785 MB | **Recommended everyday driver.** Real-time streaming ASR (~0.2s latency) for English and Hindi. |
| **Qwen3-ASR** | ~980 MB | ~1.1 GB | Multilingual champion with Dynamic Catch-Up Batching (European, East Asian, and code-mixed Hindi). |

> **Important Note on Benchmark Measurements:**
> Our published benchmark numbers (latency, memory, and speed tables in [benchmarks.md](benchmarks.md)) were conducted on the **Whisper Base** model as our standard lightweight baseline. We provide options for the larger Whisper models (Small, Medium, Large v3 Turbo, Large v3) because they can yield substantially higher transcription accuracy, but **we have not formally run benchmark tests on all of those larger variants**. Larger models require more RAM and will have longer CPU decode times unless accelerated.

**If you're not sure where to start:**
- Start with **Whisper Base (~145 MB)** to test your microphone and verify transcription right away.
- Move to **Nemotron 3.5 (~650 MB)** as your everyday driver: it streams in real time as you speak, so by the time you release the hotkey, transcription is virtually instant (~0.24s).
- Switch to **Qwen3-ASR (~980 MB)** or **Whisper Large v3 Turbo (~1.6 GB)** when transcription fidelity and handling nuanced terminology or accented speech is your highest priority.

Downloads happen directly in **Models & providers** with real-time progress bars (speed and bytes). You can delete any engine at any time with one click to recover disk space. Hover over the disk badge (`on disk X MB 📊`) to see an interactive doughnut chart breakdown.

### Fallback

If your chosen engine fails for any reason, Infinisper falls back to an available downloaded Whisper model rather than losing what you said. You can toggle this in the Dashboard if you'd rather see the raw error.

---

## AI cleanup (optional)

The speech engines give you what you said. An AI model can clean it up — fix grammar,
format numbers and times sensibly, and at the stronger setting, strip out "um" and "you
know" and turn a spoken list into bullet points.

**This is the only part of Infinisper that sends anything off your machine**, and only if
you set it up. See [Privacy](privacy.md).

There are two strengths:

- **Basic** — fixes obvious mishearings and formatting. Leaves your phrasing alone.
- **Advanced** — also removes filler words and formats lists.

### Setting it up

In **Models & providers**, add a provider if you need one, then a model under it. Infinisper
routes through LiteLLM, so most providers work — Gemini, OpenAI, and anything OpenAI-compatible.

**If you'd rather nothing left your machine at all**, use [Ollama](https://ollama.com). It's
already set up as a provider at `http://127.0.0.1:11434`, so all that's left is choosing a model:
click **Add model** and Infinisper lists the ones you've already pulled. A small one (0.5B–4B) is
plenty. If Ollama isn't running, or has no models yet, the dialog says so and tells you what to do
— Infinisper never installs Ollama or downloads a model for you.

API keys go into Windows Credential Manager, not into any file in this folder.

### Three ways to run it

| Mode | What happens | Best for |
|---|---|---|
| **Speech only** | Local engine → your cursor. | Fastest (~0.2s), 100% offline, zero network or API dependency. |
| **Speech + cleanup (Recommended)** | Local engine transcribes, local AI (Ollama) or cloud tidies it up. | The polished Wispr Flow feel: clean punctuation, filler-word removal, and list formatting while keeping transcription local. |
| **Audio straight to the AI** | Your recording is sent directly to an audio-capable model, bypassing the local speech engine entirely. | **Zero local model memory footprint.** Ideal for low-RAM machines where you don't want any speech models loaded in memory. |

> **Note on Audio-to-AI models:** Not all AI models support raw audio input. Text-only models (including all standard Ollama models, Groq, and standard GPT models) cannot accept audio. Direct audio mode requires multimodal models specifically built for audio ingestion (such as Google Gemini Flash Lite or OpenAI audio-capable models).

If the cleanup step fails or times out, you still get your text — just unpolished. It's
never a reason to lose a sentence you already said.

---

## Other languages

Set your dictation language in the **Language** tab. With AI cleanup on, you can also choose
what happens to it: keep it in its own script, romanize it (Hindi as Hinglish, for example),
or translate it into another language.

## Words it keeps getting wrong

Names, acronyms, and jargon trip up every speech model. Add them in the **Language** tab,
one per line. Whisper gets them as decoding hints, and the AI cleanup step is told about
them by name.

This doesn't currently apply to Nemotron or Qwen3 — biasing those needs a file their
released builds don't include.
