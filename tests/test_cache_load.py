from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import front.cache_load_worker as cache_load_worker
import model_cache
from PyQt6.QtCore import QThread
from PyQt6.QtWidgets import QApplication
from conftest import _summary
from front.cache_load_worker import CacheLoadOutcome, CacheLoadWorker


@pytest.mark.parametrize("allow_aliases", [False, True])
def test_persisted_summary_load_does_not_depend_on_cache_key_options(
    monkeypatch, tmp_path: Path, allow_aliases: bool
) -> None:
    """A compact UI load reads the persisted entry, not a default-option key."""
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"header")
    model_cache.store_cached_inspection(
        str(model),
        {"filepath": str(model), "filename": model.name, "format": "SAFETENSORS"},
        {"allow_filename_alias_detection": allow_aliases},
    )

    assert model_cache.get_cached_inspection_summary_snapshots([str(model)]) == {
        str(model): {
            "filepath": str(model),
            "filename": model.name,
            "format": "SAFETENSORS",
            "cache_status": "snapshot",
        }
    }


def test_cache_load_worker_selects_valid_and_historic_but_not_refresh(
    monkeypatch,
) -> None:
    valid = "R:/valid.safetensors"
    stale = "R:/stale.safetensors"
    historic = "R:/missing.gguf"
    report = SimpleNamespace(
        entries=(
            SimpleNamespace(path=valid, classification="active", action="none"),
            SimpleNamespace(path=stale, classification="active", action="refresh"),
            SimpleNamespace(path=historic, classification="historic", action="archive"),
        )
    )
    monkeypatch.setattr(cache_load_worker, "list_cached_inspection_paths", lambda: [valid, stale, historic])
    monkeypatch.setattr(cache_load_worker, "get_cached_inspection_identity_snapshots", lambda _paths: {})
    monkeypatch.setattr(cache_load_worker, "verify_cache_entries", lambda _entries: report)
    monkeypatch.setattr(
        cache_load_worker,
        "iter_cached_inspection_summary_snapshots",
        lambda paths, _cancelled: ((path, {"filepath": path}) for path in paths),
    )
    worker = CacheLoadWorker(None)
    loaded = []
    worker.summary_ready.connect(loaded.append)
    worker.run()

    assert loaded == [
        {"filepath": valid, "cache_status": "snapshot"},
        {"filepath": historic, "cache_status": "historic"},
    ]
    assert worker.outcome.stale_count == 1
    assert worker.max_outstanding_events == 16


def test_cache_load_worker_cancels_between_bounded_summary_events(monkeypatch) -> None:
    paths = [f"R:/cache/{index}.safetensors" for index in range(20)]
    report = SimpleNamespace(
        entries=tuple(
            SimpleNamespace(path=path, classification="active", action="none")
            for path in paths
        )
    )
    monkeypatch.setattr(cache_load_worker, "list_cached_inspection_paths", lambda: paths)
    monkeypatch.setattr(cache_load_worker, "get_cached_inspection_identity_snapshots", lambda _paths: {})
    monkeypatch.setattr(cache_load_worker, "verify_cache_entries", lambda _entries: report)
    monkeypatch.setattr(
        cache_load_worker,
        "iter_cached_inspection_summary_snapshots",
        lambda selected, _cancelled: ((path, {"filepath": path}) for path in selected),
    )
    worker = CacheLoadWorker("active")
    received = []

    def cancel_after_first(summary: dict) -> None:
        received.append(summary)
        worker.cancel()

    worker.summary_ready.connect(cancel_after_first)
    worker.run()

    assert len(received) == 1
    assert worker.outcome.was_cancelled


def test_cache_load_worker_limits_unacknowledged_ui_events(monkeypatch) -> None:
    paths = [f"R:/cache/{index}.safetensors" for index in range(20)]
    report = SimpleNamespace(
        entries=tuple(
            SimpleNamespace(path=path, classification="active", action="none")
            for path in paths
        )
    )
    monkeypatch.setattr(cache_load_worker, "list_cached_inspection_paths", lambda: paths)
    monkeypatch.setattr(cache_load_worker, "get_cached_inspection_identity_snapshots", lambda _paths: {})
    monkeypatch.setattr(cache_load_worker, "verify_cache_entries", lambda _entries: report)
    monkeypatch.setattr(
        cache_load_worker,
        "iter_cached_inspection_summary_snapshots",
        lambda selected, _cancelled: ((path, {"filepath": path}) for path in selected),
    )
    worker = CacheLoadWorker("active")
    received = []
    worker.summary_ready.connect(received.append)
    worker.start()
    app = QApplication.instance()
    assert app is not None
    deadline = time.monotonic() + 2
    while len(received) < worker.max_outstanding_events and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert len(received) == worker.max_outstanding_events
    assert worker.isRunning()
    worker.cancel()
    while worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not worker.isRunning()


