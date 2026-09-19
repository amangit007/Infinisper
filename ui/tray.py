from PySide6.QtCore import QObject, QTimer, Signal
from PySide6.QtWidgets import QMenu, QSystemTrayIcon

from ui.assets.mark import mark_icon
from ui.theme import DARK, LIGHT
from utils.windows import system_uses_light_theme

_THEME_POLL_MS = 3000


def tray_mark_color(light_taskbar: bool) -> str:
    """Dark mark on a light taskbar, light mark on a dark one. The tray used to be light
    unconditionally, which is 1.08:1 -- invisible -- on a light taskbar."""
    return (LIGHT if light_taskbar else DARK)["text"]


def _make_icon(light_taskbar: bool):
    return mark_icon(tray_mark_color(light_taskbar))


class TrayIcon(QObject):
    open_window_requested = Signal()
    pause_toggled = Signal(bool)
    quit_requested = Signal()

    # Public, fired from _apply_status (always on the main thread) -- lets other UI,
    # e.g. the sidebar status row, mirror the tray's status text without duplicating
    # the pipeline's state bookkeeping.
    status_changed = Signal(str)

    _status_changed = Signal(str)

    def __init__(self):
        super().__init__()
        self._light_taskbar = system_uses_light_theme()
        self._icon = QSystemTrayIcon(_make_icon(self._light_taskbar))
        self._icon.setToolTip("Infinisper - Ready")

        menu = QMenu()
        self._status_action = menu.addAction("Status: Ready")
        self._status_action.setEnabled(False)
        menu.addSeparator()

        open_action = menu.addAction("Open Infinisper")
        open_action.triggered.connect(self.open_window_requested.emit)

        self._pause_action = menu.addAction("Pause dictation")
        self._pause_action.setCheckable(True)
        self._pause_action.toggled.connect(self.pause_toggled.emit)

        menu.addSeparator()
        quit_action = menu.addAction("Quit")
        quit_action.triggered.connect(self.quit_requested.emit)

        self._icon.setContextMenu(menu)
        self._icon.show()

        self._status_changed.connect(self._apply_status)

        # The taskbar theme is its own Windows setting and can change while we run.
        self._theme_timer = QTimer(self)
        self._theme_timer.setInterval(_THEME_POLL_MS)
        self._theme_timer.timeout.connect(self._refresh_icon_for_taskbar)
        self._theme_timer.start()

    def _refresh_icon_for_taskbar(self):
        light = system_uses_light_theme()
        if light != self._light_taskbar:
            self._light_taskbar = light
            self._icon.setIcon(_make_icon(light))

    def set_status(self, text: str):
        self._status_changed.emit(text)

    def _apply_status(self, text: str):
        self._status_action.setText(f"Status: {text}")
        self._icon.setToolTip(f"Infinisper - {text}")
        self.status_changed.emit(text)
