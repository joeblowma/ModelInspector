# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Integration contracts for JSONC settings, live theme, and MainWindow wiring."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QSettings
from PyQt6.QtWidgets import QApplication

from back.settings_store import open_settings
from front.application import apply_theme
from front.integration_controller import IntegrationMixin
import front.integration_controller as integration_controller


class _Signal:
    def connect(self, callback) -> None:
        self.callback = callback


class _CacheSyncWorker:
    started_paths: list[list[str]] = []

    def __init__(self, paths, _options, _threads) -> None:
        self.paths = list(paths)
        self.result_ready = _Signal()
        self.error_occurred = _Signal()
        self.all_done = _Signal()

    def start(self) -> None:
        self.started_paths.append(self.paths)


class _CacheHost(IntegrationMixin):
    def __init__(self, paths: list[str]) -> None:
        self._paths = paths
        self._cache_sync_worker = None
        self._allow_filename_alias_detection = False

    def _list_cached_inspection_paths(self) -> list[str]:
        return self._paths


def _verify_cache_sync(monkeypatch, path: Path, entry: dict):
    _CacheSyncWorker.started_paths = []
    monkeypatch.setattr(integration_controller, "AnalysisWorker", _CacheSyncWorker)
    monkeypatch.setattr(
        integration_controller,
        "get_cached_inspection_identity_snapshots",
        lambda paths: {str(path): entry},
    )
    host = _CacheHost([str(path)])
    report = host._cache_report()
    host._schedule_cache_sync()
    return report.entries[0], _CacheSyncWorker.started_paths


def _cached_identity(path: Path, *, size: int | None, mtime_ns: int | None) -> dict:
    identity = {"resolved_filepath": str(path)}
    if size is not None:
        identity["file_size"] = size
    if mtime_ns is not None:
        identity["mtime_ns"] = mtime_ns
    return {"filepath": str(path), "identity": identity}


def _summary(path: str, architecture: str, model_type: str) -> dict:
    return {
        "filepath": path,
        "filename": Path(path).name,
        "format": Path(path).suffix.lstrip(".").upper(),
        "file_size": 1,
        "file_size_friendly": "1 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": architecture,
        "model_type": model_type,
        "components": {},
        "named_text_encoders": {},
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }


def test_jsonc_store_migrates_ini_and_recovers_malformed_content(tmp_path: Path) -> None:
    legacy = tmp_path / "settings.ini"
    ini = QSettings(str(legacy), QSettings.Format.IniFormat)
    ini.setValue("analysis_threads", "4")
    ini.setValue("default_tab", "data")
    ini.sync()
    destination = tmp_path / "settings.jsonc"
    migrated = open_settings(destination, legacy)
    assert migrated.value("analysis_threads") == "4"
    assert migrated.value("default_tab") == "data"
    assert "Migrated" in migrated.diagnostic
    destination.write_text("{ invalid", encoding="utf-8")
    recovered = open_settings(destination, legacy)
    assert recovered.value("analysis_threads") == 2
    assert destination.with_suffix(".jsonc.invalid").exists()
    assert "Malformed" in recovered.diagnostic


