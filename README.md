<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Infinisper logo — a clipboard capturing a speech bubble with sound waves leaving it">
</p>

<h1 align="center">Infinisper</h1>
<p align="center"><em>local-first dictation for Windows</em></p>

<p align="center">
  <a href="https://github.com/amangit007/infinisper/actions/workflows/tests.yml"><img src="https://github.com/amangit007/infinisper/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
</p>

<p align="center">
  <img src="assets/demo.gif" width="860" alt="Holding Ctrl+Win and speaking a sentence: the floating pill shows the mic level, then the cleaned-up text appears in Notepad">
</p>

**Hold a key, speak, release — the text lands wherever your cursor is.**

Speech recognition runs on your PC. An optional AI step tidies the text — removes "um" and "uh",
fixes punctuation, turns a spoken list into bullets — and that can run on your PC too, through
[Ollama](https://ollama.com). No subscription, no account, MIT licensed.

---

## Why it feels fast

Time from letting go of the key to finished text, measured on a laptop (Ryzen 7, no dedicated GPU):

| Setup | Wait |
|---|---|
| Nemotron streaming, no cleanup | **0.24 s** — however long you spoke |
| Nemotron + local Ollama cleanup (qwen 0.5B–0.8B) | **0.56 s** — nothing leaves the machine |
| Nemotron + Groq (GPT-OSS 120B) | 0.78 s |
| Nemotron + Gemini 3.5 Flash Lite | 1.02 s |

Nemotron transcribes *while you're still talking*, which is why the wait doesn't grow with a longer
take. Every number comes from a script in [`benchmarks/`](benchmarks) you can run yourself — see
[Benchmarks](docs/benchmarks.md) for the full tables, including memory use and other languages.

## What you get

- **Works in any app.** A global hotkey (`Ctrl+Win` by default, configurable) pastes into Notepad, Chrome, Slack, VS Code — and puts your clipboard back afterwards.
- **Three speech engines.** Whisper for a quick start, Nemotron for fast everyday dictation (it also scored best on Hindi), Qwen3-ASR for accuracy in French, German, Chinese and Japanese. Switch any time.
- **Optional AI cleanup**, your choice of where it runs: local (Ollama), or a hosted model (Gemini, Groq, OpenAI, and others through LiteLLM). It can also translate or write Hindi in Latin script.
- **Private by default.** Your voice never leaves the machine unless *you* send audio to a cloud model. API keys live in Windows Credential Manager, not in a file.
- **A small floating indicator** that shows your mic level without taking focus, and a light and dark theme.

## Install

You need Windows 10 or 11 and Python 3.12, 3.13 or 3.14 (tick **Add Python to PATH** when installing it).

```cmd
git clone https://github.com/amangit007/infinisper.git
cd infinisper
install.bat
run.bat
```

It starts with Whisper. Its small model (about 140 MB) downloads by itself the first time you launch,
so that first start needs internet; after that it works offline. Faster and more accurate engines are
a click away in **Models & providers** — nothing else downloads until you ask.

## Documentation

| | |
|---|---|
| [Getting started](docs/getting-started.md) | Install, first dictation, the tray menu |
| [Choosing a model](docs/choosing-a-model.md) | Which speech engine and which cleanup model to pick |
| [Performance guide](docs/performance-guide.md) | Tested setups and tuning tips |
| [Benchmarks](docs/benchmarks.md) | Measured speed, memory and accuracy |
| [How it works](docs/how-it-works.md) | What happens between the hotkey and the paste |
| [Privacy](docs/privacy.md) | Exactly what leaves your machine, and when |
| [Troubleshooting](docs/troubleshooting.md) | When something doesn't behave |

## Built with

| | |
|---|---|
| UI | PySide6 (LGPL-3.0, dynamically linked) |
| Speech | sherpa-onnx (Nemotron, Qwen3-ASR), faster-whisper, Silero VAD — Apache-2.0 / MIT |
| AI cleanup | LiteLLM (MIT) — Ollama, Gemini, Groq, OpenAI and more |
| Keys | keyring (MIT) — Windows Credential Manager |

## Development

```cmd
pip install -r requirements-dev.txt
pytest
python benchmarks/engines.py
```

The tests cover the audio chain, the streaming and chunking logic, the cleanup safeguards, and the
theme contrast ratios.

## License

[MIT](LICENSE).
