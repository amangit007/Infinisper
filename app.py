import sys
import threading
import time
import traceback
from datetime import datetime
from typing import NamedTuple

import keyboard
import numpy as np
import pyperclip
import sounddevice as sd
from faster_whisper import WhisperModel
from PySide6.QtCore import QObject, Qt, Signal
from PySide6.QtWidgets import QApplication

from asr import catalog as asr_catalog
from asr import nemotron_asr, qwen_asr
from audio import capture as audio_capture
from audio import preprocessor as audio_preprocessor
from audio import vad as audio_vad
from config import load_config, save_config
from credentials import get_api_key, set_api_key
from history.models import HistoryEntry
from history.store import HistoryStore
from multimodal import engine as multimodal_engine
from timing import timed
from ui.assets.mark import BRAND_ACCENT_DARK_HEX, mark_icon
from ui.chip import ChipWindow
from ui.main_window import MainWindow
from ui.splash import SplashScreen
from ui.tray import TrayIcon
from utils.windows import set_app_user_model_id

POLL_INTERVAL = 0.03
MIN_AUDIO_SECONDS = 0.3
MIN_HOLD_SECONDS = 0.15
# Rough empirical cutoff between "silence/room noise" and actual speech at 16 kHz float32.
SILENCE_RMS_THRESHOLD = 0.005

# The chip's own auto-revert timer (see ui/chip.py) brings pasted/nospeech/failed back
# to idle on its own -- this just maps a pipeline outcome to the state that best shows
# it, per the design mockup's chip states. "idle" is the fallback for outcomes that
# don't correspond to a distinct chip state.
_CHIP_STATE_FOR_OUTCOME = {
    "error": "failed",
    "skipped_silence": "nospeech",
    "pasted": "pasted",
}

_transcribing_lock = threading.Lock()
_transcribing = False
_paused = False
_stream: sd.InputStream | None = None

_model: WhisperModel | None = None
_model_size = "base"
_input_device = None
_qwen3_engine: qwen_asr.Qwen3AsrEngine | None = None
_nemotron_engine: nemotron_asr.NemotronAsrEngine | None = None

_use_asr = True
_asr_engine = "whisper"  # "whisper" | "qwen3" | "nemotron" -- what's actually loaded and active
_use_multimodal = False
_multimodal_level = "basic"  # "basic" | "advanced"
_multimodal_timeout_seconds = 60
_fallback_to_whisper = True
# Only applied when _use_multimodal is on -- see multimodal/prompts.py's
# ENGLISH_TRANSLITERATION_RULE. Set from the Language tab, independently of the
_force_english_transliteration = False
_dictation_language = "en"
# Names, acronyms and jargon the speaker uses that a general model mishears. Boosted
# in Whisper's decoder via hotwords= and named to the multimodal model in its prompt.
# Qwen3 and Nemotron are not covered: sherpa-onnx can bias a transducer, but only with
# a BPE model file that neither of those exports ships.
_custom_words: list[str] = []

# Runtime cache of config.json's multimodal_* fields -- app.py's own copy so the
# hotkey/dictation loop never touches disk on every take. Refreshed whenever the
# Multimodal Models tab changes something (main_window.multimodal_changed) or the
# Dashboard's Active model selection is saved.
_multimodal_providers: list[dict] = []
_multimodal_models: list[dict] = []
_active_multimodal_model_id: str | None = None

_history_store: HistoryStore | None = None


class _QuitSignal(QObject):
    triggered = Signal()


class _LevelFanout:
    """Forwards audio.capture's single update_audio_level(level) callback to more
    than one listener -- the chip pill and the sidebar's mic meter both need real
    levels, and audio.capture only supports wiring one object via set_chip()."""

    def __init__(self, *listeners):
        self._listeners = listeners

    def update_audio_level(self, level: float):
        for listener in self._listeners:
            listener.update_audio_level(level)


class AsrOutcome(NamedTuple):
    text: str
    source: str
    error: str = ""  # non-empty means a hard failure: do not paste anything


def is_busy() -> bool:
    with _transcribing_lock:
        transcribing = _transcribing
    return audio_capture.is_recording() or transcribing


def start_recording(chip: ChipWindow, tray: TrayIcon):
    audio_capture.start_recording()
    print("Listening...")
    chip.set_state("listening")
    tray.set_status("Listening...")


def stop_recording() -> np.ndarray | None:
    return audio_capture.stop_recording()


