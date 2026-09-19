# How Infinisper works

A walk through what happens between pressing the hotkey and text appearing at your cursor,
and why the pieces are arranged the way they are.

You don't need this to use the app. It's here if you're curious, or if you want to change
something.

---

## The shape of it

One Python process, a handful of threads.

```
Qt main thread          the settings window, the tray icon, the floating pill
  │
  ├── audio callback    PortAudio hands over 50 ms of samples at a time
  │
  ├── hotkey loop       checks the hotkey every 30 ms
  │
  ├── pipeline thread   preprocessing, transcription, cleanup, paste
  │
  └── stream worker     only for Nemotron — decodes while you're still talking
```

Qt widgets are only ever touched from the main thread. Everything slow — model inference,
network calls, downloads — happens off it, so the window never freezes and the pill keeps
animating while a model is thinking.

The modules mirror that:

| | |
|---|---|
| `audio/` | capture, preprocessing, voice activity detection |
| `asr/` | the three speech engines and their downloads |
| `cleanup/` | optional AI cleanup, routed through LiteLLM |
| `ui/` | window, tray, floating pill, splash |
| `history/` | what you dictated, and how long each step took |
| `dictation/` | the pipeline (hotkey, record, transcribe, clean up, paste), the live settings, and the handlers that change them |
| `app.py` | builds the window, tray and pipeline, and connects them |

Inside `dictation/`, state is split by who changes it, not kept in globals. `Settings` is the
running copy of `config.json`, so a take never reads the disk. `Runtime` is what's loaded right
now: which engines, which microphone. It can differ from the settings while a model downloads.
`Pipeline` owns the per-take state, such as whether a take is in flight. `SettingsController`
handles the window's buttons: it saves to `config.json`, then updates the other two.

---

## Holding the hotkey

The microphone stream opens **once at startup and stays open** for the life of the app.
This is deliberate. Opening a PortAudio stream takes long enough that the first word of
every take was getting lost to it.

But an always-open stream needs a matching trick: it keeps a rolling **half-second ring
buffer** of the most recent audio. When you press the hotkey, that buffer is what the take
*starts* with — so the moment before you consciously started speaking is already recorded.
You can begin talking as you press, not after.

There's a small consequence: the very first take after launch gets less than half a second,
because the ring hasn't filled yet. The code tracks how much pre-roll each take actually
received, which matters in the next step.

The hotkey is checked every 30 ms by asking Windows directly whether the keys are physically
held (`GetAsyncKeyState`), rather than by installing a low-level keyboard hook. Polling is
the less elegant choice and costs up to 30 ms of response time, but a hook sits in the path
of every keystroke on the machine: anything slow in it causes system-wide typing lag, Windows
silently removes hooks that respond too slowly, and a missed key-up leaves modifiers stuck.
Asking for key state has none of those failure modes.

`Ctrl + Win` is the default, and there are presets for other combinations and single keys
such as `Right Ctrl` or `F8`. The previous take has to finish before a new one starts.

---

## Cleaning the audio

Raw microphone audio is not what a speech model wants. Four things happen before
transcription, in this order, and the order matters:

**1 · Remove DC offset.** Microphones drift off zero. Subtract the mean.

**2 · High-pass filter at 80 Hz.** Desk bumps, fan hum, and mains rumble live below speech
and only confuse the model.

