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
