"""Color tokens and QSS assembly for the Infinisper UI."""

import math

UI_FONT_FAMILY = '"Segoe UI", "Helvetica Neue", Arial, sans-serif'
MONO_FONT_FAMILY = '"Cascadia Mono", Consolas, monospace'


def oklch_to_hex(l: float, c: float, h_deg: float) -> str:
    """Convert an OKLCh color (lightness 0..1, chroma, hue in degrees) to '#rrggbb'."""
    r, g, b = _oklch_to_srgb(l, c, h_deg)
    return f"#{round(r * 255):02x}{round(g * 255):02x}{round(b * 255):02x}"


def oklch_to_rgba(l: float, c: float, h_deg: float, alpha: float) -> str:
    """Convert an OKLCh color plus an alpha fraction (0..1) to a QSS 'rgba(r, g, b, a)' string."""
    r, g, b = _oklch_to_srgb(l, c, h_deg)
    return f"rgba({round(r * 255)}, {round(g * 255)}, {round(b * 255)}, {round(alpha * 255)})"


def _oklch_to_srgb(l: float, c: float, h_deg: float) -> tuple[float, float, float]:
    h_rad = math.radians(h_deg)
    a = c * math.cos(h_rad)
    b = c * math.sin(h_rad)

    l_ = l + 0.3963377774 * a + 0.2158037573 * b
    m_ = l - 0.1055613458 * a - 0.0638541728 * b
    s_ = l - 0.0894841775 * a - 1.2914855480 * b

    l3, m3, s3 = l_**3, m_**3, s_**3

    lin_r = +4.0767416621 * l3 - 3.3077115913 * m3 + 0.2309699292 * s3
    lin_g = -1.2684380046 * l3 + 2.6097574011 * m3 - 0.3413193965 * s3
    lin_b = -0.0041960863 * l3 - 0.7034186147 * m3 + 1.7076147010 * s3

    return tuple(_linear_to_srgb(v) for v in (lin_r, lin_g, lin_b))


def _linear_to_srgb(v: float) -> float:
    v = min(1.0, max(0.0, v))
    if v <= 0.0031308:
        v = 12.92 * v
    else:
        v = 1.055 * (v ** (1 / 2.4)) - 0.055
    return min(1.0, max(0.0, v))


# Every text color below is held to WCAG AA (4.5:1) against every surface it can sit on, in
# both themes -- tests/test_theme_contrast.py fails if a token drifts under that.
# "line2" and "toggle_off" are the non-text colors that must stay visible on a card.

DARK = {
    "bg": "#14161b",
    "panel": "#1e2127",
    "panel2": "#242830",
    "panel3": "#2b3038",
    "line": "#343944",
    "line2": "#3f4550",
    "text": "#e8eaef",
    "text2": "#b3bac6",
    "dim": "#8f97a5",
    "accent": oklch_to_hex(0.72, 0.13, 255),
    "accent_soft": oklch_to_rgba(0.72, 0.13, 255, 0.14),
    "good": oklch_to_hex(0.74, 0.13, 155),
    "good_soft": oklch_to_rgba(0.74, 0.13, 155, 0.14),
    "warn": oklch_to_hex(0.79, 0.13, 80),
    "warn_soft": oklch_to_rgba(0.79, 0.13, 80, 0.14),
    "danger": oklch_to_hex(0.6, 0.17, 25),
    "danger_text": oklch_to_hex(0.7, 0.17, 25),
    "toggle_off": "#646c7a",
    "shadow": "#000000",
    "shadow_alpha": 130,
}