This one is worth a note. It's a one-pole IIR filter, which is naturally a sample-by-sample
loop — and in Python that loop costs about 134 ms on a 30-second take. Expanding the
recurrence lets NumPy compute it as a cumulative sum instead, except the expansion overflows
float64 past roughly 22,000 samples. So it's computed in blocks of 1024 with the filter state
carried across each seam: 5.8 ms, **23× faster**, and identical to the loop to within 7×10⁻⁸.
(See [Benchmarks](benchmarks.md#the-audio-cleanup-chain).)

**3 · Notch out the hotkey click.** Pressing Ctrl+Win makes a mechanical noise your
microphone hears. It does **not** land at the start of the recording — it lands where the
pre-roll buffer ends and live recording begins, which is why the previous step tracked how
much pre-roll this take got. A raised-cosine notch attenuates it; a rectangular gate would
remove the click and introduce two new discontinuities instead.

It only fires if there's genuinely a transient there, so a quiet keyboard costs no audio.

**4 · Trim to speech, then normalise.** Silero VAD drops the silence, *then* the level is
brought to about −20 dBFS.

That order is the point. Normalising before trimming measures the level across speech *plus*
the silence around it, which understates it. And the normalisation is driven by RMS, not by
the loudest sample — an earlier peak-based version gave quiet speech 1.2× gain where it
needed 48×, because a single surviving click pinned the peak. The feature meant to help
quiet voices was being cancelled by the click it had failed to remove.

---

## Transcribing

Three engines, one job. Which runs is your choice; see
[Choosing a model](choosing-a-model.md).

**Whisper** is a batch engine: it gets the finished take and transcribes it after you release. The wait grows with how long you spoke.

**Qwen3-ASR** streams via **Dynamic Catch-Up Batching**. Its session begins when you press the hotkey. As speech accumulates, natural breath pauses (~400 ms) or maximum chunk intervals trigger segment dispatches to a background worker while you are still speaking. If incoming speech chunks arrive faster than the model can decode, the worker pulls all accumulated chunks and processes them in a single batch pass via `sherpa_onnx.OfflineRecognizer.decode_streams()`. Offline multi-chunk takes also benefit from batch decoding, cutting multi-chunk decode times nearly in half while keeping post-speech latency down to ~0.6–1.4s. The pieces are stitched back together using smart capitalization rules that preserve acronyms and the pronoun "I".

**Nemotron 3.5** streams. Its session starts the moment you press the hotkey, gets the
pre-roll buffer immediately, and then receives each 50 ms chunk as PortAudio delivers it.
Decoding happens on its own worker thread, fed through a queue so the audio callback is
never blocked — a slow decode must not stall the microphone.

By the time you release, most of the work is done. What's left is finalising the last chunk,
which takes roughly the same time no matter how long you spoke. In practice that moved
Nemotron's median transcription time after release from 2.18 s to 127 ms.

Streamed audio still gets the 80 Hz high-pass filter, but a stateful version: it carries the
filter's memory from one chunk to the next, so the seams between chunks don't produce clicks
of their own.

One detail: the stream is fed 1.2 seconds of trailing silence before being closed. The model
works in 1120 ms windows, and without padding the final window never completes — you lose
the last word or its closing consonant.

If the configured engine fails, Infinisper falls back to Whisper rather than losing the
take. You can turn that off if you'd rather see the failure.

---

## Optional AI cleanup

If you've enabled it, the transcript then goes to an AI model — cloud or local Ollama, both
reached through LiteLLM, so one call shape covers every provider.

Three guardrails, all of them from things that actually went wrong:

**Retries are disabled.** LiteLLM otherwise inherits the OpenAI SDK's default of two silent
retries *inside* our own timeout window. A slow request was being retried three times before
anything was reported, which multiplied real latency and hid the first attempt's actual
error behind a generic timeout. There's already a recovery strategy one layer up — fall back
to the local engine — and same-provider retries underneath it just hide problems.

**Output length is sanity-checked.** If the polished text comes back shorter than 0.4× or
longer than 2.5× the input, it's discarded and the raw transcript is used. That signature
means the model *answered* your dictation instead of tidying it.

**When audio goes straight to an AI model, the text part of the request is empty.**
LiteLLM requires at least one text part alongside audio, but any actual wording there —
even "transcribe this" — measurably biases the model toward inventing speech when the audio
is silent. Tested against a pure sine tone: a worded prompt hallucinated a sentence, a blank
one did not.

**An overloaded model is skipped for a minute.** A provider that answers "503, high demand"
can take 8–24 seconds to say so, and waiting that long on every dictation just to be told no
again makes the app feel broken. After two overload or timeout failures in a row, that model
is skipped for 60 seconds and the take goes straight to the fallback. Wrong-key and
unknown-model errors are never skipped: they fail instantly and the message should stay
visible until they're fixed.

Local models through Ollama needed some fixes of their own:

- **Thinking is switched off.** Reasoning models will spend tens of seconds deliberating
  over a tidy-up job. The request tells Ollama not to think, and temperature is fixed at 0
  so the same sentence always comes back the same way.
- **IPv4 fast connection (`127.0.0.1`).** Local endpoints automatically normalize to IPv4 (`127.0.0.1`) to eliminate Windows IPv6 resolution delays.
- **The model is kept loaded.** Ollama unloads an idle model after five minutes, and loading
  one again takes 1.5 s for a 0.5B model and about 10 s for a 4B one. At startup Infinisper
  sends an empty request that loads the active model without generating anything, and every
  later request asks Ollama to keep it for 30 minutes (a Dashboard setting, since a loaded
  model holds its memory). It's skipped entirely if you leave the setting on Ollama's default.
- **Chatty output is stripped.** Small models like to wrap the answer — "Here is the
  cleaned text:", surrounding quotes, or the `<<< >>>` delimiters the prompt uses to mark the
  input. Those are removed before anything is pasted.

Underneath all of it is one rule: **cleanup failing never costs you a sentence.** If the
audio path fails you fall back to the local engine; if the *text* cleanup fails you keep the
unpolished transcript, even with fallback switched off — because by then the transcription
already succeeded, and there's nothing to recover.

---

## Getting the text to your cursor

Clipboard, then `Ctrl+V`. It's not elegant, but it's the only delivery method that works in
every Windows application — synthesised keystrokes get dropped or reordered by editors with
their own input handling.

Your previous clipboard contents are put back afterwards, on a background thread, after a
1.5 second delay. This used to be a blocking `sleep(0.3)` inside the pipeline, which was
both a permanent tax on every take and a race — applications that read the clipboard lazily
(some Electron apps, remote desktop sessions, certain web editors) could reach the restore
and paste your *old* contents instead. Waiting longer off the critical path costs nothing.

The restore only happens if our text is still on the clipboard. If you copied something in
the meantime, your copy wins.

---

## Where things are kept

| | |
|---|---|
| Settings | `config.json`, next to the app |
| History | `history.json`, next to the app |
| Downloaded models | `models/`, next to the app |
| API keys | Windows Credential Manager, under `infinisper` |
| Audio | nowhere — memory only, discarded after each take |

Every take is timed step by step and written to history, which is how the History tab can
show you where the time went on any given sentence.

---

## Things deliberately left out

**No partial text on screen while you speak.** Nemotron decodes as you talk, but the pill
never shows in-progress text. Partials flicker and rewrite themselves, and reading them
while speaking is a distraction. Streaming is used here as a latency technique, not a UI
feature.

**No cloud speech recognition.** Transcription is always local. Only the optional AI cleanup
step can involve a network, and only if you configure it.

**The pill never takes focus.** It's frameless, always-on-top, click-through, and shown
without activating. If it ever took focus, the application you're dictating into would lose
its caret and the paste would go nowhere. That constraint is why it has no buttons — every
interactive element is another chance to steal focus.

**No PyQt.** PySide6 is the official Qt binding under LGPL-3.0; PyQt is GPL or paid. Every
dependency here has to permit commercial use.

---

## Known rough edges

Worth knowing if you're reading the code:

- **The Nemotron streaming path runs a stateful high-pass filter (>80 Hz)** in its worker
  thread to eliminate desk rumble and DC drift. Batch engines additionally get whole-take
  VAD silence trimming and RMS normalisation; the streaming session is decoded in real time
  as chunks arrive, so whole-take normalisation is bypassed to avoid dynamic pumping artifacts.
- **Custom dictionary terms only reach Whisper and the cleanup step.** Biasing Qwen3 or
  Nemotron needs a tokenizer file their published builds don't ship.
