# Future Capabilities & Research Roadmap

This document outlines architectural enhancements, research directions, and exploratory ideas for Infinisper. These proposals aim to elevate accuracy, responsiveness, and user experience while preserving Infinisper's core philosophy: **100% private, local-first, and highly optimized for consumer CPUs**.

> [!WARNING]
> **Exploratory Research Notice:** The items listed below represent experimental concepts and potential research avenues under investigation. They do not constitute a fixed commitment, guarantee, or definitive timeline for inclusion in future releases. Features may be adapted, redesigned, or omitted based on performance benchmarks, hardware overhead, and community needs.

---

## 1. Context-Aware Dictation & Active Window Adaptation

### Definition
Instead of applying a single generic cleanup prompt to all text, Infinisper can detect the foreground application when the hotkey is pressed and dynamically adapt its transcription formatting and vocabulary.

### Value to the User
* **Code Editors (VS Code, Cursor, Windows Terminal):** Preserves programming language syntax, formats spoken variables into `camelCase` or `snake_case`, and prevents accidental expansion of technical jargon.
* **Team Chat (Slack, Discord, WhatsApp, Teams):** Adopts a natural, casual tone with sentence-cased fragments, emoji awareness, and conversational phrasing.
* **Email & Documents (Outlook, Word, Google Docs):** Automatically formats structured paragraphs, formal greetings, sign-offs, and professional punctuation.

---

## 2. Speech Repair & Mid-Sentence Self-Correction

### Definition
Humans naturally hesitate, backtrack, and self-correct while thinking out loud (e.g., *"Let's meet on Tuesday... actually, make that Wednesday afternoon"* or *"Send it to Alex... no wait, Priya"*).

### Value to the User
* Upgrades the AI cleanup stage to identify natural speech disfluencies and conversational repairs.
* Outputs only the user's final intended statement, eliminating the need to stop, backspace, and re-dictate when speaking naturally.

---

## 3. High-Performance C/C++ Inference Runtime for Qwen3-ASR

### Definition
While Qwen3-ASR currently runs via ONNX Runtime in Python, its acoustic encoder and autoregressive LLM decoder can be executed via a dedicated, lightweight C/C++ inference engine (such as `antirez/qwen-asr` or optimized C++ BLAS runtimes).

### Value to the User
* **Zero Python Overhead:** Bypasses Python Global Interpreter Lock (GIL) constraints and runtime startup delays.
* **Smaller Memory Footprint:** Decreases RAM usage from ~1.8–2.5 GB down to ~600–800 MB.
* **2× to 3× Faster CPU Inference:** Leverages hand-tuned OpenBLAS and AVX2/AVX-512 matrix multiplication routines natively, achieving faster-than-realtime transcription even on modest hardware.

---

## 4. Advanced Acoustic & Phonetic Hotword Biasing

### Definition
Currently, custom dictionary terms are injected into Whisper's prompt and the post-ASR cleanup prompt. Advanced hotword biasing introduces acoustic and phonetic dictionary enforcement directly into Nemotron and Qwen3-ASR before text generation occurs.

### Value to the User
* Guarantees that specialized product names, company acronyms, and regional proper nouns are recognized correctly at the acoustic level, preventing phonetic mishearings from ever reaching the cleanup step.

---

## 5. Unified "Models & Providers" Dashboard UX

### Definition
Currently, speech engines (Whisper, Nemotron, Qwen3) and AI cleanup providers (Ollama, Gemini, Groq) are configured in separate sections of the Dashboard. A unified design consolidates them into an intuitive, card-based interface.

### Value to the User
* **One-Click Orchestration:** Each model card displays its active status, local vs. cloud badge, download size, memory footprint, and latency tier.
* **Preset Bundles:** Quickly toggle between predefined profiles (e.g., *"Ultra-Fast Everyday"*, *"Maximum Multilingual Accuracy"*, or *"Zero-RAM Cloud"*).

---

## 6. Surrounding Screen Context via Accessibility APIs

### Definition
Using the Windows UI Automation accessibility tree, Infinisper can inspect the text immediately preceding the user's cursor in the active input box before recording begins.

### Value to the User
* **Contextual Coherence:** When replying to an email, message, or ticket, the AI cleanup stage reads the preceding conversation context.
* **Automatic Name & Jargon Resolution:** If replying to an email from *"Siddharth discussing Kubernetes pods"*, the model automatically infers proper spellings without needing them pre-added to the custom dictionary.

---

## 7. Command Mode (Voice-to-Action Editing)

### Definition
A dual-mode dictation trigger: if text is highlighted when the hotkey is pressed, Infinisper treats spoken words as an instruction to transform that selected text rather than transcribing raw speech.

### Value to the User
* **Highlight & Transform:** Select a paragraph and say *"make this concise"*, *"turn into bullet points"*, *"translate to German"*, or *"fix tone"*.
* Replaces the selected text in place with the transformed output.

---

## 8. Direct OS Text Injection (Clipboard-Free Pasting)

### Definition
Currently, text insertion simulates a `Ctrl+V` clipboard paste while backing up and restoring prior clipboard contents. Direct injection leverages Windows UI Automation text patterns (`IUIAutomationValuePattern`) or synthetic `SendInput` keystrokes.

### Value to the User
* **Zero Clipboard Interference:** Eliminates edge cases with third-party clipboard managers (like Windows Clipboard History or Ditto).
* **Terminal Compatibility:** Works reliably in command prompts and terminal emulators where `Ctrl+V` has special terminal control meanings.

---

## 9. One-Click Vocabulary Learning from History

### Definition
Enhances the History tab so that any misheard or corrected word can be added directly to the personal dictionary with a single click.

### Value to the User
* Effortlessly builds a personalized lexicon over time directly from daily dictation logs without manually typing terms into the settings menu.

---

## 10. Dual-Audio Meeting Dictation (WASAPI Loopback)

### Definition
Captures both the user's microphone and system audio output simultaneously using Windows WASAPI loopback capture.

### Value to the User
* Transcribes two-sided calls (Zoom, Microsoft Teams, Google Meet, Discord) locally on the machine, generating unified meeting notes and transcripts with zero cloud exposure.

---

## 11. Hands-Free Local Wake-Word Activation

### Definition
An optional hands-free mode driven by a low-power, lightweight on-device wake-word model (such as openWakeWord).

### Value to the User
* Allows users to dictate by saying a custom wake phrase (e.g., *"Hey Flow"*) without needing to reach for a keyboard shortcut—ideal for accessibility and multitasking.

---

## 12. AI Meeting Notetaker & Structured Brain Dumps

### Definition
A dedicated long-form mode inspired by Wispr Flow Notetaker. Rather than just transcribing short dictation bursts, it continuously captures extended meetings, interviews, or unstructured voice brain dumps, transforming them into rich, structured notes.

### Value to the User
* **Automated Meeting Artifacts:** Extracts executive summaries, key decisions made, and categorized action items with implied owners and deadlines.
* **One-Click Follow-Up Generation:** Generates ready-to-send follow-up emails, Slack sync recaps, or task tickets directly from meeting transcripts.
* **"What Did I Miss?" Live Catch-Up:** Allows users to query the ongoing meeting transcript in real time (e.g., *"What was just decided about the API?"*) to get an immediate summary without interrupting the speaker.
* **Local Markdown Vault Integration:** Automatically exports structured notes directly into personal local knowledge bases like Obsidian, Logseq, or local Markdown directories with zero cloud lock-in.