class _SlowCacheLoadWorker(QThread):
    def __init__(self) -> None:
        super().__init__()
        self.cancel_called = False

    def cancel(self) -> None:
        self.cancel_called = True
        self.requestInterruption()

    def run(self) -> None:
        while not self.isInterruptionRequested():
            time.sleep(0.01)


def test_close_cancels_cache_load_worker(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    app = QApplication.instance()
    assert app is not None
    window = MainWindow()
    worker = _SlowCacheLoadWorker()
    window._cache_load_worker = worker
    worker.start()
    try:
        deadline = time.monotonic() + 2
        while not worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert worker.isRunning()
        window.close()
        while worker.isRunning() and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)
        assert not worker.isRunning()
        assert worker.cancel_called
    finally:
        worker.cancel()
        worker.wait(1000)
        window.close()


def test_zero_result_cache_load_reenables_visible_actions(
    monkeypatch, tmp_path: Path
) -> None:
    """A cancelled/failed load that produced no results re-enables the cache
    load actions without a synchronous cache re-report."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    app = QApplication.instance()
    assert app is not None
    window = MainWindow()
    try:
        availability = SimpleNamespace(
            load_cache=True, load_cache_all=True, load_cache_archived=True
        )
        monkeypatch.setattr(
            window,
            "_cache_report",
            lambda: SimpleNamespace(availability=availability),
        )
        window._refresh_cache_menu_actions()
        assert window._cache_load_active_action.isVisible()
        # Simulate the disable performed at load start.
        for name in (
            "_cache_load_active_action",
            "_cache_load_all_action",
            "_cache_load_archived_action",
        ):
            getattr(window, name).setEnabled(False)
        worker = SimpleNamespace(
            outcome=CacheLoadOutcome(stale_count=0, was_cancelled=True)
        )
        window._cache_load_worker = worker
        window._finish_cache_load_projection(worker)
        assert window._cache_load_active_action.isEnabled()
        assert window._cache_load_all_action.isEnabled()
        assert window._cache_load_archived_action.isEnabled()
    finally:
        window.close()


def test_injected_cache_load_matches_worker_selection(
    monkeypatch, tmp_path: Path
) -> None:
    """The injection seam selects/labels summaries exactly like the worker:
    historic -> "historic", active action "none" -> "snapshot", stale skipped."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    app = QApplication.instance()
    assert app is not None
    window = MainWindow()
    try:
        report = SimpleNamespace(
            entries=(
                SimpleNamespace(
                    path="R:/active.safetensors",
                    classification="active",
                    action="none",
                ),
                SimpleNamespace(
                    path="R:/stale.safetensors",
                    classification="active",
                    action="refresh",
                ),
                SimpleNamespace(
                    path="R:/historic.gguf",
                    classification="historic",
                    action="archive",
                ),
            )
        )
        monkeypatch.setattr(window, "_cache_report", lambda: report)
        snapshots = {
            "R:/active.safetensors": _summary(
                "R:/active.safetensors", "Arch", "Checkpoint"
            ),
            "R:/stale.safetensors": _summary(
                "R:/stale.safetensors", "Arch", "Checkpoint"
            ),
            "R:/historic.gguf": _summary(
                "R:/historic.gguf", "Arch", "Checkpoint"
            ),
        }
        requested: list[list[str]] = []

        def loader(paths):
            requested.append(list(paths))
            return {path: snapshots[path] for path in paths}

        monkeypatch.setattr(
            window, "_get_cached_inspection_summary_snapshots", loader
        )
        window._load_cache_all()  # wanted=None
        assert requested == [["R:/active.safetensors", "R:/historic.gguf"]]
        statuses = {data["filepath"]: data["cache_status"] for data in window._results}
        assert statuses == {
            "R:/active.safetensors": "snapshot",
            "R:/historic.gguf": "historic",
        }
    finally:
        window.close()
