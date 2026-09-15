"""Infinisper's brand mark: a clipboard capturing a speech bubble with sound
waves leaving it -- clipboard (captured), bubble (speech), waves (in motion).
Paths and the legibility ladder are lifted directly from `Infinisper Brand.html`
(the "Construction" and "Legibility ladder" panels), not redrawn from scratch.

One stroke-only vector, recolored by substituting {color} rather than keeping
separate colored copies -- matches the brand doc's own handoff note: "render
with QSvgRenderer and recolour by swapping stroke; no PNG set needed above
32px."
"""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from ui.theme import oklch_to_hex

# The brand doc's own two colors for the mark: the canonical brand blue for
# light backgrounds, and a lightened oklch() variant for dark ones (a plain
# hex on a dark panel reads too saturated/heavy -- same reasoning as the app's
# own DARK/LIGHT accent tokens in ui/theme.py, just a distinct brand-specific
# value rather than reusing the UI accent).
BRAND_HEX = "#14588b"
BRAND_ACCENT_DARK_HEX = oklch_to_hex(0.70, 0.105, 245)

# Full detail: clipboard, its pin, the speech bubble, and three waves. Legible
# from ~28px up -- below that the clipboard reads as noise, hence COMPACT below.
FULL_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="5.25 -0.6 56.5 56.5" \
fill="none" stroke="{color}" stroke-width="3.4" stroke-linecap="round" stroke-linejoin="round">
<path d="M25 21.35 V11.5 Q25 8 28.5 8 H33"/>
<path d="M49 8 H53.5 Q57 8 57 11.5 V50.5 Q57 54 53.5 54 H28.5 Q25 54 25 50.5 V46.65"/>
<rect x="34" y="4.8" width="14" height="6.4" rx="1.8" fill="{color}" stroke="none"/>
<circle cx="41" cy="3.1" r="2.4" stroke-width="2.1"/>
<path d="M28.49 45.78 A13 13 0 1 1 28.49 22.22"/>
<path d="M13.81 43.19 C10.8 47.6, 9.9 49.6, 10.5 50.1 C11.1 50.6, 14.4 49.2, 18.55 46.22"/>
<path d="M27.59 27.45 A8 8 0 0 1 27.59 40.55"/>
<path d="M31.84 25.16 A12.5 12.5 0 0 1 31.84 42.84"/>
<path d="M35.02 21.98 A17 17 0 0 1 35.02 46.02"/>
</svg>"""

# Reduced detail for tray/titlebar scale -- per the brand doc's own legibility
# ladder ("the mark sheds detail rather than shrinking"): drop the clipboard and
# pin, keep the bubble, its tail, and one wave.
COMPACT_MARK_SVG = """<svg xmlns="http://www.w3.org/2000/svg" viewBox="4.87 18.3 35 35" \
fill="none" stroke="{color}" stroke-width="5" stroke-linecap="round" stroke-linejoin="round">
<path d="M28.49 45.78 A13 13 0 1 1 28.49 22.22"/>
<path d="M13.81 43.19 C10.8 47.6, 9.9 49.6, 10.5 50.1 C11.1 50.6, 14.4 49.2, 18.55 46.22"/>
<path d="M32.58 25.97 A12.5 12.5 0 0 1 32.58 42.03"/>
</svg>"""

_ICON_SIZES = (16, 24, 32, 48, 64, 128, 256)
_COMPACT_BELOW_PX = 28


def mark_pixmap(color: str, size: int, *, compact: bool | None = None) -> QPixmap:
    """Renders the mark at `size`x`size`. `compact` auto-picks the reduced-detail
    variant below _COMPACT_BELOW_PX unless explicitly forced either way.
    """
    if compact is None:
        compact = size < _COMPACT_BELOW_PX
    svg = (COMPACT_MARK_SVG if compact else FULL_MARK_SVG).format(color=color)
    renderer = QSvgRenderer(QByteArray(svg.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size, size))
    painter.end()
    return pixmap


def mark_icon(color: str) -> QIcon:
    """Multi-resolution QIcon for the window/taskbar/tray -- Qt and Windows pick
    whichever pixmap is closest to what they're actually painting (titlebar,
    Alt+Tab, tray), so all the common sizes are pre-rendered once.
    """
    icon = QIcon()
    for size in _ICON_SIZES:
        icon.addPixmap(mark_pixmap(color, size))
    return icon
