# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Integration contracts for JSONC settings, live theme, and MainWindow wiring."""

from __future__ import annotations

import os
import sys
from pathlib import Path

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
        assert window.advanced_viewer_btn.toolTip()
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
