import time

import pytest

import app


class FakeClipboard:
    """Stands in for pyperclip so the tests never touch the real system clipboard."""

    def __init__(self, initial=""):
        self.value = initial
        self.writes = []

    def paste(self):
        return self.value

    def copy(self, text):
        self.value = text
        self.writes.append(text)


@pytest.fixture
def clipboard(monkeypatch):
    fake = FakeClipboard("the user's own earlier copy")
    monkeypatch.setattr(app, "pyperclip", fake)
    monkeypatch.setattr(app, "keyboard", type("K", (), {"send": staticmethod(lambda combo: None)}))
    # The real 1.5 s wait is deliberate in production and far too slow for a test.
    monkeypatch.setattr(app, "CLIPBOARD_RESTORE_SECONDS", 0.05)
    return fake


def wait_for_restore():
    time.sleep(0.05 * 4)


def test_paste_puts_the_dictated_text_on_the_clipboard(clipboard):
    app.paste_text("hello world")
    assert "hello world" in clipboard.writes


def test_previous_clipboard_is_restored_afterwards(clipboard):
    original = clipboard.value
    app.paste_text("dictated text")
    assert clipboard.value == "dictated text"  # still ours immediately after pasting
    wait_for_restore()
    assert clipboard.value == original


def test_paste_does_not_block_the_pipeline(clipboard):
    """The restore used to be a flat 300 ms sleep inside this call. It must now happen
    off the critical path."""
    start = time.perf_counter()
    app.paste_text("dictated text")
    elapsed_ms = (time.perf_counter() - start) * 1000
    assert elapsed_ms < 50, f"paste_text blocked for {elapsed_ms:.0f} ms"


def test_a_newer_user_copy_is_never_clobbered(clipboard):
    """If the user copies something during the restore window, their copy wins."""
    app.paste_text("dictated text")
    clipboard.copy("something the user copied just now")
    wait_for_restore()
    assert clipboard.value == "something the user copied just now"


def test_restore_is_skipped_when_the_previous_clipboard_could_not_be_read(monkeypatch):
    class Unreadable(FakeClipboard):
        def paste(self):
            raise RuntimeError("clipboard locked by another process")

    fake = Unreadable()
    monkeypatch.setattr(app, "pyperclip", fake)
    monkeypatch.setattr(app, "keyboard", type("K", (), {"send": staticmethod(lambda combo: None)}))
    monkeypatch.setattr(app, "CLIPBOARD_RESTORE_SECONDS", 0.05)

    app.paste_text("dictated text")  # must not raise
    wait_for_restore()
    assert fake.writes == ["dictated text"]


def test_a_failing_restore_does_not_raise(monkeypatch):
    fake = FakeClipboard("original")
    monkeypatch.setattr(app, "pyperclip", fake)
    monkeypatch.setattr(app, "CLIPBOARD_RESTORE_SECONDS", 0.05)

    def explode(text):
        raise RuntimeError("clipboard locked")

    app._restore_clipboard_later("original", fake.value)
    fake.copy = explode
    wait_for_restore()  # the worker thread must swallow this, not crash
