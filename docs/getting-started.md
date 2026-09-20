# Getting started

## Install

You need Windows 10 or 11 (64-bit) and Python 3.12, 3.13 or 3.14. When you install Python, tick
**"Add Python to PATH"** — if you miss it, the setup script won't find Python.

```cmd
git clone https://github.com/amangit007/infinisper.git
cd infinisper
install.bat
```

`install.bat` creates a virtual environment and installs the dependencies. It takes a few
minutes the first time. After that, launch with `run.bat`.

## First run

Infinisper opens a settings window and places an icon in your system tray. **No speech model is auto-downloaded by default**, saving your bandwidth and storage until you decide.

On your first launch:
1. The app shows an onboarding banner welcoming you to download an ASR model.
2. You can click **Download Whisper Base (~145 MB)** for a quick start, or navigate to **Models & providers** to select any model variant (from ultra-light Whisper Tiny to real-time streaming Nemotron or Whisper Large v3 Turbo).
3. Live progress bars track percentage, bytes downloaded, and speed.
4. Once downloaded, your chosen engine is ready to transcribe offline immediately.

You can delete any downloaded model at any time from **Models & providers** to reclaim disk space, or hover over the disk usage badge (`on disk X MB 📊`) for an interactive storage breakdown. See [Choosing a model](choosing-a-model.md) for recommendations.

## Dictating

1. Put your cursor wherever you want the text — Notepad, Chrome, Slack, VS Code, anything.
2. Hold **Ctrl + Win** (you can change the hotkey in the app — presets include `Right Ctrl` and `F8`).
3. Speak. A small pill appears at the bottom of your screen showing your mic level.
4. Release. The text appears at your cursor a moment later.

You don't need to click on Infinisper first. The hotkey works from any application, and the
pill never steals focus from what you're typing in.

Speak normally. You don't have to say punctuation out loud — the speech model adds it.

## The tray icon

Right-click it for:

- **Open Infinisper** — the settings window
- **Pause dictation** — the hotkey stops responding until you untick it
- **Quit**

The top line shows the current status (Ready, Listening, Transcribing).

Closing the settings window doesn't quit the app; it keeps running in the tray so the
hotkey stays live. Use **Quit** to actually stop it.

## Settings at a glance

| Tab | What's there |
|---|---|
| **Dashboard** | Which engines are on, your microphone, and whether to clean up text with an AI model |
| **Models & providers** | Download or delete speech engines; add cloud or local AI providers |
| **Language** | Your dictation language, and words the model keeps getting wrong |
| **History** | Everything you've dictated, with timings for each step |

Your settings live in `config.json` next to the app, and your dictation history in
`history.json`. Both stay on your machine.

## Start with Windows

There's an autostart toggle in the app. Turning it on adds Infinisper to your Windows
startup items so the hotkey is available as soon as you log in.
