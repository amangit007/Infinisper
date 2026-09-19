import sys
from unittest.mock import patch

import pytest
from PySide6.QtWidgets import QApplication

from history.store import HistoryStore
from ui.assets.mark import BRAND_ACCENT_DARK_HEX, mark_icon
from ui.main_window import MainWindow
from utils.windows import (
    HOTKEY_PRESETS,
    VK_CONTROL,
    VK_F8,
    VK_LWIN,
    VK_MENU,
    VK_RWIN,
    is_hotkey_pressed,
    set_app_user_model_id,
)


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
        "use_cleanup": False,
        "cleanup_level": "fast",
        "cleanup_timeout_seconds": 10,
        "fallback_to_whisper": True,
        "cleanup_providers": [],
        "cleanup_models": [],
        "active_cleanup_model_id": None,
        "force_english_transliteration": False,
        "dictation_language": "en",
        "custom_words": [],
    }
    win = MainWindow(config, store)
    assert not win.windowIcon().isNull()
    win.close()


def test_is_hotkey_pressed_windows_success():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            def mock_get_async_key_state(code):
                if code in (VK_CONTROL, VK_LWIN):
                    return 0x8000
                return 0

            mock_windll.user32.GetAsyncKeyState.side_effect = mock_get_async_key_state
            assert is_hotkey_pressed() is True


def test_is_hotkey_pressed_right_windows_key():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            def mock_get_async_key_state(code):
                if code in (VK_CONTROL, VK_RWIN):
                    return 0x8000
                return 0

            mock_windll.user32.GetAsyncKeyState.side_effect = mock_get_async_key_state
            assert is_hotkey_pressed() is True


def test_is_hotkey_pressed_only_one_key():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            # Only Ctrl pressed
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code == VK_CONTROL else 0
            assert is_hotkey_pressed() is False

            # Only Win pressed
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code == VK_LWIN else 0
            assert is_hotkey_pressed() is False


def test_is_hotkey_pressed_neither_pressed():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.user32.GetAsyncKeyState.return_value = 0
            assert is_hotkey_pressed() is False


def test_is_hotkey_pressed_non_windows_fallback():
    with patch("sys.platform", "linux"):
        with patch("keyboard.is_pressed") as mock_is_pressed:
            mock_is_pressed.side_effect = lambda key: key in ("ctrl", "windows")
            assert is_hotkey_pressed() is True

            mock_is_pressed.side_effect = lambda key: key == "ctrl"
            assert is_hotkey_pressed() is False


def test_is_hotkey_pressed_exception_handling():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.user32.GetAsyncKeyState.side_effect = RuntimeError("Mock error")
            with patch("keyboard.is_pressed", side_effect=RuntimeError("Keyboard fallback error")):
                assert is_hotkey_pressed() is False


def test_is_hotkey_pressed_custom_preset_ctrl_alt():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code in (VK_CONTROL, VK_MENU) else 0
            assert is_hotkey_pressed("ctrl+alt") is True
            # Fails if only Ctrl is held
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code == VK_CONTROL else 0
            assert is_hotkey_pressed("ctrl+alt") is False


def test_is_hotkey_pressed_custom_preset_f8():
    with patch("sys.platform", "win32"):
        with patch("ctypes.windll", create=True) as mock_windll:
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0x8000 if code == VK_F8 else 0
            assert is_hotkey_pressed("f8") is True
            mock_windll.user32.GetAsyncKeyState.side_effect = lambda code: 0
            assert is_hotkey_pressed("f8") is False


def test_hotkey_presets_structure():
    assert "ctrl+win" in HOTKEY_PRESETS
    assert "ctrl+alt" in HOTKEY_PRESETS
    for preset_id, info in HOTKEY_PRESETS.items():
        assert "display" in info
        assert "vk_groups" in info
        assert "keyboard_names" in info
        assert len(info["vk_groups"]) > 0

