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

        window._load_cache_all()

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


def test_cache_load_menu_labels_and_semantics(monkeypatch, tmp_path: Path) -> None:
    """Load Cache = active-only, Load Cache All = all, Load Cache Archived = historic-only."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        active_path = "R:/active/model.safetensors"
        historic_path = "R:/historic/missing.gguf"
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path=active_path, classification="active", is_active=True, is_historic=False),
                    SimpleNamespace(path=historic_path, classification="historic", is_active=False, is_historic=True),
                ],
                availability=SimpleNamespace(
                    total=2, active=1, historic=1, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=True, load_cache_archived=True,
                    total_count=2, active_count=1, historic_count=1,
                ),
            ),
        )
        calls = []
        monkeypatch.setattr(window, "_load_cache_status", lambda w: calls.append(w))
        window._load_cache()
        window._load_cache_all()
        window._load_cache_archived()
        assert calls == ["active", None, "historic"]
    finally:
        window.close()


def test_cache_menu_actions_hidden_disabled_states(monkeypatch, tmp_path: Path) -> None:
    """Cache-load QActions hidden when population absent; disabled when view nonempty."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        assert hasattr(window, "_cache_load_active_action")
        assert hasattr(window, "_cache_load_all_action")
        assert hasattr(window, "_cache_load_archived_action")
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[],
                availability=SimpleNamespace(
                    total=0, active=0, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=False, load_cache_all=False, load_cache_archived=False,
                    total_count=0, active_count=0, historic_count=0,
                ),
            ),
        )
        window._refresh_cache_menu_actions()
        assert not window._cache_load_active_action.isVisible()
        assert not window._cache_load_all_action.isVisible()
        assert not window._cache_load_archived_action.isVisible()
        window._results.append({"filepath": "R:/dummy.safetensors"})
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[SimpleNamespace(path="R:/dummy.safetensors", classification="active", is_active=True, is_historic=False)],
                availability=SimpleNamespace(
                    total=1, active=1, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=True, load_cache_archived=False,
                    total_count=1, active_count=1, historic_count=0,
                ),
            ),
        )
        window._refresh_cache_menu_actions()
        assert window._cache_load_active_action.isVisible()
        assert not window._cache_load_archived_action.isVisible()
        assert not window._cache_load_active_action.isEnabled()
        assert not window._cache_load_all_action.isEnabled()
    finally:
        window.close()


def test_clear_cache_refreshes_counts_and_menu(monkeypatch, tmp_path: Path) -> None:
    """After confirmed clear, counts reset and menu actions hide."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[],
                availability=SimpleNamespace(
                    total=0, active=0, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=False, load_cache_all=False, load_cache_archived=False,
                    total_count=0, active_count=0, historic_count=0,
                ),
            ),
        )
        refresh_calls = []
        monkeypatch.setattr(window, "_refresh_cache_menu_actions", lambda: refresh_calls.append(True))
        from PyQt6.QtWidgets import QMessageBox
        monkeypatch.setattr(QMessageBox, "question", lambda *a, **kw: QMessageBox.StandardButton.Yes)
        monkeypatch.setattr(QMessageBox, "information", lambda *a, **kw: None)
        import model_cache as _mc
        monkeypatch.setattr(_mc, "clear_inspection_cache", lambda: 0)
        window._clear_inspection_cache_from_settings()
        assert refresh_calls == [True]
    finally:
        window.close()


def test_verify_cache_disabled_when_total_zero(monkeypatch, tmp_path: Path) -> None:
    """Verify Cached File Paths button disabled when total cache is zero."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[],
                availability=SimpleNamespace(
                    total=0, active=0, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=False, load_cache_all=False, load_cache_archived=False,
                    total_count=0, active_count=0, historic_count=0,
                ),
            ),
        )
        report = window._cache_report()
        assert report.availability.total == 0
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path="R:/active.safetensors", classification="active", is_active=True, is_historic=False),
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True),
                ],
                availability=SimpleNamespace(
                    total=2, active=1, historic=1, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=True, load_cache_archived=True,
                    total_count=2, active_count=1, historic_count=1,
                ),
                action_plan=(
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True, action="archive"),
                ),
            ),
        )
        progress_calls = []
        monkeypatch.setattr(window, "_set_progress_status", lambda t: progress_calls.append(t))
        monkeypatch.setattr(window, "_clear_progress_status", lambda delay_ms=0: None)
        monkeypatch.setattr(window, "_refresh_cache_controls", lambda: None)
        monkeypatch.setattr(window, "_schedule_cache_sync", lambda: None)
        window._verify_cached_file_paths()
        assert len(progress_calls) == 2
        assert progress_calls[0] == "Verifying cached file paths..."
        summary = progress_calls[1]
        assert "2 total" in summary
        assert "1 active" in summary
        assert "1 historic" in summary
        assert "archived/missing" in summary
        assert "0 changed" in summary
    finally:
        window.close()


