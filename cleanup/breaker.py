"""Stops asking a model that is already overloaded.

A provider that answers "503, high demand" can take 8-24 s to say so. If every dictation
waits that long just to be told no again, the app feels broken. After a couple of such
failures in a row the model is skipped for a short cooldown, so the take goes straight to
the fallback (the unpolished transcript, or local Whisper for the audio path).
"""

import time
from concurrent.futures import TimeoutError as FutureTimeoutError

import litellm

OVERLOAD_STATUS_CODES = (408, 429, 500, 502, 503, 504)


def is_overload_error(exc: BaseException) -> bool:
    """True for "try again later" failures. A wrong key or model name (401/403/404) is not
    one: those never fix themselves, and they fail fast, so the user should keep seeing them."""
    if isinstance(exc, (FutureTimeoutError, litellm.Timeout)):
        return True
    return getattr(exc, "status_code", None) in OVERLOAD_STATUS_CODES


class CircuitBreaker:
    def __init__(self, threshold: int = 2, cooldown_seconds: float = 60.0, clock=time.monotonic):
        self._threshold = threshold
        self._cooldown = cooldown_seconds
        self._clock = clock
        self._failures: dict[str, int] = {}
        self._open_until: dict[str, float] = {}

    def retry_in(self, key: str) -> float:
        """Seconds until `key` is tried again; 0 if it can be tried now."""
        until = self._open_until.get(key)
        if until is None:
            return 0.0
        remaining = until - self._clock()
        if remaining <= 0:
            # Cooldown over: let one request through, and start counting again.
            del self._open_until[key]
            self._failures.pop(key, None)
            return 0.0
        return remaining

    def is_open(self, key: str) -> bool:
        return self.retry_in(key) > 0

    def record_failure(self, key: str):
        self._failures[key] = self._failures.get(key, 0) + 1
        if self._failures[key] >= self._threshold:
            self._open_until[key] = self._clock() + self._cooldown

    def record_success(self, key: str):
        self._failures.pop(key, None)
        self._open_until.pop(key, None)
