"""The dictation pipeline: hold the hotkey, record, transcribe, clean up, paste.

`Pipeline` owns the state that is per-take (are we recording, is a take in flight, the open
Nemotron stream) and reads the rest from `Settings` and `Runtime`. `chip` and `tray` are
duck-typed: anything with `set_state(str)` / `set_status(str)`.
"""

import threading
import time
import traceback
from datetime import datetime
from typing import NamedTuple

import numpy as np

from audio import capture as audio_capture
from audio import preprocessor as audio_preprocessor
from audio import vad as audio_vad
from cleanup import catalog as cleanup_catalog
from cleanup import engine as cleanup_engine
from dictation import paste
from dictation.settings import Runtime, Settings
from history.models import HistoryEntry
from timing import timed
from utils.windows import is_hotkey_pressed

POLL_INTERVAL = 0.03
MIN_AUDIO_SECONDS = 0.3
MIN_HOLD_SECONDS = 0.15
WARM_AGAIN_AFTER_SECONDS = 600

# Map pipeline outcomes to overlay chip states.
_CHIP_STATE_FOR_OUTCOME = {
    "error": "failed",
    "skipped_silence": "nospeech",
    "pasted": "pasted",
}


class AsrOutcome(NamedTuple):
    text: str
    source: str
    error: str = ""  # non-empty means a hard failure: do not paste anything


