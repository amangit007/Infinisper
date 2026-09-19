import os
import sys
from pathlib import Path

_APP_NAME = "Infinisper"


def is_frozen() -> bool:
    """True if running as a compiled/packaged binary (e.g. PyInstaller)."""
    return getattr(sys, "frozen", False)


def get_bundle_dir() -> Path:
    """Directory containing bundled application assets and code.
    In development, this is the repository root.
    In PyInstaller frozen mode, this is sys._MEIPASS or executable directory.
    """
    if is_frozen():
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            return Path(meipass)
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_data_dir() -> Path:
    """Directory where user configuration, history, and models are stored.
    In development: returns repository root so existing tests & workflows work as-is.
    When packaged: returns %APPDATA%/Infinisper to ensure safe write permissions.
    """
    if is_frozen():
        appdata = os.environ.get("APPDATA")
        if appdata:
            base = Path(appdata)
        else:
            base = Path.home() / "AppData" / "Roaming"
        data_dir = base / _APP_NAME
        data_dir.mkdir(parents=True, exist_ok=True)
        return data_dir

    return Path(__file__).resolve().parent.parent


def get_config_path() -> Path:
    """Path to config.json."""
    return get_data_dir() / "config.json"


def get_history_path() -> Path:
    """Path to history.json."""
    return get_data_dir() / "history.json"


def get_models_dir() -> Path:
    """Directory for downloaded local models (Nemotron, Qwen3)."""
    models_dir = get_data_dir() / "models"
    models_dir.mkdir(parents=True, exist_ok=True)
    return models_dir


def get_asset_path(relative_name: str) -> Path:
    """Resolves an asset file from the bundled assets folder."""
    return get_bundle_dir() / "assets" / relative_name
