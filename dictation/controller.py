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

        spec = _ENGINES[engine_id]
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

    def delete_model(self, engine_id: str):
        """Permanently deletes a downloaded ASR engine's weights, after a
        confirmation dialog naming the exact size/path. Refused only while the
        app is busy dictating -- deleting the currently active engine is allowed;
        since Whisper itself can never be deleted, it's always safe to fall back
        to as the new active engine.
        """
        rt = self.runtime
        if self.pipeline.is_busy():
            print("Still dictating -- try deleting the model again in a moment.")
            return

        was_active = engine_id == rt.active_engine
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

        if was_active:
            rt.active_engine = "whisper"
            current_config = load_config()
            current_config["asr_engine"] = "whisper"
            save_config(current_config)
            self.main_window.dashboard_tab.set_active_engine_radio("whisper")
            print("Switched to Whisper since the active engine's model was deleted.")

        self.main_window.refresh_engine_statuses(rt.active_engine, busy=False)

    def activate_asr_engine(self, engine_id: str):
        """Immediate engine switch triggered from the Models & providers table's
        Activate button -- unlike Dashboard's Save, this doesn't wait for the rest
        of the settings form. Engine switches can still trigger a real download, so
        qwen3/nemotron go through the same background load Dashboard's Save uses; only
        whisper (always available) switches synchronously.
        """
        if self.pipeline.is_busy():
            print("Still dictating -- try activating a different engine again in a moment.")
            return
        if engine_id == self.runtime.active_engine:
            return
        if engine_id != "whisper" and engine_id not in _ENGINES:
            print(f"Unknown speech engine '{engine_id}', ignoring.")
            return

        persisted_config = load_config()
        persisted_config["asr_engine"] = engine_id
        save_config(persisted_config)

        self.main_window.dashboard_tab.set_active_engine_radio(engine_id)
        self._switch_to(engine_id)

    def set_whisper_model_size(self, new_model_size: str):
        """Immediate model-size switch triggered from the Models & providers table's
        Whisper row -- persists and reloads the live model right away, the same way
        activate_asr_engine() does for engine switches, rather than waiting for
        Dashboard's Save. No engine-status UI refresh needed: the combo the user
        just changed already reflects the new value on its own.
        """
        rt = self.runtime
        if self.pipeline.is_busy():
            print("Still dictating -- try changing the model size again in a moment.")
            return
        if new_model_size == rt.whisper_size:
            return

        persisted_config = load_config()
        persisted_config["model_size"] = new_model_size
        save_config(persisted_config)

        print(f"Loading {new_model_size} model...")
        self.tray.set_status(f"Loading {new_model_size} model...")
        rt.whisper = WhisperModel(new_model_size, device="cpu", compute_type="int8")
        rt.whisper_size = new_model_size
        self.tray.set_status("Ready")
        print("Model updated.")

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

        # Merge into the existing saved config rather than overwriting it outright --
        # config.json also holds cleanup_providers/cleanup_models (managed by
        # the Models & providers tab), which this dialog knows nothing about and
        # must not wipe out.
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
            print(f"Loading {new_model_size} model...")
            tray.set_status(f"Loading {new_model_size} model...")
            rt.whisper = WhisperModel(new_model_size, device="cpu", compute_type="int8")
            rt.whisper_size = new_model_size
            print("Model updated.")

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
            self.main_window.refresh_engine_statuses(rt.active_engine, busy=self.pipeline.is_busy())

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
