# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""File-operation controller: move and dump behind a modal progress dialog.

Long operations run on a :class:`FileOperationWorker` while a window-modal
``QProgressDialog`` blocks further GUI use but keeps the event loop painting
and processing. The worker reference is held until the terminal ``finished``
signal, so the QThread is never released while it is still winding down.
Moves are no-clobber: colliding destinations are skipped and reported, never
overwritten.
"""

from __future__ import annotations

import os
from pathlib import Path

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox, QProgressDialog

from app_paths import ensure_output_dir
from front.file_operation_worker import FileOperationWorker


class FileOperationControllerMixin:
    """Own long file operations (move, dump) with modal progress and safe errors."""

    _file_op_worker: FileOperationWorker | None
    _file_op_dialog: QProgressDialog | None
    _selected_paths: set[str]

    def _file_operation_running(self) -> bool:
        worker = getattr(self, "_file_op_worker", None)
        return bool(worker is not None and worker.isRunning())

    def _scan_worker_running(self) -> bool:
        """True while any foreground or background scan may touch model files."""
        for name in ("_worker", "_discovery_worker", "_cache_sync_worker"):
            worker = getattr(self, name, None)
            if worker is not None and worker.isRunning():
                return True
        return False

    def _begin_file_operation(self, title: str, label: str, total: int) -> bool:
        if self._file_operation_running():
            return False
        # Indeterminate range (0, 0): per-file work is opaque, so a determinate
        # bar would fake precision we do not have.
        dialog = QProgressDialog(label, "Cancel", 0, 0, self)
        dialog.setWindowTitle(title)
        dialog.setWindowModality(Qt.WindowModality.WindowModal)
        dialog.setMinimumDuration(0)
        dialog.setMinimumWidth(440)
        dialog.setAutoClose(False)
        dialog.setAutoReset(False)
        dialog.canceled.connect(self._on_file_operation_cancel_requested)
        self._file_op_dialog = dialog
        dialog.show()
        return True

    def _start_file_operation(
        self, worker: FileOperationWorker, title: str, label: str
    ) -> None:
        if not self._begin_file_operation(title, label, len(worker.items)):
            return
        self._file_op_worker = worker
        worker.progress_updated.connect(self._on_file_operation_progress)
        worker.finished.connect(self._on_file_operation_finished)
        self._set_progress_status(label)
        worker.start()

    def _on_file_operation_progress(self, progress: dict) -> None:
        dialog = getattr(self, "_file_op_dialog", None)
        if dialog is None or getattr(self, "_lifecycle_closed", False):
            return
        index = int(progress.get("index") or 0)
        total = int(progress.get("total") or 1)
        filename = str(progress.get("filename") or "")
        verb = "Moving" if progress.get("phase") == "move" else "Dumping"
        dialog.setLabelText(f"{verb} {index + 1}/{total}: {filename}")
        self._set_progress_status(f"{verb} {index + 1}/{total} | {filename}")

    def _on_file_operation_cancel_requested(self) -> None:
        """Cooperative cancel: stop at the next file, keep the dialog visible.

        A running ``shutil``/``os.rename`` copy is not interrupted mid-file; the
        dialog stays open until the worker actually terminates.
        """
        worker = self._file_op_worker
        if worker is not None and worker.isRunning():
            worker.cancel()
        dialog = self._file_op_dialog
        if dialog is not None:
            dialog.setLabelText("Cancelling after the current file...")
            dialog.setCancelButton(None)
        self._set_progress_status("Cancelling after the current file...")

    def _on_file_operation_finished(self) -> None:
        """Terminal handler: release the worker only after the thread exited."""
        worker = self._file_op_worker
        if worker is None:
            return
        result = getattr(worker, "result", None) or {}
        dialog = self._file_op_dialog
        self._file_op_dialog = None
        if dialog is not None:
            dialog.close()
            dialog.deleteLater()
        worker.deleteLater()
        self._file_op_worker = None
        if getattr(self, "_close_pending", False) or getattr(
            self, "_lifecycle_closed", False
        ):
            return
        if result.get("mode") == "move":
            self._finish_move_operation(result)
        else:
            self._finish_dump_operation(result)

    # --- Move ------------------------------------------------------------

    def _move_selected_files(self) -> None:
        if self._file_operation_running():
            return
        if self._scan_worker_running():
            self._set_progress_status(
                "Wait for the current scan to finish before moving files."
            )
            self._clear_progress_status(delay_ms=4000)
            return
        selected = self._visible_selected_paths()
        if not selected:
            self._set_progress_status("Select one or more models to move.")
            self._clear_progress_status(delay_ms=3500)
            return
        target = QFileDialog.getExistingDirectory(
            self, "Select destination folder", str(ensure_output_dir())
        )
        if not target:
            return
        specs: list[tuple[str, str]] = []
        for src in selected:
            dst = str(Path(target) / Path(src).name)
            specs.append((src, dst))
        worker = FileOperationWorker("move", specs)
        self._start_file_operation(
            worker, "Move Files", f"Moving {len(specs)} file(s)..."
        )

    def _finish_move_operation(self, result: dict) -> None:
        moved = [str(p) for p in result.get("moved") or ()]
        skipped = list(result.get("skipped") or [])
        failed = list(result.get("failed") or [])
        cancelled = bool(result.get("cancelled"))
        if moved:
            moved_set = set(moved)
            self._queued_files = [p for p in self._queued_files if p not in moved_set]
            self._results = [
                r for r in self._results if r.get("filepath") not in moved_set
            ]
            self._selected_paths -= moved_set
            self._rebuild_views_from_results()
            self._update_file_count()
        if cancelled:
            self._set_progress_status(
                f"Move cancelled: {len(moved)} moved, {len(skipped)} skipped, "
                f"{len(failed)} failed."
            )
            self._clear_progress_status(delay_ms=5000)
        elif skipped or failed:
            self._report_move_issues(moved, skipped, failed)
        else:
            self._set_progress_status(f"Moved {len(moved)} file(s).")
            self._clear_progress_status(delay_ms=4000)
        if self._selected_action == "move_files":
            self.selected_action_btn.setText(f"Moved {len(moved)} file(s)")
            QTimer.singleShot(3000, self._refresh_selected_action_button)

    def _report_move_issues(
        self, moved: list[str], skipped: list, failed: list
    ) -> None:
        """Report skipped (no-clobber) and failed paths without losing them."""
        lines = [
            f"{Path(src).name}: {reason}" for src, reason in [*skipped, *failed][:20]
        ]
        if len(skipped) + len(failed) > 20:
            lines.append(f"...and {len(skipped) + len(failed) - 20} more")
        self._set_progress_status(
            f"Moved {len(moved)} | {len(skipped)} skipped | {len(failed)} failed."
        )
        QMessageBox.warning(
            self,
            "Move incomplete",
            f"{len(skipped)} skipped, {len(failed)} failed:\n\n"
            + "\n".join(lines),
        )
        self._clear_progress_status(delay_ms=6000)

    # --- Dump ------------------------------------------------------------

    def _dump_all(self) -> None:
        if self._file_operation_running():
            return
        if self._scan_worker_running():
            self._set_progress_status(
                "Wait for the current scan to finish before dumping .modelinfo."
            )
            self._clear_progress_status(delay_ms=4000)
            return
        targets = self._dump_modelinfo_targets()
        if not targets:
            self._set_progress_status(
                "Select one or more models to dump, or open a model in Raw."
            )
            self._clear_progress_status(delay_ms=3500)
            return
        worker = FileOperationWorker(
            "dump",
            targets,
            dump_json=self._dump_json_modelinfo,
            dump_options={
                "allow_filename_alias_detection": self._allow_filename_alias_detection
            },
        )
        self._start_file_operation(
            worker, "Dump .modelinfo", f"Writing .modelinfo for {len(targets)} file(s)..."
        )

    def _finish_dump_operation(self, result: dict) -> None:
        dumped = list(result.get("dumped") or [])
        failed = list(result.get("failed") or [])
        cancelled = bool(result.get("cancelled"))
        output_paths: list[str] = []
        for entry in dumped:
            outputs = list(entry.get("outputs") or [])
            output_paths.extend(outputs)
            filepath = entry.get("filepath")
            if filepath:
                data = self._result_for_filepath(filepath)
                if data:
                    data["modelinfo_outputs"] = outputs
        total = len(dumped) + len(failed)
        if self._selected_action == "dump_modelinfo":
            self.selected_action_btn.setText(f"Dumped {len(dumped)} file(s)")
        if cancelled:
            self._set_progress_status(
                f"Dump cancelled: wrote {len(dumped)}/{total}, {len(failed)} failed."
            )
            self._clear_progress_status(delay_ms=5000)
        elif failed:
            self._report_failures(
                "Dump incomplete", "Wrote .modelinfo for", len(dumped), failed, total
            )
        else:
            self._set_progress_status(
                f"Wrote .modelinfo for {len(dumped)}/{total} file(s)."
            )
            self._clear_progress_status(delay_ms=4000)
        if output_paths:
            preview = "\n".join(output_paths[:20])
            if len(output_paths) > 20:
                preview += f"\n...and {len(output_paths) - 20} more"
            self.selected_action_btn.setToolTip(
                f"Last .modelinfo output paths:\n{preview}"
            )
        QTimer.singleShot(3000, self._refresh_selected_action_button)

    # --- Shared failure reporting -----------------------------------------

    def _report_failures(
        self, title: str, done_label: str, succeeded: int, failed: list, total: int
    ) -> None:
        details = "\n".join(
            f"{Path(path).name}: {reason}" for path, reason in failed[:20]
        )
        if len(failed) > 20:
            details += f"\n...and {len(failed) - 20} more"
        self._set_progress_status(
            f"{done_label} {succeeded}/{total} | {len(failed)} failed."
        )
        QMessageBox.warning(
            self, title, f"{len(failed)} file(s) failed:\n\n{details}"
        )
        self._clear_progress_status(delay_ms=6000)
