<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Infinisper logo — a clipboard capturing a speech bubble with sound waves leaving it">
</p>

<h1 align="center">Infinisper</h1>
<p align="center"><strong>Instant ~0.24s Streaming Voice Typing for Windows (No GPU Required).</strong></p>
<p align="center"><em>Hold a key, speak naturally, release — clean, AI-polished text lands at your cursor in a fraction of a second. 100% offline & private.</em></p>

<p align="center">
  <a href="https://github.com/amangit007/Infinisper/releases/tag/v1.1.0"><img src="https://img.shields.io/github/v/release/amangit007/Infinisper?color=0078d4&label=release" alt="latest release"></a>
  <a href="https://github.com/amangit007/Infinisper/actions/workflows/tests.yml"><img src="https://github.com/amangit007/Infinisper/actions/workflows/tests.yml/badge.svg" alt="tests"></a>
  <img src="https://img.shields.io/badge/platform-Windows%2010%2F11-0078d4" alt="Windows 10/11">
  <img src="https://img.shields.io/badge/license-MIT-green" alt="MIT license">
  <img src="https://img.shields.io/badge/privacy-100%25%20local-success" alt="100% Local">
  <img src="https://img.shields.io/badge/hardware-runs%20on%20CPU-blueviolet" alt="Runs on CPU">
</p>

<p align="center">
  <a href="https://github.com/amangit007/Infinisper/releases/download/v1.1.0/Infinisper-v1.1.0-Setup.exe">
    <img src="https://img.shields.io/badge/Download_for_Windows-v1.1.0_Setup.exe-0078D4?style=for-the-badge&logo=windows&logoColor=white" alt="Download for Windows">
  </a>
  &nbsp;
  <a href="https://github.com/amangit007/Infinisper/releases/download/v1.1.0/Infinisper-v1.1.0-Portable.zip">
    <img src="https://img.shields.io/badge/Download_Portable-v1.1.0_Zip-2ea44f?style=for-the-badge&logo=windows&logoColor=white" alt="Download Portable">
  </a>
</p>

<p align="center">
  <img src="assets/demo.gif" width="860" alt="Holding Ctrl+Win and speaking a sentence: the floating pill shows the mic level, then the cleaned-up text appears in Notepad">
</p>

Most voice dictation tools on Windows force you to compromise:
1. **Cloud Dictation (e.g. Wispr Flow):** Makes you pay a monthly recurring subscription and streams your live microphone audio to remote servers.
2. **Standard Whisper Wrappers:** Process audio in batch mode, forcing you to wait 3–5 seconds after speaking for the model to finish decoding on your CPU.

**Infinisper is engineered differently: a dedicated, real-time streaming speech engine that processes 50 ms audio chunks in RAM *while you are still speaking*. By the time your finger leaves the hotkey, 95% of the transcription is already completed.**

---

## The 5 Core Unfair Advantages

* ⚡ **Instant Response (~0.24s Latency on CPU):** Powered by Nemotron 3.5 streaming ASR via `sherpa-onnx`. Zero waiting for batch decodes, even on standard Intel & AMD CPUs without a dedicated GPU.
* 🛡️ **Zero Lost Words (500ms Pre-Roll Ring Buffer):** A circular memory buffer in RAM ensures your first syllable is never truncated if you speak the exact millisecond you press the hotkey.
* 📋 **Non-Destructive Clipboard:** Pastes into any app but automatically restores whatever code snippet, regex, or password you had previously copied.
* 🌐 **Multilingual & Code-Mixing Champion:** Integrates Qwen3-ASR for complex code-mixed speech (e.g. Hinglish, multilingual European/Asian languages) where Whisper frequently hallucinates.
* 🎙️ **Studio Audio Pipeline:** 23×-vectorized 80 Hz rumble filter, mechanical keyboard click notch filter, and Silero VAD for acoustic isolation.

---

## How It Compares

