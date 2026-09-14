# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
"""Analysis and scan-projection methods for the main Model Inspector window."""

from pathlib import Path

from back.checkpoint_reader import CHECKPOINT_SAFETY_METADATA
from back.inspection_summary import compact_inspection_summary
from back.model_classification import format_params, format_size
from background_tasks import AnalysisWorker
from front.scan_projection import ProjectionEvent, ScanProjectionBuffer


MODEL_FORMAT_FILTERS = (".safetensors", ".gguf", ".ckpt", ".onnx", ".pt", ".pth")


class AnalysisControllerMixin:
    """Cooperative mixin for asynchronous analysis and result projection."""

    def _analyze_all(self):
        if not self._queued_files:
            return
        self._start_analysis(list(self._queued_files), clear_existing=True)

    def _start_analysis(self, paths: list[str], clear_existing: bool):
        if not paths:
            return
        if self._worker and self._worker.isRunning():
            return
        # File-operation guard: never scan files mid-move/dump.
        if self._file_operation_running():
            self._set_progress_status(
                "Wait for the current file operation to finish before scanning."
            )
            self._clear_progress_status(delay_ms=4000)
            return
        includes_checkpoint = any(
            Path(path).suffix.lower() in {".ckpt", ".pt", ".pth"} for path in paths
        )

        self._scan_generation = self._projection.begin()
        self.analyze_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setMaximum(len(paths))
        self.progress.setValue(0)
        self._set_cancel_available(True)
        self._analysis_done_count = 0
        self._analysis_error_count = 0
        self._analysis_total_count = len(paths)
        self._analysis_bytes_scanned = 0
        self._set_progress_status(
            f"Scanning 0/{self._analysis_total_count} | Bytes scanned: 0 B"
        )
        header = self.table.horizontalHeader()
        assert header is not None
        self._table_sort_restore = (
            self.table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        self.table.setSortingEnabled(False)

        if clear_existing:
            self._pending_filter_arches.clear()
            self._pending_filter_tags.clear()
            self._pending_filter_formats.clear()
            self._results.clear()
            self._cards.clear()
            self._path_to_card.clear()
            self._path_to_simple_card.clear()
            self._path_to_row.clear()
            self._selected_paths.clear()
            self._active_arch_filter = None
            self._active_tag_filter = None
            self._active_format_filter = None
            self._clear_cards()
            self.arch_filter_btn.clear_items()
            self.tag_filter_btn.clear_items()
            self._reset_format_filter_items()
            self.table.setRowCount(0)
            self.raw_combo.clear()
            self.raw_text.clear()
            self._raw_loaded_filepath = None
            self._update_raw_controls()
            self._update_selection_ui_state()

        self._worker = AnalysisWorker(
            list(paths),
            inspect_options={
                "allow_filename_alias_detection": self._allow_filename_alias_detection,
                "cache_full_data": self._cache_full_data_on_analyze,
            },
            threads=self._analysis_threads,
            checkpoint_safety=(
                CHECKPOINT_SAFETY_METADATA if includes_checkpoint else None
            ),
        )
        worker = self._worker
        generation = self._scan_generation
        worker.result_ready.connect(
            lambda data, g=generation, w=worker: self._on_result(g, w, data)
        )
        worker.error_occurred.connect(
            lambda filepath, error, g=generation, w=worker: self._on_error(
                g, w, filepath, error
            )
        )
        worker.all_done.connect(
            lambda g=generation, w=worker: self._on_all_done(g, w)
        )
        worker.start()

    def _on_result(self, *args):
        if len(args) == 1:
            generation = self._scan_generation
            worker = None
            data = args[0]
        else:
            generation, worker, data = args
        summary = compact_inspection_summary(data)
        self._projection.enqueue(
            ProjectionEvent(
                generation,
                "result",
                summary,
                worker.acknowledge_event if worker is not None else None,
            )
        )

    def _on_error(self, *args):
        if len(args) == 2:
            generation = self._scan_generation
            worker = None
            filepath, error = args
        else:
            generation, worker, filepath, error = args
        self._projection.enqueue(
            ProjectionEvent(
                generation,
                "error",
                (filepath, error),
                worker.acknowledge_event if worker is not None else None,
            )
        )

    def _project_scan_event(self, kind: str, payload: object):
        if kind == "result":
            self._project_result(payload)
        else:
            filepath, error = payload
            self._project_error(str(filepath), str(error))

    def _project_result(self, data: dict):
        self._normalize_result_data(data)
        self._results.append(data)
        self._analysis_done_count += 1
        self._analysis_bytes_scanned += int(data.get("file_size") or 0)
        self._update_analysis_progress(data.get("filepath", ""))
        self._add_card(data)
        self._add_table_row(data)
        self._apply_visibility_to_projected_item(data)
        self._pending_filter_arches.append(data.get("architecture", "Unknown"))
        self._pending_filter_tags.extend(self._filter_tags_for_data(data))
        self._pending_filter_formats.append(self._format_filter_for_data(data))

    def _project_error(self, filepath: str, error: str):
        self._analysis_done_count += 1
        self._analysis_error_count += 1
        try:
            self._analysis_bytes_scanned += Path(filepath).stat().st_size
        except OSError:
            pass
        self._update_analysis_progress(filepath)
        # Add an error card
        err_data = {
            "filepath": filepath,
            "filename": Path(filepath).name,
            "format": Path(filepath).suffix.lower().lstrip(".").upper() or "UNKNOWN",
            "architecture": "ERROR",
            "model_type": error,
            "adapter_type": None,
            "quantization": None,
            "total_params_friendly": "-",
            "file_size_friendly": "-",
            "precision_summary": "-",
            "component_precision_summary": "-",
            "component_precisions": {},
            "precision_display": "-",
            "tensor_count": 0,
            "components": {},
            "named_text_encoders": {},
            "lora_rank": None,
            "training_meta": {},
            "extra": {},
            "is_moe": False,
            "expert_count": None,
            "expert_used_count": None,
        }
        self._results.append(err_data)
        self._add_card(err_data)
        self._add_table_row(err_data)
        self._apply_visibility_to_projected_item(err_data)
        self._pending_filter_arches.append(err_data.get("architecture", "Unknown"))
        self._pending_filter_tags.extend(self._filter_tags_for_data(err_data))
        self._pending_filter_formats.append(self._format_filter_for_data(err_data))

    def _on_all_done(self, generation: int, worker: AnalysisWorker):
        self._projection.mark_terminal(generation, worker)

    def _reconcile_projected_results(self, final: bool):
        self.arch_filter_btn.add_items(self._pending_filter_arches)
        self.tag_filter_btn.add_items(self._pending_filter_tags)
        self.format_filter_btn.add_items(self._pending_filter_formats)
        self._pending_filter_arches.clear()
        self._pending_filter_tags.clear()
        self._pending_filter_formats.clear()
        if not final:
            return
        self.arch_filter_btn.replace_items(
            data.get("architecture", "Unknown") for data in self._results
        )
        self.tag_filter_btn.replace_items(
            tag for data in self._results for tag in self._filter_tags_for_data(data)
        )
        self._apply_arch_filter(
            refresh_raw=False,
            refresh_geometry=False,
            update_selection=False,
        )
        self._refresh_raw_combo_filtered()
        self._sync_selection_visuals()
        self._refresh_card_layout_geometry()

    def _apply_visibility_to_projected_item(self, data: dict):
        fp = str(data.get("filepath") or "")
        if not fp:
            return
        visible = self._is_data_visible(data)
        card = self._path_to_card.get(fp)
        if card is None:
            card = self._path_to_simple_card.get(fp)
        if card:
            card.set_filter_visible(visible)
        row = self._row_for_filepath(fp)
        if row is not None:
            self.table.setRowHidden(row, not visible)

    def _finish_analysis_projection(self, terminal: object):
        worker = terminal
        if worker is not self._worker:
            return
        self._restore_table_sorting()
        self.analyze_btn.setEnabled(True)
        self._set_cancel_available(False)
        was_cancelled = bool(worker.was_cancelled)
        error_text = (
            f" | Errors: {self._analysis_error_count}"
            if self._analysis_error_count
            else ""
        )
        if was_cancelled:
            self._set_progress_status(
                f"Analysis cancelled: {self._analysis_done_count}/{self._analysis_total_count} "
                f"parsed | Partial results remain visible{error_text}"
            )
        else:
            self._set_progress_status(
                f"Scanned {self._analysis_done_count}/{self._analysis_total_count} | "
                f"Bytes scanned: {self._format_bytes(self._analysis_bytes_scanned)}{error_text}"
            )
        self._clear_progress_status(delay_ms=4000)

    def _restore_table_sorting(self):
        if self._table_sort_restore is None:
            return
        sorting_enabled, column, order = self._table_sort_restore
        self._table_sort_restore = None
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(column, order)
        self.table.setSortingEnabled(sorting_enabled)

    def _reset_format_filter_items(self):
        self.format_filter_btn.blockSignals(True)
        try:
            self.format_filter_btn.clear_items()
            for ext in MODEL_FORMAT_FILTERS:
                self.format_filter_btn.ensure_item(ext)
        finally:
            self.format_filter_btn.blockSignals(False)

    def _update_analysis_progress(self, filepath: str):
        total = self._analysis_total_count
        self.progress.setValue(self._analysis_done_count)
        filename = Path(filepath).name if filepath else "-"
        error_text = (
            f" | Errors: {self._analysis_error_count}"
            if self._analysis_error_count
            else ""
        )
        self._set_progress_status(
            f"Scanning {self._analysis_done_count}/{total} | "
            f"Bytes scanned: {self._format_bytes(self._analysis_bytes_scanned)} | "
            f"{filepath or filename}{error_text}"
        )

    def _normalize_result_data(self, data: dict):
        arch = str(data.get("architecture") or "Unknown")
        if arch.startswith("GGUF "):
            data["architecture"] = arch[5:]
        try:
            data["file_size_friendly"] = format_size(int(data.get("file_size") or 0))
        except (TypeError, ValueError):
            data.setdefault("file_size_friendly", "-")
        try:
            data["total_params_friendly"] = format_params(
                int(data.get("total_params") or 0)
            )
        except (TypeError, ValueError):
            data.setdefault("total_params_friendly", "-")
        if not data.get("format"):
            suffix = Path(str(data.get("filepath") or "")).suffix.lower().lstrip(".")
            data["format"] = suffix.upper() if suffix else "UNKNOWN"
        if "is_moe" not in data:
            metadata = data.get("metadata") or {}
            arch_text = str(data.get("architecture") or "").lower()
            expert_count = None
            expert_used_count = None
            is_moe = "moe" in arch_text
            for key, value in metadata.items():
                lk = str(key).lower()
                if "expert" in lk or "moe" in lk:
                    is_moe = True
                try:
                    int_value = int(value)
                except (TypeError, ValueError):
                    int_value = None
                if lk.endswith(".expert_count"):
                    expert_count = int_value
                elif lk.endswith(".expert_used_count"):
                    expert_used_count = int_value
            data["is_moe"] = is_moe
            data["expert_count"] = expert_count
            data["expert_used_count"] = expert_used_count


AnalysisMixin = AnalysisControllerMixin