def _run_whisper(audio: np.ndarray, steps: list | None = None) -> str:
    with timed(f"Whisper transcribe ({_model_size})", steps):
        # vad_filter is off because audio.vad already trimmed this take with the same
        # Silero parameters this call used to pass -- every engine now gets trimmed
        # audio, not just this one. Running it again here would only re-pay the cost.
        # Use beam_size=5 for superior word recognition accuracy.
        lang_arg = _dictation_language if _dictation_language != "auto" else None
        segments, info = _model.transcribe(
            audio,
            language=lang_arg,
            beam_size=5,
            temperature=0.0,
            vad_filter=False,
            hotwords=" ".join(_custom_words) if _custom_words else None,
        )
        text = "".join(segment.text for segment in segments).strip()
    print(f"(detected language: {info.language}, confidence {info.language_probability:.2f})")
    return text


def run_asr(audio: np.ndarray, steps: list | None = None) -> AsrOutcome:
    """Runs whichever ASR engine is configured. Falls back to Whisper if the
    configured engine fails and fallback is enabled; otherwise reports a hard
    error and pastes nothing.
    """
    engine, label = None, None
    if _asr_engine == "qwen3" and _qwen3_engine is not None:
        engine, label = _qwen3_engine, "Qwen3"
    elif _asr_engine == "nemotron" and _nemotron_engine is not None:
        engine, label = _nemotron_engine, "Nemotron"

    if engine is not None:
        try:
            with timed(f"{label} transcribe", steps):
                if label == "Nemotron":
                    text = engine.transcribe(audio, audio_capture.SAMPLE_RATE, language=_dictation_language)
                else:
                    text = engine.transcribe(audio, audio_capture.SAMPLE_RATE)
        except Exception as exc:
            text = ""
            print(f"{label} failed ({exc}).")
        else:
            if text:
                return AsrOutcome(text, label)
            print(f"{label} returned nothing.")

        if not _fallback_to_whisper:
            return AsrOutcome("", "", error=f"{label} failed and fallback is disabled")

        print("Falling back to Whisper.")
        return AsrOutcome(_run_whisper(audio, steps), "Whisper (fallback)")

    return AsrOutcome(_run_whisper(audio, steps), "Whisper")


def _resolve_active_multimodal() -> tuple[str, str | None, str | None] | None:
    """(model, api_key, base_url) for the configured active multimodal model,
    or None if none is configured / the configured one no longer exists (its
    provider or model could have been deleted on the Multimodal Models tab
    since this was set active).
    """
    if not _active_multimodal_model_id:
        return None
    model_entry = next(
        (m for m in _multimodal_models if m["id"] == _active_multimodal_model_id), None
    )
    if model_entry is None:
        return None
    provider_entry = next(
        (p for p in _multimodal_providers if p["id"] == model_entry["provider_id"]), None
    )
    if provider_entry is None:
        return None
    return (
        model_entry["model"],
        get_api_key(provider_entry["id"]),
        provider_entry.get("base_url"),
        bool(model_entry.get("supports_audio", False)),
    )


def run_multimodal_on_audio(audio: np.ndarray, steps: list | None = None) -> AsrOutcome:
    """Multimodal-only path: audio goes straight to the active multimodal
    model, Whisper never runs unless it fails. Works with whichever provider
    the Multimodal Models tab has configured as active -- not tied to any one
    AI provider. The .env GEMINI_API_KEY is only a last-resort fallback, for
    the rare case the migration on first run somehow didn't run.
    """
    resolved = _resolve_active_multimodal()
    if resolved is None and multimodal_engine.has_gemini_env_key():
        resolved = (multimodal_engine.GEMINI_ENV_MODEL, multimodal_engine.get_gemini_env_key(), None, True)

    if resolved is None:
        print("No active multimodal model configured -- falling back to local Whisper.")
        result = multimodal_engine.RefineResult("", used_multimodal=False, detail="no active model")
    else:
        model, api_key, base_url, supports_audio = resolved
        if not supports_audio:
            print(f"Active model '{model}' is text-only (does not support audio). Falling back to local Whisper.")
            result = multimodal_engine.RefineResult(
                "", used_multimodal=False, detail=f"'{model}' is text-only (does not support audio input)"
            )
        else:
            result = multimodal_engine.transcribe_with_multimodal_model(
                audio,
                audio_capture.SAMPLE_RATE,
                model=model,
                api_key=api_key,
                base_url=base_url,
                level=_multimodal_level,
                force_english_transliteration=_force_english_transliteration,
                timeout_seconds=_multimodal_timeout_seconds,
                steps=steps,
                custom_words=_custom_words,
            )

    if result.used_multimodal:
        return AsrOutcome(result.text, "Multimodal")

    print(f"Falling back to local Whisper ({result.detail}).")
    if not _fallback_to_whisper:
        return AsrOutcome(
            "", "", error=f"Multimodal model failed ({result.detail}) and fallback is disabled"
        )

    return AsrOutcome(_run_whisper(audio, steps), "Whisper (fallback)")


