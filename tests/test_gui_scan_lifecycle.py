# pyright: reportAttributeAccessIssue=false, reportUnusedExpression=false
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication

import gui
from gui import MainWindow, ModelCard
from front.scan_projection import ProjectionEvent


def _summary(path: str) -> dict:
    return {
        "filepath": path,
        "filename": Path(path).name,
        "format": "SAFETENSORS",
        "file_size": 10,
        "file_size_friendly": "10 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": "Test",
        "model_type": "Checkpoint",
        "adapter_type": None,
        "quantization": None,
        "components": {},
        "named_text_encoders": {},
        "lora_rank": None,
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }


def test_cards_use_one_compact_mode(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        for index in range(12):
            data = _summary(f"R:/synthetic/model-{index}.safetensors")
            window._results.append(data)
            window._add_card(data)
        assert len(window._path_to_card) == 12
        assert not hasattr(window, "cards_simple_view_cb")
        assert not hasattr(window, "simple_cards_scroll")
    finally:
        window.close()


def test_discovery_runs_asynchronously_and_queues_terminal_paths(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "nested" / "model.safetensors"
    model.parent.mkdir()
    model.write_bytes(b"")
    second_model = tmp_path / "second" / "other.gguf"
    second_model.parent.mkdir()
    second_model.write_bytes(b"")
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    window._auto_analyze_on_add = False
    try:
        window._start_discovery([str(model.parent), str(second_model.parent)])
        deadline = time.monotonic() + 5
        while (
            str(second_model) not in window._queued_files
            and time.monotonic() < deadline
        ):
            app.processEvents()
        assert str(model) in window._queued_files
        assert str(second_model) in window._queued_files
        assert window._discovery_worker is not None
        assert not window._discovery_worker.isRunning()
    finally:
        window.close()


def test_analysis_terminal_waits_for_final_projection(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class WorkerDouble:
        was_cancelled = False

        def __init__(self):
            self.acknowledged = 0

        def acknowledge_event(self):
            self.acknowledged += 1

        def isRunning(self):
            return False

    worker = WorkerDouble()
    window._worker = worker
    generation = window._projection.begin()
    window._scan_generation = generation
    window._analysis_total_count = 17
    global_calls = {
        name: 0
        for name in (
            "_apply_arch_filter",
            "_refresh_raw_combo_filtered",
            "_sync_selection_visuals",
            "_refresh_card_layout_geometry",
        )
    }
    for name in global_calls:
        original = getattr(window, name)

        def counted(*args, _name=name, _original=original, **kwargs):
            global_calls[_name] += 1
            return _original(*args, **kwargs)

        monkeypatch.setattr(window, name, counted)
    try:
        for index in range(17):
            window._projection.enqueue(
                ProjectionEvent(
                    generation,
                    "result",
                    _summary(f"R:/synthetic/model-{index}.safetensors"),
                    worker.acknowledge_event,
                )
            )
        window._projection.mark_terminal(generation, worker)
        deadline = time.monotonic() + 5
        while window._projection.pending_count and time.monotonic() < deadline:
            app.processEvents()
        app.processEvents()
        assert len(window._results) == 17
        assert window.table.rowCount() == 17
        assert worker.acknowledged == 17
        assert window._projection.pending_count == 0
        assert global_calls == {name: 1 for name in global_calls}
    finally:
        window._worker = None
        window.close()


def test_model_card_skips_redundant_selection_styles(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    card = ModelCard(_summary("R:/synthetic/model.safetensors"))
    refreshes = []
    monkeypatch.setattr(card, "_refresh_style", lambda: refreshes.append(True))

    card.set_selected(False)
    card.set_selected(False)
    card.set_selected(True)
    card.set_selected(True)
    card.set_selected(False)

    assert len(refreshes) == 2
    assert QApplication.instance() is app


def test_startup_cache_uses_compact_batch_and_restores_sorting(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    paths = [f"R:/synthetic/cached-{index}.safetensors" for index in range(21)]
    calls = []
    monkeypatch.setattr(gui, "list_cached_inspection_paths", lambda: paths)

    def summaries(requested):
        calls.append(list(requested))
        return {path: _summary(path) for path in requested}

    monkeypatch.setattr(gui, "get_cached_inspection_summary_snapshots", summaries)
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()
    window._load_default_libraries_on_startup = True
    sort_states = []
    original_add_row = window._add_table_row

    def add_row(data):
        sort_states.append(window.table.isSortingEnabled())
        original_add_row(data)

    window._add_table_row = add_row
    try:
        window._load_default_libraries_from_cache_on_startup()
        deadline = time.monotonic() + 5
        while window.table.rowCount() < len(paths) and time.monotonic() < deadline:
            app.processEvents()
        assert calls == [paths]
        assert window.table.rowCount() == len(paths)
        assert sort_states == [False] * len(paths)
        assert window.table.isSortingEnabled()
        assert window._startup_sort_restore is None
    finally:
        window.close()


def test_startup_cache_cancel_restores_sorting(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    paths = [f"R:/synthetic/cached-{index}.safetensors" for index in range(21)]
    monkeypatch.setattr(gui, "list_cached_inspection_paths", lambda: paths)
    monkeypatch.setattr(
        gui,
        "get_cached_inspection_summary_snapshots",
        lambda requested: {path: _summary(path) for path in requested},
    )
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()
    window._load_default_libraries_on_startup = True
    try:
        window._load_default_libraries_from_cache_on_startup()
        assert window.table.rowCount() == 20
        assert not window.table.isSortingEnabled()
        window._cancel_current_operation()
        app.processEvents()
        assert window.table.rowCount() == 20
        assert window.table.isSortingEnabled()
        assert window._startup_sort_restore is None
    finally:
        window.close()


def test_clear_stops_queued_startup_cache_batches(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    paths = [f"R:/synthetic/cached-{index}.safetensors" for index in range(21)]
    monkeypatch.setattr(gui, "list_cached_inspection_paths", lambda: paths)
    monkeypatch.setattr(
        gui,
        "get_cached_inspection_summary_snapshots",
        lambda requested: {path: _summary(path) for path in requested},
    )
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    app.processEvents()
    window._load_default_libraries_on_startup = True
    try:
        window._load_default_libraries_from_cache_on_startup()
        assert window.table.rowCount() == 20
        window._clear_all()
        app.processEvents()
        assert window.table.rowCount() == 0
        assert window._results == []
        assert window.table.isSortingEnabled()
    finally:
        window.close()


def test_close_is_deferred_until_slow_thread_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()

    class SlowWorker(QThread):
        def cancel(self):
            self.requestInterruption()

        def run(self):
            self.msleep(400)

    worker = SlowWorker()
    window._worker = worker
    window.show()
    app.processEvents()
    worker.start()
    try:
        started = time.monotonic()
        assert window.close() is False
        assert time.monotonic() - started < 0.15
        assert worker.isRunning()
        assert window.isVisible()
        assert window._close_pending
        assert QApplication.instance() is app
        assert worker.parent() is None
        assert window.close() is False
        assert window._close_waiting_workers == {worker}
        assert worker.wait(2000)
        deadline = time.monotonic() + 2
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
        assert not window.isVisible()
        assert not window._close_pending
    finally:
        if worker.isRunning():
            worker.wait(2000)
        if window.isVisible():
            window.close()


def test_raw_full_dump_prefixes_cached_and_generated_output(tmp_path, monkeypatch):
    from front import window_lifecycle

    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    QApplication.instance() or QApplication([])
    window = MainWindow()
    filepath = "R:/synthetic/current-model.safetensors"
    window._results.append(_summary(filepath))
    try:
        window._get_cached_raw_dump = lambda _path: (
            "legacy data\n  Top key prefixes (depth 2):\n"
            "    model.layers 2\n  All tensor keys (1):\n    cached tensor keys"
        )
        window._load_raw_dump(filepath)
        cached_text = window.raw_text.toPlainText()
        assert cached_text.startswith("CURRENT MODEL / OUTPUT\nOutput: Full tensor key dump")
        assert "File: current-model.safetensors" in cached_text
        assert window._RAW_DUMP_SEPARATOR in cached_text
        assert "Top key prefixes" not in cached_text
        assert cached_text.endswith("cached tensor keys")

        stored = []
        window._get_cached_raw_dump = lambda _path: None
        monkeypatch.setattr(
            window_lifecycle, "generate_modelinfo_dump", lambda _path: "generated tensor keys"
        )
        monkeypatch.setattr(
            window_lifecycle, "store_raw_dump", lambda _path, dump: stored.append(dump)
        )
        window._load_raw_dump(filepath)
        assert stored and stored[0].startswith("CURRENT MODEL / OUTPUT\n")
        assert window.raw_text.toPlainText().endswith("generated tensor keys")
    finally:
        window.close()


def test_modelinfo_dump_omits_top_key_prefixes(monkeypatch):
    from modelinfo import generate_modelinfo_dump
    import modelinfo

    tensor_info = {
        "model.layers.0.weight": {"shape": [2], "dtype": "F16"},
        "model.layers.1.weight": {"shape": [2], "dtype": "F16"},
    }
    monkeypatch.setattr(
        modelinfo, "_read_header_or_cached", lambda _filepath: ({}, tensor_info, 4)
    )

    dump = generate_modelinfo_dump("current-model.safetensors")

    assert "Top key prefixes" not in dump
    assert "All tensor keys (2):" in dump