# Light mode used to be white cards on a barely-off-white background (1.14:1) with a
# secondary text color at 3.9:1. The background is now visibly tinted so the cards read as
# cards, and every text color has real margin over 4.5:1.
LIGHT = {
    "bg": "#e5e8ee",
    "panel": "#ffffff",
    "panel2": "#f3f5f8",
    "panel3": "#e8ebf0",
    "line": "#d8dde5",
    "line2": "#c1c8d2",
    "text": "#191c22",
    "text2": "#3f4653",
    "dim": "#586071",
    "accent": oklch_to_hex(0.50, 0.14, 255),
    "accent_soft": oklch_to_rgba(0.50, 0.14, 255, 0.10),
    "good": oklch_to_hex(0.48, 0.12, 155),
    "good_soft": oklch_to_rgba(0.48, 0.12, 155, 0.10),
    "warn": oklch_to_hex(0.50, 0.11, 65),
    "warn_soft": oklch_to_rgba(0.50, 0.11, 65, 0.12),
    "danger": oklch_to_hex(0.55, 0.19, 25),
    "danger_text": oklch_to_hex(0.50, 0.18, 25),
    "toggle_off": "#8b94a1",
    "shadow": "#141923",
    "shadow_alpha": 60,
}

# Hover fill for the window's close button; white text sits on it in both themes.
DANGER_STRONG = oklch_to_hex(0.55, 0.19, 25)

THEMES = {"dark": DARK, "light": LIGHT}


