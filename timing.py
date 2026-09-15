import time
from contextlib import contextmanager


@contextmanager
def timed(label: str, steps: list | None = None):
    """steps, when passed, collects (label, elapsed_ms) for the History tab --
    a second, structured record of the same timing this always prints, not a
    replacement for the print.
    """
    start = time.perf_counter()
    try:
        yield
    finally:
        # Always prints, even if the wrapped code raises -- "this failed after
        # 4000ms" is as useful for diagnosing slowness as a successful timing.
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"[timing] {label}: {elapsed_ms:.0f}ms")
        if steps is not None:
            steps.append((label, elapsed_ms))
