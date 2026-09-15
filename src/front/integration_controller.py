# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Focused bindings for Explorer, advanced facts, table layout, and cache UI."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
import weakref

from PyQt6 import sip
from PyQt6.QtCore import QObject, QTimer
from PyQt6.QtWidgets import QFileDialog, QMessageBox

from app_paths import ensure_output_dir
from back.checkpoint_reader import CHECKPOINT_SAFETY_METADATA
from back.cache_verifier import verify_cache_entries
from back.settings_store import open_settings
from background_tasks import AnalysisWorker
from front.advanced_viewer import AdvancedViewerDialog
from front.cache_identity import get_cached_inspection_identity_snapshots
from front.cache_load_controller import CacheLoadControllerMixin
from front.data_columns import DATA_COLUMNS
from front.settings_data_tab import ColumnDefinition
from model_cache import get_cached_inspection_snapshots


def _run_deferred_settings_rebuild(window_ref, generation: int) -> None:
    """Run a queued rebuild only while its Python window wrapper is alive."""
    window = window_ref()
    if window is not None:
        window._run_settings_rebuild(generation)


class IntegrationMixin(CacheLoadControllerMixin):
    """Keep optional Phase 2/3 features out of the near-limit core mixins."""

    def _configure_extended_ui(self) -> None:
        self._advanced_dialog: AdvancedViewerDialog | None = None
        self._settings_dialog = None
        self._settings_rebuild_generation = 0
        self._data_layout = self._settings_data_layout()
        self._apply_data_layout(self._data_layout)
        self._init_smart_groups()
        header = self.table.horizontalHeader()
        assert header is not None
        header.sectionMoved.connect(lambda *_args: self._capture_data_layout())
        header.sectionResized.connect(lambda *_args: self._capture_data_layout())
        # One cache report feeds both the initial controls and the deferred
        # background sync.  Nothing can change the cache between construction
        # and the zero-delay timer, so a second enumeration/stat pass would be
        # pure startup cost on large caches.
        startup_report = self._cache_report()
        self._refresh_cache_controls(startup_report)
        QTimer.singleShot(0, lambda: self._schedule_cache_sync(startup_report))

    def _open_settings(self) -> None:
        from front.settings_dialog import SettingsDialog
        dialog = SettingsDialog(
            self, allow_filename_alias_detection=self._allow_filename_alias_detection,
            auto_analyze_on_add=self._auto_analyze_on_add, dump_json_modelinfo=self._dump_json_modelinfo,
            auto_load_raw_dump=self._auto_load_raw_dump,
            cache_full_data_on_analyze=self._cache_full_data_on_analyze, analysis_threads=self._analysis_threads,
            add_mode=self._add_mode, default_tab=self._default_tab,
            data_columns=self._column_definitions(),
            data_configuration=self._capture_data_layout(),
            theme_id=self._data_layout.get("theme", "default"),
            dialog_size=self._remembered_settings_size(),
        )
        # Track the live dialog so background cache sync can refresh its counts
        # while it is open, without holding a dangling reference after close.
        self._settings_dialog = dialog
        dialog.clear_cache_btn.clicked.connect(
            lambda: self._clear_inspection_cache_from_settings(dialog)
        )
        dialog.verify_cache_btn.clicked.connect(self._verify_cached_file_paths)
        dialog.themeChanged.connect(self._apply_theme)
        dialog.themePreviewChanged.connect(self._apply_theme_preview)
        self._refresh_cache_dialog(dialog)
        accepted = dialog.exec()
        self._settings_dialog = None
        # Remember the window size for both OK and X/close dismissal.
        self._save_settings_size(dialog)
        if not accepted:
            return
        self._allow_filename_alias_detection = dialog.alias_checkbox.isChecked()
        self._auto_analyze_on_add = dialog.auto_analyze_checkbox.isChecked()
        self._dump_json_modelinfo = dialog.dump_json_checkbox.isChecked()
        self._auto_load_raw_dump = dialog.auto_load_raw_checkbox.isChecked()
        self._cache_full_data_on_analyze = dialog.cache_full_data_checkbox.isChecked()
        self._analysis_threads = int(dialog.analysis_threads_combo.currentData() or 1)
        self._add_mode = str(dialog.add_mode_combo.currentData() or "replace")
        self._default_tab = str(dialog.default_tab_combo.currentData() or "cards")
        self._data_layout = dialog.data_settings_tab.export_configuration()
        self._data_layout["theme"] = dialog.current_theme_id()
        self._schedule_settings_rebuild()

    def _schedule_settings_rebuild(self) -> None:
        """Defer the expensive model reprojection until Settings has closed."""
        if not self._settings_rebuild_is_active():
            return
        self._settings_rebuild_generation += 1
        generation = self._settings_rebuild_generation
        window_ref = weakref.ref(self)
        QTimer.singleShot(
            0,
            lambda ref=window_ref, generation=generation: _run_deferred_settings_rebuild(
                ref, generation
            ),
        )

    def _settings_rebuild_is_active(self) -> bool:
        """Return whether a deferred callback may still touch this window."""
        if getattr(self, "_close_pending", False) or getattr(
            self, "_lifecycle_closed", False
        ):
            return False
        if isinstance(self, QObject):
            try:
                if sip.isdeleted(self):
                    return False
            except (TypeError, RuntimeError):
                return False
        return True

    def _run_settings_rebuild(self, generation: int) -> None:
        if self._settings_rebuild_is_active() and generation == self._settings_rebuild_generation:
            self._apply_data_layout(self._data_layout)
            self._save_accepted_settings()
            self._update_raw_controls()
            self._update_analyze_slot()
            self._apply_default_tab()
            # Cards are rendered from result data only; Settings never changes
            # them.  Rebuilding every card here was the multi-second close
            # freeze, so only the changed projections (columns, persistence,
            # controls, default tab) are refreshed.

    def _save_accepted_settings(self) -> None:
        """Persist one accepted dialog as a single crash-safe settings update."""
        column_visibility = {
            name: self._persisted_column_visible(index)
            for index, name in enumerate(self._table_columns)
            if index != 0
        }
        store = open_settings(
            self._settings_path(), self._legacy_settings_path(), defer_initial_save=True
        )
        store.setValues(
            {
                "allow_filename_alias_detection": str(self._allow_filename_alias_detection).lower(),
                "auto_analyze_on_add": str(self._auto_analyze_on_add).lower(),
                "dump_json_modelinfo": str(self._dump_json_modelinfo).lower(),
                "auto_load_raw_dump": str(self._auto_load_raw_dump).lower(),
                "cache_full_data_on_analyze": str(self._cache_full_data_on_analyze).lower(),
                "analysis_threads": str(self._analysis_threads),
                "add_mode": self._add_mode,
                "default_tab": self._default_tab,
                "table_columns": json.dumps(column_visibility),
                "data_layout": self._capture_data_layout(),
            }
        )

    def _refresh_cache_dialog(self, dialog) -> None:
        report = self._cache_report().availability
        dialog.cache_counts_label.setText(f"Total: {report.total}  Active: {report.active}  Historic: {report.historic}")
        dialog.verify_cache_btn.setEnabled(report.total > 0)

    def _apply_theme(self, theme_id: str, theme=None) -> None:
        from PyQt6.QtWidgets import QApplication
        from front.application import apply_theme
        application = QApplication.instance()
        if application is not None:
            apply_theme(application, theme_id, theme=theme, parent=self)
            self._refresh_theme_colors()

    def _apply_theme_preview(self, theme) -> None:
        """Apply a validated in-memory palette without requiring a disk round-trip."""
        if theme is not None:
            self._apply_theme(str(getattr(theme, "id", "default")), theme)

    def _refresh_theme_colors(self) -> None:
        """Re-apply theme colors to widgets that cached them at construction time."""
        try:
            from back.theme_loader import get_global_theme_colors
            tc = get_global_theme_colors()
        except Exception:
            return
        for name in ("progress_label", "selected_count_label", "table_selected_count_label"):
            label = getattr(self, name, None)
            if label is not None:
                label.setStyleSheet("color: %(muted)s; font-size: 11px;" % tc)
        placeholder = getattr(self, "cards_placeholder", None)
        if placeholder is not None:
            placeholder.setStyleSheet("color: %(surface_alt)s; font-size: 14px; padding: 60px;" % tc)
        settings_dialog = getattr(self, "_settings_dialog", None)
        if settings_dialog is not None:
            try:
                settings_dialog.refresh_theme(tc)
            except RuntimeError:
                self._settings_dialog = None
        # Refresh ModelCard stylesheets
        cards_container = getattr(self, "cards_scroll", None)
        if cards_container is not None:
            try:
                root = cards_container.rootPane()
                if root is not None:
                    for child in root.children():
                        if hasattr(child, "_refresh_style") and hasattr(child, "filepath"):
                            child._refresh_style()
            except Exception:
                pass
        # Refresh embedded Explorer stylesheets.
        explorer = getattr(self, "_explorer", None)
        if explorer is not None and hasattr(explorer, "refresh_theme"):
            try:
                explorer.refresh_theme(tc)
            except Exception:
                pass
        advanced_dialog = getattr(self, "_advanced_dialog", None)
        if advanced_dialog is not None and advanced_dialog.isVisible():
            try:
                advanced_dialog.refresh_theme()
            except RuntimeError:
                self._advanced_dialog = None

    def _settings_data_layout(self) -> dict[str, Any]:
        store = open_settings(self._settings_path(), self._legacy_settings_path())
        raw = store.value("data_layout", {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _remembered_settings_size(self):
        """Previously accepted Settings size, or the canonical default."""
        from back.settings_store import DEFAULTS
        store = open_settings(
            self._settings_path(), self._legacy_settings_path(), defer_initial_save=True
        )
        return store.value("settings_size", DEFAULTS.get("settings_size"))

    def _save_settings_size(self, dialog) -> None:
        """Persist the Settings size on both OK and X/close dismissal."""
        getter = getattr(dialog, "dialog_size", None)
        if not callable(getter):
            return
        size = getter()
        if not isinstance(size, (list, tuple)) or len(size) != 2:
            return
        try:
            width, height = int(size[0]), int(size[1])
        except (TypeError, ValueError):
            return
        if width <= 0 or height <= 0:
            return
        store = open_settings(
            self._settings_path(), self._legacy_settings_path(), defer_initial_save=True
        )
        store.setValue("settings_size", {"width": width, "height": height})

    def _settings_path(self):
        from app_paths import settings_path
        return settings_path()

    def _legacy_settings_path(self):
        from app_paths import legacy_settings_path
        return legacy_settings_path()

    def _column_definitions(self) -> list[ColumnDefinition]:
        """Canonical column definitions seeded into Settings and reset."""
        return list(DATA_COLUMNS)

    def _save_data_layout(self) -> None:
        store = open_settings(self._settings_path(), self._legacy_settings_path())
        store.setValue("data_layout", self._capture_data_layout())

    def _show_advanced_viewer(self) -> None:
        filepath = str(self.raw_combo.currentData() or "")
        self._show_advanced_viewer_for_path(filepath)

    def _show_advanced_viewer_for_path(self, filepath: str) -> None:
        """Open the exact requested model, never an arbitrary selected entry."""
        filepath = str(filepath or "")
        inspection = self._result_for_filepath(filepath) if filepath else None
        if inspection is None and filepath:
            inspection = get_cached_inspection_snapshots([filepath]).get(filepath)
        if inspection is None:
            QMessageBox.information(self, "Advanced Viewer", "The requested model is unavailable.")
            return
        detail = get_cached_inspection_snapshots([filepath]).get(filepath, {}) if filepath else {}
        self._advanced_dialog = AdvancedViewerDialog(
            self, detail or inspection
        )
        explorer = self._advanced_dialog.explorer_tab
        explorer.inspect_requested.connect(self._handle_explorer_inspect)
        explorer.export_requested.connect(self._handle_explorer_export)
        explorer.extraction_requested.connect(self._handle_explorer_extract)
        self._advanced_dialog.exec()

    def _handle_explorer_inspect(self, request: dict[str, Any]) -> None:
        path = str(request.get("inspection", {}).get("filepath") or "")
        if path and Path(path).is_file():
            self._add_files([path])
        else:
            QMessageBox.information(self, "Explorer", "The cached header is historic or unavailable; no file inspection was started.")

    def _save_explorer_request(self, request: dict[str, Any], title: str) -> None:
        destination, _ = QFileDialog.getSaveFileName(
            self, title, str(ensure_output_dir()), "JSON files (*.json)"
        )
        if not destination:
            return
        payload = {"candidate": request.get("candidate", {}), "inspection": request.get("inspection", {}), "header_only": True}
        try:
            Path(destination).write_text(json.dumps(payload, indent=2, ensure_ascii=False, default=str), encoding="utf-8")
        except OSError as exc:
            QMessageBox.warning(self, title, f"Could not write the selected destination: {exc}")

    def _handle_explorer_export(self, request: dict[str, Any]) -> None:
        self._save_explorer_request(request, "Export Explorer Header")

    def _handle_explorer_extract(self, request: dict[str, Any]) -> None:
        self._save_explorer_request(request, "Save Extraction Request")

    def _cache_report(self):
        paths = self._list_cached_inspection_paths()
        identities = get_cached_inspection_identity_snapshots(paths)
        # Do not eagerly materialize summaries: path-only records preserve
        # behavior for entries that cannot be read, while normal entries retain
        # their persisted size/mtime identity for verification.
        entries = [identities.get(path, {"filepath": path}) for path in paths]
        return verify_cache_entries(entries)

    def _refresh_cache_controls(self, report=None) -> None:
        if report is None:
            report = self._cache_report()
        availability = report.availability
        label = getattr(self, "cache_counts_label", None)
        if label is not None:
            label.setText(f"Total: {availability.total}  Active: {availability.active}  Historic: {availability.historic}")
        self._refresh_cache_menu_actions(availability)

    def _refresh_cache_menu_actions(self, availability=None) -> None:
        """Show/hide cache-load actions based on cache population and view state."""
        if availability is None:
            availability = getattr(self._cache_report(), "availability", None)
        view_nonempty = bool(self._results)
        if availability is None:
            # Minimal test mocks may only expose entries; still honor the
            # view-nonempty disable rule.
            self._refresh_cache_menu_enabled()
            return
        actions = (
            (getattr(self, "_cache_load_active_action", None), availability.load_cache),
            (getattr(self, "_cache_load_all_action", None), availability.load_cache_all),
            (getattr(self, "_cache_load_archived_action", None), availability.load_cache_archived),
        )
        for action, available in actions:
            if action is not None:
                action.setVisible(available)
                action.setEnabled(not view_nonempty)

    def _refresh_cache_menu_enabled(self) -> None:
        """Disable cache-load actions whenever the view is non-empty (cheap)."""
        view_nonempty = bool(getattr(self, "_results", None))
        for name in (
            "_cache_load_active_action",
            "_cache_load_all_action",
            "_cache_load_archived_action",
        ):
            action = getattr(self, name, None)
            if action is not None:
                action.setEnabled(not view_nonempty)

    def _refresh_tracked_settings_dialog(self) -> None:
        """Refresh an open Settings dialog's cache counts without dangling access."""
        dialog = getattr(self, "_settings_dialog", None)
        if dialog is None:
            return
        if isinstance(dialog, QObject):
            try:
                if sip.isdeleted(dialog):
                    return
            except (TypeError, RuntimeError):
                return
        self._refresh_cache_dialog(dialog)

    def _on_cache_sync_completed(self) -> None:
        """Refresh cache-driven UI after the background sync worker finishes."""
        self._cache_sync_worker = None
        self._refresh_cache_controls()
        self._refresh_tracked_settings_dialog()

    def _schedule_cache_sync(self, report=None) -> None:
        """Refresh changed, available headers in a worker without blocking Qt."""
        if report is None:
            report = self._cache_report()
        paths = [entry.path for entry in report.entries if entry.action == "refresh" and entry.is_active]
        if not paths or getattr(self, "_cache_sync_worker", None) is not None:
            return
        worker = AnalysisWorker(
            paths,
            {
                "allow_filename_alias_detection": self._allow_filename_alias_detection,
                "checkpoint_safety": CHECKPOINT_SAFETY_METADATA,
            },
            1,
        )
        self._cache_sync_worker = worker
        worker.result_ready.connect(lambda _data, w=worker: w.acknowledge_event())
        worker.error_occurred.connect(lambda _path, _error, w=worker: w.acknowledge_event())
        worker.all_done.connect(self._on_cache_sync_completed)
        worker.start()

    def _verify_cached_file_paths(self) -> None:
        """Verify cached file paths and surface a completion summary.

        Shows initial progress, derives missing/archive vs changed/refresh
        counts from the actual verifier action values, schedules changed
        entries through the existing background cache sync mechanism (without
        inspecting missing historic entries), and refreshes cache controls
        on completion.  When a sync worker is already running, the summary
        distinguishes entries already being synced from newly scheduled ones.
        """
        self._set_progress_status("Verifying cached file paths...")
        report = self._cache_report()
        availability = report.availability
        action_plan = report.action_plan
        archived = sum(1 for e in action_plan if e.action == "archive")
        changed = sum(1 for e in action_plan if e.action == "refresh")

        # A running worker means those changed entries were not newly queued;
        # report them honestly instead of claiming a fresh schedule.
        had_sync_worker = getattr(self, "_cache_sync_worker", None) is not None
        if changed:
            self._schedule_cache_sync()

        self._refresh_cache_controls()
        if changed and had_sync_worker:
            changed_note = f"{changed} changed entries already being synced"
        else:
            changed_note = f"{changed} changed entries scheduled for inspection"
        self._set_progress_status(
            f"Verify: {availability.total} total, {availability.active} active, "
            f"{availability.historic} historic | "
            f"{archived} archived/missing, {changed_note}"
        )
        self._clear_progress_status(delay_ms=8000)