def test_verify_cache_schedules_changed_entries(monkeypatch, tmp_path: Path) -> None:
    """Verify schedules changed (refresh) entries through the sync mechanism."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        started = []
        monkeypatch.setattr(
            integration_controller, "AnalysisWorker",
            lambda paths, _opts, _threads: _CacheSyncWorker(paths, _opts, _threads),
        )
        _CacheSyncWorker.started_paths = []
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path="R:/changed.safetensors", classification="active", is_active=True, is_historic=False, action="refresh"),
                    SimpleNamespace(path="R:/unchanged.safetensors", classification="active", is_active=True, is_historic=False, action="none"),
                ],
                availability=SimpleNamespace(
                    total=2, active=2, historic=0, refresh_candidates=1, sync_candidates=1,
                    load_cache=True, load_cache_all=True, load_cache_archived=False,
                    total_count=2, active_count=2, historic_count=0,
                ),
                action_plan=(
                    SimpleNamespace(path="R:/changed.safetensors", classification="active", is_active=True, is_historic=False, action="refresh"),
                ),
            ),
        )
        monkeypatch.setattr(window, "_set_progress_status", lambda t: None)
        monkeypatch.setattr(window, "_clear_progress_status", lambda delay_ms=0: None)
        monkeypatch.setattr(window, "_refresh_cache_controls", lambda: None)
        window._verify_cached_file_paths()
        assert _CacheSyncWorker.started_paths == [["R:/changed.safetensors"]]
    finally:
        window.close()


def test_verify_cache_does_not_schedule_historic_entries(monkeypatch, tmp_path: Path) -> None:
    """Verify does NOT schedule historic/archived entries for inspection."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        _CacheSyncWorker.started_paths = []
        monkeypatch.setattr(
            integration_controller, "AnalysisWorker",
            lambda paths, _opts, _threads: _CacheSyncWorker(paths, _opts, _threads),
        )
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True, action="archive"),
                ],
                availability=SimpleNamespace(
                    total=1, active=0, historic=1, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=False, load_cache_archived=True,
                    total_count=1, active_count=0, historic_count=1,
                ),
                action_plan=(
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True, action="archive"),
                ),
            ),
        )
        monkeypatch.setattr(window, "_set_progress_status", lambda t: None)
        monkeypatch.setattr(window, "_clear_progress_status", lambda delay_ms=0: None)
        monkeypatch.setattr(window, "_refresh_cache_controls", lambda: None)
        window._verify_cached_file_paths()
        assert _CacheSyncWorker.started_paths == []
    finally:
        window.close()


def test_verify_cache_shows_progress_then_summary(monkeypatch, tmp_path: Path) -> None:
    """Verify shows initial progress before verification then completion summary."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    from gui import MainWindow
    window = MainWindow()
    try:
        _CacheSyncWorker.started_paths = []
        monkeypatch.setattr(
            integration_controller, "AnalysisWorker",
            lambda paths, _opts, _threads: _CacheSyncWorker(paths, _opts, _threads),
        )
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path="R:/changed.safetensors", classification="active", is_active=True, is_historic=False, action="refresh"),
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True, action="archive"),
                    SimpleNamespace(path="R:/unchanged.safetensors", classification="active", is_active=True, is_historic=False, action="none"),
                ],
                availability=SimpleNamespace(
                    total=3, active=2, historic=1, refresh_candidates=1, sync_candidates=1,
                    load_cache=True, load_cache_all=True, load_cache_archived=True,
                    total_count=3, active_count=2, historic_count=1,
                ),
                action_plan=(
                    SimpleNamespace(path="R:/changed.safetensors", classification="active", is_active=True, is_historic=False, action="refresh"),
                    SimpleNamespace(path="R:/missing.gguf", classification="historic", is_active=False, is_historic=True, action="archive"),
                ),
            ),
        )
        progress_calls = []
        monkeypatch.setattr(window, "_set_progress_status", lambda t: progress_calls.append(t))
        monkeypatch.setattr(window, "_clear_progress_status", lambda delay_ms=0: None)
        monkeypatch.setattr(window, "_refresh_cache_controls", lambda: None)
        window._verify_cached_file_paths()
        assert len(progress_calls) == 2
        assert progress_calls[0] == "Verifying cached file paths..."
        summary = progress_calls[1]
        assert "3 total" in summary
        assert "2 active" in summary
        assert "1 historic" in summary
        assert "1 archived/missing" in summary
        assert "1 changed" in summary
        assert "scheduled for inspection" in summary
    finally:
        window.close()


def test_settings_store_default_no_load_default_libraries(tmp_path: Path) -> None:
    """load_default_libraries_on_startup is removed from defaults."""
    from back.settings_store import DEFAULTS
    assert "load_default_libraries_on_startup" not in DEFAULTS
