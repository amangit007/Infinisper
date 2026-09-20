"""Reacts to the user changing something in the window: engine switches, model deletes,
the Dashboard's Save, the Language tab, and the Models & providers tab.

Each handler persists the change to config.json and then updates the live `Settings` /
`Runtime` the pipeline reads. The handlers run on the Qt main thread; the slow parts
(downloading and loading a model) go to a background thread and report back through the
tray status and `main_window.engine_status_refresh_requested`.
"""

import threading
from typing import NamedTuple

from faster_whisper import WhisperModel

from asr import catalog as asr_catalog
from asr import nemotron_asr, qwen_asr
from audio import capture as audio_capture
from config import load_config, save_config
from dictation.pipeline import Pipeline


class _EngineSpec(NamedTuple):
    module: object  # asr.qwen_asr / asr.nemotron_asr: is_downloaded(), download(), and the engine class
    engine_class: str
    attribute: str  # on Runtime
    label: str
    short_name: str  # as shown in "Ready (...)"
    download_size: str


_ENGINES = {
    "qwen3": _EngineSpec(qwen_asr, "Qwen3AsrEngine", "qwen3", "Qwen3-ASR", "Qwen3-ASR", "~980 MB"),
    "nemotron": _EngineSpec(nemotron_asr, "NemotronAsrEngine", "nemotron", "Nemotron 3.5 ASR", "Nemotron", "~650 MB"),
}


