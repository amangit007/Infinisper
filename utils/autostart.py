import os
import sys
import winreg

_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
_APP_NAME = "Infinisper"


def is_autostart_enabled() -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_READ) as key:
            winreg.QueryValueEx(key, _APP_NAME)
            return True
    except (FileNotFoundError, OSError):
        return False


def set_autostart(enabled: bool) -> bool:
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, _RUN_KEY, 0, winreg.KEY_SET_VALUE) as key:
            if enabled:
                # If packaged as exe, use executable path; otherwise pythonw running main.py
                if getattr(sys, "frozen", False):
                    cmd = f'"{sys.executable}"'
                else:
                    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "main.py"))
                    pythonw = sys.executable.replace("python.exe", "pythonw.exe")
                    cmd = f'"{pythonw}" "{main_py}"'
                winreg.SetValueEx(key, _APP_NAME, 0, winreg.REG_SZ, cmd)
            else:
                try:
                    winreg.DeleteValue(key, _APP_NAME)
                except FileNotFoundError:
                    pass
        return True
    except OSError:
        return False
