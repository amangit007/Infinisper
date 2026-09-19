"""If something unexpected goes wrong inside the hotkey loop, the loop must recover, not die."""

import pytest

import app


class StopLoop(BaseException):
    """Raised by the stubbed sleep to get out of the otherwise endless loop."""


class FakeSession:
    def __init__(self):
        self.aborted = False

    def abort(self):
        self.aborted = True


class FakeChip:
    def __init__(self):
        self.states = []

    def set_state(self, state):
        self.states.append(state)


class FakeTray:
    def set_status(self, text):
        pass


def test_an_error_while_a_streaming_take_is_open_aborts_it_and_keeps_the_loop_alive(monkeypatch):
    """The recovery block used to assign the stream session without declaring it global, so
    the recovery itself raised UnboundLocalError and the hotkey thread died silently."""
    session = FakeSession()
    chip = FakeChip()

    def boom(hotkey):
        raise RuntimeError("keyboard state unavailable")

    def stop_after_recovery(seconds):
        raise StopLoop

    monkeypatch.setattr(app, "_nemotron_stream_session", session)
    monkeypatch.setattr(app, "is_hotkey_pressed", boom)
    monkeypatch.setattr(app, "stop_recording", lambda: None)
    monkeypatch.setattr(app.time, "sleep", stop_after_recovery)

    with pytest.raises(StopLoop):  # reached the sleep that follows recovery: the loop is alive
        app.hotkey_loop(chip, FakeTray(), None)

    assert session.aborted
    assert app._nemotron_stream_session is None
    assert chip.states[-1] == "failed"
