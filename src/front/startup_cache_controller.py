# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false
# pylint: disable=no-member
"""Startup cache hydration and settings actions for the main window."""

from PyQt6.QtWidgets import QMessageBox

from model_cache import (
    clear_inspection_cache,
)


class StartupCacheControllerMixin:
    """Load compact cached results and manage settings/cache reset actions."""

    _discovery_generation: int
    _card_rebuild_generation: int

    def _restore_startup_table_sorting(self):
        if self._startup_sort_restore is None:
            return
        sorting_enabled, column, order = self._startup_sort_restore
        self._startup_sort_restore = None
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(column, order)
        self.table.setSortingEnabled(sorting_enabled)

    def _clear_inspection_cache_from_settings(self, dialog=None):
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
        self._refresh_cache_menu_actions()
        if dialog is not None:
            self._refresh_cache_dialog(dialog)

    def _apply_default_tab(self):
        tab_idx = {
            "cards": 0,
            "data": 1,
            "raw": 2,
        }.get(self._default_tab, 0)
        self.tabs.setCurrentIndex(tab_idx)

    def _clear_all(self):
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
        self._refresh_cache_menu_actions()


StartupCacheMixin = StartupCacheControllerMixin
