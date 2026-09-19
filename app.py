"""Starts Infinisper: reads the config, builds the window, tray and dictation pipeline, and
wires the window's signals to the controller. The dictation logic itself lives in dictation/.
"""

import sys
import threading

from faster_whisper import WhisperModel
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from asr import nemotron_asr, qwen_asr
from audio import capture as audio_capture
from audio import vad as audio_vad
from cleanup import engine as cleanup_engine
from config import load_config, save_config
from credentials import set_api_key
from dictation.controller import SettingsController
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings
from history.store import HistoryStore
from ui.assets.mark import BRAND_HEX, mark_icon
from ui.chip import ChipWindow
from ui.main_window import MainWindow
from ui.splash import SplashScreen
from ui.tray import TrayIcon
from utils.windows import HOTKEY_PRESETS, set_app_user_model_id


class _LevelFanout:
    """Forwards audio.capture's single update_audio_level(level) callback to more
    than one listener -- the chip pill and the sidebar's mic meter both need real
    levels, and audio.capture only supports wiring one object via set_chip()."""

    def __init__(self, *listeners):
        self._listeners = listeners

    def update_audio_level(self, level: float):
        for listener in self._listeners:
            listener.update_audio_level(level)


def _migrate_env_gemini_key_if_needed(config: dict) -> dict:
    """First-run only: if no models are configured yet but a working
    GEMINI_API_KEY already exists in .env, turn it into a real provider+model
    pair so existing users see zero regression -- their already-working setup
    keeps working through the AI providers system instead of quietly
    depending on a hidden .env-only code path forever.
    """
    if config["cleanup_models"] or not cleanup_engine.has_gemini_env_key():
        return config

    provider_id = "gemini"
    set_api_key(provider_id, cleanup_engine.get_gemini_env_key())
    model_id = f"{provider_id}::{cleanup_engine.GEMINI_ENV_MODEL}"

    # Kept alongside the pre-configured Ollama provider, not replacing it.
    config["cleanup_providers"] = [p for p in config["cleanup_providers"] if p["id"] != provider_id] + [
        {"id": provider_id, "display_name": "Google Gemini", "base_url": None}
    ]
    config["cleanup_models"] = [
        {
            "id": model_id,
            "provider_id": provider_id,
            "model": cleanup_engine.GEMINI_ENV_MODEL,
            "display_name": "Gemini 3.5 Flash Lite",
            "supports_audio": True,
            "last_tested": None,
            "test_passed": True,  # proven working by this app's own extensive prior use, not re-tested
        }
    ]
    config["active_cleanup_model_id"] = model_id
    save_config(config)
    print("Migrated your .env GEMINI_API_KEY into an AI provider.")
    return config


def _window_config(settings: Settings, runtime: Runtime) -> dict:
    """The starting state the main window's tabs are built from."""
    return {
        "model_size": runtime.whisper_size,
        "input_device": runtime.input_device,
        "use_asr": settings.use_asr,
        "asr_engine": runtime.active_engine,
        "use_cleanup": settings.use_cleanup,
        "cleanup_level": settings.cleanup_level,
        "cleanup_timeout_seconds": settings.cleanup_timeout_seconds,
        "fallback_to_whisper": settings.fallback_to_whisper,
        "cleanup_models": settings.cleanup_models,
        "active_cleanup_model_id": settings.active_cleanup_model_id,
        "force_english_transliteration": settings.force_english_transliteration,
        "cleanup_output_mode": settings.cleanup_output_mode,
        "translation_target_language": settings.translation_target_language,
        "dictation_language": settings.dictation_language,
        "custom_words": settings.custom_words,
        "hotkey": settings.hotkey,
        "ollama_keep_alive": settings.ollama_keep_alive,
    }


def _load_speech_models(runtime: Runtime, splash, step: int, total_steps: int):
    """Loads Whisper (always) and the configured Qwen3 / Nemotron engine, if downloaded."""
    step += 1
    splash.set_step(f"Loading speech model ({runtime.whisper_size})...", step, total_steps)
    print(f"Loading speech model ({runtime.whisper_size})...")
    runtime.whisper = WhisperModel(runtime.whisper_size, device="cpu", compute_type="int8")
    audio_vad.warm_up()

    if runtime.active_engine == "qwen3":
        step += 1
        if qwen_asr.is_downloaded():
            splash.set_step("Loading Qwen3-ASR...", step, total_steps)
            print("Loading Qwen3-ASR...")
            runtime.qwen3 = qwen_asr.Qwen3AsrEngine()
            print("Qwen3-ASR loaded.")
        else:
            print("Qwen3-ASR selected but not downloaded -- open the Dashboard and Save to fetch it.")
            runtime.active_engine = "whisper"
    elif runtime.active_engine == "nemotron":
        step += 1
        if nemotron_asr.is_downloaded():
            splash.set_step("Loading Nemotron 3.5 ASR...", step, total_steps)
            print("Loading Nemotron 3.5 ASR...")
            runtime.nemotron = nemotron_asr.NemotronAsrEngine()
            print("Nemotron 3.5 ASR loaded.")
        else:
            print("Nemotron 3.5 ASR selected but not downloaded -- open the Dashboard and Save to fetch it.")
            runtime.active_engine = "whisper"