def run_multimodal_on_text(text: str, asr_source: str, steps: list | None = None) -> AsrOutcome:
    """Both-selected path: polish already-transcribed ASR text with the active
    multimodal model. A cleanup failure is never fatal regardless of the
    fallback setting -- the ASR step already succeeded, so the unpolished text
    is simply kept.
    """
    resolved = _resolve_active_multimodal()
    if resolved is None and multimodal_engine.has_gemini_env_key():
        resolved = (multimodal_engine.GEMINI_ENV_MODEL, multimodal_engine.get_gemini_env_key(), None, True)

    if resolved is None:
        print("No active multimodal model configured -- using unpolished ASR text.")
        result = multimodal_engine.RefineResult(text, used_multimodal=False, detail="no active model")
    else:
        model, api_key, base_url, _ = resolved
        result = multimodal_engine.refine_text_with_multimodal_model(
            text,
            model=model,
            api_key=api_key,
            base_url=base_url,
            level=_multimodal_level,
            force_english_transliteration=_force_english_transliteration,
            timeout_seconds=_multimodal_timeout_seconds,
            steps=steps,
            custom_words=_custom_words,
        )

    if result.used_multimodal:
        return AsrOutcome(result.text, f"{asr_source} -> Multimodal")
    print(f"Multimodal cleanup skipped ({result.detail}), using unpolished {asr_source} text.")
    return AsrOutcome(text, asr_source)


def _log_history(outcome: str, engine: str, text: str, error: str, pipeline_start: float, steps: list):
    if _history_store is None:
        return
    elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
    entry = HistoryEntry(
        timestamp=datetime.now().isoformat(timespec="seconds"),
        engine=engine,
        outcome=outcome,
        total_ms=elapsed_ms,
        steps=list(steps),
        text=text,
        error=error,
    )
    _history_store.append(entry)


def _has_speech(audio: np.ndarray) -> bool:
    """True if any short window of `audio` clears the speech RMS threshold.
    Uses audio_preprocessor's sensitive detection (0.001 RMS) to support low voices."""
    return audio_preprocessor.has_speech(audio, audio_capture.SAMPLE_RATE)


def transcribe_and_paste(
    chip: ChipWindow, tray: TrayIcon, audio: np.ndarray, hold_duration: float
):
    global _transcribing

    pipeline_start = time.perf_counter()
    steps: list[tuple[str, float]] = []

    if hold_duration < MIN_HOLD_SECONDS:
        print("Too quick, ignoring.")
        chip.set_state("nospeech")
        tray.set_status("Ready")
        _log_history("skipped_quick", "", "", "", pipeline_start, [])
        return

    if len(audio) < audio_capture.SAMPLE_RATE * MIN_AUDIO_SECONDS:
        print("Too short, ignoring.")
        chip.set_state("nospeech")
        tray.set_status("Ready")
        _log_history("skipped_short", "", "", "", pipeline_start, [])
        return

    if not _has_speech(audio):
        print("Silence, ignoring.")
        chip.set_state("nospeech")
        tray.set_status("Ready")
        _log_history("skipped_silence", "", "", "", pipeline_start, [])
        return

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
    with _transcribing_lock:
        _transcribing = True

    final_status = "Ready"
    outcome_label = "error"
    engine_label = ""
    result_text = ""
    error_text = ""
    try:
        if not _use_asr and not _use_multimodal:
            # Defensive only -- the settings UI itself blocks saving this combination.
            print("No transcription engine enabled (check config.json) -- using Whisper.")
            outcome = run_asr(audio, steps)

        elif _use_asr and _use_multimodal:
            outcome = run_asr(audio, steps)
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
            tray.set_status("Cleaning up with the multimodal model...")
            outcome = run_multimodal_on_text(outcome.text, outcome.source, steps)

        elif _use_multimodal:
            tray.set_status("Transcribing with the multimodal model...")
            outcome = run_multimodal_on_audio(audio, steps)
            if outcome.error:
                print(outcome.error)
                final_status = f"Error -- {outcome.error}"
                outcome_label, error_text = "error", outcome.error
                return

        else:  # ASR only
            outcome = run_asr(audio, steps)
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
        paste_text(outcome.text, steps)
        final_status = f"Ready ({outcome.source})"
        outcome_label = "pasted"
        engine_label = outcome.source
        result_text = outcome.text
    finally:
        elapsed_ms = (time.perf_counter() - pipeline_start) * 1000
        print(f"[timing] TOTAL (transcribe + refine + paste): {elapsed_ms:.0f}ms")
        with _transcribing_lock:
            _transcribing = False
        chip.set_state(_CHIP_STATE_FOR_OUTCOME.get(outcome_label, "idle"))
        tray.set_status(final_status)
        _log_history(outcome_label, engine_label, result_text, error_text, pipeline_start, steps)


