from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import background_tasks
import gui
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _full_result(filepath: str, index: int) -> dict:
    architecture = "Architecture A" if index % 2 == 0 else "Architecture B"
    return {
        "filepath": filepath,
        "resolved_filepath": filepath,
        "filename": Path(filepath).name,
        "format": "SAFETENSORS",
        "file_size": 1_000 + index,
        "file_size_friendly": "1.0 KB",
        "tensor_count": 10 + index,
        "total_params": 100_000 + index,
        "total_params_friendly": "100K",
        "architecture": architecture,
        "arch_details": {"large": "not resident"},
        "model_type": "Checkpoint",
        "adapter_type": None,
        "quantization": None,
        "components": {"unet": True},
        "named_text_encoders": {},
        "lora_rank": None,
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "precision_summary": "FP16",
        "component_precision_summary": "UNet FP16",
        "component_precisions": {"unet": "FP16"},
        "precision_display": "FP16",
        "training_meta": {"software": "synthetic"},
        "extra": {"model_title": f"Synthetic {index}"},
        "warnings": [],
        "metadata": {"large": "x" * 20_000},
        "tensor_info": {f"tensor.{item}": {"shape": [2, 2]} for item in range(50)},
        "dtypes": [{"dtype": "F16", "count": 50}],
    }


def _wait_for_analysis(window: gui.MainWindow, timeout: float = 10.0) -> None:
    app = _app()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        worker = window._worker
        if (
            worker is not None
            and not worker.isRunning()
            and window._projection.pending_count == 0
            and window.analyze_btn.isEnabled()
        ):
            app.processEvents()
            return
    raise AssertionError("analysis did not reach terminal projected state")


def test_integrated_worker_projection_filters_sorting_and_raw_summary(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    paths = [f"R:/synthetic/model-{index:03d}.safetensors" for index in range(24)]
    bad_path = paths[7]

    def inspect(filepath: str, options=None):
        index = paths.index(filepath)
        if filepath == bad_path:
            raise ValueError("synthetic malformed header")
        time.sleep(0.001)
        return _full_result(filepath, index)

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    app = _app()
    window = gui.MainWindow()
    window._analysis_threads = 3
    header = window.table.horizontalHeader()
    assert header is not None
    window.table.setSortingEnabled(True)
    window.table.sortItems(3, Qt.SortOrder.DescendingOrder)
    expected_sort_column = header.sortIndicatorSection()
    expected_sort_order = header.sortIndicatorOrder()

    try:
        window._start_analysis(paths, clear_existing=True)
        _wait_for_analysis(window)

        worker = window._worker
        assert worker is not None
        assert len(window._results) == len(paths)
        assert window.table.rowCount() == len(paths)
        assert len(window._path_to_card) == len(paths)
        assert len(window._path_to_simple_card) == 0
        assert window._analysis_error_count == 1
        assert worker.peak_in_flight <= max(2, 2 * worker.threads)
        assert worker.peak_outstanding_events <= max(8, 2 * worker.threads)
        assert worker.outstanding_events == 0

        successful = [
            result
            for result in window._results
            if result.get("architecture") != "ERROR"
        ]
        assert successful
        assert all("metadata" not in result for result in successful)
        assert all("tensor_info" not in result for result in successful)
        assert all("arch_details" not in result for result in successful)
        assert {result["filepath"] for result in successful} == set(paths) - {bad_path}

        assert window.table.isSortingEnabled()
        assert header.sortIndicatorSection() == expected_sort_column
        assert header.sortIndicatorOrder() == expected_sort_order

        window._active_arch_filter = {"Architecture A"}
        window._apply_arch_filter()
        visible = set(window._visible_paths())
        expected_visible = {
            result["filepath"]
            for result in successful
            if result["architecture"] == "Architecture A"
        }
        assert visible == expected_visible

        selected = next(iter(expected_visible))
        window._selected_paths.add(selected)
        window._sync_selection_visuals()
        assert window.selected_count_label.text().startswith("1 selected")

        window._show_raw_summary(selected)
        raw_text = window.raw_text.toPlainText()
        assert f"Path: {selected}" in raw_text
        assert "Architecture: Architecture A" in raw_text

        monkeypatch.setattr(gui, "get_cached_raw_dump", lambda _: "cached full dump")
        window._load_raw_dump(selected)
        assert window.raw_text.toPlainText() == "cached full dump"
        app.processEvents()
    finally:
        window.close()


def test_replace_and_additive_queue_modes(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = _app()
    window = gui.MainWindow()
    window._auto_analyze_on_add = False
    try:
        window._add_mode = "replace"
        assert window._queue_files(["first", "second"]) == ["first", "second"]
        assert window._queue_files(["third"]) == ["third"]
        assert window._queued_files == ["third"]

        window._add_mode = "additive"
        assert window._queue_files(["third", "fourth"]) == ["fourth"]
        assert window._queued_files == ["third", "fourth"]
    finally:
        window.close()
        app.processEvents()
