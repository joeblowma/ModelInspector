# pyright: reportAttributeAccessIssue=false
"""Cache-load UI flow, kept separate from Settings integration bindings."""

from __future__ import annotations

from pathlib import Path

from front.cache_load_worker import CacheLoadWorker
from front.scan_projection import ProjectionEvent


class CacheLoadControllerMixin:
    """Project persisted cache summaries off the GUI thread in bounded batches."""

    def _load_cache_status(self, wanted: str | None) -> None:
        if getattr(self, "_cache_load_worker", None) is not None:
            return
        loader = self._get_cached_inspection_summary_snapshots
        if getattr(loader, "__self__", None) is not self:
            self._clear_all()
            self._disable_table_sorting_for_cache_load()
            self._load_injected_cache_summaries(wanted, loader)
            return
        if self._worker and self._worker.isRunning():
            self._set_progress_status("Wait for analysis to finish before loading cache.")
            return
        # Load Cache replaces the current view rather than appending to it, so
        # clear first even for repeated loads.
        self._clear_all()
        self._disable_table_sorting_for_cache_load()
        generation = self._projection.begin()
        worker = CacheLoadWorker(wanted)
        self._cache_load_worker = worker
        self._cache_load_generation = generation
        self._cache_load_wanted = wanted
        self._cache_load_projected_count = 0
        self._cache_load_progress_total = 0
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._set_cancel_available(True)
        self._set_progress_status("Finding cached entries...")
        for name in (
            "_cache_load_active_action",
            "_cache_load_all_action",
            "_cache_load_archived_action",
        ):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(False)
        worker.report_ready.connect(
            lambda report, g=generation, w=worker: self._on_cache_load_report(g, w, report)
        )
        worker.progress_ready.connect(
            lambda phase, done, total, g=generation, w=worker: self._on_cache_load_progress(
                g, w, phase, done, total
            )
        )
        worker.summary_ready.connect(
            lambda data, g=generation, w=worker: self._on_cache_load_summary(g, w, data)
        )
        worker.all_done.connect(
            lambda g=generation, w=worker: self._on_cache_load_done(g, w)
        )
        worker.start()

    def _load_injected_cache_summaries(self, wanted: str | None, loader) -> None:
        """Retain the public MainWindow cache-summary injection seam for tests.

        Mirrors ``CacheLoadWorker.run`` selection: historic entries load as
        ``historic``, active entries with action ``none`` load as ``snapshot``,
        and stale/refresh entries are skipped (they sync instead of loading).
        """
        report = self._cache_report()
        statuses: dict[str, str] = {}
        for entry in report.entries:
            if entry.classification == "historic":
                if wanted in (None, "historic"):
                    statuses[entry.path] = "historic"
            elif getattr(entry, "action", "none") == "none":
                if wanted in (None, "active"):
                    statuses[entry.path] = "snapshot"
        loaded = 0
        for path, data in loader(list(statuses)).items():
            if self._result_for_filepath(path):
                continue
            data = dict(data)
            data.update(
                {
                    "filepath": path,
                    "filename": str(data.get("filename") or Path(path).name),
                    "cache_status": statuses[path],
                }
            )
            self._project_cache_result(data)
            loaded += 1
        self._reconcile_projected_results(True)
        self._restore_table_sorting()
        self._set_progress_status(f"Loaded {loaded} cached summaries")

    def _load_cache(self) -> None:
        self._load_cache_status("active")

    def _load_cache_all(self) -> None:
        self._load_cache_status(None)

    def _load_cache_archived(self) -> None:
        self._load_cache_status("historic")

    def _on_cache_load_report(self, generation: int, worker, report) -> None:
        if generation != self._cache_load_generation or worker is not self._cache_load_worker:
            return
        self._schedule_cache_sync(report)

    def _on_cache_load_progress(
        self, generation: int, worker, phase: str, completed: int, total: int
    ) -> None:
        if (
            generation != self._cache_load_generation
            or worker is not self._cache_load_worker
            or getattr(self, "_lifecycle_closed", False)
        ):
            return
        if phase == "scan":
            self.progress.setRange(0, 0)
            self._set_progress_status("Finding cached entries...")
        elif phase == "verify":
            self.progress.setRange(0, max(1, total))
            self.progress.setValue(completed)
            self._set_progress_status(f"Verifying cached entries ({completed}/{total})")
        elif phase == "load":
            self._cache_load_progress_total = total
            self._cache_load_projected_count = 0
            self.progress.setRange(0, max(1, total + 1))
            self.progress.setValue(0)
            self._set_progress_status(f"Loading cached summaries (0/{total})")

    def _on_cache_load_summary(self, generation: int, worker, data: dict) -> None:
        if (
            generation != self._cache_load_generation
            or worker is not self._cache_load_worker
            or getattr(self, "_lifecycle_closed", False)
        ):
            worker.acknowledge_event()
            return
        self._projection.enqueue(
            ProjectionEvent(generation, "cache_result", data, worker.acknowledge_event)
        )

    def _on_cache_load_done(self, generation: int, worker) -> None:
        if generation != self._cache_load_generation or worker is not self._cache_load_worker:
            return
        if getattr(self, "_lifecycle_closed", False):
            self._cache_load_worker = None
            return
        self._projection.mark_terminal(generation, worker)

    def _project_cache_result(self, data: dict) -> None:
        filepath = str(data.get("filepath") or "")
        if not filepath or self._result_for_filepath(filepath):
            return
        data.pop("_cache_key", None)
        data.pop("_cache_options", None)
        data["filename"] = str(data.get("filename") or Path(filepath).name)
        self._normalize_result_data(data)
        self._queued_files.append(filepath)
        self._results.append(data)
        self._add_card(data)
        self._add_table_row(data)
        self._apply_visibility_to_projected_item(data)
        if hasattr(self, "_cache_load_projected_count"):
            self._cache_load_projected_count += 1
            total = self._cache_load_progress_total
            self.progress.setValue(min(self._cache_load_projected_count, total))
            self._set_progress_status(
                f"Loading cached summaries ({self._cache_load_projected_count}/{total})"
            )

    def _disable_table_sorting_for_cache_load(self) -> None:
        """Disable live sorting while batch-inserting cached rows.

        Mirrors the analysis path so cache rows are never inserted under an
        active sort indicator; the saved state is restored when the load ends.
        """
        header = self.table.horizontalHeader()
        assert header is not None
        self._table_sort_restore = (
            self.table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        self.table.setSortingEnabled(False)

    def _finish_cache_load_projection(self, worker) -> None:
        if worker is not self._cache_load_worker:
            return
        self._cache_load_worker = None
        self._restore_table_sorting()
        self._apply_arch_filter()
        outcome = worker.outcome
        if outcome.was_cancelled:
            message = "Cache loading cancelled; partial summaries remain visible"
        else:
            self.progress.setValue(max(1, getattr(self, "_cache_load_progress_total", 0) + 1))
            count = len(self._results)
            message = f"Loaded {count} cached summaries"
            if outcome.stale_count:
                message += f"; {outcome.stale_count} stale entries syncing"
        self._set_progress_status(message)
        self._clear_progress_status(delay_ms=4000)
        # Re-enable visible actions after every load so repeated loads remain
        # possible (each load clears the current view first).
        self._re_enable_cache_load_actions()

    def _re_enable_cache_load_actions(self) -> None:
        """Re-enable available cache-load actions after a load completes.

        Visibility already encodes availability and does not change during a
        load, so only the visible actions are re-enabled.  This avoids a
        synchronous cache re-report on the GUI thread.
        """
        for name in (
            "_cache_load_active_action",
            "_cache_load_all_action",
            "_cache_load_archived_action",
        ):
            action = getattr(self, name, None)
            if action is not None and action.isVisible():
                action.setEnabled(True)
