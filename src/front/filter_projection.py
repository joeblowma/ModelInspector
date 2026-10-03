"""Chunked GUI filter projection and normalized path identity helpers."""

from __future__ import annotations

import os
import weakref
from collections.abc import Callable

from PyQt6.QtCore import QTimer


def path_identity(filepath: str) -> str:
    """Return a case-aware identity for equivalent lexical and symlink paths."""
    return os.path.normcase(os.path.realpath(filepath))


def _project_one(
    data,
    active_arch,
    active_tags,
    active_formats,
    get_tags,
    get_format,
    apply_visibility,
    counts,
) -> None:
    filepath = str(data.get("filepath") or "")
    if not filepath:
        return
    architecture = data.get("architecture", "")
    tags = get_tags(data)
    tag_set = set(tags)
    file_format = get_format(data)
    arch_match = active_arch is None or architecture in active_arch
    tag_match = active_tags is None or bool(tag_set & active_tags)
    format_match = active_formats is None or file_format in active_formats
    arch_counts, tag_counts, format_counts = counts
    if tag_match and format_match:
        arch_counts[architecture] = arch_counts.get(architecture, 0) + 1
    if arch_match and format_match:
        for tag in tags:
            tag_counts[tag] = tag_counts.get(tag, 0) + 1
    if arch_match and tag_match:
        format_counts[file_format] = format_counts.get(file_format, 0) + 1
    apply_visibility(filepath, arch_match and tag_match and format_match)


class FilterProjection:
    """Apply filter visibility in event-loop batches, keeping the latest request."""

    _BATCH_SIZE = 32
    _ASYNC_THRESHOLD = 64

    def __init__(self, owner):
        self._owner = weakref.ref(owner)
        self._timer = QTimer(owner)
        self._timer.setSingleShot(True)
        self._timer.timeout.connect(self._process_batch)
        self._generation = 0
        self._pending = False

    @property
    def pending(self) -> bool:
        return self._pending

    @property
    def index(self) -> int:
        return self._index

    def cancel(self) -> None:
        self._timer.stop()
        self._generation += 1
        self._pending = False

    def request(
        self,
        results: list[dict],
        active_arch: set[str] | None,
        active_tags: set[str] | None,
        active_formats: set[str] | None,
        *,
        get_tags: Callable[[dict], list[str]],
        get_format: Callable[[dict], str],
        apply_visibility: Callable[[str, bool], None],
        report_progress: Callable[[int, int], None],
        complete: Callable[[dict[str, int], dict[str, int], dict[str, int]], None],
        responsive: bool,
    ) -> None:
        self._timer.stop()
        self._generation += 1
        self._results = list(results)
        self._active_arch = None if active_arch is None else set(active_arch)
        self._active_tags = None if active_tags is None else set(active_tags)
        self._active_formats = None if active_formats is None else set(active_formats)
        self._get_tags = get_tags
        self._get_format = get_format
        self._apply_visibility = apply_visibility
        self._report_progress = report_progress
        self._complete = complete
        self._arch_counts: dict[str, int] = {}
        self._tag_counts: dict[str, int] = {}
        self._format_counts: dict[str, int] = {}
        self._index = 0
        self._pending = True
        self._batch_size = (
            self._BATCH_SIZE
            if responsive and len(self._results) >= self._ASYNC_THRESHOLD
            else max(1, len(self._results))
        )
        self._process_batch()

    def _process_batch(self) -> None:
        if not self._pending:
            return
        owner = self._owner()
        if owner is None or getattr(owner, "_close_pending", False) or getattr(
            owner, "_lifecycle_closed", False
        ):
            self._pending = False
            return

        generation = self._generation
        end = min(self._index + self._batch_size, len(self._results))
        for data in self._results[self._index:end]:
            _project_one(
                data,
                self._active_arch,
                self._active_tags,
                self._active_formats,
                self._get_tags,
                self._get_format,
                self._apply_visibility,
                (self._arch_counts, self._tag_counts, self._format_counts),
            )
            self._index += 1

        if generation != self._generation:
            return
        self._report_progress(self._index, len(self._results))
        if self._index < len(self._results):
            self._timer.start(0)
            return

        self._pending = False
        self._complete(self._arch_counts, self._tag_counts, self._format_counts)


def apply_filter_projection(
    owner,
    *,
    refresh_raw: bool,
    refresh_geometry: bool,
    update_selection: bool,
) -> None:
    """Project current filter state and finalize dependent UI once per request."""
    results = list(owner._results)
    projection = getattr(owner, "_filter_projection", None)
    responsive = refresh_raw and refresh_geometry
    status_restore = getattr(owner, "_filter_status_restore", None)
    workers = (
        getattr(owner, "_worker", None),
        getattr(owner, "_cache_load_worker", None),
        getattr(owner, "_cache_sync_worker", None),
    )
    analysis_running = any(worker and worker.isRunning() for worker in workers)
    if responsive and not analysis_running and status_restore is None:
        owner._filter_status_restore = (
            owner.progress_label.text(),
            owner.progress_label.toolTip(),
        )

    def apply_visibility(filepath: str, visible: bool) -> None:
        card = owner._path_to_card.get(filepath)
        if card:
            card.set_filter_visible(visible)
        row = owner._row_for_filepath(filepath)
        if row is not None and 0 <= row < owner.table.rowCount():
            if owner.table.isRowHidden(row) != (not visible):
                owner.table.setRowHidden(row, not visible)

    def report_progress(done: int, total: int) -> None:
        if not responsive or owner._filter_status_restore is None:
            return
        previous_generation = getattr(owner, "_filter_status_generation", None)
        if (
            previous_generation is not None
            and owner._progress_status_generation != previous_generation
        ):
            owner._filter_status_restore = None
            owner._filter_status_generation = None
            return
        owner._set_progress_status(f"Updating filters: {done}/{total} models")
        owner._filter_status_generation = owner._progress_status_generation

    def complete(arch_counts, tag_counts, format_counts) -> None:
        owner.arch_filter_btn.set_counts(arch_counts)
        owner.tag_filter_btn.set_counts(tag_counts)
        owner.format_filter_btn.set_counts(format_counts)
        if refresh_geometry:
            owner._refresh_card_layout_geometry()
        if refresh_raw:
            owner._refresh_raw_combo_filtered()
        if update_selection:
            owner._update_selection_ui_state()
        saved_status = getattr(owner, "_filter_status_restore", None)
        expected_generation = getattr(owner, "_filter_status_generation", None)
        if (
            saved_status is not None
            and expected_generation is not None
            and owner._progress_status_generation == expected_generation
        ):
            owner._set_progress_status(saved_status[0])
            owner.progress_label.setToolTip(saved_status[1])
        owner._filter_status_restore = None
        owner._filter_status_generation = None

    if not responsive or len(results) < FilterProjection._ASYNC_THRESHOLD:
        if projection is not None:
            projection.cancel()
        counts = ({}, {}, {})
        for data in results:
            _project_one(
                data,
                owner._active_arch_filter,
                owner._active_tag_filter,
                owner._active_format_filter,
                owner._filter_tags_for_data,
                owner._format_filter_for_data,
                apply_visibility,
                counts,
            )
        complete(*counts)
        return

    if projection is None:
        projection = FilterProjection(owner)
        owner._filter_projection = projection
    projection.request(
        results,
        owner._active_arch_filter,
        owner._active_tag_filter,
        owner._active_format_filter,
        get_tags=owner._filter_tags_for_data,
        get_format=owner._format_filter_for_data,
        apply_visibility=apply_visibility,
        report_progress=report_progress,
        complete=complete,
        responsive=responsive,
    )