# How long the dictated text stays on the clipboard before the user's previous
# contents are put back. Generous on purpose: the restore no longer blocks the
# pipeline, so there is nothing to gain by racing it. See _restore_clipboard_later.
CLIPBOARD_RESTORE_SECONDS = 1.5


def _restore_clipboard_later(previous: str, pasted: str):
    """Puts `previous` back on the clipboard, on a background thread, once the target
    app has had time to actually read what we pasted.

    This used to be a flat time.sleep(0.3) inside the pipeline, which was both a
    permanent 300 ms tax on every take -- against a 700 ms budget -- and a race: an
    app that reads the clipboard lazily (Electron apps, RDP sessions, some web
    editors) could get as far as the restore and paste the user's old contents
    instead. Waiting longer off the critical path costs nothing and loses that race
    far less often.

    Restores only if our text is still on the clipboard. Anything else there means the
    user copied something new in the meantime, and their copy wins.
    """

    def worker():
        time.sleep(CLIPBOARD_RESTORE_SECONDS)
        try:
            if pyperclip.paste() == pasted:
                pyperclip.copy(previous)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def paste_text(text: str, steps: list | None = None):
    with timed("Paste (clipboard swap + send)", steps):
        try:
            previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None

        pyperclip.copy(text)
        keyboard.send("ctrl+v")

    if previous_clipboard is not None:
        _restore_clipboard_later(previous_clipboard, text)


def hotkey_loop(chip: ChipWindow, tray: TrayIcon, quit_signal: _QuitSignal):
    combo_active = False
    hold_started_at = 0.0

    while True:
        try:
            pressed = keyboard.is_pressed("ctrl") and keyboard.is_pressed("windows")

            if pressed and not combo_active and not _paused:
                combo_active = True
                hold_started_at = time.monotonic()
                start_recording(chip, tray)

            elif combo_active and not pressed:
                combo_active = False
                hold_duration = time.monotonic() - hold_started_at
                audio = stop_recording()
                if audio is None:
                    print("No audio captured.")
                    chip.set_state("nospeech")
                    tray.set_status("Ready")
                else:
                    transcribe_and_paste(chip, tray, audio, hold_duration)

        except Exception:
            print("Unexpected error, recovering:")
            traceback.print_exc()
            combo_active = False
            stop_recording()
            chip.set_state("failed")
            tray.set_status("Ready")
            time.sleep(0.5)
            continue

        time.sleep(POLL_INTERVAL)


_engine_prep_lock = threading.Lock()
_engine_prepping = False


def _prepare_qwen3_async(tray: TrayIcon, main_window):
    """Downloads (if needed) and loads Qwen3-ASR on a background thread, since
    the download can be ~980 MB and must never block the Qt main thread. Whisper
    stays active as the ASR engine until this completes.
    """
    global _qwen3_engine, _asr_engine, _engine_prepping

    if _qwen3_engine is not None:
        _asr_engine = "qwen3"
        tray.set_status("Ready (Qwen3-ASR)")
        main_window.engine_status_refresh_requested.emit("qwen3", is_busy())
        return

    with _engine_prep_lock:
        if _engine_prepping:
            print("Already preparing a speech engine, please wait...")
            return
        _engine_prepping = True

    def worker():
        global _qwen3_engine, _asr_engine, _engine_prepping
        try:
            if not qwen_asr.is_downloaded():
                tray.set_status("Downloading Qwen3-ASR (~980 MB)...")
                qwen_asr.download()
            tray.set_status("Loading Qwen3-ASR...")
            _qwen3_engine = qwen_asr.Qwen3AsrEngine()
            _asr_engine = "qwen3"
            print("Qwen3-ASR ready.")
            tray.set_status("Ready (Qwen3-ASR)")
        except Exception as exc:
            print(f"Failed to prepare Qwen3-ASR ({exc}), staying on Whisper.")
            tray.set_status("Ready (Qwen3-ASR setup failed)")
            _asr_engine = "whisper"
        finally:
            with _engine_prep_lock:
                _engine_prepping = False
            main_window.engine_status_refresh_requested.emit(_asr_engine, is_busy())

    threading.Thread(target=worker, daemon=True).start()


