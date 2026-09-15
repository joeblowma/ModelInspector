# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Cache menu and manual cache-verification integration contracts."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

import front.integration_controller as integration_controller
from front.integration_controller import IntegrationMixin


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

    def isRunning(self) -> bool:
        return False


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


# ---------------------------------------------------------------------------
# Cache entry classification & sync scheduling
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Cache-load menu labels, visibility, and enabled states
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Manual cache verification (verify cached file paths)
# ---------------------------------------------------------------------------


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