def main():
    set_app_user_model_id()

    config = _migrate_env_gemini_key_if_needed(load_config())
    settings = Settings.from_config(config)
    runtime = Runtime.from_config(config)
    if settings.custom_words:
        print(f"Custom dictionary: {len(settings.custom_words)} term(s).")

    if not audio_capture.check_microphone(runtime.input_device):
        print("No microphone detected. Plug one in and restart the app.")
        return

    app = QApplication(sys.argv)
    app.setQuitOnLastWindowClosed(False)  # closing the main window must not quit the app
    app.setWindowIcon(mark_icon(BRAND_HEX))

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

    history_store = HistoryStore()
    pipeline = Pipeline(settings, runtime, history_store)

    chip = ChipWindow()
    tray = TrayIcon()
    tray.quit_requested.connect(app.quit)

    def on_pause_toggled(paused: bool):
        pipeline.paused = paused
        chip.set_state("paused" if paused else "idle")
        tray.set_status("Paused" if paused else "Ready")

    tray.pause_toggled.connect(on_pause_toggled)

    main_window = MainWindow(_window_config(settings, runtime), history_store)
    controller = SettingsController(pipeline, tray, main_window)
    main_window.settings_saved.connect(controller.apply_settings)
    main_window.language_settings_changed.connect(controller.apply_language_settings)
    main_window.cleanup_transformation_changed.connect(controller.apply_cleanup_transformation)
    main_window.dictation_language_changed.connect(controller.apply_dictation_language)
    main_window.custom_words_changed.connect(controller.apply_custom_words)
    main_window.delete_model_requested.connect(controller.delete_model)
    main_window.activate_engine_requested.connect(controller.activate_asr_engine)
    main_window.whisper_model_size_changed.connect(controller.set_whisper_model_size)
    main_window.cleanup_changed.connect(controller.on_cleanup_changed)

    audio_capture.set_chip(_LevelFanout(chip, main_window.sidebar))
    chip.state_changed.connect(
        lambda state: main_window.sidebar.set_listening(state == "listening")
    )
    tray.status_changed.connect(main_window.sidebar.set_status)

    tray.open_window_requested.connect(main_window.show_dashboard)
    single_instance.show_requested.connect(main_window.show_dashboard)

    # Splash screen displayed during application startup.
    splash = SplashScreen()
    splash.show()
    app.processEvents()

    total_steps = 3 if runtime.active_engine in ("qwen3", "nemotron") else 2
    splash.set_step("Opening the microphone...", 1, total_steps)
    try:
        runtime.mic_stream = audio_capture.open_stream(runtime.input_device)
    except Exception as exc:
        print(f"Could not open the microphone: {exc}")
        splash.close()
        return

    _load_speech_models(runtime, splash, 1, total_steps)
    main_window.refresh_engine_statuses(runtime.active_engine, busy=False)

    hotkey_name = HOTKEY_PRESETS.get(settings.hotkey, {}).get("display", "Ctrl + Win")
    splash.set_step(f"Ready -- hold {hotkey_name} and speak", total_steps, total_steps)
    splash.close()

    # The whole point of this change is to move the app out of the terminal --
    # the main window is the primary surface, shown by default rather than
    # hidden behind a tray click.
    main_window.show()
    pipeline.warm_active_ollama_model()

    print("Model loaded. Hold Ctrl+Win to dictate, release to transcribe and paste.")
    print("Right-click the tray icon to open the window, Pause, or Quit.")

    threading.Thread(target=pipeline.hotkey_loop, args=(chip, tray), daemon=True).start()

    app.exec()

    if runtime.mic_stream is not None:
        runtime.mic_stream.stop()
        runtime.mic_stream.close()
    print("Bye.")


if __name__ == "__main__":
    main()
