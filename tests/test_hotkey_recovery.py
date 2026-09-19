"""If something unexpected goes wrong inside the hotkey loop, the loop must recover, not die."""

import pytest

from dictation import pipeline as pipeline_module
from dictation.pipeline import Pipeline
from dictation.settings import Runtime, Settings


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
    the recovery itself raised UnboundLocalError and the hotkey thread died silently. The
    state now lives on the pipeline, but the recovery path still has to clear it."""
    session = FakeSession()
    chip = FakeChip()
    pipeline = Pipeline(Settings(), Runtime(stream_session=session))

    def boom(hotkey):
        raise RuntimeError("keyboard state unavailable")

    def stop_after_recovery(seconds):
        raise StopLoop

    monkeypatch.setattr(pipeline_module, "is_hotkey_pressed", boom)
    monkeypatch.setattr(pipeline, "stop_recording", lambda: None)
    monkeypatch.setattr(pipeline_module.time, "sleep", stop_after_recovery)

    with pytest.raises(StopLoop):  # reached the sleep that follows recovery: the loop is alive
        pipeline.hotkey_loop(chip, FakeTray())

    assert session.aborted
    assert pipeline.runtime.stream_session is None
    assert chip.states[-1] == "failed"
