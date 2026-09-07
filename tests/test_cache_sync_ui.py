# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Focused UI contracts for cache-sync refresh and action availability."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6 import sip
from PyQt6.QtCore import QObject
from PyQt6.QtWidgets import QApplication

from back.cache_verifier import CacheAvailability, CacheVerificationReport
from conftest import _summary


def _availability(**overrides) -> CacheAvailability:
    values = {
        "total": 0,
        "active": 0,
        "historic": 0,
        "refresh_candidates": 0,
        "sync_candidates": 0,
    }
    values.update(overrides)
    return CacheAvailability(**values)


class _FakeLabel:
    def __init__(self) -> None:
        self.text = ""

    def setText(self, text: str) -> None:
        self.text = text


class _FakeButton:
    def __init__(self) -> None:
        self.enabled = False

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class _FakeDialog(QObject):
    def __init__(self) -> None:
        super().__init__()
        self.cache_counts_label = _FakeLabel()
        self.verify_cache_btn = _FakeButton()


_APP: QApplication | None = None


def _window(monkeypatch, tmp_path: Path):
    global _APP
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    # Hold a reference for the test's lifetime: GC would destroy all widgets.
    _APP = QApplication.instance() or QApplication([])
    return MainWindow()


def _report(availability: CacheAvailability, entries=(), action_plan=()) -> SimpleNamespace:
    return SimpleNamespace(
        entries=entries,
        availability=availability,
        action_plan=action_plan,
    )


# ---------------------------------------------------------------------------
# F1: cache-load actions disable as soon as a result lands or a cache load runs
# ---------------------------------------------------------------------------


def test_result_landing_disables_cache_load_actions(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        availability = _availability(total=1, active=1)
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(availability),
        )
        window._refresh_cache_menu_actions()
        assert window._cache_load_active_action.isVisible()
        assert window._cache_load_active_action.isEnabled()

        # A result lands: the projection path appends to _results, then renders.
        landed = _summary("R:/landed.safetensors", "Arch", "Checkpoint")
        window._results.append(landed)
        window._add_table_row(landed)
        assert not window._cache_load_active_action.isEnabled()
        assert not window._cache_load_all_action.isEnabled()
        assert not window._cache_load_archived_action.isEnabled()
    finally:
        window.close()


def test_cache_load_disables_actions_after_loading(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        cached = "R:/cached.safetensors"
        availability = _availability(total=1, active=1)
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(
                availability,
                entries=(SimpleNamespace(path=cached, classification="active"),),
            ),
        )
        monkeypatch.setattr(
            window, "_get_cached_inspection_summary_snapshots",
            lambda _paths: {cached: _summary(cached, "Arch", "Checkpoint")},
        )
        window._load_cache()
        assert not window._cache_load_active_action.isEnabled()
        assert not window._cache_load_all_action.isEnabled()
    finally:
        window.close()


# ---------------------------------------------------------------------------
# F2: historic-only cache keeps Load Cache All / Archived but hides Load Cache
# ---------------------------------------------------------------------------


def test_historic_only_cache_hides_active_load_but_keeps_all_and_archived(
    monkeypatch, tmp_path: Path
) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        # total=1 but active=0: only a historic summary is cached.
        availability = _availability(total=1, active=0, historic=1)
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(availability),
        )
        window._refresh_cache_menu_actions()
        assert not window._cache_load_active_action.isVisible()
        assert window._cache_load_all_action.isVisible()
        assert window._cache_load_archived_action.isVisible()
    finally:
        window.close()


# ---------------------------------------------------------------------------
# F5: background sync completion refreshes an open Settings dialog safely
# ---------------------------------------------------------------------------


def test_sync_completion_refreshes_open_settings_dialog(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        fake = _FakeDialog()
        window._settings_dialog = fake
        state = {"availability": _availability(total=0)}
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(state["availability"]),
        )
        window._on_cache_sync_completed()
        assert fake.cache_counts_label.text == "Total: 0  Active: 0  Historic: 0"
        assert fake.verify_cache_btn.enabled is False

        state["availability"] = _availability(total=3, active=2, historic=1)
        window._on_cache_sync_completed()
        assert fake.cache_counts_label.text == "Total: 3  Active: 2  Historic: 1"
        assert fake.verify_cache_btn.enabled is True
    finally:
        window.close()


def test_sync_completion_skips_deleted_settings_dialog(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        fake = _FakeDialog()
        window._settings_dialog = fake
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(_availability(total=2, active=1, historic=1)),
        )
        sip.delete(fake)
        # Must not raise on dangling dialog access.
        window._on_cache_sync_completed()
    finally:
        window.close()


# ---------------------------------------------------------------------------
# F6: manual verification summary distinguishes scheduled vs already-syncing
# ---------------------------------------------------------------------------


def test_verify_summary_marks_already_syncing_when_worker_exists(
    monkeypatch, tmp_path: Path
) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        window._cache_sync_worker = object()  # a running sync worker sentinel
        availability = _availability(total=1, active=1)
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: _report(
                availability,
                action_plan=(SimpleNamespace(action="refresh"),),
            ),
        )
        scheduled = []
        monkeypatch.setattr(window, "_schedule_cache_sync", lambda: scheduled.append(True))
        progress_calls = []
        monkeypatch.setattr(window, "_set_progress_status", lambda t: progress_calls.append(t))
        monkeypatch.setattr(window, "_clear_progress_status", lambda delay_ms=0: None)
        monkeypatch.setattr(window, "_refresh_cache_controls", lambda: None)
        window._verify_cached_file_paths()
        summary = progress_calls[1]
        assert "1 changed" in summary
        assert "already being synced" in summary
        assert "scheduled for inspection" not in summary
    finally:
        window.close()
