"""The settings the dictation loop reads, and the handlers that change them.

These were module-level globals in app.py, reachable only by patching the module. They now
live on `Settings`, `Runtime` and `SettingsController`, so the switching logic -- which
engine is active after a click, what gets persisted, what happens when a download fails --
can be tested directly.
"""

import pytest

from config import DEFAULT_CONFIG
from dictation import controller as controller_module
from dictation.controller import SettingsController
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings

OLLAMA = {"id": "ollama", "display_name": "Ollama", "base_url": "http://127.0.0.1:11434"}
LOCAL_MODEL = {"id": "ollama::ollama/gemma4:e4b", "provider_id": "ollama", "model": "ollama/gemma4:e4b"}


# --- Settings ---------------------------------------------------------------------


def test_from_config_reads_every_field_and_strips_blank_custom_words():
    config = dict(DEFAULT_CONFIG, custom_words=[" Kubernetes ", "", "  ", "OKR"], dictation_language="hi")
    settings = Settings.from_config(config)
    assert settings.custom_words == ["Kubernetes", "OKR"]
    assert settings.dictation_language == "hi"
    assert settings.use_asr is config["use_asr"]


def test_from_config_tolerates_a_config_written_before_newer_keys_existed():
    config = {k: v for k, v in DEFAULT_CONFIG.items()
              if k not in ("hotkey", "ollama_keep_alive", "custom_words", "dictation_language")}
    settings = Settings.from_config(config)
    assert settings.hotkey == "ctrl+win"
    assert settings.ollama_keep_alive == "30m"
    assert settings.custom_words == []
    assert settings.dictation_language == "en"


def test_the_active_model_resolves_with_its_provider_details(monkeypatch):
    monkeypatch.setattr("dictation.settings.get_api_key", lambda provider_id: f"key-for-{provider_id}")
    settings = Settings(
        cleanup_providers=[OLLAMA], cleanup_models=[LOCAL_MODEL], active_cleanup_model_id=LOCAL_MODEL["id"]
    )
    assert settings.resolve_active_cleanup() == (
        "ollama/gemma4:e4b", "key-for-ollama", "http://127.0.0.1:11434", False
    )


@pytest.mark.parametrize("providers, models, active", [
    ([OLLAMA], [LOCAL_MODEL], None),  # nothing selected
    ([OLLAMA], [], LOCAL_MODEL["id"]),  # the model was deleted after being selected
    ([], [LOCAL_MODEL], LOCAL_MODEL["id"]),  # its provider was deleted
])
def test_a_missing_active_model_resolves_to_none(providers, models, active):
    settings = Settings(cleanup_providers=providers, cleanup_models=models, active_cleanup_model_id=active)
    assert settings.resolve_active_cleanup() is None


def test_reload_picks_up_a_model_the_models_tab_just_removed():
    settings = Settings(
        cleanup_providers=[OLLAMA], cleanup_models=[LOCAL_MODEL], active_cleanup_model_id=LOCAL_MODEL["id"]
    )
    settings.reload_cleanup_models(
        {"cleanup_providers": [OLLAMA], "cleanup_models": [], "active_cleanup_model_id": None}
    )
    assert settings.cleanup_models == []
    assert settings.active_cleanup_model_id is None


def test_two_pipelines_do_not_share_state():
    """The point of leaving module globals: state belongs to an instance."""
    a, b = Pipeline(Settings(), Runtime()), Pipeline(Settings(), Runtime())
    a.settings.custom_words.append("Nemotron")
    a.runtime.active_engine = "qwen3"
    assert b.settings.custom_words == []
    assert b.runtime.active_engine == "whisper"


# --- SettingsController -----------------------------------------------------------


class Signal:
    def __init__(self, log):
        self._log = log

    def emit(self, *args):
        self._log.append(("engine_status_refresh_requested", args))


class Namespace:
    pass


class FakeMainWindow:
    def __init__(self, confirm_delete=True):
        self.log = []
        self.engine_status_refresh_requested = Signal(self.log)
        self.dashboard_tab = Namespace()
        self.dashboard_tab.set_active_engine_radio = lambda engine: self.log.append(("radio", engine))
        self.dashboard_tab.refresh_cleanup_models = lambda models, active: self.log.append(("models", active))
        self.models_tab = Namespace()
        self.models_tab.confirm_and_request_delete_engine = lambda engine, was_active: confirm_delete

    def refresh_engine_statuses(self, engine, busy):
        self.log.append(("refresh", engine, busy))


