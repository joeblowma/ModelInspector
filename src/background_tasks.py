#!/usr/bin/env python3
"""Bounded background task processing for Model Inspector."""

import os
import threading
import time
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from pathlib import Path
from typing import Any, Iterable, Optional

from PyQt6.QtCore import QThread, pyqtSignal

from back.inspection_summary import compact_inspection_summary
from back.inspection_pipeline import inspect_file
from model_readers import CHECKPOINT_MODEL_EXTENSIONS, SUPPORTED_MODEL_EXTENSIONS
from back.shard_discovery import discoverable_primary_path, is_safetensors_index_path
from back.sidecar_discovery import is_probable_sidecar_path


class DiscoveryWorker(QThread):
    """Discover supported model paths without touching GUI state."""

    progress_updated = pyqtSignal(dict)
    discovery_done = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)

    def __init__(
        self,
        root: str,
        extensions: Iterable[str] = SUPPORTED_MODEL_EXTENSIONS,
        checkpoint_safety: str = "reject",
    ):
        super().__init__()
        self.root = str(root)
        selected_extensions = tuple(str(ext).lower() for ext in extensions)
        if checkpoint_safety == "metadata":
            selected_extensions += CHECKPOINT_MODEL_EXTENSIONS
        self.extensions = tuple(dict.fromkeys(selected_extensions))
        self.checkpoint_safety = checkpoint_safety
        self._cancel_requested = threading.Event()

    def cancel(self) -> None:
        """Request cooperative cancellation of the directory walk."""
        self._cancel_requested.set()
        self.requestInterruption()

    def _cancelled(self) -> bool:
        return self._cancel_requested.is_set() or self.isInterruptionRequested()

    def run(self) -> None:
        started = time.monotonic()
        paths: list[str] = []
        seen: set[str] = set()
        scanned_directories = 0
        last_progress = 0.0
        current_directory = self.root

        def emit_error(error: OSError) -> None:
            path = str(getattr(error, "filename", None) or current_directory)
            self.error_occurred.emit(path, str(error))

        for dirpath, _, filenames in os.walk(self.root, onerror=emit_error):
            if self._cancelled():
                break
            current_directory = dirpath
            scanned_directories += 1
            for filename in filenames:
                if self._cancelled():
                    break
                filepath = Path(dirpath) / filename
                is_index = is_safetensors_index_path(filepath)
                if is_index:
                    matches_extension = ".safetensors" in self.extensions
                else:
                    matches_extension = filepath.suffix.lower() in self.extensions
                if not matches_extension or is_probable_sidecar_path(filepath):
                    continue
                try:
                    if not filepath.is_file() and not filepath.is_symlink():
                        continue
                    canonical = discoverable_primary_path(filepath)
                    if canonical is None:
                        continue
                    try:
                        resolved = str(Path(canonical).resolve(strict=True))
                    except OSError:
                        resolved = str(Path(canonical).absolute())
                except OSError as exc:
                    self.error_occurred.emit(str(filepath), str(exc))
                    continue
                if resolved in seen:
                    continue
                seen.add(resolved)
                paths.append(str(canonical))

            now = time.monotonic()
            if now - last_progress >= 0.1:
                self.progress_updated.emit(
                    self._progress(paths, scanned_directories, current_directory)
                )
                last_progress = now

        # The terminal progress update is required even if the last throttled
        # update described the same directory/counts.
        self.progress_updated.emit(
            self._progress(paths, scanned_directories, current_directory)
        )
        self.discovery_done.emit(
            {
                "root": self.root,
                "paths": tuple(paths),
                "scanned_directories": scanned_directories,
                "cancelled": self._cancelled(),
                "checkpoint_safety": self.checkpoint_safety,
                "elapsed_seconds": time.monotonic() - started,
            }
        )

    def _progress(
        self,
        paths: list[str],
        scanned_directories: int,
        current_directory: str,
    ) -> dict[str, Any]:
        return {
            "root": self.root,
            "discovered_files": len(paths),
            "scanned_directories": scanned_directories,
            "current_directory": current_directory,
        }