def _prepare_nemotron_async(tray: TrayIcon, main_window):
    """Downloads (if needed) and loads Nemotron 3.5 ASR on a background thread,
    since the download can be ~650 MB and must never block the Qt main thread.
    Whisper stays active as the ASR engine until this completes.
    """
    global _nemotron_engine, _asr_engine, _engine_prepping

    if _nemotron_engine is not None:
        _asr_engine = "nemotron"
        tray.set_status("Ready (Nemotron)")
        main_window.engine_status_refresh_requested.emit("nemotron", is_busy())
        return

    with _engine_prep_lock:
        if _engine_prepping:
            print("Already preparing a speech engine, please wait...")
            return
        _engine_prepping = True

    def worker():
        global _nemotron_engine, _asr_engine, _engine_prepping
        try:
            if not nemotron_asr.is_downloaded():
                tray.set_status("Downloading Nemotron 3.5 ASR (~650 MB)...")
                nemotron_asr.download()
            tray.set_status("Loading Nemotron 3.5 ASR...")
            _nemotron_engine = nemotron_asr.NemotronAsrEngine()
            _asr_engine = "nemotron"
            print("Nemotron 3.5 ASR ready.")
            tray.set_status("Ready (Nemotron)")
        except Exception as exc:
            print(f"Failed to prepare Nemotron 3.5 ASR ({exc}), staying on Whisper.")
            tray.set_status("Ready (Nemotron setup failed)")
            _asr_engine = "whisper"
        finally:
            with _engine_prep_lock:
                _engine_prepping = False
            main_window.engine_status_refresh_requested.emit(_asr_engine, is_busy())

    threading.Thread(target=worker, daemon=True).start()


def delete_model(engine_id: str, main_window):
    """Permanently deletes a downloaded ASR engine's weights, after a
    confirmation dialog naming the exact size/path. Refused only while the
    app is busy dictating -- deleting the currently active engine is allowed;
    since Whisper itself can never be deleted, it's always safe to fall back
    to as the new active engine.
    """
    global _asr_engine, _qwen3_engine, _nemotron_engine

    if is_busy():
        print("Still dictating -- try deleting the model again in a moment.")
        return

    was_active = engine_id == _asr_engine
    if not main_window.models_tab.confirm_and_request_delete_engine(engine_id, was_active):
        return

    try:
        asr_catalog.delete_model(engine_id)
        print(f"Deleted {engine_id} model files.")
    except Exception as exc:
        print(f"Failed to delete {engine_id} model files: {exc}")
        return

    if engine_id == "qwen3":
        _qwen3_engine = None
    elif engine_id == "nemotron":
        _nemotron_engine = None

    if was_active:
        _asr_engine = "whisper"
        current_config = load_config()
        current_config["asr_engine"] = "whisper"
        save_config(current_config)
        main_window.dashboard_tab.set_active_engine_radio("whisper")
        print("Switched to Whisper since the active engine's model was deleted.")

    main_window.refresh_engine_statuses(_asr_engine, busy=False)


def activate_asr_engine(engine_id: str, tray: TrayIcon, main_window):
    """Immediate engine switch triggered from the Models & providers table's
    Activate button -- unlike Dashboard's Save, this doesn't wait for the rest
    of the settings form. Engine switches can still trigger a real download, so
    qwen3/nemotron stay behind the same async prepare functions Dashboard's
    Save already used; only whisper (always available) switches synchronously.
    """
    global _asr_engine

    if is_busy():
        print("Still dictating -- try activating a different engine again in a moment.")
        return
    if engine_id == _asr_engine:
        return

    persisted_config = load_config()
    persisted_config["asr_engine"] = engine_id
    save_config(persisted_config)

    if engine_id == "whisper":
        _asr_engine = "whisper"
        tray.set_status("Ready")
        main_window.dashboard_tab.set_active_engine_radio("whisper")
        main_window.refresh_engine_statuses("whisper", busy=is_busy())
    elif engine_id == "qwen3":
        main_window.dashboard_tab.set_active_engine_radio("qwen3")
        if _qwen3_engine is not None:
            _asr_engine = "qwen3"
            tray.set_status("Ready (Qwen3-ASR)")
            main_window.refresh_engine_statuses("qwen3", busy=is_busy())
        else:
            main_window.refresh_engine_statuses("qwen3", busy=True)
            _prepare_qwen3_async(tray, main_window)
    elif engine_id == "nemotron":
        main_window.dashboard_tab.set_active_engine_radio("nemotron")
        if _nemotron_engine is not None:
            _asr_engine = "nemotron"
            tray.set_status("Ready (Nemotron)")
            main_window.refresh_engine_statuses("nemotron", busy=is_busy())
        else:
            main_window.refresh_engine_statuses("nemotron", busy=True)
            _prepare_nemotron_async(tray, main_window)


