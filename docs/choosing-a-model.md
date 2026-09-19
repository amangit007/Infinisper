# Choosing a model

There are two separate decisions here, and they're independent:

1. **Which speech engine** turns your voice into text. Always runs on your machine.
2. **Whether an AI model polishes** that text afterwards. Optional, off by default.

You can use just the first. Most people should start there.

---

## Speech engines

All three run locally. Your audio never leaves your computer.

| | Download | Good for |
|---|---|---|
| **Whisper** (base / small) | Already there | Getting started with the least memory. No download step. |
| **Nemotron 3.5 ASR** | ~650 MB | Fast everyday dictation for English and Hindi. Streams in real time while you talk (~0.2s latency). |
| **Qwen3-ASR** | ~980 MB | Highest overall accuracy across multilingual dictation (French, German, Chinese, Japanese, and nuanced Hindi). |

**If you're not sure:**
- Start on **Whisper** to test out your microphone and hotkey immediately.
- Move to **Nemotron** for your everyday driver: it's lightning fast, streams while you speak, and handles English and Hindi reliably.
- Switch to **Qwen3-ASR** whenever transcription fidelity is your top priority: in daily use it delivers the highest accuracy across multilingual dictation (including European, East Asian, and complex or code-mixed Hindi speech). With Dynamic Catch-Up Batching, speech is segmented and decoded in the background while you speak, keeping response times under ~0.6–1.4s on standard CPUs.

Downloads happen in **Models & providers**, with a progress bar, and only when you click.
You can delete an engine from the same screen to get the disk space back.

### Fallback

If your chosen engine fails for any reason, Infinisper falls back to Whisper rather than
losing what you said. You can turn that off in the Dashboard if you'd rather see the error.

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
