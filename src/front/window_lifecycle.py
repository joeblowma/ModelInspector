# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
# pylint: disable=no-member
from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from back.checkpoint_reader import CHECKPOINT_SAFETY_METADATA
from back.reporting import generate_modelinfo_dump
from model_cache import store_raw_dump


def _combo_data_str(value) -> str | None:
    return str(value) if value else None


class WindowLifecycleMixin:
    """Window shutdown and raw-view lifecycle helpers."""

    _card_rebuild_generation: int
    _discovery_generation: int

    _RAW_DUMP_SEPARATOR = "=" * 70

    def _on_raw_selection_changed(self, index):
        if index < 0:
            self.raw_text.clear()
            self._raw_loaded_filepath = None
            return
        filepath = _combo_data_str(self.raw_combo.itemData(index))
        if not filepath:
            return
        self._update_raw_controls()
        self._show_raw_for_current_setting(filepath)

    def _show_raw_for_current_setting(self, filepath: str):
        analysis_running = bool(self._worker and self._worker.isRunning())
        if self._auto_load_raw_dump and not analysis_running:
            self._load_raw_dump(filepath)
        else:
            self._show_raw_summary(filepath)

    def _result_for_filepath(self, filepath: str) -> dict | None:
        for data in self._results:
            if data.get("filepath") == filepath:
                return data
        return None

    def _show_raw_summary(self, filepath: str):
        data = self._result_for_filepath(filepath)
        if not data:
            self.raw_text.setPlainText(
                "No inspection summary is available for this model."
            )
            self._raw_loaded_filepath = None
            return
        lines = [
            f"File: {data.get('filename', Path(filepath).name)}",
            f"Path: {filepath}",
        ]
        resolved = data.get("resolved_filepath")
        if resolved and resolved != filepath:
            lines.append(f"Resolved path: {resolved}")
        lines.extend(
            [
                f"Architecture: {data.get('architecture', 'Unknown')}",
                f"Model type: {data.get('model_type', 'Unknown')}",
                f"Size: {data.get('file_size_friendly', '-')}",
                f"Parameters: {data.get('total_params_friendly', '-')}",
                f"Tensors: {data.get('tensor_count', 0)}",
                f"Precision: {data.get('precision_display') or data.get('precision_summary', '-')}",
                "",
                "Full tensor key dump is not loaded automatically for large files.",
                "Click Load Full Dump to generate it.",
            ]
        )
        self.raw_text.setPlainText("\n".join(lines))
        self._raw_loaded_filepath = None

    def _raw_dump_with_current_info(self, filepath: str, dump: str) -> str:
        """Prefix raw dumps with a stable, copyable summary of the current model."""
        normalized_dump = dump.replace("\r\n", "\n").replace("\r", "\n")
        if normalized_dump.startswith("CURRENT MODEL / OUTPUT\n"):
            return dump
        legacy_prefix_heading = "\n  Top key prefixes (depth 2):"
        legacy_prefix_start = dump.find(legacy_prefix_heading)
        if legacy_prefix_start >= 0:
            tensor_keys_start = dump.find("\n  All tensor keys", legacy_prefix_start)
            if tensor_keys_start >= 0:
                dump = dump[:legacy_prefix_start] + dump[tensor_keys_start:]
        data = self._result_for_filepath(filepath) or {}
        lines = [
            "CURRENT MODEL / OUTPUT",
            "Output: Full tensor key dump",
            f"File: {data.get('filename', Path(filepath).name)}",
            f"Path: {filepath}",
            f"Architecture: {data.get('architecture', 'Unknown')}",
            f"Model type: {data.get('model_type', 'Unknown')}",
            f"Size: {data.get('file_size_friendly', '-')}",
            f"Parameters: {data.get('total_params_friendly', '-')}",
            f"Tensors: {data.get('tensor_count', 0)}",
            f"Precision: {data.get('precision_display') or data.get('precision_summary', '-')}",
            self._RAW_DUMP_SEPARATOR,
        ]
        return "\n".join(lines) + "\n" + dump

    def _load_selected_raw_dump(self):
        filepath = _combo_data_str(self.raw_combo.currentData())
        if not filepath:
            return
        self._load_raw_dump(filepath)

    def _load_raw_dump(self, filepath: str):
        # The host bridge preserves the public ``gui.get_cached_raw_dump``
        # seam without making this reusable mixin import ``gui``.
        cached_dump = self._get_cached_raw_dump(filepath)
        if cached_dump is not None:
            self.raw_text.setPlainText(
                self._raw_dump_with_current_info(filepath, cached_dump)
            )
            self._raw_loaded_filepath = filepath
            self._set_progress_status(f"Loaded cached full dump: {Path(filepath).name}")
            self._clear_progress_status(delay_ms=1500)
            return
        try:
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self._set_progress_status(f"Loading full dump: {Path(filepath).name}")
            QApplication.processEvents()
            self.raw_load_btn.setEnabled(False)
            self.raw_load_btn.setText("Loading...")
            try:
                dump = generate_modelinfo_dump(
                    filepath,
                    options={"checkpoint_safety": CHECKPOINT_SAFETY_METADATA},
                )
            except TypeError:
                # Retain the one-argument injection seam used by older callers.
                # Its default checkpoint policy still rejects unsafe formats.
                dump = generate_modelinfo_dump(filepath)
            dump = self._raw_dump_with_current_info(filepath, dump)
            store_raw_dump(filepath, dump)
            self.raw_text.setPlainText(dump)
            self._raw_loaded_filepath = filepath
        except Exception as e:
            if not Path(filepath).exists():
                self._show_raw_summary(filepath)
                self._set_progress_status(
                    f"No cached full dump/tensor data for unavailable file: {Path(filepath).name}"
                )
            else:
                self.raw_text.setPlainText(f"Error reading file:\n{e}")
            self._raw_loaded_filepath = None
        finally:
            self.raw_load_btn.setEnabled(True)
            self.raw_load_btn.setText("Load Full Dump")
            self._clear_progress_status(delay_ms=1500)

    def closeEvent(self, event):
        self._lifecycle_closed = True
        running_workers = {
            worker
            for worker in (self._worker, self._discovery_worker)
            if worker is not None and worker.isRunning()
        }
        if running_workers:
            event.ignore()
            if self._close_pending:
                return
            self._close_pending = True
            self._projection.invalidate()
            self._card_rebuild_generation += 1
            self._discovery_generation += 1
            self._restore_table_sorting()
            self._close_waiting_workers = running_workers
            for worker in running_workers:
                worker.finished.connect(
                    lambda w=worker: self._on_close_worker_finished(w)
                )
                worker.cancel()
                if not worker.isRunning():
                    self._on_close_worker_finished(worker)
            return

        self._close_pending = False
        self._close_waiting_workers.clear()
        self._projection.invalidate()
        self._card_rebuild_generation += 1
        self._discovery_generation += 1
        self._restore_table_sorting()
        super().closeEvent(event)

    def _on_close_worker_finished(self, worker):
        if worker not in self._close_waiting_workers:
            return
        self._close_waiting_workers.discard(worker)
        if self._close_pending and not self._close_waiting_workers:
            QTimer.singleShot(0, self.close)


LifecycleMixin = WindowLifecycleMixin