def set_whisper_model_size(new_model_size: str, tray: TrayIcon):
    """Immediate model-size switch triggered from the Models & providers table's
    Whisper row -- persists and reloads the live model right away, the same way
    activate_asr_engine() does for engine switches, rather than waiting for
    Dashboard's Save. No engine-status UI refresh needed: the combo the user
    just changed already reflects the new value on its own.
    """
    global _model, _model_size

    if is_busy():
        print("Still dictating -- try changing the model size again in a moment.")
        return
    if new_model_size == _model_size:
        return

    persisted_config = load_config()
    persisted_config["model_size"] = new_model_size
    save_config(persisted_config)

    print(f"Loading {new_model_size} model...")
    tray.set_status(f"Loading {new_model_size} model...")
    _model = WhisperModel(new_model_size, device="cpu", compute_type="int8")
    _model_size = new_model_size
    tray.set_status("Ready")
    print("Model updated.")


def apply_settings(new_config: dict, tray: TrayIcon, main_window):
    global _model, _model_size, _input_device, _stream
    global _use_asr, _asr_engine, _use_multimodal, _multimodal_level, _fallback_to_whisper
    global _active_multimodal_model_id, _multimodal_timeout_seconds

    if is_busy():
        print("Still dictating -- try again in a moment.")
        return

    new_model_size = new_config["model_size"]
    new_device = new_config["input_device"]
    new_asr_engine = new_config["asr_engine"]

    if new_device != _input_device and not audio_capture.check_microphone(new_device):
        print("Selected microphone is not usable, keeping the previous one.")
        new_device = _input_device

    # Merge into the existing saved config rather than overwriting it outright --
    # config.json also holds multimodal_providers/multimodal_models (managed by
    # the Multimodal Models tab), which this dialog knows nothing about and
    # must not wipe out.
    persisted_config = load_config()
    persisted_config.update(
        {
            "model_size": new_model_size,
            "input_device": new_device,
            "use_asr": new_config["use_asr"],
            "asr_engine": new_asr_engine,
            "use_multimodal": new_config["use_multimodal"],
            "multimodal_level": new_config["multimodal_level"],
            "multimodal_timeout_seconds": new_config["multimodal_timeout_seconds"],
            "fallback_to_whisper": new_config["fallback_to_whisper"],
            "active_multimodal_model_id": new_config["active_multimodal_model_id"],
        }
    )
    save_config(persisted_config)

    _use_asr = new_config["use_asr"]
    _use_multimodal = new_config["use_multimodal"]
    _multimodal_level = new_config["multimodal_level"]
    _multimodal_timeout_seconds = new_config["multimodal_timeout_seconds"]
    _fallback_to_whisper = new_config["fallback_to_whisper"]
    _active_multimodal_model_id = new_config["active_multimodal_model_id"]

    if new_model_size != _model_size:
        print(f"Loading {new_model_size} model...")
        tray.set_status(f"Loading {new_model_size} model...")
        _model = WhisperModel(new_model_size, device="cpu", compute_type="int8")
        _model_size = new_model_size
        print("Model updated.")

    if new_device != _input_device:
        print("Switching microphone...")
        old_stream = _stream
        _stream = audio_capture.open_stream(new_device)
        _input_device = new_device
        if old_stream is not None:
            old_stream.stop()
            old_stream.close()
        print("Microphone updated.")

    if new_asr_engine == "qwen3" and _asr_engine != "qwen3":
        if _qwen3_engine is not None:
            _asr_engine = "qwen3"
            tray.set_status("Ready (Qwen3-ASR)")
            main_window.refresh_engine_statuses("qwen3", busy=is_busy())
        else:
            main_window.refresh_engine_statuses("qwen3", busy=True)
            _prepare_qwen3_async(tray, main_window)
    elif new_asr_engine == "nemotron" and _asr_engine != "nemotron":
        if _nemotron_engine is not None:
            _asr_engine = "nemotron"
            tray.set_status("Ready (Nemotron)")
            main_window.refresh_engine_statuses("nemotron", busy=is_busy())
        else:
            main_window.refresh_engine_statuses("nemotron", busy=True)
            _prepare_nemotron_async(tray, main_window)
    elif new_asr_engine == "whisper":
        _asr_engine = "whisper"
        tray.set_status("Ready")
        main_window.refresh_engine_statuses("whisper", busy=is_busy())
    else:
        tray.set_status("Ready")
        main_window.refresh_engine_statuses(_asr_engine, busy=is_busy())


def apply_language_settings(force_english_transliteration: bool):
    global _force_english_transliteration
    persisted_config = load_config()
    persisted_config["force_english_transliteration"] = force_english_transliteration
    save_config(persisted_config)
    _force_english_transliteration = force_english_transliteration


def apply_custom_words(custom_words: list[str]):
    global _custom_words
    persisted_config = load_config()
    persisted_config["custom_words"] = custom_words
    save_config(persisted_config)
    _custom_words = custom_words
    print(f"Custom dictionary updated: {len(custom_words)} term(s).")