class FakeTray:
    def __init__(self):
        self.statuses = []

    def set_status(self, text):
        self.statuses.append(text)


class Harness:
    def __init__(self, monkeypatch, runtime=None, settings=None, confirm_delete=True):
        self.saved = {}
        self.stored = dict(DEFAULT_CONFIG)
        monkeypatch.setattr(controller_module, "load_config", lambda: dict(self.stored))
        monkeypatch.setattr(controller_module, "save_config", self._save)
        self.pipeline = Pipeline(settings or Settings(), runtime or Runtime())
        self.tray = FakeTray()
        self.window = FakeMainWindow(confirm_delete)
        self.controller = SettingsController(self.pipeline, self.tray, self.window)
        self.prepared = []
        monkeypatch.setattr(self.controller, "_prepare_async", self.prepared.append)

    def _save(self, config):
        self.saved = dict(config)
        self.stored = dict(config)


@pytest.fixture
def harness(monkeypatch):
    return Harness(monkeypatch)


def test_activating_whisper_switches_at_once_and_persists_it(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(active_engine="nemotron", nemotron=object()))
    h.controller.activate_asr_engine("whisper")
    assert h.pipeline.runtime.active_engine == "whisper"
    assert h.saved["asr_engine"] == "whisper"
    assert ("radio", "whisper") in h.window.log


def test_activating_a_loaded_engine_switches_without_a_download(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(nemotron=object()))
    h.controller.activate_asr_engine("nemotron")
    assert h.pipeline.runtime.active_engine == "nemotron"
    assert h.tray.statuses[-1] == "Ready (Nemotron)"
    assert h.prepared == []


def test_activating_an_engine_that_is_not_loaded_starts_a_background_load(harness):
    harness.controller.activate_asr_engine("qwen3")
    assert harness.prepared == ["qwen3"]
    assert harness.pipeline.runtime.active_engine == "whisper"  # unchanged until it finishes loading
    assert ("refresh", "qwen3", True) in harness.window.log  # the UI shows it as busy


def test_activating_the_engine_already_active_does_nothing(harness):
    harness.controller.activate_asr_engine("whisper")
    assert harness.saved == {}
    assert harness.window.log == []


def test_an_unknown_engine_id_changes_nothing(harness):
    """It used to be written to config.json before being rejected, leaving a value the
    next launch could not load."""
    harness.controller.activate_asr_engine("whisper-xl")
    assert harness.pipeline.runtime.active_engine == "whisper"
    assert harness.saved == {}
    assert harness.prepared == []


def test_nothing_switches_while_a_take_is_in_flight(monkeypatch):
    h = Harness(monkeypatch)
    monkeypatch.setattr(h.pipeline, "is_busy", lambda: True)
    h.controller.activate_asr_engine("qwen3")
    h.controller.set_whisper_model_size("small")
    h.controller.apply_settings(dict(DEFAULT_CONFIG))
    assert h.saved == {}
    assert h.prepared == []


def test_deleting_the_active_engine_falls_back_to_whisper(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(active_engine="nemotron", nemotron=object()))
    deleted = []
    monkeypatch.setattr(controller_module.asr_catalog, "delete_model", deleted.append)

    h.controller.delete_model("nemotron")

    assert deleted == ["nemotron"]
    assert h.pipeline.runtime.nemotron is None
    assert h.pipeline.runtime.active_engine == "whisper"
    assert h.saved["asr_engine"] == "whisper"
    assert ("refresh", "whisper", False) in h.window.log


def test_deleting_an_inactive_engine_leaves_the_active_one_alone(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(active_engine="nemotron", nemotron=object(), qwen3=object()))
    monkeypatch.setattr(controller_module.asr_catalog, "delete_model", lambda engine: None)

    h.controller.delete_model("qwen3")

    assert h.pipeline.runtime.qwen3 is None
    assert h.pipeline.runtime.active_engine == "nemotron"
    assert h.saved == {}


def test_declining_the_delete_confirmation_deletes_nothing(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(qwen3=object()), confirm_delete=False)
    monkeypatch.setattr(
        controller_module.asr_catalog, "delete_model", lambda engine: pytest.fail("deleted after 'No'")
    )
    h.controller.delete_model("qwen3")
    assert h.pipeline.runtime.qwen3 is not None


