#!/usr/bin/env python3
"""
Background task processing for Model Inspector.

This module encapsulates the thread-pool based analysis workers,
keeping the GUI unburdened with concurrency details.
"""

import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Optional
from PyQt6.QtCore import QThread, pyqtSignal

from inspect_model import inspect_file


# ---------------------------------------------------------------------------
# Analysis Worker
# ---------------------------------------------------------------------------


class AnalysisWorker(QThread):
    """Runs inspect_file() on a list of paths in a background thread.

    Emits per-file results via `result_ready` signal, errors via `error_occurred`
    signal, and `all_done` when the queue is fully exhausted.

    Attributes:
        filepaths: List of paths to inspect.
        inspect_options: Dictionary passed to inspect_file().
        threads: Number of parallel workers (1 for sequential).
        _cancel_requested: Flag set when cancel() is called.
        was_cancelled: True if the operation was aborted mid-flight.
    """

    result_ready = pyqtSignal(dict)  # emitted per file
    error_occurred = pyqtSignal(str, str)  # filepath, error message
    all_done = pyqtSignal()

    def __init__(
        self,
        filepaths: list[str],
        inspect_options: Optional[dict[str, Any]] = None,
        threads: int = 1,
    ):
        super().__init__()
        self.filepaths = filepaths
        self.inspect_options = inspect_options or {}
        self.threads = max(1, int(threads or 1))
        self._cancel_requested = False
        self.was_cancelled = False

    def cancel(self) -> None:
        """Signal cancellation. The worker will stop accepting new work" """
        self._cancel_requested = True
        self.requestInterruption()

    def run(self) -> None:
        if self.threads > 1:
            self._run_parallel()
            return

        for fp in self.filepaths:
            if self._cancel_requested or self.isInterruptionRequested():
                self.was_cancelled = True
                break
            try:
                result = inspect_file(fp, options=self.inspect_options)
                self.result_ready.emit(result)
            except Exception as e:
                self.error_occurred.emit(fp, str(e))
        self.all_done.emit()

    def _inspect_one(self, fp: str) -> dict[str, Any]:
        return inspect_file(fp, options=self.inspect_options)

    def _run_parallel(self) -> None:
        """Execute all tasks via a ThreadPoolExecutor.

        Tasks are submitted to the pool and completed in any order.
        Errors from individual futures are caught and emitted as `error_occurred`.
        """
        max_workers = min(self.threads, len(self.filepaths))

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_path = {
                executor.submit(self._inspect_one, fp): fp
                for fp in self.filepaths
            }

            for future in as_completed(future_to_path):
                fp = future_to_path[future]

                if self._cancel_requested or self.isInterruptionRequested():
                    self.was_cancelled = True
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                try:
                    self.result_ready.emit(future.result())
                except Exception as e:
                    self.error_occurred.emit(fp, str(e))

        self.all_done.emit()