| Feature | Infinisper | Cloud Dictation (Wispr Flow) | Typical Whisper Wrappers |
|---|---|---|---|
| **Pricing** | **Free & Open Source (MIT)** | Paid subscription (~$12–$15/mo) | Free / Open Source |
| **Speech Recognition** | **100% Local (Runs on CPU)** | Remote cloud servers | Local or Cloud |
| **Latency** | **~0.24s (Streaming ASR)** | ~1.0s (Network round-trip) | 2–8s (Batch waits for audio to end) |
| **Hardware Needed** | **Standard Intel / AMD CPU** | Any (Cloud-based) | Often requires NVIDIA GPU |
| **Model Configurability** | **8 local engines (Whisper Tiny→Large-v3, Nemotron, Qwen3)** | Closed / Fixed | Usually 1 fixed Whisper model |
| **Storage Transparency** | **Interactive disk breakdown & 1-click delete** | N/A (Cloud hosted) | Unmanaged hidden cache folders |
| **First-Word Truncation** | **None (500ms pre-roll buffer)** | Rare | Very common (mic start delay) |
| **Clipboard Safety** | **Restores previous clipboard** | Direct hook / paste | Overwrites system clipboard |
| **AI Formatting & Polish** | **Local via Ollama** (or Cloud) | Cloud AI | None (raw text only) |
| **Audio Privacy** | **100% Local (RAM only)** | Sent to remote servers | 100% Local |

---

## Why Infinisper Stands Out from Other GitHub Alternatives

If you explore open-source Wispr Flow alternatives on GitHub, most fall into one of two traps:
1. **Barebones Whisper Wrappers:** They record audio to a file and run batch Whisper on key release, forcing you to wait 3–6 seconds after every sentence, frequently cutting off your first word, and dumping gigabytes of untracked model files in hidden cache folders.
2. **Cloud-Tethered Clones:** They hook a hotkey but stream your live microphone audio to remote servers (OpenAI or Groq), requiring recurring API fees and sacrificing audio privacy.

**Infinisper combines instant out-of-the-box speed with deep local configurability and storage sovereignty:**

- **⚡ Real-Time Streaming on CPU:** Native FastConformer streaming (Nemotron 3.5) and Dynamic Catch-Up Batching (Qwen3-ASR) decode 50 ms audio slices *while you speak*, delivering instant ~0.24s transcription on standard CPUs without a discrete GPU.
- **🎛️ Complete Model Sovereignty:** Choose from 6 discrete Whisper sizes (Tiny, Base, Small, Medium, Large v3 Turbo, Large v3) for batch accuracy, streaming Nemotron for speed, or Qwen3 for multilingual code-mixing. **Zero silent auto-downloads** — you download and activate only what you want.
- **📊 Visual Storage Transparency:** Full control over your disk footprint with real-time byte/speed progress meters, an interactive storage breakdown doughnut chart, and 1-click model deletion.
- **🛡️ 100% Private Hybrid AI Polish:** Clean up "um/uh", fix grammar, and format spoken lists locally using pre-warmed Ollama LLMs with thinking suppression, or optional free cloud fallbacks.
- **🎙️ Studio Audio Engineering:** A 500 ms pre-roll ring buffer prevents first-syllable loss; an 80 Hz rumble notch filter rejects mic thumps; and non-destructive clipboard restoration preserves your previously copied code and passwords.

---

## Why It Feels Instant (Even on CPU)

Most offline speech tools use batch processing: you speak for 20 seconds, release the key, and then wait several seconds while the model decodes the full audio file.

Infinisper uses **real-time streaming speech recognition**. It processes 50 ms audio chunks *while you are still speaking*. 

### Measured response times (key release → text pasted)

Measured on a standard laptop CPU (Ryzen 7, 8 cores). The speech engine runs **purely on the CPU**:

| Stage | What runs | Hardware | Wait time |
|---|---|---|---|
| **Speech to Text** | Nemotron (Streaming ASR) | **CPU** | **~0.24 s** *(constant, however long you spoke)* |
| **Optional AI Cleanup** | Ollama (e.g. Qwen 0.5B–1.5B) | Local CPU / GPU | **+ 0.30–0.50 s** *(nothing leaves PC)* |
| **Optional Cloud Cleanup** | Groq or Gemini Flash Lite | Free Cloud API | + 0.50–0.80 s |

