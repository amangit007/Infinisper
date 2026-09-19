"""Monochrome line icons, drawn from SVG paths and tinted at render time.

The paths are from Lucide (https://lucide.dev, ISC licence): 24x24 grid, 2px round stroke.
They replace Unicode characters (✎ × □ ✕ ◑ ⚠️) that had no consistent weight, took the
wrong color in one theme or the other, and in one case rendered as a color emoji.
"""

from PySide6.QtCore import QByteArray, QRectF, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

_PATHS = {
    "minus": '<path d="M5 12h14"/>',
    "square": '<rect width="16" height="16" x="4" y="4" rx="2"/>',
    "x": '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
    "pencil": (
        '<path d="M21.174 6.812a1 1 0 0 0-3.986-3.987L3.842 16.174a2 2 0 0 0-.5.83l-1.321 4.352'
        'a.5.5 0 0 0 .623.622l4.353-1.32a2 2 0 0 0 .83-.497z"/><path d="m15 5 4 4"/>'
    ),
    "contrast": '<circle cx="12" cy="12" r="10"/><path d="M12 18a6 6 0 0 0 0-12v12z"/>',
    "eye": (
        '<path d="M2.062 12.348a1 1 0 0 1 0-.696 10.75 10.75 0 0 1 19.876 0 1 1 0 0 1 0 .696 '
        '10.75 10.75 0 0 1-19.876 0"/><circle cx="12" cy="12" r="3"/>'
    ),
    "eye-off": (
        '<path d="M10.733 5.076a10.744 10.744 0 0 1 11.205 6.575 1 1 0 0 1 0 .696 10.747 10.747 0 0 1-1.444 2.49"/>'
        '<path d="M14.084 14.158a3 3 0 0 1-4.242-4.242"/>'
        '<path d="M17.479 17.499a10.75 10.75 0 0 1-15.417-5.151 1 1 0 0 1 0-.696 10.75 10.75 0 0 1 4.446-5.143"/>'
        '<path d="m2 2 20 20"/>'
    ),
    "triangle-alert": (
        '<path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3"/>'
        '<path d="M12 9v4"/><path d="M12 17h.01"/>'
    ),
}

_SVG = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="none" stroke="{color}" '
    'stroke-width="{width}" stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)
_SUPERSAMPLE = 2  # rendered at 2x so the icon stays sharp on scaled displays


def icon_names() -> list[str]:
    return sorted(_PATHS)


def icon_svg(name: str, color: str, stroke_width: float = 2.0) -> str:
    return _SVG.format(color=color, width=stroke_width, body=_PATHS[name])


def icon_pixmap(name: str, color: str, size: int, stroke_width: float = 2.0) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(icon_svg(name, color, stroke_width).encode("utf-8")))
    pixmap = QPixmap(size * _SUPERSAMPLE, size * _SUPERSAMPLE)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    renderer.render(painter, QRectF(0, 0, size * _SUPERSAMPLE, size * _SUPERSAMPLE))
    painter.end()
    pixmap.setDevicePixelRatio(_SUPERSAMPLE)
    return pixmap


def icon(name: str, color: str, size: int = 16, stroke_width: float = 2.0) -> QIcon:
    return QIcon(icon_pixmap(name, color, size, stroke_width))
