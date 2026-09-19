"""Putting dictated text into whatever app has focus: clipboard swap, Ctrl+V, restore."""

import threading
import time

import keyboard
import pyperclip

from timing import timed

# How long the dictated text stays on the clipboard before the user's previous
# contents are put back. Generous on purpose: the restore no longer blocks the
# pipeline, so there is nothing to gain by racing it. See restore_clipboard_later.
CLIPBOARD_RESTORE_SECONDS = 1.5
_clipboard_lock = threading.Lock()


def restore_clipboard_later(previous: str, pasted: str):
    """Puts `previous` back on the clipboard, on a background thread, once the target
    app has had time to actually read what we pasted.

    This used to be a flat time.sleep(0.3) inside the pipeline, which was both a
    permanent 300 ms tax on every take -- against a 700 ms budget -- and a race: an
    app that reads the clipboard lazily (Electron apps, RDP sessions, some web
    editors) could get as far as the restore and paste the user's old contents
    instead. Waiting longer off the critical path costs nothing and loses that race
    far less often.

    Restores only if our text is still on the clipboard. Anything else there means the
    user copied something new in the meantime, and their copy wins.
    """

    def worker():
        time.sleep(CLIPBOARD_RESTORE_SECONDS)
        try:
            with _clipboard_lock:
                if pyperclip.paste() == pasted:
                    pyperclip.copy(previous)
        except Exception:
            pass

    threading.Thread(target=worker, daemon=True).start()


def paste_text(text: str, steps: list | None = None):
    with timed("Paste (clipboard swap + send)", steps):
        try:
            with _clipboard_lock:
                previous_clipboard = pyperclip.paste()
        except Exception:
            previous_clipboard = None

        with _clipboard_lock:
            pyperclip.copy(text)
        keyboard.send("ctrl+v")

    if previous_clipboard is not None:
        restore_clipboard_later(previous_clipboard, text)