> **Total time from releasing the hotkey to formatted text:**
> - **~0.24 s** with local speech recognition alone (raw verbatim text)
> - **~0.56 s** with local speech + recommended local Ollama cleanup
>
> Every benchmark is reproducible on your own PC via the scripts in [`benchmarks/`](benchmarks). See the full [Benchmarks Guide](docs/benchmarks.md) for memory consumption, accuracy scores, and multilingual evaluations.

---

## Quick Start

### Option A: Single-Click Windows Installer (Recommended)

1. Download **[`Infinisper-v1.1.0-Setup.exe`](https://github.com/amangit007/Infinisper/releases/download/v1.1.0/Infinisper-v1.1.0-Setup.exe)** from the [Releases page](https://github.com/amangit007/Infinisper/releases/tag/v1.1.0).
2. Run the installer and launch Infinisper.
3. Put your cursor in any application, hold **`Ctrl + Win`**, speak, and release.

### Option B: Run from Source (Developers)

#### Requirements
- **Windows 10 or 11** (64-bit)
- **Python 3.12, 3.13, or 3.14** (ensure **"Add Python to PATH"** is checked)
- Standard multi-core CPU (no GPU required)

```cmd
git clone https://github.com/amangit007/Infinisper.git
cd infinisper
install.bat
run.bat
```

1. `install.bat` creates a virtual environment and installs dependencies.
2. `run.bat` launches Infinisper into your system tray and opens the Dashboard.
3. Put your cursor in any app, hold **`Ctrl + Win`**, speak, and release.

Infinisper keeps your initial download light and does not auto-download speech models in the background. On your first launch, an onboarding banner lets you download **Whisper Base (~145 MB)** with one click, or choose from real-time streaming **Nemotron 3.5**, **Qwen3-ASR**, or larger Whisper models (Small to Large-v3) in **Models & providers**.

---

### Recommended: Local AI cleanup with Ollama

For the full Wispr Flow experience (stripping "um/uh", fixing grammar, formatting lists into bullets) without anything leaving your machine:
1. Install [Ollama](https://ollama.com) and pull a small model:
   ```cmd
   ollama run qwen2.5:0.5b
   ```
2. Open Infinisper's **Models & providers** tab, select **Ollama (local)**, and choose your model.
3. That's it — 100% offline, intelligent dictation.

---

## Documentation

Comprehensive guides covering setup, tuning, and internal architecture:

| Guide | Description |
|---|---|
| [Getting Started](docs/getting-started.md) | Installation, first dictation, tray options, and hotkey configuration |
| [Choosing a Model](docs/choosing-a-model.md) | Comparing speech engines (Nemotron, Qwen3, Whisper) and cleanup models |
| [Performance Guide](docs/performance-guide.md) | CPU optimization, latency tuning, and recommended setups |
| [Benchmarks](docs/benchmarks.md) | Verified latency, memory usage, and multilingual accuracy benchmarks |
| [How It Works](docs/how-it-works.md) | Audio engineering, ring buffers, streaming architecture, and paste mechanics |
| [Future Capabilities](docs/future-capabilities.md) | Roadmap covering active window adaptation, command mode, and screen context |
| [Privacy](docs/privacy.md) | Exact details on memory handling, data isolation, and API security |
| [Troubleshooting](docs/troubleshooting.md) | Solutions for hotkeys, audio devices, and local connections |

---

## Built with

| Component | Library / Framework | License |
|---|---|---|
| **UI** | PySide6 (Qt for Python) | LGPL-3.0 |
| **Speech Engines** | sherpa-onnx (Nemotron, Qwen3), faster-whisper | Apache-2.0 / MIT |
| **Audio Processing** | Silero VAD, SoundDevice, NumPy | MIT / BSD |
| **AI Cleanup** | LiteLLM (Ollama, Gemini, Groq, OpenAI) | MIT |
| **Key Storage** | Keyring (Windows Credential Manager) | MIT |

---

## Development & Building

```cmd
.\.venv\Scripts\pip install -r requirements-dev.txt
.\.venv\Scripts\pytest
python benchmarks/engines.py
```

To compile the standalone Windows executable and installer locally:
```cmd
build_installer.bat
```

---

## License

Released under the [MIT License](LICENSE).
