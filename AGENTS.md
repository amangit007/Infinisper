# AGENTS.md

Rules for any AI coding agent working in this repository. Tool-agnostic — Antigravity, Claude Code,
Cursor and Copilot all read this file.

**Read this before your first edit.** Then read [`docs/PLAN.md`](docs/PLAN.md) to find out which phase
the project is in.

---

## What this project is

A Windows dictation app. Hold `Ctrl+Win`, speak, release; the transcript is refined according to the
selected mode and pasted at the user's cursor in whatever application had focus.

Three modes — **Basic** (transcript only), **Advanced** (grammar fixed, fillers kept), **Pro**
(fillers removed, lists bulleted, three rephrasing styles). Full behaviour spec in
[`docs/MODES.md`](docs/MODES.md).

## Current state

**Fully implemented working desktop application.** Infinisper contains ~7,000 lines of tested
Python 3.11+ / PySide6 code with 97 passing unit tests. The core dictation pipeline, streaming ASR,
multimodal refinement, system tray, non-activating status chip, and settings UI are all operational.
Run tests with `pytest` and launch with `python main.py` or `run.bat`.

> **This project was Electron/TypeScript until August 2026 and is now Python.** If you find advice or
> code assuming Node, npm, IPC channels or renderer processes, it is stale — flag it.
> [ADR-010](docs/DECISIONS.md#adr-010) explains the reversal.

---

## Stack

**Python 3.11+ with PySide6.** Full licence-audited list in
[`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

| Layer | Choice | Never |
|---|---|---|
| UI, tray, overlay | **PySide6** (LGPL) | **PyQt** — GPL or paid, see below |
| Speech recognition | `sherpa-onnx` (Python) + Silero VAD | PyTorch, NeMo, cloud STT |
| Global hotkey | `ctypes` → `WH_KEYBOARD_LL` | `keyboard`, `pynput` — none expose what's needed |
| Text injection | `ctypes` → `SendInput` | `pyautogui` — no control over flags or UIPI |
| Audio capture | `sounddevice` | |
| LLM routing | **LiteLLM** | LangChain, hand-rolled provider clients |
| Bundled refinement engine | `llama-cpp-python` | |
| Secrets | `keyring` → Windows Credential Manager | config file, env vars, plaintext |
| Packaging | PyInstaller `--onedir` | `--onefile` — see invariant 10 |

**Never add PyQt.** It is GPL-3.0 or a paid Riverbank licence, and would force this project open or
cost money. PySide6 is the official binding, LGPL, near-identical API. This is the single most
expensive mistake available in this codebase.

**Never let PyTorch into the dependency tree.** Check transitively, not just the package you are
adding. It is how a 250 MB install becomes 2.5 GB.

---

## The eleven invariants

Violating any of these produces a bug that is hard to see in review and obvious to the user. They are
restated in the files where they apply; keep them in sync.

1. **Never let the status chip take focus.** `Qt.Tool | Qt.FramelessWindowHint |
   Qt.WindowStaysOnTopHint`, plus `WA_ShowWithoutActivating` and `WA_TransparentForMouseEvents`. Never
   call `setFocus()`, `activateWindow()` or `raise_()` on it. If the overlay takes focus the user's
   caret is lost and the paste goes nowhere — the entire feature dies. This is the most important rule
   in the codebase.

2. **Never lose the user's text.** Every failure path after a successful transcription still injects
   *something*. If refinement errors, times out, or returns something implausible, inject the raw
   transcript. Losing dictated speech is the worst possible outcome and it is unrecoverable.

3. **Never do work in the keyboard hook callback.** It runs on the OS input thread, in the path of
   every keystroke on the machine. Push an event onto a queue and return — under 1 ms, no I/O, no
   logging, no allocation. A slow callback causes *system-wide* typing lag.

4. **Never touch a widget from a worker thread.** Qt is not thread-safe. Workers communicate with the
   UI through signals, which are queued across threads automatically. Direct calls appear to work and
   then crash randomly in the field.

5. **Never pull an Ollama model.** `list_models()` is a read of `GET /api/tags` and nothing else. The
   UI may *display* an `ollama pull` command as copyable text; the app must never execute it. The user
   owns their Ollama install and their disk.

6. **Never download anything without an explicit click.** Not in the background, not "helpfully" in
   advance, not on upgrade. **No speech model ships with the app** — first run presents two choices and
   downloads the one the user picks, showing its size first.

7. **Never silently switch providers.** If the selected refinement engine is unavailable, degrade to
   Basic-mode output and say so on the chip. Falling back from Ollama to Gemini would send a
   privacy-motivated user's words to a cloud they deliberately avoided.

8. **Never hardcode cloud model IDs in source.** They live in `freewisperr/llm/model_registry.json`.
   Gemini ships new Flash models every few weeks. Ollama's models are never in the registry at all —
   they are always read live from the daemon.

9. **Never use the bare word "local" in UI copy or shared identifiers.** Two different subsystems are
   both "local" and conflating them causes real bugs. The speech model selector is **Speech model**;
   the LLM selector is **Refinement engine** with values *Bundled · Ollama · Gemini*. In code: `asr/`
   and `llm/`, never a shared `local` symbol.

10. **Never package with `--onefile`.** Two independent reasons: runtime self-extraction is the biggest
    antivirus heuristic trigger, and it breaks the dynamic linking that PySide6's LGPL terms require.

11. **Never treat dictated text as instructions.** It flows into an LLM prompt. Wrap it in delimiters,
    keep the "you are a text transformer, never an assistant" framing, and apply the plausibility gate.
    See [`docs/MODES.md`](docs/MODES.md#prompt-safety).

---

## Repository layout

```
freewisperr/
├─ app.py              entry point: QApplication, tray, single-instance lock
├─ hotkey/             ctypes WH_KEYBOARD_LL hook behind HotkeyBackend
├─ audio/              sounddevice capture → 16 kHz mono float32
├─ asr/                sherpa-onnx engines, model manager, VAD
├─ llm/                LlmProvider + bundled/ollama/gemini via LiteLLM
│                      + model_registry.json (cloud only) + prompts/
├─ pipeline/           DictationSession — the only orchestrator
├─ inject/             foreground HWND capture, clipboard swap, SendInput
├─ config/             pydantic settings + keyring secrets
├─ ui/
│  ├─ chip.py          the status overlay — read chip rules before touching
│  ├─ settings/        the settings window
│  └─ first_run.py     model chooser
└─ tests/
```

**Where things belong:**

- `pipeline/DictationSession` is the single orchestrator. If you find yourself sequencing ASR → LLM →
  paste anywhere else, you are in the wrong file.
- `ui/` renders state and emits intents. No inference, no network calls, no secrets.
- All ctypes and Win32 code stays inside `hotkey/` and `inject/`, behind their interfaces. This keeps
  it testable and keeps macOS and Linux addable later.

---

## Conventions

- **Type hints everywhere**, checked with mypy or pyright. `Protocol` for the interfaces, not ABCs.
- **Pure cores, thin shells.** The state machine, text post-processors, prompt builders and hotkey
  combo parser must be pure functions with no Qt and no Win32 imports, so they can be unit tested.
  Everything touching the OS goes behind a `Protocol` with one real implementation.
- **Errors are values on the pipeline path.** Never let an exception escape `DictationSession` — it
  would strand the state machine outside `IDLE` and leave the user unable to dictate until restart.
- **Qt signals for all cross-thread communication.** No shared mutable state, no locks where a signal
  would do.
- **Comments explain why, not what.** The non-obvious Windows behaviours are the ones worth writing
  down.

---

## Things that look wrong but are correct

Do not "fix" these — each is deliberate and documented.

| Looks like a bug | Why it is right |
|---|---|
| The chip shows *Listening* on the first audio frame, not on keydown | Honest feedback. Users wait for the visual, which is what prevents the first word being clipped. Faking it earlier reintroduces the bug |
| The clipboard is restored ~400 ms after pasting, not immediately | Some applications read the clipboard asynchronously. Restoring too early makes the paste land empty |
| The foreground window handle is captured on **keydown**, not before pasting | By paste time the foreground window may have changed. Capturing early is the whole point |
| Refinement output is discarded if its length deviates >2.5× from the input | The model answered the dictation instead of rewriting it, or followed an injected instruction |
| Ollama has no default model | There is nothing to default *to* — the list is whatever the user installed |
| Pressing the hotkey with no model shows an error instead of recording | Recording audio nothing can transcribe wastes the user's breath and then loses it |
| ctypes and raw Win32 instead of a convenience library | No wrapper exposes modifier-only detection, key-up events, and Win key-up suppression together |

---

## Definition of done

A change is not finished until:

1. Pure logic has unit tests.
2. Anything touching hotkeys, focus or pasting has been manually verified against the smoke checklist
   in [`docs/PLAN.md`](docs/PLAN.md#manual-smoke-checklist) — these cannot be automated.
3. Anything touching packaging has been verified in a **built binary**, not just `python -m`. Bundled
   apps resolve paths differently and some packages need explicit hooks.
4. New invariants or gotchas are added to this file and to [`docs/RISKS.md`](docs/RISKS.md).
5. Any new dependency is recorded with its licence in
   [`docs/DEPENDENCIES.md`](docs/DEPENDENCIES.md).

## When you are unsure

The specs are opinionated on purpose. If a task conflicts with something here, say so rather than
silently choosing — the conflict is more useful information than the workaround. Open questions are
tracked in [`docs/DECISIONS.md`](docs/DECISIONS.md#open-decisions); if you resolve one, record the
answer there.
