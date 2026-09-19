"""Windows shell and OS integration utilities."""

import sys


def set_app_user_model_id(app_id: str = "infinisper.dictation.desktop") -> bool:
    """Set the explicit Application User Model ID (AUMID) for the current process on Windows.

    Without an explicit AUMID, Windows groups the application under generic
    python.exe/pythonw.exe and displays the default Python script icon on the
    taskbar instead of the application's custom window icon.
    """
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        res = ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(app_id)
        return res == 0
    except Exception:
        return False


def system_uses_light_theme() -> bool:
    """True when the Windows taskbar and tray are light.

    This is a separate setting from the app's own light/dark switch, and from Windows'
    "app mode": someone can run a dark taskbar with light apps, or the reverse. A tray icon
    has to match the taskbar it sits on, so read that setting directly. Defaults to dark
    (the Windows default) if the setting can't be read.
    """
    if sys.platform != "win32":
        return False
    try:
        import winreg

        with winreg.OpenKey(
            winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
        ) as key:
            return bool(winreg.QueryValueEx(key, "SystemUsesLightTheme")[0])
    except OSError:
        return False


VK_CONTROL = 0x11
VK_RCONTROL = 0xA3
VK_MENU = 0x12  # Alt key
VK_SHIFT = 0x10
VK_LWIN = 0x5B
VK_RWIN = 0x5C
VK_F8 = 0x77
VK_F9 = 0x78
VK_F12 = 0x7B

HOTKEY_PRESETS = {
    "ctrl+win": {
        "display": "Ctrl + Win",
        "description": "Default — conflict-free, holds without Start menu opening",
        "vk_groups": [(VK_CONTROL,), (VK_LWIN, VK_RWIN)],
        "keyboard_names": ["ctrl", "windows"],
    },
    "ctrl+alt": {
        "display": "Ctrl + Alt",
        "description": "Universal modifier pair, easy thumb-and-finger hold",
        "vk_groups": [(VK_CONTROL,), (VK_MENU,)],
        "keyboard_names": ["ctrl", "alt"],
    },
    "ctrl+shift": {
        "display": "Ctrl + Shift",
        "description": "Classic combo, quick to press on left hand",
        "vk_groups": [(VK_CONTROL,), (VK_SHIFT,)],
        "keyboard_names": ["ctrl", "shift"],
    },
    "alt+shift": {
        "display": "Alt + Shift",
        "description": "Accessible adjacent keys",
        "vk_groups": [(VK_MENU,), (VK_SHIFT,)],
        "keyboard_names": ["alt", "shift"],
    },
    "right_ctrl": {
        "display": "Right Ctrl",
        "description": "Single-key push-to-talk using right hand",
        "vk_groups": [(VK_RCONTROL,)],
        "keyboard_names": ["right ctrl"],
    },
    "f8": {
        "display": "F8",
        "description": "Single function key, rarely assigned in editors",
        "vk_groups": [(VK_F8,)],
        "keyboard_names": ["f8"],
    },
    "f9": {
        "display": "F9",
        "description": "Single function key push-to-talk",
        "vk_groups": [(VK_F9,)],
        "keyboard_names": ["f9"],
    },
    "f12": {
        "display": "F12",
        "description": "Single function key push-to-talk",
        "vk_groups": [(VK_F12,)],
        "keyboard_names": ["f12"],
    },
}


def is_hotkey_pressed(hotkey_id: str = "ctrl+win") -> bool:
    """Return True if the configured hotkey combination is physically held down.

    Uses Windows GetAsyncKeyState to query hardware key state directly without
    installing a low-level keyboard hook (WH_KEYBOARD_LL). This avoids OS
    timeouts (LowLevelHooksTimeout), silent hook removal by Windows, and stuck
    modifier keys. Falls back to the keyboard library on non-Windows platforms.
    """
    preset = HOTKEY_PRESETS.get(hotkey_id, HOTKEY_PRESETS["ctrl+win"])

    if sys.platform == "win32":
        try:
            import ctypes

            user32 = ctypes.windll.user32
            # Each entry in vk_groups represents a required logical key;
            # tuples represent alternatives (e.g. (VK_LWIN, VK_RWIN) means either Left or Right Win).
            for group in preset["vk_groups"]:
                if not any(bool(user32.GetAsyncKeyState(vk) & 0x8000) for vk in group):
                    return False
            return True
        except Exception:
            pass

    try:
        import keyboard

        return all(keyboard.is_pressed(name) for name in preset.get("keyboard_names", []))
    except Exception:
        return False
