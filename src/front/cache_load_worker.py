"""Bounded background delivery of persisted cache summaries."""

from __future__ import annotations

import threading
from dataclasses import dataclass

from PyQt6.QtCore import QThread, pyqtSignal

from back.cache_verifier import verify_cache_entries
from front.cache_identity import get_cached_inspection_identity_snapshots
from model_cache import (
    iter_cached_inspection_summary_snapshots,
    list_cached_inspection_paths,
)


@dataclass(frozen=True)
class CacheLoadOutcome:
    stale_count: int
    was_cancelled: bool


class CacheLoadWorker(QThread):
    """Read compact persisted summaries without inspecting any model files."""

    summary_ready = pyqtSignal(dict)
    report_ready = pyqtSignal(object)
    all_done = pyqtSignal()

    def __init__(self, wanted: str | None) -> None:
        super().__init__()
        self.wanted = wanted
        self.outcome = CacheLoadOutcome(0, False)
        self._cancel_requested = threading.Event()
        self._capacity = threading.Condition()
        self._outstanding = 0
        self.max_outstanding_events = 16

    def cancel(self) -> None:
        self._cancel_requested.set()
        self.requestInterruption()
        with self._capacity:
            self._capacity.notify_all()

    def acknowledge_event(self) -> None:
        with self._capacity:
            self._outstanding = max(0, self._outstanding - 1)
            self._capacity.notify_all()

    def _cancelled(self) -> bool:
        return self._cancel_requested.is_set() or self.isInterruptionRequested()

    def _emit_summary(self, summary: dict) -> bool:
        with self._capacity:
            while self._outstanding >= self.max_outstanding_events and not self._cancelled():
                self._capacity.wait(timeout=0.05)
            if self._cancelled():
                return False
            self._outstanding += 1
        self.summary_ready.emit(summary)
        return True

    def run(self) -> None:
        stale_count = 0
        try:
            paths = list_cached_inspection_paths()
            identities = get_cached_inspection_identity_snapshots(paths)
            report = verify_cache_entries(
                [identities.get(path, {"filepath": path}) for path in paths]
            )
            self.report_ready.emit(report)
            statuses: dict[str, str] = {}
            for entry in report.entries:
                if self._cancelled():
                    break
                if entry.classification == "historic":
                    if self.wanted in (None, "historic"):
                        statuses[entry.path] = "historic"
                elif entry.action == "none":
                    if self.wanted in (None, "active"):
                        statuses[entry.path] = "snapshot"
                else:
                    stale_count += 1
            for path, summary in iter_cached_inspection_summary_snapshots(
                list(statuses), self._cancelled
            ):
                if self._cancelled() or not self._emit_summary(
                    {
                        **summary,
                        "filepath": path,
                        "cache_status": statuses[path],
                    }
                ):
                    break
        finally:
            self.outcome = CacheLoadOutcome(stale_count, self._cancelled())
            self.all_done.emit()