class Pipeline:
    def __init__(self, settings: Settings, runtime: Runtime, history_store=None):
        self.settings = settings
        self.runtime = runtime
        self.history_store = history_store
        self.paused = False
        self._transcribing = False
        self._transcribing_lock = threading.Lock()
        self._last_warmed: tuple | None = None

    def is_busy(self) -> bool:
        with self._transcribing_lock:
            transcribing = self._transcribing
        return audio_capture.is_recording() or transcribing

    # ---- recording -------------------------------------------------------------------

    def start_recording(self, chip, tray):
        rt, settings = self.runtime, self.settings
        rt.stream_session = None

        preroll_chunks = audio_capture.start_recording()
        print("Listening...")
        chip.set_state("listening")
        tray.set_status("Listening...")

        if settings.use_asr and rt.active_engine == "nemotron" and rt.nemotron is not None:
            try:
                session = rt.nemotron.start_stream(
                    sample_rate=audio_capture.SAMPLE_RATE, language=settings.dictation_language
                )
                if preroll_chunks:
                    for chunk in preroll_chunks:
                        session.feed_chunk(chunk)
                audio_capture.set_chunk_listener(session.feed_chunk)
                rt.stream_session = session
            except Exception as exc:
                print(f"Failed to start Nemotron stream ({exc}), falling back to buffer.")
                rt.stream_session = None

    def stop_recording(self) -> np.ndarray | None:
        audio_capture.clear_chunk_listener()
        return audio_capture.stop_recording()

    def _abort_stream_session(self):
        session, self.runtime.stream_session = self.runtime.stream_session, None
        if session is not None:
            try:
                session.abort()
            except Exception:
                pass

    # ---- speech to text --------------------------------------------------------------

    def run_whisper(self, audio: np.ndarray, steps: list | None = None) -> str:
        rt, settings = self.runtime, self.settings
        with timed(f"Whisper transcribe ({rt.whisper_size})", steps):
            # vad_filter is off because audio.vad already trimmed this take with the same
            # Silero parameters this call used to pass -- every engine now gets trimmed
            # audio, not just this one. Running it again here would only re-pay the cost.
            # Use beam_size=5 for superior word recognition accuracy.
            lang_arg = settings.dictation_language if settings.dictation_language != "auto" else None
            segments, info = rt.whisper.transcribe(
                audio,
                language=lang_arg,
                beam_size=5,
                temperature=0.0,
                vad_filter=False,
                hotwords=" ".join(settings.custom_words) if settings.custom_words else None,
            )
            text = "".join(segment.text for segment in segments).strip()
        print(f"(detected language: {info.language}, confidence {info.language_probability:.2f})")
        return text

    def run_asr(self, audio: np.ndarray, steps: list | None = None) -> AsrOutcome:
        """Runs whichever ASR engine is configured. Falls back to Whisper if the
        configured engine fails and fallback is enabled; otherwise reports a hard
        error and pastes nothing.
        """
        rt, settings = self.runtime, self.settings
        engine, label = None, None
        if rt.active_engine == "qwen3" and rt.qwen3 is not None:
            engine, label = rt.qwen3, "Qwen3"
        elif rt.active_engine == "nemotron" and rt.nemotron is not None:
            engine, label = rt.nemotron, "Nemotron"

        if engine is None:
            return AsrOutcome(self.run_whisper(audio, steps), "Whisper")

        try:
            if label == "Nemotron" and rt.stream_session is not None:
                session, rt.stream_session = rt.stream_session, None
                with timed("Nemotron stream finalize", steps):
                    text = session.finish()
            else:
                with timed(f"{label} transcribe", steps):
                    if label == "Nemotron":
                        text = engine.transcribe(
                            audio, audio_capture.SAMPLE_RATE, language=settings.dictation_language
                        )
                    else:
                        text = engine.transcribe(audio, audio_capture.SAMPLE_RATE)
        except Exception as exc:
            text = ""
            print(f"{label} failed ({exc}).")
        else:
            if text:
                return AsrOutcome(text, label)
            print(f"{label} returned nothing.")

        if not settings.fallback_to_whisper:
            return AsrOutcome("", "", error=f"{label} failed and fallback is disabled")

        print("Falling back to Whisper.")
        return AsrOutcome(self.run_whisper(audio, steps), "Whisper (fallback)")

    # ---- AI cleanup ------------------------------------------------------------------

    def _active_cleanup(self):
        """The active AI model, or the .env Gemini key as a last resort for the rare case
        the first-run migration didn't run."""
        resolved = self.settings.resolve_active_cleanup()
        if resolved is None and cleanup_engine.has_gemini_env_key():
            resolved = (cleanup_engine.GEMINI_ENV_MODEL, cleanup_engine.get_gemini_env_key(), None, True)
        return resolved

    def _cleanup_options(self) -> dict:
        s = self.settings
        return dict(
            level=s.cleanup_level,
            force_english_transliteration=s.force_english_transliteration,
            dictation_language=s.dictation_language,
            output_mode=s.cleanup_output_mode,
            target_language=s.translation_target_language,
            timeout_seconds=s.cleanup_timeout_seconds,
            custom_words=s.custom_words,
            keep_alive=s.ollama_keep_alive,
        )

    def run_cleanup_on_audio(self, audio: np.ndarray, steps: list | None = None) -> AsrOutcome:
        """Audio-direct path: audio goes straight to the active AI
        model, Whisper never runs unless it fails. Works with whichever provider
        the Models & providers tab has configured as active -- not tied to any one
        AI provider.
        """
        resolved = self._active_cleanup()

        if resolved is None:
            print("No active AI model configured -- falling back to local Whisper.")
            result = cleanup_engine.RefineResult("", used_model=False, detail="no active model")
        else:
            model, api_key, base_url, supports_audio = resolved
            if not supports_audio:
                print(f"Active model '{model}' is text-only (does not support audio). Falling back to local Whisper.")
                result = cleanup_engine.RefineResult(
                    "", used_model=False, detail=f"'{model}' is text-only (does not support audio input)"
                )
            else:
                result = cleanup_engine.transcribe_audio_with_model(
                    audio,
                    audio_capture.SAMPLE_RATE,
                    model=model,
                    api_key=api_key,
                    base_url=base_url,
                    steps=steps,
                    **self._cleanup_options(),
                )

        if result.used_model:
            return AsrOutcome(result.text, "AI audio")

        print(f"Falling back to local Whisper ({result.detail}).")
        if not self.settings.fallback_to_whisper:
            return AsrOutcome(
                "", "", error=f"AI model failed ({result.detail}) and fallback is disabled"
            )

        return AsrOutcome(self.run_whisper(audio, steps), "Whisper (fallback)")

    def run_cleanup_on_text(self, text: str, asr_source: str, steps: list | None = None) -> AsrOutcome:
        """Both-selected path: polish already-transcribed ASR text with the active
        AI model. A cleanup failure is never fatal regardless of the
        fallback setting -- the ASR step already succeeded, so the unpolished text
        is simply kept.
        """
        resolved = self._active_cleanup()

        if resolved is None:
            print("No active AI model configured -- using unpolished ASR text.")
            result = cleanup_engine.RefineResult(text, used_model=False, detail="no active model")
        else:
            model, api_key, base_url, _ = resolved
            result = cleanup_engine.refine_text_with_model(
                text,
                model=model,
                api_key=api_key,
                base_url=base_url,
                steps=steps,
                **self._cleanup_options(),
            )

        if result.used_model:
            return AsrOutcome(result.text, f"{asr_source} -> AI cleanup")
        print(f"AI cleanup skipped ({result.detail}), using unpolished {asr_source} text.")
        return AsrOutcome(text, asr_source)

    def warm_active_ollama_model(self):
        """Loads the active model into Ollama's memory in the background, so the first dictation
        isn't the one that pays for it -- a cold gemma4:e4b took ~10 s where a loaded one takes
        ~1 s. Only for a local Ollama model, only when AI cleanup is on, and never when the user
        left keep-alive at Ollama's own default. Quiet if Ollama isn't running: this is a
        convenience, and the app never starts Ollama or downloads anything on the user's behalf.
        """
        keep_alive = self.settings.ollama_keep_alive
        if not (self.settings.use_cleanup and keep_alive):
            return
        resolved = self.settings.resolve_active_cleanup()
        if resolved is None:
            return
        model, _key, base_url, _supports_audio = resolved
        if not model.startswith("ollama/") or not cleanup_catalog.is_local_endpoint(model, base_url):
            return

        signature = (model, base_url, keep_alive)
        last = self._last_warmed
        if last and last[0] == signature and time.monotonic() - last[1] < WARM_AGAIN_AFTER_SECONDS:
            return
        self._last_warmed = (signature, time.monotonic())

        def work():
            started = time.perf_counter()
            if cleanup_engine.warm_up_ollama(model, base_url, keep_alive):
                print(f"Loaded {model} into Ollama ({time.perf_counter() - started:.1f} s); "
                      f"keeping it for {keep_alive}.")

        threading.Thread(target=work, daemon=True).start()

    # ---- one take, start to finish ---------------------------------------------------

    def _log_history(self, outcome: str, engine: str, text: str, error: str, pipeline_start: float, steps: list):
        if self.history_store is None:
            return
        elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        self.history_store.append(HistoryEntry(
            timestamp=datetime.now().isoformat(timespec="seconds"),
            engine=engine,
            outcome=outcome,
            total_ms=elapsed_ms,
            steps=list(steps),
            text=text,
            error=error,
        ))

    def _skip_take(self, chip, tray, reason: str, message: str, pipeline_start: float):
        print(message)
        self._abort_stream_session()
        chip.set_state("nospeech")
        tray.set_status("Ready")
        self._log_history(reason, "", "", "", pipeline_start, [])

    def transcribe_and_paste(self, chip, tray, audio: np.ndarray, hold_duration: float):
        settings = self.settings
        pipeline_start = time.perf_counter()
        steps: list[tuple[str, float]] = []

        if hold_duration < MIN_HOLD_SECONDS:
            return self._skip_take(chip, tray, "skipped_quick", "Too quick, ignoring.", pipeline_start)
        if len(audio) < audio_capture.SAMPLE_RATE * MIN_AUDIO_SECONDS:
            return self._skip_take(chip, tray, "skipped_short", "Too short, ignoring.", pipeline_start)
        # Uses audio_preprocessor's sensitive detection (0.001 RMS) to support low voices.
        if not audio_preprocessor.has_speech(audio, audio_capture.SAMPLE_RATE):
            return self._skip_take(chip, tray, "skipped_silence", "Silence, ignoring.", pipeline_start)

        with self._transcribing_lock:
            self._transcribing = True

        final_status = "Ready"
        outcome_label = "error"
        engine_label = ""
        result_text = ""
        error_text = ""
        try:
            # Remove DC bias, filter desk rumble, and notch out the hotkey click -- which sits
            # at the pre-roll boundary, so capture has to say how much pre-roll this take
            # actually got (less than the nominal 0.5s on the first take after launch).
            audio = audio_preprocessor.clean_speech_audio(
                audio,
                audio_capture.SAMPLE_RATE,
                click_at_seconds=audio_capture.preroll_seconds_used(),
            )
            # Trim to speech before normalising, so the level is measured over speech rather
            # than over speech plus the silence around it.
            with timed("VAD trim", steps):
                audio = audio_vad.trim_to_speech(audio, audio_capture.SAMPLE_RATE)
            audio = audio_preprocessor.normalize_audio(audio)

            print("Transcribing...")
            chip.set_state("transcribing")
            tray.set_status("Transcribing...")
            if not settings.use_asr and not settings.use_cleanup:
                # Defensive only -- the settings UI itself blocks saving this combination.
                print("No transcription engine enabled (check config.json) -- using Whisper.")
                outcome = self.run_asr(audio, steps)

            elif settings.use_asr and settings.use_cleanup:
                outcome = self.run_asr(audio, steps)
                if outcome.error:
                    print(outcome.error)
                    final_status = f"Error -- {outcome.error}"
                    outcome_label, error_text = "error", outcome.error
                    return
                if not outcome.text:
                    print("Didn't catch anything.")
                    outcome_label = "skipped_silence"
                    return
                chip.set_state("polishing")
                tray.set_status("Cleaning up with the AI model...")
                outcome = self.run_cleanup_on_text(outcome.text, outcome.source, steps)

            elif settings.use_cleanup:
                tray.set_status("Transcribing with the AI model...")
                outcome = self.run_cleanup_on_audio(audio, steps)
                if outcome.error:
                    print(outcome.error)
                    final_status = f"Error -- {outcome.error}"
                    outcome_label, error_text = "error", outcome.error
                    return

            else:  # ASR only
                outcome = self.run_asr(audio, steps)
                if outcome.error:
                    print(outcome.error)
                    final_status = f"Error -- {outcome.error}"
                    outcome_label, error_text = "error", outcome.error
                    return

            if not outcome.text:
                print("Didn't catch anything.")
                outcome_label = "skipped_silence"
                return

            print(f"[{outcome.source}] {outcome.text}")
            paste.paste_text(outcome.text, steps)
            final_status = f"Ready ({outcome.source})"
            outcome_label = "pasted"
            engine_label = outcome.source
            result_text = outcome.text
        finally:
            self._abort_stream_session()
            elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
            print(f"[timing] TOTAL (transcribe + refine + paste): {elapsed_ms:.0f}ms")
            with self._transcribing_lock:
                self._transcribing = False
            chip.set_state(_CHIP_STATE_FOR_OUTCOME.get(outcome_label, "idle"))
            tray.set_status(final_status)
            self._log_history(outcome_label, engine_label, result_text, error_text, pipeline_start, steps)

    # ---- the hotkey ------------------------------------------------------------------

    def hotkey_loop(self, chip, tray):
        combo_active = False
        hold_started_at = 0.0

        while True:
            try:
                pressed = is_hotkey_pressed(self.settings.hotkey)

                if pressed and not combo_active and not self.paused and not self.is_busy():
                    combo_active = True
                    hold_started_at = time.monotonic()
                    self.start_recording(chip, tray)

                elif combo_active and not pressed:
                    combo_active = False
                    hold_duration = time.monotonic() - hold_started_at
                    audio = self.stop_recording()
                    if audio is None:
                        print("No audio captured.")
                        chip.set_state("nospeech")
                        tray.set_status("Ready")
                    else:
                        threading.Thread(
                            target=self.transcribe_and_paste,
                            args=(chip, tray, audio, hold_duration),
                            daemon=True,
                        ).start()

            except Exception:
                print("Unexpected error, recovering:")
                traceback.print_exc()
                combo_active = False
                self._abort_stream_session()
                self.stop_recording()
                chip.set_state("failed")
                tray.set_status("Ready")
                time.sleep(0.5)
                continue

            time.sleep(POLL_INTERVAL)
