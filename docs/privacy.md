# Privacy

The short version: **transcription happens on your machine.** Nothing is uploaded unless
you deliberately turn on the AI cleanup step and point it at a cloud provider.

## Your voice

Audio is captured at 16 kHz, held in memory while you're speaking, and discarded as soon as
the take is transcribed. It's never written to disk. There is no recordings folder.

The microphone stream stays open while the app runs — that's what lets the first word of
each take survive, rather than being lost to the moment it takes a mic to spin up. Nothing
is kept from it unless you're holding the hotkey.

## What leaves your machine

| | Leaves your machine? |
|---|---|
| Speech engines (Whisper, Nemotron, Qwen3) | No. Fully local. |
| AI cleanup via Ollama | No. Local model, local request. |
| AI cleanup via a cloud provider | Yes — see below. |
| Usage stats, telemetry, crash reports | None. There is no analytics of any kind. |

If you configure a cloud provider for cleanup, then depending on the mode you chose, either
your **transcribed text** or your **actual audio recording** is sent to that provider. The
Dashboard shows which route is active before you dictate. If that's not what you want,
either leave the cleanup step off or use Ollama.

## API keys

Keys go into Windows Credential Manager through the `keyring` library. They aren't stored in
`config.json`, in a `.env` file, or anywhere else in this folder. You can see and revoke
them in Windows' own **Credential Manager** under the name `infinisper`.

## Your dictation history

Everything you dictate is saved to `history.json` next to the app, along with timings, so
you can look back at what you said. This file never leaves your machine, and it isn't
tracked by git.

If you'd rather not keep it, delete the file — the app recreates an empty one. Clearing it
while the app is running is easiest from the **History** tab.

## The clipboard

Text is delivered by putting it on your clipboard and sending Ctrl+V, because that's the
only method that works reliably across every Windows application.

Infinisper puts your previous clipboard contents back afterwards. If you copied something
new in the meantime, your copy wins and the restore is skipped.

## Microphone access

Windows may show a microphone indicator whenever Infinisper is running, because the audio
stream stays open. That's expected. Use **Pause dictation** in the tray menu if you want the
hotkey to stop responding.
