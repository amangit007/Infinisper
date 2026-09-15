<p align="center">
  <img src="assets/logo.svg" width="96" height="96" alt="Infinisper logo — a clipboard capturing a speech bubble with sound waves leaving it">
</p>

<h1 align="center">Infinisper</h1>
<p align="center"><em>local-first dictation</em></p>

**Ultra-fast, private, on-device AI dictation for Windows.**

Hold `Ctrl+Win`, speak naturally, release — your words appear instantly at your cursor in whatever app you are using.

Unlike cloud dictation tools, transcription in **Infinisper** happens directly on your machine. Your voice never leaves your computer unless you explicitly choose to enable a cloud multimodal model for styling and grammar polish.

---

## ⚡ Highlights

- **Instant Dictation Anywhere**: System-wide global hotkey (`Ctrl+Win`) injects text into any editor, browser, IDE, or chat app without losing your typing caret.
- **Whisper & Nemotron 3.5 ASR**: Powered by `sherpa-onnx` and `faster-whisper` for sub-second, on-device transcription with zero cloud latency.
- **Robust on Low Voices & Whispers**: Built-in audio preprocessor featuring DC offset removal, 80 Hz high-pass rumble filter, pre-emphasis for crisp consonant clarity, and peak dynamic range normalization.
- **Wispr-Flow-Style Intelligence**: Optional AI text polishing via local or cloud LLMs (Ollama, Gemini, OpenAI) to eliminate filler words, fix grammar, and format lists into bullet points.
- **Zero Focus-Stealing Floating Chip**: Non-intrusive glassmorphism status pill at the bottom of your screen that shows real-time microphone level animations without ever taking window focus.
- **Branded Cold-Start Splash**: The mark's own anatomy — clipboard, speech bubble, sound waves — animates as the loading indicator while the speech model loads, so first launch reads as visible progress instead of a frozen window.
- **Privacy First**: Audio is held in RAM only during dictation and immediately discarded. API keys are stored in Windows Credential Manager (`keyring`), never in plaintext files.

---

## 🚀 Quick Start

### 1. Requirements
- **Windows 10 / 11** (64-bit)
- **Python 3.10+** (ensure "Add Python to PATH" is checked during installation)

### 2. One-Click Setup
1. Clone or download the repository:
   ```cmd
   git clone https://github.com/amangit007/infinisper.git
   cd infinisper
   ```
2. Double-click **`install.bat`** (or run `install.bat` in Command Prompt) to automatically create a virtual environment and install all dependencies.
3. Launch Infinisper with **`run.bat`** (or run `python main.py`).

---

## 🎙️ Speech Recognition Engines

| Engine | Type | Download Size | Best For |
|---|---|---|---|
| **Whisper (base / small)** | Local (Offline) | Included in cache (~140MB+) | Default safety-net fallback. Exceptional general English accuracy. |
| **Nemotron 3.5 ASR (0.6B)** | Local Streaming | ~650 MB | **Ultra-low latency streaming.** FastConformer-RNNT architecture transcribes in 1120ms streaming chunks. |
| **Qwen3-ASR (0.6B)** | Local (Offline) | ~980 MB | Deep multilingual accuracy and clean punctuation formatting. |

Models are downloaded directly on demand with progress bars in the **Models & providers** tab.

---

## 🛠️ Modes & AI Refinement

1. **Speech-to-Text Only**: Fast, direct transcription from your local ASR engine straight to your cursor.
2. **Speech + Multimodal Refinement**: The raw transcription is instantly polished by a fast LLM (e.g. Gemini 3.8 Flash, Ollama, etc.) to fix grammar, punctuation, and flow while preserving your meaning.
3. **Multimodal Direct Audio**: Feeds the raw audio directly to an audio-capable multimodal model for end-to-end interpretation.

---

## ⌨️ How to Use

1. Place your cursor in any textbox (Notepad, Chrome, Word, Slack, VS Code, etc.).
2. **Press and hold `Ctrl+Win`**.
3. Speak your thoughts. The floating pill at the bottom of the screen will show live microphone levels.
4. **Release `Ctrl+Win`**. The audio is transcribed, formatted, and pasted into your active application.
5. Use the system tray icon to open settings, pause dictation, switch themes, or exit.

---

## 🔒 Privacy & Architecture

- **Audio Data**: Captured via `sounddevice` at 16 kHz mono float32. Held strictly in memory and wiped immediately after inference.
- **Keyring Security**: All provider credentials use Windows Credential Manager (`_SERVICE_NAME = "infinisper"`).
- **Single-Instance Protection**: Built-in local socket lock prevents multiple background instances from colliding over microphone or hotkey access.

### Third-Party Stack & Licenses

| Layer | Library | License | Notes |
|---|---|---|---|
| **UI, Overlay & Tray** | `PySide6` | LGPL-3.0 | Official Qt bindings, dynamically linked |
| **ASR Engines** | `sherpa-onnx`, `faster-whisper` | Apache-2.0 / MIT | On-device streaming & offline transcription |
| **ONNX Runtime** | `onnxruntime` | MIT | Hardware-accelerated inference backend |
| **Audio Capture & VAD** | `sounddevice`, Silero VAD | MIT | 16 kHz float32 capture & voice activity detection |
| **LLM Routing** | `litellm` | MIT | Multi-provider polish and rephrasing |
| **Credential Storage** | `keyring` | MIT | Windows Credential Manager integration |

---

## 🧪 Development & Testing

1. Activate your virtual environment:
   ```cmd
   .venv\Scripts\activate
   ```
2. Install test dependencies:
   ```cmd
   pip install -r requirements-dev.txt
   ```
3. Run the test suite:
   ```cmd
   pytest
   ```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details. Third-party open-source libraries used in this project are listed in the table above and adhere to permissive open-source licenses (MIT, Apache-2.0, BSD-3-Clause, and LGPL-3.0).