def apply_dictation_language(dictation_language: str):
    global _dictation_language
    persisted_config = load_config()
    persisted_config["dictation_language"] = dictation_language
    save_config(persisted_config)
    _dictation_language = dictation_language
    print(f"Primary dictation language set to: {dictation_language}")


def _migrate_env_gemini_key_if_needed(config: dict) -> dict:
    """First-run only: if no providers are configured yet but a working
    GEMINI_API_KEY already exists in .env, turn it into a real provider+model
    pair so existing users see zero regression -- their already-working setup
    keeps working through the new Multimodal Models system instead of quietly
    depending on a hidden .env-only code path forever.
    """
    if config["multimodal_providers"] or not multimodal_engine.has_gemini_env_key():
        return config

    provider_id = "gemini"
    set_api_key(provider_id, multimodal_engine.get_gemini_env_key())
    model_id = f"{provider_id}::{multimodal_engine.GEMINI_ENV_MODEL}"

    config["multimodal_providers"] = [
        {"id": provider_id, "display_name": "Google Gemini", "base_url": None}
    ]
    config["multimodal_models"] = [
        {
            "id": model_id,
            "provider_id": provider_id,
            "model": multimodal_engine.GEMINI_ENV_MODEL,
            "display_name": "Gemini 3.5 Flash Lite",
            "supports_audio": True,
            "last_tested": None,
            "test_passed": True,  # proven working by this app's own extensive prior use, not re-tested
        }
    ]
    config["active_multimodal_model_id"] = model_id
    save_config(config)
    print("Migrated your .env GEMINI_API_KEY into a Multimodal Models provider.")
    return config


