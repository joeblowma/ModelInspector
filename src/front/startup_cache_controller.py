# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
# pylint: disable=no-member
"""Startup cache hydration and settings actions for the main window."""

from pathlib import Path

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QMessageBox

from front.settings_dialog import SettingsDialog
from front.window_core import _combo_data_str
from model_cache import (
    clear_inspection_cache,
)


class StartupCacheControllerMixin:
    """Load compact cached results and manage settings/cache reset actions."""

    _discovery_generation: int
    _card_rebuild_generation: int

    def _load_default_libraries_from_cache_on_startup(self):
        if not self._load_default_libraries_on_startup:
            return

        cached_paths = []
        seen = set()
        # The host owns these two accessors so legacy ``gui`` monkeypatches
        # continue to apply without introducing a front-to-gui dependency.
        for path in self._list_cached_inspection_paths():
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            cached_paths.append(path)
        if not cached_paths:
            return

        self._startup_cache_load_cancelled = False
        snapshot_count = 0
        snapshots = self._get_cached_inspection_summary_snapshots(cached_paths)
        total = len(cached_paths)
        batch_size = 20
        header = self.table.horizontalHeader()
        assert header is not None
        self._startup_sort_restore = (
            self.table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        self.table.setSortingEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self._set_cancel_available(True)

        def load_batch(start_index: int):
            nonlocal snapshot_count
            if self._startup_cache_load_cancelled:
                self._restore_startup_table_sorting()
                self._set_progress_status(
                    f"Startup cache load cancelled: {snapshot_count}/{total} summaries loaded"
                )
                self._clear_progress_status(delay_ms=4000)
                return

            end_index = min(start_index + batch_size, total)
            for path in cached_paths[start_index:end_index]:
                cached = snapshots.get(path)
                if cached is not None:
                    cached["filepath"] = path
                    cached["filename"] = Path(path).name
                    self._normalize_result_data(cached)
                    if path not in self._queued_files:
                        self._queued_files.append(path)
                    self._results.append(cached)
                    self._add_card(cached)
                    self._add_table_row(cached)
                    self.arch_filter_btn.add_item(cached.get("architecture", "Unknown"))
                    for tag in self._filter_tags_for_data(cached):
                        self.tag_filter_btn.add_item(tag)
                    self.format_filter_btn.add_item(
                        self._format_filter_for_data(cached)
                    )
                    snapshot_count += 1

            self.progress.setValue(end_index)
            self._set_progress_status(
                f"Loading startup cache: {end_index}/{total} paths | "
                f"{snapshot_count} cached summaries"
            )

            if end_index < total:
                QTimer.singleShot(0, lambda: load_batch(end_index))
                return

            self._restore_startup_table_sorting()
            if snapshot_count:
                self._apply_arch_filter()
                self._refresh_raw_combo_filtered()
                self._sync_selection_visuals()

            self._set_cancel_available(False)
            self._set_progress_status(
                f"Loaded {snapshot_count} cached summary"
                f"{'ies' if snapshot_count != 1 else 'y'}"
            )
            self._clear_progress_status(delay_ms=5000)

        load_batch(0)

    def _restore_startup_table_sorting(self):
        if self._startup_sort_restore is None:
            return
        sorting_enabled, column, order = self._startup_sort_restore
        self._startup_sort_restore = None
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(column, order)
        self.table.setSortingEnabled(sorting_enabled)

    def _open_settings(self):
        col_vis = {
            name: not self.table.isColumnHidden(idx)
            for idx, name in enumerate(self._table_columns)
            if idx != 0  # checkbox column stays visible
        }
        dlg = SettingsDialog(
            self,
            allow_filename_alias_detection=self._allow_filename_alias_detection,
            auto_analyze_on_add=self._auto_analyze_on_add,
            dump_json_modelinfo=self._dump_json_modelinfo,
            auto_load_raw_dump=self._auto_load_raw_dump,
            load_default_libraries_on_startup=self._load_default_libraries_on_startup,
            cache_full_data_on_analyze=self._cache_full_data_on_analyze,
            analysis_threads=self._analysis_threads,
            add_mode=self._add_mode,
            default_tab=self._default_tab,
            card_fields=self._card_field_visibility,
            simple_card_fields=self._simple_card_field_visibility,
            table_column_visibility=col_vis,
        )
        dlg.clear_cache_btn.clicked.connect(self._clear_inspection_cache_from_settings)
        if dlg.exec():
            self._allow_filename_alias_detection = dlg.alias_checkbox.isChecked()
            self._auto_analyze_on_add = dlg.auto_analyze_checkbox.isChecked()
            self._dump_json_modelinfo = dlg.dump_json_checkbox.isChecked()
            self._auto_load_raw_dump = dlg.auto_load_raw_checkbox.isChecked()
            self._load_default_libraries_on_startup = (
                dlg.default_libraries_checkbox.isChecked()
            )
            self._cache_full_data_on_analyze = dlg.cache_full_data_checkbox.isChecked()
            threads = _combo_data_str(dlg.analysis_threads_combo.currentData())
            self._analysis_threads = int(threads or 1)
            self._add_mode = _combo_data_str(dlg.add_mode_combo.currentData()) or "replace"
            self._default_tab = (
                _combo_data_str(dlg.default_tab_combo.currentData()) or "cards"
            )
            for key, cb in dlg.card_field_checks.items():
                self._card_field_visibility[key] = cb.isChecked()
            for key, cb in dlg.simple_card_field_checks.items():
                self._simple_card_field_visibility[key] = cb.isChecked()
            for name, cb in dlg.table_column_checks.items():
                if name in self._table_columns:
                    idx = self._table_columns.index(name)
                    self.table.setColumnHidden(idx, not cb.isChecked())
            self._save_ui_settings()
            self._rebuild_views_from_results()
            self._update_raw_controls()
            self._update_analyze_slot()
            self._apply_default_tab()

    def _clear_inspection_cache_from_settings(self):
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Clear all cached inspection summaries? Existing analyzed results stay visible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        removed = clear_inspection_cache()
        QMessageBox.information(
            self,
            "Cache Cleared",
            f"Removed {removed} cached file{'s' if removed != 1 else ''}.",
        )

    def _apply_default_tab(self):
        tab_idx = {
            "cards": 0,
            "data": 1,
            "raw": 2,
        }.get(self._default_tab, 0)
        self.tabs.setCurrentIndex(tab_idx)

    def _clear_all(self):
        self._startup_cache_load_cancelled = True
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        if self._discovery_worker and self._discovery_worker.isRunning():
            self._discovery_worker.cancel()
        self._discovery_generation += 1
        self._projection.invalidate()
        self._scan_generation = self._projection.generation
        self._card_rebuild_generation += 1
        self._restore_table_sorting()
        self._restore_startup_table_sorting()
        self._pending_filter_arches.clear()
        self._pending_filter_tags.clear()
        self._pending_filter_formats.clear()
        self._queued_files.clear()
        self._results.clear()
        self._cards.clear()
        self._path_to_card.clear()
        self._path_to_simple_card.clear()
        self._path_to_row.clear()
        self._selected_paths.clear()
        self._active_arch_filter = None
        self._active_tag_filter = None
        self._active_format_filter = None
        self._update_file_count()
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


StartupCacheMixin = StartupCacheControllerMixin
