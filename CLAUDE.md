# CLAUDE.md

Claude Code working notes for this repository.

**The shared rules live in [`AGENTS.md`](AGENTS.md) — read that first.** This file covers only the
things specific to working here with Claude Code, and does not repeat the invariants.

---

## Orientation, in order

1. [`AGENTS.md`](AGENTS.md) — stack, the eleven invariants, layout, conventions
2. [`docs/PLAN.md`](docs/PLAN.md) — which phase we are in and what "done" means for it
3. The doc for whatever you are touching:
   - behaviour of a mode or a prompt → [`docs/MODES.md`](docs/MODES.md)
   - components, threading or the state machine → [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)
   - adding or swapping a model → [`docs/MODELS.md`](docs/MODELS.md)
   - UI work → [`docs/UI-SPEC.md`](docs/UI-SPEC.md)
   - adding any library → [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md)

> **This project was Electron/TypeScript until August 2026 and is now Python + PySide6**
> ([ADR-010](docs/DECISIONS.md#adr-010)). Anything you find assuming Node, npm, renderers or IPC
> channels is stale — flag it rather than working around it.

## Current state

**Fully implemented and working desktop application.** Infinisper consists of ~7,000 lines of
tested Python 3.11+ code with 97 passing unit tests.

### What is built and working:
- **Application Core**: `main.py` and `app.py` with single-instance lock (`QLocalServer`) and Windows explicit AUMID.
- **Global Hotkey**: Low-level hook capturing `Ctrl+Win` hold-to-talk.
- **Audio Capture & DSP**: `sounddevice` at 16 kHz mono float32 with high-pass rumble filter, DC offset removal, pre-emphasis filter, peak dynamic range normalization, and Silero VAD (`audio/preprocessor.py`, `audio/vad.py`).
- **Speech Recognition (ASR)**:
  - Streaming FastConformer via `sherpa-onnx` (Nemotron 3.5 ASR)
  - `faster-whisper` (Whisper base/small)
  - Multilingual `sherpa-onnx` (Qwen3-ASR)
- **Refinement & Multimodal**: LiteLLM integration for polishing grammar/fillers and formatting via cloud LLMs (Gemini, OpenAI) or local Ollama (`multimodal/`).
- **Text Injection**: Clipboard preservation, foreground window restoration, and `SendInput` simulated Ctrl+V (`app.py`, `timing.py`).
- **User Interface**:
  - Floating non-activating status chip with animated mic levels and state transitions (`ui/chip.py`). Never steals window focus.
  - Glassmorphic settings main window with theme engine, models tab, language tab, custom dictionary, and history (`ui/main_window.py`, `ui/theme.py`, `ui/tabs/`).
  - Branded animated splash screen and system tray icon (`ui/splash.py`, `ui/tray.py`).
- **Security & Storage**: Secrets in Windows Credential Manager via `keyring` (`credentials.py`). Configuration in `config.py` / `config.json`. Dictation history in SQLite/JSON (`history/`).

### Quick Commands:
- Run the application: `python main.py` or `run.bat`
- Run unit tests: `pytest`
- Install dependencies: `install.bat` or `pip install -r requirements.txt`

---

## Verification, and its limits

Most of this app cannot be verified by reading a diff or running a test suite. Three categories, and
you should be explicit about which one you actually exercised:

**Unit-testable, so test it:** the state machine, text post-processors, prompt builders, the hotkey
combo parser, provider `probe()` result mapping. These are pure by design — if something you need to
test imports Qt or Win32, that is the bug.

**Only verifiable by hand:** hotkeys, focus behaviour, pasting, chip appearance. Use the smoke
checklist in [`docs/PLAN.md`](docs/PLAN.md#manual-smoke-checklist). Do not claim these work because the
code looks right — say you couldn't verify it and ask the user to try it.

**Only verifiable in a built binary:** model paths, PyInstaller hooks, LGPL dynamic linking, autostart,
code signing, antivirus behaviour. `python -m freewisperr` passing tells you nothing about any of these.

The one exception worth automating despite the difficulty: **assert the chip does not steal focus**.
It is invariant 1, and a regression there silently breaks the entire product.

---

## Working style for this repo

- **Ask before adding a dependency**, and check its licence first. Every dependency must be open source
  *and* permit commercial use — that constraint has already reshaped this project once (Moonshine was
  dropped over it). **Never add PyQt**: GPL or paid, where PySide6 is LGPL. See
  [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).
- **Watch for PyTorch in the transitive tree.** It is how a 250 MB install becomes 2.5 GB.
- **Qt threading discipline is on you.** Electron's process boundaries enforced separation for free;
  Qt enforces nothing. Widgets only from the main thread, workers communicate by signal. A direct
  cross-thread widget call appears to work and then crashes non-deterministically in the field.
- **Windows-specific behaviour deserves a comment.** UIPI, AltGr, the Start-menu leak, clipboard
  timing — these read as arbitrary to the next person. Write down why.
- **Prefer editing the spec over arguing in chat.** If we agree on a behaviour change, put it in the
  relevant `docs/` file in the same turn. The docs are the durable artefact; this conversation is not.
- The original design session's plan file is at
  `~/.claude/plans/i-am-thinking-of-recursive-hippo.md` if you want the full research trail, though
  note it predates the Python pivot.

## Environment

- Windows 11, PowerShell. `&&` and `||` do not work — use `;` or `if ($?) { }`.
- **Do not bulk-edit files with PowerShell.** `Get-Content -Raw` reads UTF-8 files as ANSI and
  `Set-Content` writes them back mangled, which corrupts every em-dash and box-drawing character in
  these docs. Use the Edit tool.
- Python 3.11+. Use a virtualenv; pin versions in `requirements.txt` once the project is scaffolded.
- Ollama, if installed, listens on `http://localhost:11434`. Probe it with
  `Invoke-RestMethod http://localhost:11434/api/tags` — read only, never `ollama pull`.
