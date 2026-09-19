import collections
import threading

import numpy as np
import sounddevice as sd

SAMPLE_RATE = 16000
BLOCK_SIZE = int(SAMPLE_RATE * 0.05)  # 50 ms callbacks, for predictable pre-roll granularity
PREROLL_SECONDS = 0.5
PREROLL_CHUNKS = max(1, int(PREROLL_SECONDS / 0.05))

_lock = threading.Lock()
_recording = False
_frames: list[np.ndarray] = []
_preroll: collections.deque = collections.deque(maxlen=PREROLL_CHUNKS)
_preroll_seconds_used = 0.0
_chip = None  # optional; wired via set_chip() so this module has no hard UI dependency
_chunk_listener = None  # optional; wired via set_chunk_listener() for real-time streaming


def set_chip(chip):
    """Wires an object with an `update_audio_level(level: float)` method (e.g.
    ui.chip.ChipWindow) so the listening-state waveform can be driven by real
    mic input. Optional -- capture works with no chip attached."""
    global _chip
    _chip = chip


def set_chunk_listener(listener):
    """Registers an optional callback `listener(chunk: np.ndarray)` that is called
    for each newly captured chunk while recording is active."""
    global _chunk_listener
    with _lock:
        _chunk_listener = listener


def clear_chunk_listener():
    """Unregisters the chunk listener."""
    global _chunk_listener
    with _lock:
        _chunk_listener = None


def check_microphone(device=None) -> bool:
    try:
        sd.check_input_settings(device=device, samplerate=SAMPLE_RATE, channels=1, dtype="float32")
        return True
    except Exception:
        return False


def list_input_devices() -> list[tuple[str, int]]:
    """(name, device_index) pairs for every usable input device -- for populating
    a microphone picker."""
    devices = []
    try:
        for index, device in enumerate(sd.query_devices()):
            if device.get("max_input_channels", 0) > 0:
                devices.append((device["name"], index))
    except Exception:
        pass
    return devices


def default_input_device_name() -> str | None:
    """The system's current default input device name, for display only -- `None`
    is still passed to `sd.InputStream`/`open_stream` to mean 'use the default'."""
    try:
        return sd.query_devices(kind="input")["name"]
    except Exception:
        return None


def _audio_callback(indata, frame_count, time_info, status):
    chunk = indata.copy()
    listener = None
    with _lock:
        _preroll.append(chunk)
        recording = _recording
        if recording:
            _frames.append(chunk)
            listener = _chunk_listener

    if recording and listener is not None:
        try:
            listener(chunk)
        except Exception:
            pass

    if recording and _chip is not None:
        level = float(np.sqrt(np.mean(np.square(chunk))))
        _chip.update_audio_level(level)


def open_stream(device=None) -> sd.InputStream:
    # Kept open for the app's whole lifetime so a hotkey press never waits on
    # PortAudio startup latency -- that latency was eating the first word of every take.
    stream = sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="float32",
        blocksize=BLOCK_SIZE,
        device=device,
        callback=_audio_callback,
    )
    stream.start()
    return stream


def is_recording() -> bool:
    with _lock:
        return _recording


def start_recording() -> list[np.ndarray]:
    """Begins buffering audio, seeded with the last ~0.5s of pre-roll so the
    first spoken words aren't lost to mic/thread startup latency."""
    global _recording, _frames, _preroll_seconds_used
    with _lock:
        _frames = list(_preroll)
        _preroll_seconds_used = len(_frames) * (BLOCK_SIZE / SAMPLE_RATE)
        _recording = True
        return list(_frames)


def preroll_seconds_used() -> float:
    """How much pre-roll actually seeded the current/most recent take. Normally
    PREROLL_SECONDS, but shorter for the first take after launch, before the ring
    buffer has filled. This is where the hotkey click sits in the returned audio --
    see preprocessor.suppress_transient_click, which needs to know.
    """
    with _lock:
        return _preroll_seconds_used


def stop_recording() -> np.ndarray | None:
    global _recording, _chunk_listener
    with _lock:
        _recording = False
        _chunk_listener = None
        captured = list(_frames)

    if not captured:
        return None
    return np.concatenate(captured, axis=0).flatten()
