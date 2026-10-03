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
from PyQt6.QtCore import QThread, QTimer
from PyQt6.QtWidgets import QApplication, QLabel
from conftest import _summary
from front.cache_load_worker import CacheLoadOutcome, CacheLoadWorker


def _patch_cache_worker(monkeypatch, paths, report):
    entries = [{"filepath": path, "cache_key": path, "cache_options": None,
                "entry": {"data": {"filepath": path}}} for path in paths]
    monkeypatch.setattr(cache_load_worker, "list_cached_inspection_entries", lambda _cancel=None: entries)
    monkeypatch.setattr(cache_load_worker, "get_cached_inspection_entry_identity_snapshots", lambda selected: {
        item["cache_key"]: {key: item[key] for key in ("filepath", "cache_key", "cache_options")}
        for item in selected
    })
    monkeypatch.setattr(cache_load_worker, "verify_cache_entries", lambda _entries, **_kwargs: report)
    monkeypatch.setattr(cache_load_worker, "iter_cached_inspection_entry_summary_snapshots", lambda selected, cancel: (
        (item, {"filepath": item["filepath"]}) for item in selected if not cancel()
    ))


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


def test_cache_entry_identity_roundtrips_options_and_path_alias(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    alias = tmp_path / "old-name.safetensors"
    model.write_bytes(b"old")
    ordered_options = sorted((False, True), key=lambda option: model_cache._entry_id(
        model_cache._cache_key(str(model), {"allow_filename_alias_detection": option})
    ))
    chosen_option, stale_option = ordered_options
    def store(content, name, option):
        model.write_bytes(content)
        model_cache.store_cached_inspection(
            str(model), {"filepath": str(model), "alias": str(alias), "filename": name},
            {"allow_filename_alias_detection": option},
        )

    store(b"old", "stale-entry.safetensors", stale_option)
    chosen_options = {"allow_filename_alias_detection": chosen_option}
    store(b"current file has a different size", "chosen-entry.safetensors", chosen_option)

    selected = model_cache.list_cached_inspection_entries()
    assert len(selected) == 1
    expected_key = model_cache._cache_key(str(model), chosen_options)
    assert selected[0]["cache_key"] == expected_key
    assert selected[0]["cache_options"] == chosen_options
    assert model_cache.list_cached_inspection_paths() == [str(model)]

    worker = CacheLoadWorker("active")
    loaded = []
    reports = []
    worker.summary_ready.connect(loaded.append)
    worker.report_ready.connect(reports.append)
    worker.run()

    assert len(reports[0].entries) == 1
    assert reports[0].entries[0].action == "none"
    assert reports[0].entries[0].cache_key == expected_key
    assert reports[0].entries[0].cache_options == chosen_options
    assert reports[0].entries[0].path == str(model)
    assert str(alias) in reports[0].entries[0].path_aliases
    assert worker.outcome.stale_count == 0
    assert len(loaded) == 1
    assert loaded[0]["filename"] == "chosen-entry.safetensors"
    assert loaded[0]["_cache_key"] == expected_key
    assert loaded[0]["_cache_options"] == chosen_options


def test_cache_load_worker_selects_valid_and_historic_but_not_refresh(
    monkeypatch,
) -> None:
    valid = "R:/valid.safetensors"
    stale = "R:/stale.safetensors"
    historic = "R:/missing.gguf"
    report = SimpleNamespace(
        entries=(
            SimpleNamespace(path=valid, classification="active", action="none", cache_key=valid),
            SimpleNamespace(path=stale, classification="active", action="refresh", cache_key=stale),
            SimpleNamespace(path=historic, classification="historic", action="archive", cache_key=historic),
        )
    )
    _patch_cache_worker(monkeypatch, [valid, stale, historic], report)
    worker = CacheLoadWorker(None)
    loaded = []
    worker.summary_ready.connect(loaded.append)
    worker.run()

    assert loaded == [
        {"filepath": valid, "cache_status": "snapshot", "_cache_key": valid, "_cache_options": None},
        {"filepath": historic, "cache_status": "historic", "_cache_key": historic, "_cache_options": None},
    ]
    assert worker.outcome.stale_count == 1
    assert worker.max_outstanding_events == 16


def test_cache_load_worker_cancels_between_bounded_summary_events(monkeypatch) -> None:
    paths = [f"R:/cache/{index}.safetensors" for index in range(20)]
    report = SimpleNamespace(
        entries=tuple(
            SimpleNamespace(path=path, classification="active", action="none", cache_key=path)
            for path in paths
        )
    )
    _patch_cache_worker(monkeypatch, paths, report)
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
            SimpleNamespace(path=path, classification="active", action="none", cache_key=path)
            for path in paths
        )
    )
    _patch_cache_worker(monkeypatch, paths, report)
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
    timer_observations = []
    QTimer.singleShot(
        0,
        lambda: (timer_observations.append(worker.isRunning()), worker.cancel()),
    )
    while worker.isRunning() and time.monotonic() < deadline:
        app.processEvents()
        time.sleep(0.01)
    assert not worker.isRunning()
    assert timer_observations == [True]


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


