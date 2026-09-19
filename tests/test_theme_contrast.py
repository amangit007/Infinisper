"""The UI's colors, checked as numbers.

Two complaints about the first version of the UI -- "the light mode is too much white" and
"icons are dark even in dark mode" -- were both really contrast problems. These tests pin the
fixes so a later tweak to a color can't quietly bring them back.

Ratios are WCAG 2.x: 4.5:1 is the AA minimum for text, 3:1 for the parts of a control that
have to be seen.
"""

import re
from pathlib import Path

import pytest

from ui.assets.mark import BRAND_HEX, FULL_MARK_SVG
from ui.theme import DARK, LIGHT, THEMES, build_stylesheet

TEXT_TOKENS = ["text", "text2", "dim", "accent", "good", "warn"]
SURFACES = ["panel", "panel2", "panel3", "bg"]
UI_DIR = Path(__file__).resolve().parent.parent / "ui"
ROOT = UI_DIR.parent


def _rgb(color: str) -> tuple[int, int, int]:
    if color.startswith("rgba"):
        return tuple(int(v) for v in re.findall(r"\d+", color)[:3])
    color = color.lstrip("#")
    return tuple(int(color[i:i + 2], 16) for i in (0, 2, 4))


def _luminance(color: str) -> float:
    def channel(v):
        v /= 255
        return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4

    r, g, b = (channel(v) for v in _rgb(color))
    return 0.2126 * r + 0.7152 * g + 0.0722 * b


def contrast(a: str, b: str) -> float:
    hi, lo = sorted((_luminance(a), _luminance(b)), reverse=True)
    return (hi + 0.05) / (lo + 0.05)


def over(rgba: str, background: str) -> str:
    """The solid color you see when a translucent `rgba(...)` sits on `background`."""
    r, g, b, a = (int(v) for v in re.findall(r"\d+", rgba)[:4])
    br, bg, bb = _rgb(background)
    alpha = a / 255
    return "#%02x%02x%02x" % (round(r * alpha + br * (1 - alpha)),
                              round(g * alpha + bg * (1 - alpha)),
                              round(b * alpha + bb * (1 - alpha)))


# --- text ----------------------------------------------------------------------------

@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("surface", SURFACES)
@pytest.mark.parametrize("token", TEXT_TOKENS)
def test_text_is_readable_on_every_surface(theme, surface, token):
    tokens = THEMES[theme]
    ratio = contrast(tokens[token], tokens[surface])
    assert ratio >= 4.5, f"{theme}: {token} on {surface} is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
@pytest.mark.parametrize("token", ["accent", "good", "warn"])
def test_badge_text_is_readable_on_its_tinted_background(theme, token):
    tokens = THEMES[theme]
    tint = over(tokens[f"{token}_soft"], tokens["panel"])
    ratio = contrast(tokens[token], tint)
    assert ratio >= 4.5, f"{theme}: {token} badge is {ratio:.2f}:1"


@pytest.mark.parametrize("theme", THEMES)
def test_danger_text_is_readable(theme):
    tokens = THEMES[theme]
    for surface in ("panel", "panel3"):
        assert contrast(tokens["danger_text"], tokens[surface]) >= 4.5


# --- surfaces and controls -----------------------------------------------------------

def test_light_cards_stand_out_from_the_background():
    # Was 1.14:1 -- white cards on a background that was almost white.
    assert contrast(LIGHT["panel"], LIGHT["bg"]) >= 1.2


def test_dark_cards_stand_out_from_the_background():
    assert contrast(DARK["panel"], DARK["bg"]) >= 1.1


@pytest.mark.parametrize("theme", THEMES)
def test_card_borders_are_visible(theme):
    tokens = THEMES[theme]
    assert contrast(tokens["line"], tokens["panel"]) >= 1.3
    assert contrast(tokens["line2"], tokens["panel"]) >= 1.5


@pytest.mark.parametrize("theme", THEMES)
def test_switch_track_is_visible_when_off(theme):
    tokens = THEMES[theme]
    assert contrast(tokens["toggle_off"], tokens["panel"]) >= 3.0
    assert contrast("#ffffff", tokens["toggle_off"]) >= 3.0  # the white knob stays visible on it


# --- the brand color -----------------------------------------------------------------

@pytest.mark.parametrize("name,background", [
    ("GitHub dark", "#0d1117"),
    ("GitHub light", "#ffffff"),
    ("dark taskbar", "#202020"),
    ("light taskbar", "#f3f3f3"),
])
def test_brand_blue_is_visible_on_light_and_dark_backgrounds(name, background):
    # The old logo blue (#14588b) was 2.5:1 on GitHub dark.
    assert contrast(BRAND_HEX, background) >= 3.0, name


def test_readme_logo_is_the_apps_own_mark_in_the_brand_color():
    """assets/logo.svg used to be hand-copied and had drifted to a different blue than the app.
    Regenerate it with:
        python -c "from pathlib import Path; from ui.assets.mark import *; \
Path('assets/logo.svg').write_text(FULL_MARK_SVG.format(color=BRAND_HEX) + '\\n')"
    """
    logo = (ROOT / "assets" / "logo.svg").read_text(encoding="utf-8")
    assert logo.strip() == FULL_MARK_SVG.format(color=BRAND_HEX).strip()


# --- no stray colors -----------------------------------------------------------------

def test_colors_live_in_the_theme_not_in_widgets():
    """A hex color typed into a widget can't follow the theme -- that is how a light-mode
    window ended up with a dark-mode toggle. Widgets take colors from ui/theme.py."""
    allowed = {UI_DIR / "theme.py", UI_DIR / "assets" / "mark.py"}
    offenders = []
    for path in UI_DIR.rglob("*.py"):
        if path in allowed:
            continue
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.lstrip().startswith("#"):
                continue  # a comment, not a color the widget uses
            if re.search(r"[\"']#[0-9a-fA-F]{3,8}[\"']", line):
                offenders.append(f"{path.relative_to(ROOT)}:{number}: {line.strip()}")
    assert not offenders, "hex colors outside ui/theme.py:\n" + "\n".join(offenders)


@pytest.mark.parametrize("theme", THEMES)
def test_stylesheet_is_fully_filled_in_for_both_themes(theme):
    qss = build_stylesheet(THEMES[theme])
    assert THEMES[theme]["panel"] in qss
    assert "None" not in qss
    assert "{t[" not in qss and "t['" not in qss
