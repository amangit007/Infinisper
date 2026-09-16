import time
from contextlib import contextmanager


@contextmanager
def timed(label: str, steps: list | None = None):
    """Context manager to measure and log execution time."""
    start = time.perf_counter()
    try:
        yield
    finally:
        elapsed_ms = (time.perf_counter() - start) * 1000
        print(f"[timing] {label}: {elapsed_ms:.0f}ms")
        if steps is not None:
            steps.append((label, elapsed_ms))