def test_saving_the_dashboard_updates_the_live_settings_and_keeps_the_providers(monkeypatch):
    h = Harness(monkeypatch)
    h.stored["cleanup_providers"] = [OLLAMA]
    new_config = dict(
        DEFAULT_CONFIG, use_cleanup=True, cleanup_level="advanced", hotkey="ctrl+alt",
        active_cleanup_model_id="ollama::x", cleanup_providers=[],
    )

    h.controller.apply_settings(new_config)

    settings = h.pipeline.settings
    assert (settings.use_cleanup, settings.cleanup_level, settings.hotkey) == (True, "advanced", "ctrl+alt")
    assert settings.active_cleanup_model_id == "ollama::x"
    assert h.saved["hotkey"] == "ctrl+alt"
    assert h.saved["cleanup_providers"] == [OLLAMA]  # the Dashboard doesn't own this and must not wipe it


def test_saving_with_a_new_engine_selected_starts_loading_it(harness):
    harness.controller.apply_settings(dict(DEFAULT_CONFIG, asr_engine="nemotron"))
    assert harness.prepared == ["nemotron"]


def test_saving_the_engine_that_is_already_active_just_refreshes_the_status(monkeypatch):
    h = Harness(monkeypatch, runtime=Runtime(active_engine="nemotron", nemotron=object()))
    h.controller.apply_settings(dict(DEFAULT_CONFIG, asr_engine="nemotron"))
    assert h.prepared == []
    assert h.tray.statuses[-1] == "Ready"
    assert ("refresh", "nemotron", False) in h.window.log


def test_transliterate_mode_turns_the_forced_transliteration_flag_on(harness):
    harness.controller.apply_cleanup_transformation("transliterate", "en")
    assert harness.pipeline.settings.force_english_transliteration is True
    harness.controller.apply_cleanup_transformation("translate", "fr")
    assert harness.pipeline.settings.force_english_transliteration is False
    assert harness.pipeline.settings.translation_target_language == "fr"
    assert harness.saved["cleanup_output_mode"] == "translate"


def test_a_models_tab_change_reloads_the_cache_and_refreshes_the_dashboard(harness):
    harness.stored.update(cleanup_providers=[OLLAMA], cleanup_models=[LOCAL_MODEL],
                          active_cleanup_model_id=LOCAL_MODEL["id"])
    harness.controller.on_cleanup_changed()
    assert harness.pipeline.settings.cleanup_models == [LOCAL_MODEL]
    assert ("models", LOCAL_MODEL["id"]) in harness.window.log


# --- loading an engine in the background ------------------------------------------


class ImmediateThread:
    def __init__(self, target, daemon=None):
        self._target = target

    def start(self):
        self._target()


class FakeEngineModule:
    """Stands in for asr.qwen_asr: not downloaded yet, then loads (or fails to)."""

    def __init__(self, fail=False):
        self.fail, self.downloads = fail, 0

    def is_downloaded(self):
        return self.downloads > 0

    def download(self):
        self.downloads += 1
        if self.fail:
            raise OSError("network unreachable")

    def Qwen3AsrEngine(self):
        return "loaded-engine"


def prepare(monkeypatch, module):
    h = Harness(monkeypatch)
    h.controller._prepare_async = type(h.controller)._prepare_async.__get__(h.controller)
    spec = controller_module._ENGINES["qwen3"]._replace(module=module)
    monkeypatch.setitem(controller_module._ENGINES, "qwen3", spec)
    monkeypatch.setattr(controller_module.threading, "Thread", ImmediateThread)
    h.controller._prepare_async("qwen3")
    return h


def test_a_successful_background_load_makes_the_engine_active(monkeypatch):
    module = FakeEngineModule()
    h = prepare(monkeypatch, module)
    assert module.downloads == 1
    assert h.pipeline.runtime.qwen3 == "loaded-engine"
    assert h.pipeline.runtime.active_engine == "qwen3"
    assert h.tray.statuses[-1] == "Ready (Qwen3-ASR)"
    assert ("engine_status_refresh_requested", ("qwen3", False)) in h.window.log


def test_a_failed_download_stays_on_whisper_and_says_so(monkeypatch):
    h = prepare(monkeypatch, FakeEngineModule(fail=True))
    assert h.pipeline.runtime.qwen3 is None
    assert h.pipeline.runtime.active_engine == "whisper"
    assert h.tray.statuses[-1] == "Ready (Qwen3-ASR setup failed)"
    assert ("engine_status_refresh_requested", ("whisper", False)) in h.window.log
    assert h.controller._prepping is False  # a later attempt is not blocked
