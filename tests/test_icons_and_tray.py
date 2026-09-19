"""Icon buttons follow the theme through the stylesheet; the tray follows the Windows taskbar."""

from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtWidgets import QApplication, QWidget

from ui import tray
from ui.assets.icons import icon_names, icon_pixmap, icon_svg
from ui.theme import DARK, LIGHT, THEMES, build_stylesheet
from ui.widgets.icon_button import IconButton
from utils import windows


@pytest.fixture(scope="session")
def qt_app():
    return QApplication.instance() or QApplication([])


# --- icons ---------------------------------------------------------------------------

@pytest.mark.parametrize("name", icon_names())
def test_every_icon_renders_something(qt_app, name):
    image = icon_pixmap(name, "#ff0000", 16).toImage()
    opaque = sum(1 for x in range(image.width()) for y in range(image.height()) if image.pixelColor(x, y).alpha() > 0)
    assert opaque > 10, f"{name} rendered blank"


def test_icon_takes_the_requested_color():
    assert 'stroke="#123456"' in icon_svg("x", "#123456")


def test_the_icons_that_replaced_text_glyphs_exist():
    # ✎ × □ ✕ ◑ ⚠️ and the eye emoji
    assert {"pencil", "x", "square", "minus", "contrast", "triangle-alert", "eye", "eye-off"} <= set(icon_names())


# --- icon buttons follow the stylesheet ----------------------------------------------

def _button_in_theme(theme, object_name):
    parent = QWidget()
    parent.setObjectName("RootFrame")
    button = IconButton("x", parent=parent)
    button.setObjectName(object_name)
    parent.setStyleSheet(build_stylesheet(THEMES[theme]))
    button.ensurePolished()
    return parent, button


@pytest.mark.parametrize("theme", THEMES)
def test_icon_color_comes_from_the_stylesheet(qt_app, theme):
    parent, button = _button_in_theme(theme, "GhostGlyphButton")
    assert button.iconColor.name() == THEMES[theme]["text2"]
    assert button.hoverIconColor.name() == THEMES[theme]["text"]


def test_a_button_made_after_the_theme_was_applied_is_still_themed(qt_app):
    """Model cards are created on demand, long after the theme was applied -- the case that
    an apply_theme() walk over existing widgets can never reach."""
    parent = QWidget()
    parent.setObjectName("RootFrame")
    parent.setStyleSheet(build_stylesheet(LIGHT))
    late = IconButton("pencil", parent=parent)
    late.setObjectName("GhostGlyphButton")
    late.ensurePolished()
    assert late.iconColor.name() == LIGHT["text2"]


def test_switching_theme_recolors_existing_buttons(qt_app):
    parent, button = _button_in_theme("dark", "GhostGlyphButton")
    assert button.iconColor.name() == DARK["text2"]
    parent.setStyleSheet(build_stylesheet(LIGHT))
    button.ensurePolished()
    assert button.iconColor.name() == LIGHT["text2"]


def test_delete_icon_turns_red_on_hover_and_close_turns_white(qt_app):
    _, delete = _button_in_theme("dark", "DangerGhostGlyphButton")
    assert delete.hoverIconColor.name() == DARK["danger_text"]
    _, close = _button_in_theme("dark", "TitleBarCloseButton")
    assert close.hoverIconColor.name() == "#ffffff"


# --- the tray follows the taskbar ----------------------------------------------------

def test_tray_mark_is_dark_on_a_light_taskbar_and_light_on_a_dark_one():
    assert tray.tray_mark_color(light_taskbar=True) == LIGHT["text"]
    assert tray.tray_mark_color(light_taskbar=False) == DARK["text"]


def test_tray_mark_never_matches_its_taskbar():
    from tests.test_theme_contrast import contrast

    assert contrast(tray.tray_mark_color(True), "#f3f3f3") >= 7   # was 1.08:1
    assert contrast(tray.tray_mark_color(False), "#202020") >= 7


def _registry(value=None, error=None):
    key = MagicMock()
    key.__enter__.return_value = key
    fake = MagicMock()
    fake.HKEY_CURRENT_USER = object()
    fake.OpenKey.return_value = key
    if error:
        fake.QueryValueEx.side_effect = error
    else:
        fake.QueryValueEx.return_value = (value, 4)
    return fake


@pytest.mark.parametrize("stored,expected", [(1, True), (0, False)])
def test_reads_the_taskbar_theme_from_the_registry(stored, expected):
    with patch("sys.platform", "win32"), patch.dict("sys.modules", {"winreg": _registry(stored)}):
        assert windows.system_uses_light_theme() is expected


def test_defaults_to_dark_when_the_setting_is_missing():
    with patch("sys.platform", "win32"), patch.dict("sys.modules", {"winreg": _registry(error=FileNotFoundError())}):
        assert windows.system_uses_light_theme() is False


def test_defaults_to_dark_off_windows():
    with patch("sys.platform", "linux"):
        assert windows.system_uses_light_theme() is False


def test_tray_icon_is_redrawn_when_the_taskbar_theme_changes(qt_app):
    with patch.object(tray, "system_uses_light_theme", return_value=False):
        icon = tray.TrayIcon()
    icon._theme_timer.stop()

    seen = []
    icon._icon.setIcon = lambda new_icon: seen.append(new_icon)

    with patch.object(tray, "system_uses_light_theme", return_value=False):
        icon._refresh_icon_for_taskbar()
    assert seen == []  # nothing changed, nothing redrawn

    with patch.object(tray, "system_uses_light_theme", return_value=True):
        icon._refresh_icon_for_taskbar()
    assert len(seen) == 1
