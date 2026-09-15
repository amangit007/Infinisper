import sys
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from history.store import HistoryStore
from ui.assets.mark import BRAND_ACCENT_DARK_HEX, mark_icon
from ui.main_window import MainWindow
from utils.windows import set_app_user_model_id


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if app is None:
        app = QApplication([])
    return app


def test_set_app_user_model_id_windows():
    if sys.platform == "win32":
        result = set_app_user_model_id("infinisper.dictation.test")
        assert result is True


def test_set_app_user_model_id_non_windows():
    with patch("sys.platform", "linux"):
        result = set_app_user_model_id("infinisper.dictation.test")
        assert result is False


def test_set_app_user_model_id_exception_handling():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.shell32.SetCurrentProcessExplicitAppUserModelID.side_effect = RuntimeError("Mock error")
            result = set_app_user_model_id("infinisper.dictation.test")
            assert result is False


def test_mark_icon_sizes(qapp):
    icon = mark_icon(BRAND_ACCENT_DARK_HEX)
    assert not icon.isNull()
    sizes = [s.width() for s in icon.availableSizes()]
    for expected in (16, 24, 32, 48, 64, 128, 256):
        assert expected in sizes


def test_main_window_has_icon(qapp):
    store = HistoryStore()
    config = {
        "model_size": "base.en",
        "input_device": None,
        "use_asr": False,
        "asr_engine": "whisper",
        "use_multimodal": False,
        "multimodal_level": "fast",
        "multimodal_timeout_seconds": 10,
        "fallback_to_whisper": True,
        "multimodal_providers": [],
        "multimodal_models": [],
        "active_multimodal_model_id": None,
        "force_english_transliteration": False,
        "dictation_language": "en",
        "custom_words": [],
    }
    win = MainWindow(config, store)
    assert not win.windowIcon().isNull()
    win.close()
