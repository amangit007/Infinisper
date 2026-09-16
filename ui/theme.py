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


# Alert / danger colors
DANGER = oklch_to_hex(0.6, 0.17, 25)
DANGER_TEXT = oklch_to_hex(0.7, 0.17, 25)
DANGER_STRONG = oklch_to_hex(0.55, 0.19, 25)

DARK = {
    "bg": "#16181d",
    "panel": "#1e2127",
    "panel2": "#242830",
    "panel3": "#2b3038",
    "line": "#31363f",
    "line2": "#3b414b",
    "text": "#e8eaef",
    "text2": "#b3bac6",
    "dim": "#848c9a",
    "accent": oklch_to_hex(0.72, 0.13, 255),
    "accent_soft": oklch_to_rgba(0.72, 0.13, 255, 0.14),
    "good": oklch_to_hex(0.74, 0.13, 155),
    "good_soft": oklch_to_rgba(0.74, 0.13, 155, 0.14),
    "warn": oklch_to_hex(0.79, 0.13, 80),
    "warn_soft": oklch_to_rgba(0.79, 0.13, 80, 0.14),
    "shadow": "#000000",
    "shadow_alpha": 130,
}

LIGHT = {
    "bg": "#eef0f3",
    "panel": "#ffffff",
    "panel2": "#f6f7f9",
    "panel3": "#eceef2",
    "line": "#e0e3e8",
    "line2": "#d2d6dd",
    "text": "#1a1d23",
    "text2": "#4a515c",
    "dim": "#79818e",
    "accent": oklch_to_hex(0.55, 0.13, 255),
    "accent_soft": oklch_to_rgba(0.55, 0.13, 255, 0.10),
    "good": oklch_to_hex(0.55, 0.12, 155),
    "good_soft": oklch_to_rgba(0.55, 0.12, 155, 0.10),
    "warn": oklch_to_hex(0.60, 0.12, 70),
    "warn_soft": oklch_to_rgba(0.60, 0.12, 70, 0.12),
    "shadow": "#141923",
    "shadow_alpha": 46,
}

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
    QPushButton#TitleBarButton {{
        background: transparent;
        border: none;
        border-radius: 5px;
        color: {t['dim']};
        font-size: 12px;
    }}
    QPushButton#TitleBarButton:hover {{
        background: {t['panel3']};
    }}
    QPushButton#TitleBarCloseButton:hover {{
        background: {DANGER_STRONG};
        color: #ffffff;
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
        color: {t['dim']};
        font-size: 11px;
    }}
    QPushButton#ThemeToggleButton:hover {{
        color: {t['text']};
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
    QComboBox#DeviceCombo {{
        border: 1px solid {t['line2']};
        border-radius: 7px;
        background: {t['panel2']};
        color: {t['text']};
        padding: 3px 10px;
        font-size: 12px;
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
        border-color: {DANGER};
        color: {DANGER_TEXT};
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
    QPushButton#GhostGlyphButton {{
        background: transparent;
        border: none;
        color: {t['dim']};
        font-size: 11px;
    }}
    QPushButton#GhostGlyphButton:hover {{
        color: {t['text']};
    }}
    QPushButton#DangerGhostGlyphButton {{
        background: transparent;
        border: none;
        color: {t['dim']};
        font-size: 11px;
    }}
    QPushButton#DangerGhostGlyphButton:hover {{
        color: {DANGER_TEXT};
    }}
    """