class AnalysisWorker(QThread):
    """Inspect files with bounded scheduling and acknowledged event delivery."""

    result_ready = pyqtSignal(dict)
    error_occurred = pyqtSignal(str, str)
    all_done = pyqtSignal()

    def __init__(
        self,
        filepaths: list[str],
        inspect_options: Optional[dict[str, Any]] = None,
        threads: int = 1,
        checkpoint_safety: Optional[str] = None,
    ):
        super().__init__()
        self.filepaths = filepaths
        self.inspect_options = dict(inspect_options or {})
        if checkpoint_safety is not None:
            self.inspect_options["checkpoint_safety"] = checkpoint_safety
        self.threads = max(1, int(threads or 1))
        self.max_in_flight = max(2, 2 * self.threads)
        self.max_outstanding_events = max(8, 2 * self.threads)
        self.peak_in_flight = 0
        self.peak_outstanding_events = 0
        self._cancel_requested = threading.Event()
        self._event_capacity = threading.Condition()
        self._outstanding_events = 0
        self.was_cancelled = False

    @property
    def outstanding_events(self) -> int:
        """Return the current unacknowledged result/error count."""
        with self._event_capacity:
            return self._outstanding_events

    def cancel(self) -> None:
        """Stop scheduling and wake any emitter waiting for event capacity."""
        self._cancel_requested.set()
        self.requestInterruption()
        with self._event_capacity:
            self._event_capacity.notify_all()

    def acknowledge_event(self, count: int = 1) -> None:
        """Release capacity after GUI projection or deliberate discard."""
        if count <= 0:
            return
        with self._event_capacity:
            self._outstanding_events = max(0, self._outstanding_events - count)
            self._event_capacity.notify_all()

    def _cancelled(self) -> bool:
        return self._cancel_requested.is_set() or self.isInterruptionRequested()

    def _acquire_event_slot(self) -> bool:
        with self._event_capacity:
            while (
                self._outstanding_events >= self.max_outstanding_events
                and not self._cancelled()
            ):
                self._event_capacity.wait(timeout=0.05)
            if self._cancelled():
                return False
            self._outstanding_events += 1
            self.peak_outstanding_events = max(
                self.peak_outstanding_events, self._outstanding_events
            )
            return True

    def _emit_result(self, result: dict[str, Any]) -> bool:
        if not self._acquire_event_slot():
            return False
        self.result_ready.emit(compact_inspection_summary(result))
        return True

    def _emit_error(self, filepath: str, error: Exception) -> bool:
        if not self._acquire_event_slot():
            return False
        self.error_occurred.emit(filepath, str(error))
        return True

    def run(self) -> None:
        try:
            if self.threads > 1 and len(self.filepaths) > 1:
                self._run_parallel()
            else:
                self._run_sequential()
        finally:
            self.all_done.emit()

    def _run_sequential(self) -> None:
        for filepath in self.filepaths:
            if self._cancelled():
                self.was_cancelled = True
                break
            self.peak_in_flight = max(self.peak_in_flight, 1)
            try:
                if not self._emit_result(self._inspect_one(filepath)):
                    self.was_cancelled = True
                    break
            except Exception as exc:
                if not self._emit_error(filepath, exc):
                    self.was_cancelled = True
                    break

    def _inspect_one(self, filepath: str) -> dict[str, Any]:
        return inspect_file(filepath, options=self.inspect_options)

    def _run_parallel(self) -> None:
        max_workers = min(self.threads, len(self.filepaths))
        executor = ThreadPoolExecutor(max_workers=max_workers)
        pending: dict[Future, str] = {}
        path_iterator = iter(self.filepaths)

        def replenish() -> None:
            while len(pending) < self.max_in_flight and not self._cancelled():
                try:
                    filepath = next(path_iterator)
                except StopIteration:
                    break
                pending[executor.submit(self._inspect_one, filepath)] = filepath
                self.peak_in_flight = max(self.peak_in_flight, len(pending))

        try:
            replenish()
            while pending:
                if self._cancelled():
                    self.was_cancelled = True
                    break
                completed, _ = wait(
                    tuple(pending), timeout=0.05, return_when=FIRST_COMPLETED
                )
                if not completed:
                    continue
                for future in completed:
                    filepath = pending.pop(future)
                    if self._cancelled():
                        self.was_cancelled = True
                        break
                    try:
                        emitted = self._emit_result(future.result())
                    except Exception as exc:
                        emitted = self._emit_error(filepath, exc)
                    if not emitted:
                        self.was_cancelled = True
                        break
                if self.was_cancelled:
                    break
                replenish()
        finally:
            if self._cancelled():
                self.was_cancelled = True
            for future in pending:
                future.cancel()
            # Only the bounded window can remain here, so waiting releases all
            # executor threads without scaling cancellation latency to the scan.
            executor.shutdown(wait=True, cancel_futures=True)
