# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
# pylint: disable=no-member
"""Discovery and file-queue controller for the Model Inspector window.

The controller owns the generation token and worker callback contract used by
the main window.  Directory roots are deliberately consumed one at a time so
that cancellation and stale worker signals remain deterministic.  Queue
management is kept here with discovery because both file dialogs and drops
must use the same replace/additive semantics.

The eventual host class supplies ``progress``, queue state, status helpers,
and the analysis callbacks.  This module only imports low-level discovery,
cache, and reader policy; it never imports ``gui.py``.

All public method signatures match the former ``MainWindow`` implementation.
Stale generations are ignored before touching visible state.
Cancellation remains cooperative with worker shutdown.
"""

from pathlib import Path

from PyQt6.QtWidgets import QFileDialog, QMessageBox

from background_tasks import DiscoveryWorker
from front.window_core import _model_file_filter
from model_cache import store_directory_scan
from model_readers import (
    SUPPORTED_MODEL_EXTENSIONS,
    is_checkpoint_model_path,
    is_supported_model_path,
)


class DiscoveryControllerMixin:
    """Manage asynchronous directory discovery and queued model paths.

    The host class supplies status/progress helpers, analysis entry points,
    and the queue state initialized by ``WindowCoreMixin``.
    """

    _discovery_generation: int

    def _start_discovery(
        self, roots: list[str], seed_paths: list[str] | None = None, *, checkpoint_safety: str = "reject"
    ):
        if self._worker and self._worker.isRunning():
            return
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._discovery_generation += 1
        self._discovery_roots = list(roots)
        self._discovery_paths = list(seed_paths or [])
        self._discovery_auto_analyze = self._auto_analyze_on_add
        self._discovery_checkpoint_safety = checkpoint_safety
        self._scan_cancel_requested = False
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._set_cancel_available(True)
        self._start_next_discovery_root(self._discovery_generation)

    def _start_next_discovery_root(self, generation: int):
        if generation != self._discovery_generation or self._scan_cancel_requested:
            self._finish_discovery(generation, True)
            return
        if not self._discovery_roots:
            self._finish_discovery(generation, False)
            return
        root = self._discovery_roots.pop(0)
        worker = DiscoveryWorker(
            root, extensions=SUPPORTED_MODEL_EXTENSIONS,
            checkpoint_safety=self._discovery_checkpoint_safety,
        )
        self._discovery_worker = worker
        worker.progress_updated.connect(
            lambda progress, g=generation: self._on_discovery_progress(g, progress)
        )
        worker.error_occurred.connect(
            lambda path, message, g=generation: self._on_discovery_error(
                g, path, message
            )
        )
        worker.discovery_done.connect(
            lambda terminal, g=generation: self._on_discovery_done(g, terminal)
        )
        worker.finished.connect(
            lambda g=generation, w=worker: self._on_discovery_worker_finished(g, w)
        )
        worker.start()

    def _on_discovery_progress(self, generation: int, progress: dict):
        if generation != self._discovery_generation:
            return
        discovered = int(progress.get("discovered_files") or 0)
        directories = int(progress.get("scanned_directories") or 0)
        current = str(progress.get("current_directory") or progress.get("root") or "")
        self._set_progress_status(
            f"Discovering: {discovered} files | Directories: {directories} | "
            f"Current directory: {current}"
        )

    def _on_discovery_error(self, generation: int, path: str, message: str):
        if generation == self._discovery_generation:
            self._set_progress_status(f"Discovery warning: {path} | {message}")

    def _on_discovery_done(self, generation: int, terminal: dict):
        if generation != self._discovery_generation:
            return
        self._discovery_terminal = terminal

    def _on_discovery_worker_finished(
        self, generation: int, worker: DiscoveryWorker
    ):
        if (
            generation != self._discovery_generation
            or worker is not self._discovery_worker
        ):
            return
        terminal = self._discovery_terminal or {
            "root": worker.root,
            "paths": (),
            "cancelled": True,
        }
        self._discovery_terminal = None
        paths = [str(path) for path in terminal.get("paths") or ()]
        if terminal.get("cancelled"):
            paths = [path for path in paths if not is_checkpoint_model_path(path)]
        self._discovery_paths.extend(paths)
        root = str(terminal.get("root") or "")
        if paths and not terminal.get("cancelled"):
            if terminal.get("checkpoint_safety") == "metadata":
                self._checkpoint_metadata_paths.update(
                    self._checkpoint_path_key(path)
                    for path in paths
                    if is_checkpoint_model_path(path)
                )
            store_directory_scan(root, paths)
        if terminal.get("cancelled"):
            self._finish_discovery(generation, True)
        else:
            self._start_next_discovery_root(generation)

    def _finish_discovery(self, generation: int, cancelled: bool):
        if generation != self._discovery_generation:
            return
        unique_paths = list(dict.fromkeys(self._discovery_paths))
        self._set_cancel_available(False)
        if cancelled:
            self._set_progress_status(
                f"Discovery cancelled: {len(unique_paths)} partial files found"
            )
        else:
            self._set_progress_status(f"Discovered {len(unique_paths)} files")
        if unique_paths:
            added = self._queue_files(unique_paths)
            if added and self._discovery_auto_analyze:
                self._analyze_all()
                return
        self._clear_progress_status(delay_ms=3000)

    def _queue_files(self, paths: list[str]) -> list[str]:
        if not paths:
            return []
        added = []
        if self._add_mode == "replace":
            self._queued_files.clear()

        for p in paths:
            if p not in self._queued_files:
                self._queued_files.append(p)
                added.append(p)
        self._update_file_count()
        return added

    def _add_files(self, paths: list[str]):
        added = self._queue_files(paths)
        if not added:
            return
        if self._auto_analyze_on_add:
            self._analyze_all()

    def _update_file_count(self):
        if not self.progress.isVisible():
            self._set_idle_status()
        self._update_analyze_slot()

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select model files", "", _model_file_filter()
        )
        if not paths:
            return
        supported = [p for p in paths if is_supported_model_path(p)]
        checkpoints = [p for p in paths if is_checkpoint_model_path(p)]
        supported.extend(self._confirm_checkpoint_metadata_only(checkpoints))
        if supported:
            self._add_files(supported)

    @staticmethod
    def _checkpoint_path_key(path: str) -> str:
        try:
            return str(Path(path).resolve(strict=False)).casefold()
        except OSError:
            return str(path).casefold()

    def _confirm_checkpoint_metadata_only(self, paths: list[str]) -> list[str]:
        """Ask once per selected/drop batch before opting into checkpoint metadata."""
        if not paths:
            return []
        preview = "\n".join(Path(p).name for p in paths[:8])
        if len(paths) > 8:
            preview += f"\n...and {len(paths) - 8} more"
        answer = QMessageBox.question(
            self,
            "Inspect checkpoints as metadata only?",
            "PyTorch checkpoint files can contain pickle data. Model Inspector will "
            "not deserialize pickle or load tensor payloads.\n\nContinue with safe "
            "metadata-only inspection for:\n" + preview,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return []
        self._checkpoint_metadata_paths.update(self._checkpoint_path_key(path) for path in paths)
        return paths

    def _confirm_checkpoint_discovery(self, roots: list[str]) -> bool:
        if not roots:
            return False
        answer = QMessageBox.question(
            self,
            "Discover checkpoints as metadata only?",
            "Search these folders for .ckpt, .pt, and .pth files? Any found files "
            "will be inspected only after this explicit metadata-only opt-in; pickle "
            "and tensor payloads will never be deserialized.\n\n" + "\n".join(roots[:8]),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return answer == QMessageBox.StandardButton.Yes

    def _browse_folder_recursive(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan recursively"
        )
        if not folder:
            return
        safety = "metadata" if self._confirm_checkpoint_discovery([folder]) else "reject"
        self._start_discovery([folder], checkpoint_safety=safety)


DiscoveryMixin = DiscoveryControllerMixin