class SettingsController:
    def __init__(self, pipeline: Pipeline, tray, main_window):
        self.pipeline = pipeline
        self.settings = pipeline.settings
        self.runtime = pipeline.runtime
        self.tray = tray
        self.main_window = main_window
        self._prep_lock = threading.Lock()
        self._prepping = False

    def on_download_finished(self, model_id: str, success: bool, error: str):
        if success:
            print(f"Download complete: {model_id}")
            if model_id.startswith("whisper-"):
                size = model_id.removeprefix("whisper-")
                if self.runtime.whisper is None or self.runtime.active_engine == "whisper":
                    self._load_whisper_async(size)
            elif model_id in _ENGINES:
                if self.runtime.active_engine == model_id:
                    self._prepare_async(model_id)
            self.tray.set_status("Ready")
        else:
            print(f"Download failed for {model_id}: {error}")
            self.tray.set_status(f"Download failed: {error}")

        self.main_window.refresh_engine_statuses(self.runtime.active_engine or "", busy=False)

    def start_model_download(self, model_id: str):
        if self.pipeline.is_busy():
            print("Still dictating -- try downloading again in a moment.")
            return
        print(f"Starting download for {model_id}...")
        self.tray.set_status(f"Downloading {model_id}...")
        from asr.downloader import get_downloader
        get_downloader().start_download(model_id)
        self.main_window.refresh_engine_statuses(self.runtime.active_engine or "", busy=False)

    # ---- speech engines --------------------------------------------------------------

    def _switch_to(self, engine_id: str):
        """Makes `engine_id` active now if it's loaded; otherwise loads it (downloading
        first if needed) on a background thread. Whisper is always available."""
        rt = self.runtime
        if engine_id == "whisper":
            rt.active_engine = "whisper"
            self.tray.set_status("Ready")
            self.main_window.refresh_engine_statuses("whisper", busy=self.pipeline.is_busy())
            return

        spec = _ENGINES.get(engine_id)
        if not spec:
            return

        if getattr(rt, spec.attribute) is not None:
            rt.active_engine = engine_id
            self.tray.set_status(f"Ready ({spec.short_name})")
            self.main_window.refresh_engine_statuses(engine_id, busy=self.pipeline.is_busy())
        else:
            self.main_window.refresh_engine_statuses(engine_id, busy=True)
            self._prepare_async(engine_id)

    def _prepare_async(self, engine_id: str):
        """Downloads (if needed) and loads an engine on a background thread, since the
        download can be hundreds of MB and must never block the Qt main thread. Whisper
        stays active as the ASR engine until this completes.
        """
        rt, spec = self.runtime, _ENGINES[engine_id]

        if getattr(rt, spec.attribute) is not None:
            rt.active_engine = engine_id
            self.tray.set_status(f"Ready ({spec.short_name})")
            self.main_window.engine_status_refresh_requested.emit(engine_id, self.pipeline.is_busy())
            return

        with self._prep_lock:
            if self._prepping:
                print("Already preparing a speech engine, please wait...")
                return
            self._prepping = True

        def worker():
            try:
                if not spec.module.is_downloaded():
                    self.tray.set_status(f"Downloading {spec.label} ({spec.download_size})...")
                    spec.module.download()
                self.tray.set_status(f"Loading {spec.label}...")
                setattr(rt, spec.attribute, getattr(spec.module, spec.engine_class)())
                rt.active_engine = engine_id
                print(f"{spec.label} ready.")
                self.tray.set_status(f"Ready ({spec.short_name})")
            except Exception as exc:
                print(f"Failed to prepare {spec.label} ({exc}), staying on Whisper.")
                self.tray.set_status(f"Ready ({spec.short_name} setup failed)")
                rt.active_engine = "whisper"
            finally:
                with self._prep_lock:
                    self._prepping = False
                self.main_window.engine_status_refresh_requested.emit(
                    rt.active_engine, self.pipeline.is_busy()
                )

        threading.Thread(target=worker, daemon=True).start()

    def _load_whisper_async(self, size: str):
        """Loads Whisper variant on a background thread to prevent freezing the GUI."""
        rt = self.runtime
        self.tray.set_status(f"Loading Whisper {size}...")
        self.main_window.refresh_engine_statuses(rt.active_engine or "whisper", busy=True)

        def worker():
            try:
                model_path = asr_catalog.get_whisper_model_path(size)
                print(f"Loading Whisper {size} from {model_path}...")
                model = WhisperModel(model_path, device="cpu", compute_type="int8")
                rt.whisper = model
                rt.whisper_size = size
                rt.active_engine = "whisper"
                persisted_config = load_config()
                persisted_config["model_size"] = size
                persisted_config["asr_engine"] = "whisper"
                save_config(persisted_config)
                print(f"Whisper {size} loaded.")
                self.tray.set_status("Ready")
            except Exception as exc:
                print(f"Failed to load Whisper {size} ({exc}).")
                self.tray.set_status("Whisper load failed")
            finally:
                self.main_window.engine_status_refresh_requested.emit(
                    rt.active_engine or "whisper", self.pipeline.is_busy()
                )

        threading.Thread(target=worker, daemon=True).start()

    def delete_model(self, engine_id: str):
        """Permanently deletes a downloaded ASR model's weights after confirmation."""
        rt = self.runtime
        if self.pipeline.is_busy():
            print("Still dictating -- try deleting the model again in a moment.")
            return

        was_active = False
        if engine_id.startswith("whisper-"):
            size = engine_id.removeprefix("whisper-")
            was_active = (rt.active_engine == "whisper" and rt.whisper_size == size)
        elif engine_id == "whisper":
            was_active = (rt.active_engine == "whisper")
        else:
            was_active = (engine_id == rt.active_engine)

        if not self.main_window.models_tab.confirm_and_request_delete_engine(engine_id, was_active):
            return

        try:
            asr_catalog.delete_model(engine_id)
            print(f"Deleted {engine_id} model files.")
        except Exception as exc:
            print(f"Failed to delete {engine_id} model files: {exc}")
            return

        if engine_id in _ENGINES:
            setattr(rt, _ENGINES[engine_id].attribute, None)
        elif engine_id.startswith("whisper-"):
            size = engine_id.removeprefix("whisper-")
            if rt.whisper_size == size:
                rt.whisper = None

        if was_active:
            rt.active_engine = "whisper"
            current_config = load_config()
            current_config["asr_engine"] = "whisper"
            save_config(current_config)
            self.main_window.dashboard_tab.set_active_engine_radio("whisper")
            print("Switched to Whisper since the active engine's model was deleted.")

        self.main_window.refresh_engine_statuses(rt.active_engine, busy=False)

    def activate_asr_engine(self, engine_or_model_id: str):
        """Immediate engine or model variant switch triggered from the UI."""
        if self.pipeline.is_busy():
            print("Still dictating -- try activating a different engine again in a moment.")
            return

        rt = self.runtime

        # Handle whisper variant (e.g. 'whisper-base')
        if engine_or_model_id.startswith("whisper-"):
            size = engine_or_model_id.removeprefix("whisper-")
            if rt.active_engine == "whisper" and rt.whisper_size == size:
                return
            if not asr_catalog.is_downloaded(engine_or_model_id):
                print(f"{engine_or_model_id} not downloaded, starting download...")
                self.start_model_download(engine_or_model_id)
                return
            persisted_config = load_config()
            persisted_config["asr_engine"] = "whisper"
            persisted_config["model_size"] = size
            save_config(persisted_config)
            self.main_window.dashboard_tab.set_active_engine_radio("whisper")
            rt.active_engine = "whisper"
            self.set_whisper_model_size(size)
            return

        if engine_or_model_id == rt.active_engine:
            return

        if engine_or_model_id != "whisper" and engine_or_model_id not in _ENGINES:
            print(f"Unknown speech engine '{engine_or_model_id}', ignoring.")
            return

        persisted_config = load_config()
        persisted_config["asr_engine"] = engine_or_model_id
        save_config(persisted_config)

        self.main_window.dashboard_tab.set_active_engine_radio(engine_or_model_id)
        self._switch_to(engine_or_model_id)

    def set_whisper_model_size(self, new_model_size: str):
        """Switches Whisper model size, downloading first if needed."""
        rt = self.runtime
        if self.pipeline.is_busy():
            print("Still dictating -- try changing the model size again in a moment.")
            return
        if new_model_size == rt.whisper_size and rt.whisper is not None:
            return

        model_id = f"whisper-{new_model_size}"
        if not asr_catalog.is_downloaded(model_id):
            print(f"Whisper {new_model_size} not downloaded. Starting download...")
            self.start_model_download(model_id)
            return

        self._load_whisper_async(new_model_size)

    # ---- the Dashboard's Save --------------------------------------------------------

    def apply_settings(self, new_config: dict):
        rt, settings, tray = self.runtime, self.settings, self.tray

        if self.pipeline.is_busy():
            print("Still dictating -- try again in a moment.")
            return

        new_model_size = new_config["model_size"]
        new_device = new_config["input_device"]
        new_asr_engine = new_config["asr_engine"]

        if new_device != rt.input_device and not audio_capture.check_microphone(new_device):
            print("Selected microphone is not usable, keeping the previous one.")
            new_device = rt.input_device

        persisted_config = load_config()
        persisted_config.update(
            {
                "model_size": new_model_size,
                "input_device": new_device,
                "use_asr": new_config["use_asr"],
                "asr_engine": new_asr_engine,
                "use_cleanup": new_config["use_cleanup"],
                "cleanup_level": new_config["cleanup_level"],
                "cleanup_timeout_seconds": new_config["cleanup_timeout_seconds"],
                "fallback_to_whisper": new_config["fallback_to_whisper"],
                "active_cleanup_model_id": new_config["active_cleanup_model_id"],
                "hotkey": new_config.get("hotkey", "ctrl+win"),
                "ollama_keep_alive": new_config.get("ollama_keep_alive", settings.ollama_keep_alive),
            }
        )
        save_config(persisted_config)

        settings.apply_dashboard(new_config)
        self.pipeline.warm_active_ollama_model()

        if new_model_size != rt.whisper_size:
            self.set_whisper_model_size(new_model_size)

        if new_device != rt.input_device:
            print("Switching microphone...")
            old_stream = rt.mic_stream
            rt.mic_stream = audio_capture.open_stream(new_device)
            rt.input_device = new_device
            if old_stream is not None:
                old_stream.stop()
                old_stream.close()
            print("Microphone updated.")

        if new_asr_engine == "whisper" or (new_asr_engine in _ENGINES and new_asr_engine != rt.active_engine):
            self._switch_to(new_asr_engine)
        else:
            tray.set_status("Ready")
            self.main_window.refresh_engine_statuses(rt.active_engine or "", busy=self.pipeline.is_busy())

    # ---- the Language and Models & providers tabs ------------------------------------

    def apply_language_settings(self, force_english_transliteration: bool):
        settings = self.settings
        persisted_config = load_config()
        persisted_config["force_english_transliteration"] = force_english_transliteration
        if force_english_transliteration:
            persisted_config["cleanup_output_mode"] = "transliterate"
            settings.cleanup_output_mode = "transliterate"
        elif persisted_config.get("cleanup_output_mode") == "transliterate":
            persisted_config["cleanup_output_mode"] = "original"
            settings.cleanup_output_mode = "original"
        save_config(persisted_config)
        settings.force_english_transliteration = force_english_transliteration

    def apply_cleanup_transformation(self, output_mode: str, target_language: str):
        settings = self.settings
        persisted_config = load_config()
        persisted_config["cleanup_output_mode"] = output_mode
        persisted_config["translation_target_language"] = target_language
        persisted_config["force_english_transliteration"] = (output_mode == "transliterate")
        save_config(persisted_config)
        settings.cleanup_output_mode = output_mode
        settings.translation_target_language = target_language
        settings.force_english_transliteration = (output_mode == "transliterate")
        print(f"Cleanup transformation set to: {output_mode} (target: {target_language})")

    def apply_custom_words(self, custom_words: list[str]):
        persisted_config = load_config()
        persisted_config["custom_words"] = custom_words
        save_config(persisted_config)
        self.settings.custom_words = custom_words
        print(f"Custom dictionary updated: {len(custom_words)} term(s).")

    def apply_dictation_language(self, dictation_language: str):
        persisted_config = load_config()
        persisted_config["dictation_language"] = dictation_language
        save_config(persisted_config)
        self.settings.dictation_language = dictation_language
        print(f"Primary dictation language set to: {dictation_language}")

    def on_cleanup_changed(self):
        self.settings.reload_cleanup_models(load_config())
        self.main_window.dashboard_tab.refresh_cleanup_models(
            self.settings.cleanup_models, self.settings.active_cleanup_model_id
        )
        self.pipeline.warm_active_ollama_model()
