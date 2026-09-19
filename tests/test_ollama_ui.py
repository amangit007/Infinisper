"""What the user sees for a local model: the pipeline badge, the keep-loaded control, and the
notes in the Add model dialog when Ollama isn't ready."""

import pytest
from PySide6.QtWidgets import QApplication

from cleanup.catalog import OllamaStatus
from ui.dialogs import model_dialog
from ui.tabs import dashboard_tab
from ui.tabs.dashboard_tab import DashboardTab

OLLAMA_MODEL = {
    "id": "ollama::ollama/gemma4:e4b", "provider_id": "ollama", "model": "ollama/gemma4:e4b",
    "display_name": "gemma4:e4b", "supports_audio": False,
}
GEMINI_MODEL = {
    "id": "gemini::gemini/flash", "provider_id": "gemini", "model": "gemini/flash",
    "display_name": "Gemini Flash", "supports_audio": True,
}
PROVIDERS = [
    {"id": "ollama", "display_name": "Ollama (local)", "base_url": "http://127.0.0.1:11434"},
    {"id": "gemini", "display_name": "Google Gemini", "base_url": None},
]


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


def make_dashboard(qt_app, monkeypatch, active_id, keep_alive="30m"):
    monkeypatch.setattr(dashboard_tab, "load_config", lambda: {
        "cleanup_providers": PROVIDERS, "cleanup_models": [OLLAMA_MODEL, GEMINI_MODEL], "model_size": "base",
    })
    return DashboardTab({
        "use_asr": True, "use_cleanup": True, "asr_engine": "whisper",
        "cleanup_models": [OLLAMA_MODEL, GEMINI_MODEL], "active_cleanup_model_id": active_id,
        "ollama_keep_alive": keep_alive,
    })


def test_a_local_model_is_labelled_local_not_cloud(qt_app, monkeypatch):
    tab = make_dashboard(qt_app, monkeypatch, OLLAMA_MODEL["id"])
    assert tab.pipeline._cleanup_is_local is True
    assert "nothing leaves this machine" in tab._route_label.text()


def test_a_hosted_model_is_still_labelled_cloud(qt_app, monkeypatch):
    tab = make_dashboard(qt_app, monkeypatch, GEMINI_MODEL["id"])
    assert tab.pipeline._cleanup_is_local is False
    assert "nothing leaves this machine" not in tab._route_label.text()


def test_keep_loaded_control_only_appears_for_a_local_model(qt_app, monkeypatch):
    tab = make_dashboard(qt_app, monkeypatch, OLLAMA_MODEL["id"])
    assert not tab._keep_loaded_col.isHidden()

    tab.cleanup_model_combo.setCurrentIndex(tab.cleanup_model_combo.findData(GEMINI_MODEL["id"]))
    assert tab._keep_loaded_col.isHidden()


@pytest.mark.parametrize("saved", [None, "30m", "2h", "-1"])
def test_keep_alive_choice_round_trips(qt_app, monkeypatch, saved):
    tab = make_dashboard(qt_app, monkeypatch, OLLAMA_MODEL["id"], keep_alive=saved)
    assert tab.keep_alive_combo.currentData() == saved

    emitted = []
    tab.settings_saved.connect(emitted.append)
    tab._initializing = False
    tab._emit_settings_changed()
    assert emitted[-1]["ollama_keep_alive"] == saved


def _dialog(qt_app, monkeypatch, status):
    monkeypatch.setattr(model_dialog, "ollama_status", lambda url: status)
    return model_dialog.ModelDialog([PROVIDERS[0]])


def test_dialog_explains_when_ollama_is_not_running(qt_app, monkeypatch):
    dialog = _dialog(qt_app, monkeypatch, OllamaStatus(
        [], "Ollama isn't running at http://127.0.0.1:11434. Start it, or install it first.", show_install_link=True))
    assert not dialog.ollama_note.isHidden()
    assert "isn't running" in dialog.ollama_note.text()
    assert "ollama.com/download" in dialog.ollama_note.text()


def test_dialog_explains_when_ollama_has_no_models(qt_app, monkeypatch):
    dialog = _dialog(qt_app, monkeypatch, OllamaStatus([], "Ollama is running but has no models yet."))
    assert "no models" in dialog.ollama_note.text()
    assert "download" not in dialog.ollama_note.text()


def test_dialog_lists_installed_models_and_stays_quiet(qt_app, monkeypatch):
    dialog = _dialog(qt_app, monkeypatch, OllamaStatus(["gemma4:e4b", "qwen2.5:0.5b"]))
    assert dialog.ollama_note.isHidden()
    assert [dialog.model_combo.itemText(i) for i in range(dialog.model_combo.count())] == ["gemma4:e4b", "qwen2.5:0.5b"]
