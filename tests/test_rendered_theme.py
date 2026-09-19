"""Renders real widgets and looks at their pixels.

The contrast tests check the color tokens. These check the tokens actually reach the screen:
in dark mode several dashboard controls used to come out as white native-Windows boxes because
the stylesheet only knew about combo boxes that had been given an object name.
"""

import pytest
from PySide6.QtWidgets import QApplication, QVBoxLayout, QWidget

from ui.tabs import dashboard_tab
from ui.tabs.dashboard_tab import DashboardTab
from ui.theme import THEMES, build_stylesheet

MODEL = {"id": "ollama::ollama/gemma4:e4b", "provider_id": "ollama", "model": "ollama/gemma4:e4b",
         "display_name": "gemma4:e4b", "supports_audio": False}
PROVIDERS = [{"id": "ollama", "display_name": "Ollama (local)", "base_url": "http://127.0.0.1:11434"}]


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


def _rendered_dashboard(qt_app, monkeypatch, theme):
    monkeypatch.setattr(dashboard_tab, "load_config", lambda: {
        "cleanup_providers": PROVIDERS, "cleanup_models": [MODEL], "model_size": "base"})
    tab = DashboardTab({"use_asr": True, "use_cleanup": True, "asr_engine": "nemotron",
                        "cleanup_models": [MODEL], "active_cleanup_model_id": MODEL["id"]})
    tab.apply_theme(THEMES[theme])
    root = QWidget()
    root.setObjectName("RootFrame")
    QVBoxLayout(root).addWidget(tab)
    root.setStyleSheet(build_stylesheet(THEMES[theme]))
    root.resize(1300, 900)
    root.show()
    qt_app.processEvents()
    return root, tab


def _color_near(pixel, hex_color, tolerance=6):
    target = tuple(int(hex_color.lstrip("#")[i:i + 2], 16) for i in (0, 2, 4))
    return all(abs(a - b) <= tolerance for a, b in zip((pixel.red(), pixel.green(), pixel.blue()), target))


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("control", ["device_combo", "hotkey_combo", "cleanup_model_combo", "timeout_spinbox", "keep_alive_combo"])
def test_dashboard_controls_are_drawn_in_the_current_theme(qt_app, monkeypatch, theme, control):
    root, tab = _rendered_dashboard(qt_app, monkeypatch, theme)
    widget = getattr(tab, control)
    image = widget.grab().toImage()
    pixel = image.pixelColor(5, image.height() // 2)  # inside the border, left of the text
    assert _color_near(pixel, THEMES[theme]["panel2"]), (
        f"{control} in {theme} mode is {pixel.name()}, expected {THEMES[theme]['panel2']}")
    root.close()


@pytest.mark.parametrize("theme", THEMES)
def test_radio_buttons_are_drawn_in_the_current_theme(qt_app, monkeypatch, theme):
    root, tab = _rendered_dashboard(qt_app, monkeypatch, theme)
    checked = next(row.radio for row in tab.rows.values() if row.radio.isChecked())
    image = checked.grab().toImage()
    center = image.pixelColor(image.width() // 2, image.height() // 2)
    # The checked radio's dot is the accent color, not the native black/white.
    assert _color_near(center, THEMES[theme]["accent"], tolerance=40) or center.blue() > center.red() + 20, center.name()
    root.close()
