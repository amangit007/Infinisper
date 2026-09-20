import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

import pytest
from PySide6.QtWidgets import QApplication

from asr import catalog as asr_catalog
from asr.downloader import ModelDownloader, format_bytes, get_downloader
from ui.theme import DARK
from ui.widgets.disk_pie_chart import DiskPieChartPopover, DoughnutChartWidget


@pytest.fixture(scope="session")
def qapp():
    return QApplication.instance() or QApplication([])


def test_format_bytes():
    assert format_bytes(512) == "0.5 KB"
    assert format_bytes(1024 * 1024) == "1.0 MB"
    assert format_bytes(150 * 1024 * 1024) == "150.0 MB"
    assert format_bytes(2 * 1024 * 1024 * 1024) == "2.00 GB"


def test_asr_catalog_models_order_and_metadata():
    assert "whisper-tiny" in asr_catalog.MODELS
    assert "whisper-base" in asr_catalog.MODELS
    assert "whisper-small" in asr_catalog.MODELS
    assert "whisper-medium" in asr_catalog.MODELS
    assert "nemotron" in asr_catalog.MODELS
    assert "qwen3" in asr_catalog.MODELS

    for mid, meta in asr_catalog.MODELS.items():
        assert "label" in meta
        assert "size_label" in meta
        assert "expected_bytes" in meta
        assert "color" in meta
        assert meta["expected_bytes"] > 0


def test_get_disk_breakdown_contains_base_app():
    breakdown = asr_catalog.get_disk_breakdown()
    assert len(breakdown) >= 1
    base_entry = breakdown[0]
    assert base_entry["id"] == "base_app"
    assert "Base Application" in base_entry["name"]
    assert base_entry["size_bytes"] > 0


def test_downloader_singleton():
    d1 = get_downloader()
    d2 = get_downloader()
    assert d1 is d2
    assert isinstance(d1, ModelDownloader)


def test_doughnut_chart_widget(qapp):
    slices = asr_catalog.get_disk_breakdown()
    total_bytes = sum(s["size_bytes"] for s in slices)
    widget = DoughnutChartWidget(slices, total_bytes, tokens=DARK)
    assert widget.width() == 140
    assert widget.height() == 140


def test_disk_pie_chart_popover_builds(qapp):
    popover = DiskPieChartPopover(tokens=DARK)
    assert popover is not None
    assert popover.chart is not None
    popover.close()