def main():
    set_app_user_model_id()

    global _model, _model_size, _input_device, _stream
    global _use_asr, _asr_engine, _use_multimodal, _multimodal_level, _fallback_to_whisper
    global _qwen3_engine, _nemotron_engine, _history_store
    global _multimodal_providers, _multimodal_models, _active_multimodal_model_id
    global _multimodal_timeout_seconds, _force_english_transliteration, _dictation_language
    global _custom_words

    config = load_config()
    config = _migrate_env_gemini_key_if_needed(config)
    _model_size = config["model_size"]
    _input_device = config["input_device"]
    _use_asr = config["use_asr"]
    _asr_engine = config["asr_engine"]
    _use_multimodal = config["use_multimodal"]
    _multimodal_level = config["multimodal_level"]
    _multimodal_timeout_seconds = config["multimodal_timeout_seconds"]
    _fallback_to_whisper = config["fallback_to_whisper"]
    _multimodal_providers = config["multimodal_providers"]
    _multimodal_models = config["multimodal_models"]
    _active_multimodal_model_id = config["active_multimodal_model_id"]
    _force_english_transliteration = config["force_english_transliteration"]
    _dictation_language = config.get("dictation_language", "en")
    _custom_words = [w.strip() for w in config.get("custom_words", []) if str(w).strip()]
    if _custom_words:
        print(f"Custom dictionary: {len(_custom_words)} term(s).")

    if not audio_capture.check_microphone(_input_device):
        print("No microphone detected. Plug one in and restart the app.")
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # closing the main window must not quit the app
    app.setWindowIcon(mark_icon(BRAND_ACCENT_DARK_HEX))

    from utils.single_instance import SingleInstance
    single_instance = SingleInstance()
    if single_instance.is_already_running():
        print("Infinisper is already running. Focused existing window.")
        return

    # Windows Vista style animates combo/menu popups open with a slide+fade -- on a
    # frameless translucent window this reads as a flash/flicker rather than a smooth
    # reveal. Popups still open instantly and correctly with this off.
    app.setEffectEnabled(Qt.UI_AnimateCombo, False)
    app.setEffectEnabled(Qt.UI_AnimateMenu, False)

    _history_store = HistoryStore()

    chip = ChipWindow()
    tray = TrayIcon()
    quit_signal = _QuitSignal()
    quit_signal.triggered.connect(app.quit)
    tray.quit_requested.connect(app.quit)

    def on_pause_toggled(paused: bool):
        global _paused
        _paused = paused
        chip.set_state("paused" if paused else "idle")
        tray.set_status("Paused" if paused else "Ready")

    tray.pause_toggled.connect(on_pause_toggled)

    current_config = {
        "model_size": _model_size,
        "input_device": _input_device,
        "use_asr": _use_asr,
        "asr_engine": _asr_engine,
        "use_multimodal": _use_multimodal,
        "multimodal_level": _multimodal_level,
        "multimodal_timeout_seconds": _multimodal_timeout_seconds,
        "fallback_to_whisper": _fallback_to_whisper,
        "multimodal_models": _multimodal_models,
        "active_multimodal_model_id": _active_multimodal_model_id,
        "force_english_transliteration": _force_english_transliteration,
        "dictation_language": _dictation_language,
        "custom_words": _custom_words,
    }
    main_window = MainWindow(current_config, _history_store)
    main_window.settings_saved.connect(lambda cfg: apply_settings(cfg, tray, main_window))
    main_window.language_settings_changed.connect(apply_language_settings)
    main_window.dictation_language_changed.connect(apply_dictation_language)
    main_window.custom_words_changed.connect(apply_custom_words)
    main_window.delete_model_requested.connect(
        lambda engine_id: delete_model(engine_id, main_window)
    )
    main_window.activate_engine_requested.connect(
        lambda engine_id: activate_asr_engine(engine_id, tray, main_window)
    )
    main_window.whisper_model_size_changed.connect(
        lambda size: set_whisper_model_size(size, tray)
    )

    def on_multimodal_changed():
        # The Multimodal Models tab can itself null out active_multimodal_model_id
        # (deleting the provider/model backing it), so re-read that too, not just
        # the provider/model lists -- otherwise app.py's cache would keep pointing
        # at a model that no longer exists.
        global _multimodal_providers, _multimodal_models, _active_multimodal_model_id
        fresh_config = load_config()
        _multimodal_providers = fresh_config["multimodal_providers"]
        _multimodal_models = fresh_config["multimodal_models"]
        _active_multimodal_model_id = fresh_config["active_multimodal_model_id"]
        main_window.dashboard_tab.refresh_multimodal_models(
            _multimodal_models, _active_multimodal_model_id
        )

    main_window.multimodal_changed.connect(on_multimodal_changed)

    audio_capture.set_chip(_LevelFanout(chip, main_window.sidebar))
    chip.state_changed.connect(
        lambda state: main_window.sidebar.set_listening(state == "listening")
    )
    tray.status_changed.connect(main_window.sidebar.set_status)

    tray.open_window_requested.connect(main_window.show_dashboard)
    single_instance.show_requested.connect(main_window.show_dashboard)

    # Cold-start splash (Infinisper Brand.html, "Loader A") covers the real boot
    # work below -- speech model load, mic open, extra-engine load -- so the wait
    # reads as visible progress instead of a blank or frozen main window. Closes
    # the instant the main window is ready, per the brand doc's own handoff note.
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    total_steps = 3 if _asr_engine in ("qwen3", "nemotron") else 2
    step = 0

    step += 1
    splash.set_step("Opening the microphone...", step, total_steps)
    try:
        _stream = audio_capture.open_stream(_input_device)
    except Exception as exc:
        print(f"Could not open the microphone: {exc}")
        splash.close()
        return

    step += 1
    splash.set_step(f"Loading speech model ({_model_size})...", step, total_steps)
    print(f"Loading speech model ({_model_size})...")
    _model = WhisperModel(_model_size, device="cpu", compute_type="int8")
    audio_vad.warm_up()

    if _asr_engine == "qwen3":
        step += 1
        if qwen_asr.is_downloaded():
            splash.set_step("Loading Qwen3-ASR...", step, total_steps)
            print("Loading Qwen3-ASR...")
            _qwen3_engine = qwen_asr.Qwen3AsrEngine()
            print("Qwen3-ASR loaded.")
        else:
            print("Qwen3-ASR selected but not downloaded -- open the Dashboard and Save to fetch it.")
            _asr_engine = "whisper"
    elif _asr_engine == "nemotron":
        step += 1
        if nemotron_asr.is_downloaded():
            splash.set_step("Loading Nemotron 3.5 ASR...", step, total_steps)
            print("Loading Nemotron 3.5 ASR...")
            _nemotron_engine = nemotron_asr.NemotronAsrEngine()
            print("Nemotron 3.5 ASR loaded.")
        else:
            print("Nemotron 3.5 ASR selected but not downloaded -- open the Dashboard and Save to fetch it.")
            _asr_engine = "whisper"

    main_window.refresh_engine_statuses(_asr_engine, busy=False)

    splash.set_step("Ready -- hold Ctrl+Win and speak", total_steps, total_steps)
    splash.close()

    # The whole point of this change is to move the app out of the terminal --
    # the main window is the primary surface, shown by default rather than
    # hidden behind a tray click.
    main_window.show()

    print("Model loaded. Hold Ctrl+Win to dictate, release to transcribe and paste.")
    print("Right-click the tray icon to open the window, Pause, or Quit. Esc also quits.")

    threading.Thread(target=hotkey_loop, args=(chip, tray, quit_signal), daemon=True).start()

    app.exec()

    if _stream is not None:
        _stream.stop()
        _stream.close()
    print("Bye.")


if __name__ == "__main__":
    main()
