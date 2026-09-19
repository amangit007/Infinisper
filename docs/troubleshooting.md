# Troubleshooting

## The hotkey does nothing

**Check the tray icon first** — if **Pause dictation** is ticked, untick it.

**In an app running as administrator?** Windows won't let a normal program send keystrokes
into an elevated window. Task Manager, Registry Editor, and some installers are affected.
Run Infinisper as administrator too, or dictate somewhere else and paste.

**Nothing in the tray at all?** The app may not have started. Run `run.bat` from a Command
Prompt so you can see the error.

## I get "Too quick, ignoring"

You need to hold the key for at least a moment — very short presses are treated as
accidental. Hold `Ctrl + Win` for the whole time you're speaking, then release.

## It says "Silence, ignoring" but I definitely spoke

Check the mic level pill at the bottom of the screen while you talk. If it isn't moving,
Windows is recording from a different device than you think.

Pick the right microphone in the **Dashboard**. Laptops with several inputs (built-in array,
headset, webcam) often default to one you're not talking into.

## The first word gets cut off

It shouldn't — the app keeps a rolling half-second of audio so the start of your sentence
survives. The one exception is the very first take right after launch, before that buffer
has filled. Dictate once, discard it, and the next one will be complete.

## The text is wrong in the same way every time

Names, acronyms, and jargon are the usual culprits. Add them in the **Language** tab, one
per line.

If it's a whole language being misheard, set your dictation language explicitly in that tab
instead of leaving it on automatic.

## Transcription is slow

Check the **History** tab — it breaks each take down by step, so you can see whether time is
going to the speech engine, the AI cleanup, or the network.

If the speech engine is the slow part, try Nemotron; it transcribes while you talk rather
than after you stop. If it's the network, the cleanup step is the cost — turn it off, or run
it locally through Ollama.

## Local cleanup through Ollama is slow or fails

- **First request after a break is slow:** Ollama unloads idle models after 5 minutes. On the Dashboard, ensure **Keep model loaded** is active (default is 30 minutes) so the model remains warm in memory.
- **Use a lightweight model:** Compact models between 0.5B and 1.5B parameters (e.g. `qwen2.5:0.5b`) provide fast text cleanup with low resource usage. Larger models (>7B) add noticeable latency without meaningful benefit for simple punctuation and formatting.
- **Connection check:** Ensure Ollama is running locally. If configuring a custom endpoint, use `http://127.0.0.1:11434`.

## My old clipboard came back instead of the dictated text

Some applications read the clipboard lazily — certain Electron apps, remote desktop
sessions, and a few web editors. Infinisper waits before restoring your previous clipboard
contents, but a slow app can still lose the race.

Dictate again; it usually works the second time. If one app does it consistently, that's
worth an issue.

## A model download failed

Downloads resume, so start it again from **Models & providers**. If it keeps failing partway,
check you have the disk space — Qwen3 needs about 980 MB and Nemotron about 650 MB.

## The AI cleanup isn't doing anything

Open **Models & providers** and use the test button on the model. Common causes:

- No model is set as active.
- The model is **text-only** but you picked the audio-straight-to-AI mode. That mode needs a
  model that accepts audio.
- The API key is missing or expired.

If the cleanup step fails, you still get your transcribed text — so an unpolished result is
the symptom to look for, not an error message.

A cloud model that answers "high demand" or "rate limited" twice in a row is skipped for about a
minute, so you aren't left waiting on it for every dictation. Your text still arrives, just
unpolished, until it recovers.

## "Infinisper is already running"

It's in the tray. The app only runs one copy at a time so two instances don't fight over
your microphone and hotkey; launching it again just brings the existing window forward.

If there's no tray icon and you still get this message, the previous process didn't shut
down cleanly. End `python.exe` in Task Manager and start again.

## Still stuck

Run `run.bat` from a Command Prompt rather than double-clicking it — the app logs each step
of the pipeline to the console, and that output is what's useful in a bug report.
