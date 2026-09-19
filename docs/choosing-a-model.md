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
| **Nemotron 3.5 ASR** | ~650 MB | Everyday English dictation, and Hindi. Fastest, and more accurate than Whisper. Transcribes while you talk. |
| **Qwen3-ASR** | ~980 MB | Highest accuracy on the European and East Asian languages tested. Slowest of the three. |

**If you're not sure:** start on Whisper, move to Nemotron once you're dictating daily, and
switch to Qwen3 for French, German, Chinese or Japanese. For Hindi, Nemotron measured better
than Qwen3, and Whisper's small default model doesn't handle it at all. For measured speeds and
recommended combinations, see the [performance guide](performance-guide.md).

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

| Mode | What happens |
|---|---|
| Speech only | Local engine → your cursor. Fastest. |
| Speech + cleanup | Local engine transcribes, the AI model tidies it up. |
| Audio straight to the AI | Your recording goes to a model that handles audio directly, skipping the local engine. |

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