def build_stylesheet(tokens: dict, maximized: bool = False) -> str:
    """The app-wide QSS for the current theme. Applied at the MainWindow root so it cascades
    to every child; new sections are appended here stage by stage rather than scattering
    per-widget setStyleSheet calls.

    `maximized` is a plain Python branch, not a QSS dynamic-property selector
    (`[maximized="true"]`) -- this codebase hit real, repeated cases where Qt's dynamic
    property selectors didn't visually re-match after the property changed at runtime,
    even for rules that looked like they should trivially apply. Baking window-state
    into which literal string gets generated sidesteps that whole class of bug.
    """
    t = tokens
    root_frame_border = (
        "border: none; border-radius: 0px;"
        if maximized
        else f"border: 1px solid {t['line2']}; border-radius: 10px;"
    )
    return f"""
    QWidget#RootFrame {{
        background: {t['bg']};
        {root_frame_border}
    }}
    QWidget#RootFrame, QWidget#RootFrame QWidget {{
        color: {t['text']};
        font-family: {UI_FONT_FAMILY};
    }}
    QWidget#RootFrame QWidget:disabled {{
        color: {t['dim']};
    }}

    QWidget#TitleBar {{
        background: {t['panel']};
        border-top-left-radius: 10px;
        border-top-right-radius: 10px;
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#TitleBarLabel {{
        font-size: 12px;
        font-weight: 600;
        color: {t['text2']};
    }}
    QPushButton#TitleBarButton, QPushButton#TitleBarCloseButton {{
        background: transparent;
        border: none;
        border-radius: 5px;
        qproperty-iconColor: {t['text2']};
        qproperty-hoverIconColor: {t['text']};
    }}
    QPushButton#TitleBarButton:hover {{
        background: {t['panel3']};
    }}
    QPushButton#TitleBarCloseButton {{
        /* qproperty-* is applied when the widget is polished, not on :hover, so the white
           hover icon is set here; hoverIconColor only takes effect while hovered anyway. */
        qproperty-hoverIconColor: #ffffff;
    }}
    QPushButton#TitleBarCloseButton:hover {{
        background: {DANGER_STRONG};
    }}

    QWidget#Sidebar {{
        background: {t['panel']};
        border-right: 1px solid {t['line']};
    }}
    QLabel#SidebarBrand {{
        font-size: 17px;
        font-weight: 650;
        color: {t['text']};
    }}
    QLabel#SidebarSubtitle {{
        font-size: 11px;
        color: {t['dim']};
        font-family: {MONO_FONT_FAMILY};
    }}
    QWidget#SidebarMicPanel {{
        background: {t['panel2']};
        border: 1px solid {t['line']};
        border-radius: 9px;
    }}
    QLabel#SidebarMicLabel {{
        font-size: 10.5px;
        color: {t['dim']};
    }}
    QLabel#SidebarDbLabel {{
        font-size: 10.5px;
        color: {t['dim']};
        font-family: {MONO_FONT_FAMILY};
    }}
    QLabel#SidebarDeviceLabel {{
        font-size: 11px;
        color: {t['dim']};
    }}
    QLabel#SidebarStatusText {{
        font-size: 11.5px;
        color: {t['text2']};
    }}
    QLabel#SidebarHotkeyText {{
        font-size: 11px;
        color: {t['dim']};
        font-family: {MONO_FONT_FAMILY};
    }}
    QPushButton#ThemeToggleButton {{
        background: transparent;
        border: 1px solid {t['line2']};
        border-radius: 6px;
        qproperty-iconColor: {t['text2']};
        qproperty-hoverIconColor: {t['text']};
    }}
    QPushButton#ThemeToggleButton:hover {{
        border-color: {t['accent']};
    }}

    QWidget#DashboardHeader {{
        border-bottom: 1px solid {t['line']};
    }}
    QWidget#DashboardScrollViewport, QWidget#DashboardScrollContent {{
        background: {t['bg']};
    }}
    QLabel#PageTitle {{
        font-size: 15px;
        font-weight: 600;
        color: {t['text']};
    }}
    QLabel#PageHint {{
        font-size: 12px;
        color: {t['dim']};
    }}

    QWidget#Card {{
        border: 1px solid {t['line']};
        border-radius: 11px;
        background: {t['panel']};
    }}
    QWidget#CardHeader {{
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#CardTitle {{
        font-size: 12.5px;
        font-weight: 600;
        color: {t['text']};
    }}
    QLabel#CardSubtitle {{
        font-size: 11.5px;
        color: {t['dim']};
    }}
    QLabel#RouteLabel {{
        font-size: 11.5px;
        color: {t['dim']};
    }}
    QLabel#LegendLabel {{
        font-size: 10.5px;
        color: {t['dim']};
    }}
    QPushButton#FooterLink {{
        background: transparent;
        border: none;
        border-top: 1px solid {t['line']};
        color: {t['dim']};
        font-size: 11.5px;
        text-align: left;
        padding: 11px 18px;
    }}
    QPushButton#FooterLink:hover {{
        color: {t['accent']};
    }}
    /* Every combo box and spin box, not just the ones that happened to get an object name --
       the dashboard's shortcut, model and timeout controls had none, so in dark mode they
       fell back to the native white Windows look. */
    QComboBox, QSpinBox {{
        border: 1px solid {t['line2']};
        border-radius: 7px;
        background: {t['panel2']};
        color: {t['text']};
        padding: 3px 10px;
        font-size: 12px;
    }}
    QComboBox:hover, QSpinBox:hover {{
        border-color: {t['dim']};
    }}
    QComboBox:focus, QSpinBox:focus {{
        border-color: {t['accent']};
    }}
    QLabel#SectionLabel {{
        font-size: 11px;
        color: {t['dim']};
    }}
    QComboBox:disabled, QLabel#SectionLabel:disabled {{
        color: {t['dim']};
        background: {t['panel2']};
    }}

    QWidget#FallbackRow {{
        border: 1px solid {t['line']};
        border-radius: 11px;
        background: {t['panel']};
    }}
    QPlainTextEdit#DictionaryEdit {{
        border: 1px solid {t['line2']};
        border-radius: 8px;
        background: {t['panel2']};
        color: {t['text']};
        padding: 8px 10px;
        font-size: 12.5px;
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
    }}
    QPlainTextEdit#DictionaryEdit:focus {{
        border: 1px solid {t['accent']};
    }}
    QLabel#FallbackText {{
        font-size: 12.5px;
        color: {t['text']};
    }}
    QLabel#FallbackHint {{
        font-size: 11.5px;
        color: {t['dim']};
    }}
    QCheckBox::indicator {{
        width: 15px;
        height: 15px;
        border: 1.5px solid {t['line2']};
        border-radius: 4px;
        background: transparent;
    }}
    QCheckBox::indicator:checked {{
        background: {t['accent']};
        border-color: {t['accent']};
    }}
    QRadioButton::indicator {{
        width: 15px;
        height: 15px;
        border: 1.5px solid {t['line2']};
        border-radius: 9px;
        background: {t['panel']};
    }}
    QRadioButton::indicator:hover {{
        border-color: {t['accent']};
    }}
    QRadioButton::indicator:checked {{
        border-color: {t['accent']};
        background: qradialgradient(cx: 0.5, cy: 0.5, radius: 0.5, fx: 0.5, fy: 0.5,
            stop: 0 {t['accent']}, stop: 0.42 {t['accent']},
            stop: 0.48 {t['panel']}, stop: 1 {t['panel']});
    }}

    QLabel#EngineRowName {{
        font-size: 12.5px;
        font-weight: 550;
        color: {t['text']};
    }}
    QLabel#EngineRowSubtitle {{
        font-size: 11.5px;
        color: {t['dim']};
    }}

    QComboBox QAbstractItemView {{
        background: {t['panel']};
        border: 1px solid {t['line2']};
        border-radius: 7px;
        color: {t['text']};
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
        outline: none;
        padding: 4px;
    }}

    QTabWidget::pane {{
        border: 1px solid {t['line']};
        border-radius: 9px;
        background: {t['panel']};
        top: -1px;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {t['dim']};
        padding: 8px 18px;
        border: none;
        font-size: 12.5px;
    }}
    QTabBar::tab:selected {{
        color: {t['text']};
        border-bottom: 2px solid {t['accent']};
    }}
    QTabBar::tab:hover {{
        color: {t['text']};
    }}

    QWidget#ModelsPage, QWidget#HistoryPage {{
        background: {t['bg']};
    }}
    QTableView {{
        background: {t['panel']};
        alternate-background-color: {t['panel2']};
        gridline-color: {t['line']};
        color: {t['text']};
        border: 1px solid {t['line']};
        border-radius: 9px;
        selection-background-color: {t['accent_soft']};
        selection-color: {t['text']};
    }}
    QTableView::item {{
        padding: 4px 6px;
    }}
    QHeaderView::section {{
        background: {t['panel2']};
        color: {t['dim']};
        border: none;
        border-bottom: 1px solid {t['line']};
        padding: 6px 8px;
    }}
    QTextEdit {{
        background: {t['panel']};
        color: {t['text']};
        border: 1px solid {t['line']};
        border-radius: 9px;
        padding: 6px;
    }}

    QWidget#ModelsScrollViewport, QWidget#ModelsScrollContent {{
        background: {t['bg']};
    }}
    QLabel#SectionNumberLabel {{
        font-size: 13.5px;
        font-weight: 650;
        color: {t['text']};
    }}
    QLabel#SectionHintLabel {{
        font-size: 11.5px;
        color: {t['dim']};
    }}
    QLabel#DiskUsageLabel {{
        font-size: 11.5px;
        color: {t['dim']};
        font-family: {MONO_FONT_FAMILY};
    }}
    QWidget#TableCardHeader {{
        background: {t['panel2']};
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#TableCardHeaderTitle {{
        font-size: 12px;
        font-weight: 600;
        color: {t['text']};
    }}
    QLabel#TableCardHeaderNote {{
        font-size: 11.5px;
        color: {t['dim']};
    }}
    QWidget#ColumnHeaderRow {{
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#ColumnHeaderLabel {{
        font-size: 10.5px;
        color: {t['dim']};
    }}
    QWidget#EngineTableRow {{
        background: transparent;
        border-bottom: 1px solid {t['line']};
    }}
    QWidget#EngineTableRowActive {{
        background: {t['accent_soft']};
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#StatusActivePill {{
        background: {t['accent']};
        color: #ffffff;
        font-size: 11px;
        font-weight: 600;
        border-radius: 6px;
        padding: 4px 10px;
    }}
    QPushButton#PillButton {{
        background: transparent;
        border: 1px solid {t['line2']};
        border-radius: 6px;
        color: {t['text2']};
        font-size: 11px;
        padding: 4px 10px;
    }}
    QPushButton#PillButton:hover {{
        border-color: {t['accent']};
        color: {t['accent']};
    }}
    QPushButton#PillButton:disabled {{
        color: {t['dim']};
        border-color: {t['line']};
    }}
    QPushButton#DangerPillButton {{
        background: transparent;
        border: 1px solid {t['line2']};
        border-radius: 6px;
        color: {t['text2']};
        font-size: 11px;
        padding: 4px 10px;
    }}
    QPushButton#DangerPillButton:hover {{
        border-color: {t['danger']};
        color: {t['danger_text']};
    }}
    QPushButton#DangerPillButton:disabled {{
        color: {t['dim']};
        border-color: {t['line']};
    }}
    QLabel#BundledBadge {{
        color: {t['dim']};
        font-size: 11px;
        padding: 4px 10px;
    }}
    QLabel#WarnBadge {{
        color: {t['warn']};
        background: {t['warn_soft']};
        border: 1px solid {t['warn']};
        border-radius: 4px;
        font-size: 10.5px;
        font-weight: 600;
        padding: 1px 6px;
    }}
    QComboBox#SizeCombo {{
        border: 1px solid {t['line2']};
        border-radius: 6px;
        background: {t['panel2']};
        color: {t['text2']};
        font-family: {MONO_FONT_FAMILY};
        font-size: 11px;
        padding: 2px 8px;
    }}
    QLabel#MonoValueLabel {{
        color: {t['text2']};
        font-family: {MONO_FONT_FAMILY};
        font-size: 12.5px;
    }}
    QLabel#MutedValueLabel {{
        color: {t['text2']};
        font-size: 12.5px;
    }}
    QWidget#TableCardFooter {{
        background: {t['panel2']};
    }}
    QLabel#TableCardFooterNote {{
        color: {t['dim']};
        font-size: 11.5px;
    }}
    QWidget#ListRow {{
        background: transparent;
        border-bottom: 1px solid {t['line']};
    }}
    QWidget#ListRowActive {{
        background: {t['accent_soft']};
        border-bottom: 1px solid {t['line']};
    }}
    QLabel#ListRowTitle {{
        font-size: 12.5px;
        font-weight: 550;
        color: {t['text']};
    }}
    QLabel#ListRowMono {{
        font-size: 11px;
        color: {t['dim']};
        font-family: {MONO_FONT_FAMILY};
    }}
    QPushButton#AddPillButton {{
        background: transparent;
        border: 1px solid {t['accent']};
        border-radius: 6px;
        color: {t['accent']};
        font-size: 11.5px;
        padding: 5px 11px;
    }}
    QPushButton#AddPillButton:hover {{
        background: {t['accent_soft']};
    }}
    QLabel#TagGood {{
        background: {t['good_soft']};
        color: {t['good']};
        font-size: 9.5px;
        border-radius: 4px;
        padding: 2px 6px;
    }}
    QLabel#TagNeutral {{
        background: {t['panel3']};
        color: {t['dim']};
        font-size: 9.5px;
        border-radius: 4px;
        padding: 2px 6px;
    }}
    QToolButton#InfoButton {{
        background: transparent;
        border: 1px solid {t['line2']};
        border-radius: 9px;
        color: {t['text2']};
        font-size: 11px;
        font-weight: bold;
    }}
    QToolButton#InfoButton:hover {{
        background: {t['accent']};
        border-color: {t['accent']};
        color: {t['panel']};
    }}
    QPushButton#GhostGlyphButton, QPushButton#DangerGhostGlyphButton {{
        background: transparent;
        border: none;
        border-radius: 5px;
        qproperty-iconColor: {t['text2']};
    }}
    QPushButton#GhostGlyphButton {{
        qproperty-hoverIconColor: {t['text']};
    }}
    QPushButton#GhostGlyphButton:hover {{
        background: {t['panel3']};
    }}
    QPushButton#DangerGhostGlyphButton {{
        qproperty-hoverIconColor: {t['danger_text']};
    }}
    QPushButton#DangerGhostGlyphButton:hover {{
        background: {t['panel3']};
    }}
    """
