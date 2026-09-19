# Performance & Optimization Guide

Practical advice for getting maximum speed and accuracy out of Infinisper on your hardware. Infinisper is designed to work out of the box on standard consumer CPUs, but you can tune your setup based on your workflow.

---

## Recommended Setups

| Your Goal | Speech Engine | AI Cleanup | Notes |
|---|---|---|---|
| **Fastest start, lowest memory** | Whisper (CPU) | Off | Works offline right after install; minimal RAM footprint. |
| **Everyday dictation (Recommended)** | Nemotron 3.5 (CPU) | Ollama (local, e.g. Qwen 0.5B–1.5B) | 100% local and private. ~0.5s response time. |
| **Long-form prose & bulleted lists** | Nemotron 3.5 (CPU) | Ollama (local, Gemma 4B) or Cloud (free tier) | Maximum formatting precision. |
| **Multilingual (FR, DE, ZH, JA)** | Qwen3-ASR (CPU) | Optional | Highest transcription fidelity for European & Asian languages. |
| **Hindi & Hinglish** | Nemotron 3.5 (CPU) | Optional (Ollama or Cloud) | Best-in-class accuracy for spoken Hindi. |

---

## The Speech Engines

All three engines run **100% locally on your CPU**. No discrete GPU or CUDA installation is required.

### 1. Nemotron 3.5 ASR (Best for Everyday English & Hindi)
- **Streaming by default:** Transcribes 50 ms audio slices while you are speaking. When you release the hotkey, only the final frame remains to decode.
- **Sub-200ms latency:** Typically finishes in ~130–170 ms on an ordinary laptop CPU.
- **Hindi accuracy:** Scored an impressive 1.9% Character Error Rate (CER) on real read speech, significantly outperforming Whisper Base.

### 2. Qwen3-ASR (Best for Non-English European & East Asian Languages)
- **High precision:** Tested as the top local engine for French, German, Chinese, and Japanese.
- **Batch processing:** Transcribes after key release. For best speed, speak in natural chunks (1–2 sentences at a time) rather than continuous multi-minute monologues.

### 3. Whisper (Quick Start)
- Bundled default that downloads a small model (~140 MB) on first launch. Low memory, reliable for basic dictation. Most daily users will prefer upgrading to Nemotron via **Models & providers**.

### Real-world latency on CPU

Medians over real dictation on an AMD Ryzen 7 laptop (no GPU used for speech recognition):

| Setup | Speech Engine (CPU) | Total (Key Release → Pasted Text) |
|---|---|---|
| **Nemotron (Streaming)** | **131 ms** | **169 ms** |
| **Nemotron + Local Ollama Cleanup** | 131 ms | **~0.56 s** |
| **Nemotron + Cloud Cleanup** | 127 ms | **1.06 s** |
| **Qwen3-ASR (Batch)** | 1.74 s | 3.35 s |

---

## AI Cleanup: Recommended Local Ollama Setup

AI cleanup is optional, but recommended if you want the polished Wispr Flow feel: removing filler words ("um", "like", "you know"), correcting punctuation, and structuring spoken lists into bullets.

### Recommended: Local Ollama (100% Offline)
To keep your data completely private, run a local LLM through [Ollama](https://ollama.com):
- **Model size recommendations:** A compact model between **0.5B and 1.5B parameters** (e.g. `qwen2.5:0.5b` or `qwen2.5:1.5b`) is lightning fast and runs smoothly on both CPU and GPU. For longer complex dictations, a ~4B model (like `gemma:4b`) provides higher formatting reliability.
- **Keep model loaded:** Ollama unloads idle models after 5 minutes by default. Infinisper automatically pre-warms your active model at launch and keeps it in memory for **30 minutes** (customizable in the Dashboard). A loaded model responds 5–8× faster than a cold start.
- **Reasoning disabled:** Thinking is automatically disabled for Ollama models so you don't wait tens of seconds on reasoning tokens for simple grammar cleanup.

### Optional: Cloud Providers
If you prefer not running a local LLM or have very constrained RAM, Infinisper supports Gemini (Flash Lite free tier), Groq, OpenAI, and any OpenAI-compatible provider via LiteLLM. Audio or text only leaves your machine if you explicitly configure a cloud provider.

---

## Regulating Accuracy in the Language Tab

Speech recognition models can sometimes mishear uncommon words or struggle with language switching. Use the **Language** tab to maximize transcription accuracy:

1. **Set your dictation language explicitly:**
   Instead of leaving the language on automatic detection, select your primary language. This eliminates detection latency and prevents misidentifying accents.
2. **Add custom vocabulary & jargon:**
   Technical terms, project codenames, acronyms, and proper names can be added one per line in the custom dictionary. Whisper uses these as decoding prompts, and the cleanup step is explicitly instructed to recognize and preserve them.
3. **Language transformations:**
   If you dictate in one language but want the text output in another (e.g., spoken Hindi formatted as Latin Hinglish, or direct translation), configure the output mode in the Language tab with cleanup enabled.

---

## Hardware & CPU vs. GPU Realities

- **Speech recognition runtime:** The bundled `sherpa-onnx` and `faster-whisper` runtimes use optimized int8 CPU instructions. They do not require a discrete GPU to be fast.
- **Ollama GPU offloading:** If you have an NVIDIA or AMD GPU, Ollama will automatically offload cleanup models to GPU VRAM for near-instant 150–250ms text polishing. If you are on CPU only, lightweight 0.5B–1.5B models will still complete cleanup in well under a second.
