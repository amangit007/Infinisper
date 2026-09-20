"""Asynchronous model downloader for Infinisper.

Downloads models (Whisper variants, Nemotron, Qwen3) on background threads with real-time
progress updates (bytes downloaded, total bytes, percentage, download speed) emitted via
PySide6 Qt Signals so the GUI stays completely responsive.
"""

import threading
import time
from pathlib import Path

from huggingface_hub import snapshot_download
from PySide6.QtCore import QObject, Signal


def format_bytes(num_bytes: float) -> str:
    """Formats byte counts into clean human-readable strings (KB, MB, GB)."""
    if num_bytes < 1024 * 1024:
        return f"{num_bytes / 1024:.1f} KB"
    if num_bytes < 1024 * 1024 * 1024:
        return f"{num_bytes / (1024 * 1024):.1f} MB"
    return f"{num_bytes / (1024 * 1024 * 1024):.2f} GB"


class ModelDownloader(QObject):
    """Manages background downloads for local speech models."""

    # Emits: (model_id, downloaded_bytes, total_bytes, percentage, speed_str, status_str)
    progress_updated = Signal(str, int, int, float, str, str)

    # Emits: (model_id, success, error_message)
    download_finished = Signal(str, bool, str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._active_downloads: dict[str, threading.Thread] = {}
        self._cancel_flags: dict[str, bool] = {}
        self._lock = threading.Lock()

    def is_downloading(self, model_id: str | None = None) -> bool:
        with self._lock:
            if model_id is not None:
                return model_id in self._active_downloads
            return bool(self._active_downloads)

    def cancel_download(self, model_id: str):
        with self._lock:
            if model_id in self._active_downloads:
                self._cancel_flags[model_id] = True

    def start_download(self, model_id: str):
        """Starts downloading `model_id` in a background daemon thread."""
        with self._lock:
            if model_id in self._active_downloads:
                return
            self._cancel_flags[model_id] = False
            thread = threading.Thread(
                target=self._download_worker,
                args=(model_id,),
                daemon=True,
            )
            self._active_downloads[model_id] = thread
            thread.start()

    def _get_download_spec(self, model_id: str) -> tuple[str, Path, list[str], int]:
        """Returns (repo_id, destination_directory, allow_patterns, expected_bytes)."""
        from asr import catalog as asr_catalog

        meta = asr_catalog.get_model_info(model_id)
        repo_id = meta["repo_id"]
        dest_dir = asr_catalog.model_dir(model_id)
        expected_bytes = meta.get("expected_bytes", 100 * 1024 * 1024)

        if meta.get("engine_id") == "whisper":
            allow_patterns = [
                "config.json",
                "preprocessor_config.json",
                "model.bin",
                "model.safetensors",
                "tokenizer.json",
                "vocabulary.*",
            ]
        elif meta.get("engine_id") == "nemotron":
            from asr import nemotron_asr

            allow_patterns = nemotron_asr.REQUIRED_FILES
        elif meta.get("engine_id") == "qwen3":
            from asr import qwen_asr

            allow_patterns = [*qwen_asr.REQUIRED_FILES, "tokenizer/*"]
        else:
            allow_patterns = ["*"]

        return repo_id, dest_dir, allow_patterns, expected_bytes

    def _download_worker(self, model_id: str):
        try:
            repo_id, dest_dir, allow_patterns, expected_bytes = self._get_download_spec(model_id)
            dest_dir.mkdir(parents=True, exist_ok=True)

            stop_monitor = threading.Event()
            start_time = time.time()
            last_bytes = 0
            last_time = start_time

            def monitor():
                nonlocal last_bytes, last_time
                while not stop_monitor.wait(0.25):
                    if self._cancel_flags.get(model_id, False):
                        break

                    try:
                        current_bytes = sum(
                            f.stat().st_size for f in dest_dir.rglob("*") if f.is_file()
                        )
                    except Exception:
                        current_bytes = 0

                    now = time.time()
                    time_delta = max(now - last_time, 0.001)
                    bytes_delta = max(current_bytes - last_bytes, 0)
                    speed = bytes_delta / time_delta
                    last_bytes = current_bytes
                    last_time = now

                    pct = min((current_bytes / max(expected_bytes, 1)) * 100.0, 99.0)
                    speed_str = f"{format_bytes(speed)}/s" if speed > 1024 else ""
                    status_str = f"Downloading... {format_bytes(current_bytes)} / {format_bytes(expected_bytes)}"

                    self.progress_updated.emit(
                        model_id, current_bytes, expected_bytes, pct, speed_str, status_str
                    )

            monitor_thread = threading.Thread(target=monitor, daemon=True)
            monitor_thread.start()

            try:
                snapshot_download(
                    repo_id=repo_id,
                    local_dir=str(dest_dir),
                    allow_patterns=allow_patterns,
                )
            finally:
                stop_monitor.set()
                monitor_thread.join(timeout=1.0)

            if self._cancel_flags.get(model_id, False):
                self.download_finished.emit(model_id, False, "Download cancelled.")
                return

            # Final 100% emission
            total_disk = sum(f.stat().st_size for f in dest_dir.rglob("*") if f.is_file())
            self.progress_updated.emit(
                model_id, total_disk, total_disk, 100.0, "", "Download complete"
            )
            self.download_finished.emit(model_id, True, "")

        except Exception as exc:
            self.download_finished.emit(model_id, False, str(exc))
        finally:
            with self._lock:
                self._active_downloads.pop(model_id, None)
                self._cancel_flags.pop(model_id, None)


# Global singleton instance
downloader = ModelDownloader()


def get_downloader() -> ModelDownloader:
    """Returns the application-wide ModelDownloader singleton."""
    return downloader