def test_historic_cache_load_reports_phases_and_keeps_gui_timer_responsive(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    active = tmp_path / "active.safetensors"
    historic = tmp_path / "historic.gguf"
    active.write_bytes(b"active")
    historic.write_bytes(b"historic")
    for model in (active, historic):
        model_cache.store_cached_inspection(
            str(model), _summary(str(model), "Arch", "Checkpoint")
        )
    historic.unlink()

    from gui import MainWindow

    app = QApplication.instance()
    assert app is not None
    original_iterator = cache_load_worker.iter_cached_inspection_entry_summary_snapshots

    def delayed_summaries(entries, should_cancel):
        for selected, summary in original_iterator(entries, should_cancel):
            time.sleep(0.02)
            if should_cancel():
                return
            yield selected, summary

    monkeypatch.setattr(
        cache_load_worker,
        "iter_cached_inspection_entry_summary_snapshots",
        delayed_summaries,
    )
    window = MainWindow()
    progress_texts = []
    progress_states = []
    window.progress.valueChanged.connect(
        lambda value: progress_states.append((value, window.progress.maximum()))
    )
    set_status = window._set_progress_status

    def capture_status(text):
        progress_texts.append(text)
        set_status(text)

    monkeypatch.setattr(window, "_set_progress_status", capture_status)
    timer_ran_while_loading = []
    worker = None
    try:
        window._load_cache_all()
        worker = window._cache_load_worker
        assert worker is not None
        QTimer.singleShot(0, lambda: timer_ran_while_loading.append(worker.isRunning()))
        deadline = time.monotonic() + 4
        while window._cache_load_worker is not None and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.005)
        app.processEvents()

        assert window._cache_load_worker is None
        assert timer_ran_while_loading == [True]
        assert "Verifying cached entries (1/2)" in progress_texts
        assert "Verifying cached entries (2/2)" in progress_texts
        assert "Loading cached summaries (1/2)" in progress_texts
        assert "Loading cached summaries (2/2)" in progress_texts
        assert progress_texts[-1] == "Loaded 2 cached summaries"
        assert window.progress.value() == window.progress.maximum()
        assert progress_states.index((2, 3)) < progress_states.index((3, 3))
        assert {
            data["cache_status"] for data in window._results
    } == {"snapshot", "historic"}
    finally:
        if worker is not None and worker.isRunning():
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


def test_full_cache_load_projects_historic_tag_and_visible_filter_counts(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    app = QApplication.instance()
    assert app is not None
    window = MainWindow()
    active = "R:/active.safetensors"
    historic = "R:/historic/missing.gguf"
    try:
        monkeypatch.setattr(
            window,
            "_cache_report",
            lambda: SimpleNamespace(
                entries=(
                    SimpleNamespace(path=active, classification="active", action="none"),
                    SimpleNamespace(path=historic, classification="historic", action="archive"),
                )
            ),
        )
        snapshots = {
            active: _summary(active, "ActiveArch", "Checkpoint"),
            historic: _summary(historic, "HistoricArch", "Checkpoint"),
        }
        monkeypatch.setattr(
            window,
            "_get_cached_inspection_summary_snapshots",
            lambda paths: {path: snapshots[path] for path in paths},
        )

        window._load_cache_all()

        historic_data = next(data for data in window._results if data["filepath"] == historic)
        assert historic_data["cache_status"] == "historic"
        assert "Historic" in window._filter_tags_for_data(historic_data)
        assert "Historic" in window.tag_filter_btn._arch_checks
        historic_card = window._path_to_card[historic]
        assert any(label.text() == "Historic" for label in historic_card.findChildren(QLabel))
        historic_row = window._row_for_filepath(historic)
        active_row = window._row_for_filepath(active)
        assert historic_row is not None and active_row is not None
        format_column = window._table_columns.index("Format")
        format_item = window.table.item(historic_row, format_column)
        assert format_item is not None and "Historic" in format_item.text()

        window._on_tag_filter_changed({"Historic"})
        assert not window.table.isRowHidden(historic_row)
        assert window.table.isRowHidden(active_row)
        assert window.arch_filter_btn._counts["HistoricArch"] == 1
        assert window.arch_filter_btn._counts["ActiveArch"] == 0
        assert window.arch_filter_btn._arch_checks["ActiveArch"].isChecked()

        window._on_tag_filter_changed(None)
        assert window.arch_filter_btn._counts["HistoricArch"] == 1
        assert window.arch_filter_btn._counts["ActiveArch"] == 1
    finally:
        window.close()