def test_unchanged_active_cache_entry_does_not_schedule_sync(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "unchanged.safetensors"
    path.write_bytes(b"unchanged")
    stat = path.stat()

    entry, started_paths = _verify_cache_sync(
        monkeypatch,
        path,
        _cached_identity(path, size=stat.st_size, mtime_ns=stat.st_mtime_ns),
    )

    assert entry.classification == "active"
    assert entry.action == "none"
    assert started_paths == []


def test_changed_size_or_mtime_cache_entry_schedules_sync(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "changed.safetensors"
    path.write_bytes(b"unchanged")
    stat = path.stat()

    size_entry, size_syncs = _verify_cache_sync(
        monkeypatch,
        path,
        _cached_identity(path, size=stat.st_size + 1, mtime_ns=stat.st_mtime_ns),
    )
    mtime_entry, mtime_syncs = _verify_cache_sync(
        monkeypatch,
        path,
        _cached_identity(path, size=stat.st_size, mtime_ns=stat.st_mtime_ns - 1),
    )

    assert size_entry.action == mtime_entry.action == "refresh"
    assert size_syncs == [[str(path)]]
    assert mtime_syncs == [[str(path)]]


def test_legacy_active_cache_entry_without_identity_schedules_sync(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "legacy.safetensors"
    path.write_bytes(b"legacy")

    entry, started_paths = _verify_cache_sync(
        monkeypatch,
        path,
        {"filepath": str(path), "identity": {"resolved_filepath": str(path)}},
    )

    assert entry.classification == "active"
    assert entry.action == "refresh"
    assert started_paths == [[str(path)]]


def test_missing_cache_entry_is_historic_and_never_schedules_sync(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "missing.safetensors"

    entry, started_paths = _verify_cache_sync(
        monkeypatch,
        path,
        _cached_identity(path, size=1, mtime_ns=1),
    )

    assert entry.classification == "historic"
    assert entry.action == "archive"
    assert started_paths == []


def test_settings_cache_load_reconciles_filters_and_preserves_active_selection(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    from gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    existing_a = "R:/existing/a.safetensors"
    existing_b = "R:/existing/b.gguf"
    cached = "R:/cached/c.ckpt"
    existing_results = [
        _summary(existing_a, "Architecture A", "Checkpoint"),
        _summary(existing_b, "Architecture B", "LoRA"),
    ]
    snapshots = {
        existing_a: _summary(existing_a, "Architecture A", "Checkpoint"),
        cached: _summary(cached, "Architecture C", "Text Encoder"),
    }
    try:
        for data in existing_results:
            window._normalize_result_data(data)
            window._results.append(data)
            window._add_card(data)
            window._add_table_row(data)
        window.arch_filter_btn.replace_items(
            data["architecture"] for data in window._results
        )
        window.tag_filter_btn.replace_items(
            tag for data in window._results for tag in window._filter_tags_for_data(data)
        )
        window.format_filter_btn.replace_items(
            window._format_filter_for_data(data) for data in window._results
        )
        window.arch_filter_btn._arch_checks["Architecture B"].setChecked(False)
        window.tag_filter_btn._arch_checks["LoRA"].setChecked(False)
        window.format_filter_btn._arch_checks[".gguf"].setChecked(False)
        window._selected_paths.add(existing_a)
        monkeypatch.setattr(
            window,
            "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path=existing_a, classification="active"),
                    SimpleNamespace(path=cached, classification="active"),
                ]
            ),
        )
        monkeypatch.setattr(
            window,
            "_get_cached_inspection_summary_snapshots",
            lambda _paths: snapshots,
        )

        window._load_cache()

        assert set(window.arch_filter_btn._arch_checks) == {
            "Architecture A", "Architecture B", "Architecture C"
        }
        assert set(window.tag_filter_btn._arch_checks) == {
            "Checkpoint", "LoRA", "Text Encoder"
        }
        assert set(window.format_filter_btn._arch_checks) == {
            ".safetensors", ".gguf", ".ckpt"
        }
        assert window.arch_filter_btn._arch_checks["Architecture A"].isChecked()
        assert not window.arch_filter_btn._arch_checks["Architecture C"].isChecked()
        assert window.tag_filter_btn._arch_checks["Checkpoint"].isChecked()
        assert not window.tag_filter_btn._arch_checks["Text Encoder"].isChecked()
        assert window.format_filter_btn._arch_checks[".safetensors"].isChecked()
        assert not window.format_filter_btn._arch_checks[".ckpt"].isChecked()
        assert window.table.isRowHidden(window._row_for_filepath(cached))
        assert window.raw_combo.findData(existing_a) >= 0
        assert window.raw_combo.findData(cached) == -1
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "1 selected"
        assert window.progress_label.text() == "Loaded 1 cached summaries"
    finally:
        window.close()


def test_theme_application_and_mainwindow_explorer_wiring(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    theme_id, diagnostics = apply_theme(app, "github")
    assert theme_id == "github"
    assert diagnostics == ()
    from gui import MainWindow

    window = MainWindow()
    try:
        assert not hasattr(window, "raw_sections")
        assert not hasattr(window, "advanced_viewer_btn")
        assert callable(window._show_advanced_viewer_for_path)
        assert callable(window._open_table_row_in_advanced_viewer)
        assert not hasattr(window, "explorer_tab")
        layout = window._capture_data_layout()
        assert {entry["key"] for entry in layout["columns"]} >= {"selection", "column_1"}
        window._apply_data_layout({
            "columns": [
                {"key": "column_2", "visible": False, "width": 123},
                {"key": "selection", "visible": True, "width": 34},
            ],
            "theme": "github",
        })
        assert window.table.isColumnHidden(2)
        window.table.setColumnHidden(2, False)
        assert window.table.columnWidth(2) == 123
        assert window.table.horizontalHeader().visualIndex(2) == 0
    finally:
        window.close()
