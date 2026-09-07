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

from back.cache_verifier import verify_cache_entries
from back.settings_store import open_settings
from background_tasks import AnalysisWorker
from front.advanced_viewer import AdvancedViewerDialog
from front.cache_identity import get_cached_inspection_identity_snapshots
from front.settings_data_tab import ColumnDefinition
from front.window_layout import SMART_COLUMN_GROUPS
from model_cache import get_cached_inspection_snapshots


_DIFFUSION_PARTS = ("unet", "vae", "text_encoder", "text_encoder_2", "transformer")


def _result_uses_smart_group(key: str, data: dict) -> bool:
    """Whether one loaded result genuinely uses a smart group's family columns.

    Mirrors what ``_add_table_row`` renders: only fields producing a real
    value (not the "-" placeholder) count as genuine usage.
    """
    if key == "llm":
        return bool(data.get("is_moe")) or data.get("expert_count") is not None or data.get("expert_used_count") is not None
    if key == "diffusion":
        comps = data.get("components") or {}
        precs = data.get("component_precisions") or {}
        return any(precs.get(part) or comps.get(part) for part in _DIFFUSION_PARTS) or bool(data.get("named_text_encoders"))
    if key == "adapter":
        return bool(data.get("adapter_type")) or bool(data.get("lora_rank"))
    return False


def _run_deferred_settings_rebuild(window_ref, generation: int) -> None:
    """Run a queued rebuild only while its Python window wrapper is alive."""
    window = window_ref()
    if window is not None:
        window._run_settings_rebuild(generation)


class IntegrationMixin:
    """Keep optional Phase 2/3 features out of the near-limit core mixins."""

    def _configure_extended_ui(self) -> None:
        self._advanced_dialog: AdvancedViewerDialog | None = None
        self._settings_rebuild_generation = 0
        self._data_layout = self._settings_data_layout()
        self._apply_data_layout(self._data_layout)
        self._init_smart_groups()
        header = self.table.horizontalHeader()
        assert header is not None
        header.sectionMoved.connect(lambda *_args: self._capture_data_layout())
        header.sectionResized.connect(lambda *_args: self._capture_data_layout())
        self._refresh_cache_controls()
        QTimer.singleShot(0, self._schedule_cache_sync)

    def _open_settings(self) -> None:
        from front.settings_dialog import SettingsDialog
        dialog = SettingsDialog(
            self, allow_filename_alias_detection=self._allow_filename_alias_detection,
            auto_analyze_on_add=self._auto_analyze_on_add, dump_json_modelinfo=self._dump_json_modelinfo,
            auto_load_raw_dump=self._auto_load_raw_dump,
            cache_full_data_on_analyze=self._cache_full_data_on_analyze, analysis_threads=self._analysis_threads,
            add_mode=self._add_mode, default_tab=self._default_tab, card_fields=self._card_field_visibility,
            simple_card_fields=self._simple_card_field_visibility, data_columns=self._column_definitions(),
            data_configuration=self._capture_data_layout(),
            theme_id=self._data_layout.get("theme", "default"),
        )
        dialog.clear_cache_btn.clicked.connect(
            lambda: self._clear_inspection_cache_from_settings(dialog)
        )
        dialog.verify_cache_btn.clicked.connect(self._verify_cached_file_paths)
        dialog.themeChanged.connect(self._apply_theme)
        dialog.themePreviewChanged.connect(self._apply_theme_preview)
        self._refresh_cache_dialog(dialog)
        if not dialog.exec():
            return
        self._allow_filename_alias_detection = dialog.alias_checkbox.isChecked()
        self._auto_analyze_on_add = dialog.auto_analyze_checkbox.isChecked()
        self._dump_json_modelinfo = dialog.dump_json_checkbox.isChecked()
        self._auto_load_raw_dump = dialog.auto_load_raw_checkbox.isChecked()
        self._cache_full_data_on_analyze = dialog.cache_full_data_checkbox.isChecked()
        self._analysis_threads = int(dialog.analysis_threads_combo.currentData() or 1)
        self._add_mode = str(dialog.add_mode_combo.currentData() or "replace")
        self._default_tab = str(dialog.default_tab_combo.currentData() or "cards")
        for key, check in dialog.card_field_checks.items():
            self._card_field_visibility[key] = check.isChecked()
        for key, check in dialog.simple_card_field_checks.items():
            self._simple_card_field_visibility[key] = check.isChecked()
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
            self._rebuild_active_cards_time_sliced()

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
                "detailed_card_fields": json.dumps(self._card_field_visibility),
                "simple_card_fields": json.dumps(self._simple_card_field_visibility),
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

    def _apply_theme_preview(self, theme) -> None:
        """Apply a validated in-memory palette without requiring a disk round-trip."""
        if theme is not None:
            self._apply_theme(str(getattr(theme, "id", "default")), theme)

    def _settings_data_layout(self) -> dict[str, Any]:
        store = open_settings(self._settings_path(), self._legacy_settings_path())
        raw = store.value("data_layout", {})
        return dict(raw) if isinstance(raw, dict) else {}

    def _settings_path(self):
        from app_paths import settings_path
        return settings_path()

    def _legacy_settings_path(self):
        from app_paths import legacy_settings_path
        return legacy_settings_path()

    def _column_definitions(self) -> list[ColumnDefinition]:
        return [
            ColumnDefinition(self._column_key(index), label, index != 0, self.table.columnWidth(index), 32)
            for index, label in enumerate(self._table_columns)
        ]

    def _column_key(self, index: int) -> str:
        return "selection" if index == 0 else f"column_{index}"

    # --- Smart Data-column groups (runtime-only, never persisted) ---------

    def _init_smart_groups(self) -> None:
        self._smart_group_state: dict[str, bool] = {key: False for key in SMART_COLUMN_GROUPS}
        self._smart_group_manual: set[str] = set()
        self._smart_group_indices: dict[str, int] = {}
        self._smart_group_owner: dict[str, str] = {}
        for key, spec in SMART_COLUMN_GROUPS.items():
            for name in spec["columns"]:
                if name in self._table_columns:
                    self._smart_group_indices[name] = self._table_columns.index(name)
                    self._smart_group_owner[name] = key
        # Snapshot persisted per-column visibility as the mask baseline.
        self._smart_group_baseline = {
            name: not self.table.isColumnHidden(index)
            for name, index in self._smart_group_indices.items()
        }
        self._apply_smart_group_masks()

    def _apply_smart_group_masks(self) -> None:
        """Off masks all group columns; on reveals only baseline-visible ones."""
        for name, index in self._smart_group_indices.items():
            visible = (
                self._smart_group_baseline.get(name, True)
                and self._smart_group_state[self._smart_group_owner[name]]
            )
            self.table.setColumnHidden(index, not visible)

    def _set_smart_group_checkbox(self, key: str, checked: bool) -> None:
        checkbox = self._smart_group_checkboxes.get(key)
        if checkbox is not None and checkbox.isChecked() != checked:
            checkbox.blockSignals(True)
            checkbox.setChecked(checked)
            checkbox.blockSignals(False)

    def _on_smart_group_toggled(self, key: str, checked: bool) -> None:
        if key not in SMART_COLUMN_GROUPS or not hasattr(self, "_smart_group_state"):
            return
        self._smart_group_manual.add(key)  # an explicit user toggle wins the session
        self._smart_group_state[key] = bool(checked)
        self._set_smart_group_checkbox(key, bool(checked))
        self._apply_smart_group_masks()

    def _note_result_for_smart_groups(self, data: dict) -> None:
        """Auto-enable groups whose family columns the loaded result uses."""
        changed = False
        for key in SMART_COLUMN_GROUPS:
            if self._smart_group_state[key] or key in self._smart_group_manual:
                continue
            if _result_uses_smart_group(key, data):
                self._smart_group_state[key] = True
                self._set_smart_group_checkbox(key, True)
                changed = True
        if changed:
            self._apply_smart_group_masks()

    def _reset_auto_smart_groups(self) -> None:
        """Revert auto-enabled groups to the session default (unchecked)."""
        for key in SMART_COLUMN_GROUPS:
            if self._smart_group_state[key] and key not in self._smart_group_manual:
                self._smart_group_state[key] = False
                self._set_smart_group_checkbox(key, False)
        self._apply_smart_group_masks()

    def _persisted_column_visible(self, index: int) -> bool:
        """Column visibility for persistence: smart-group masks are excluded."""
        if index <= 0 or index >= len(self._table_columns):
            return True
        name = self._table_columns[index]
        owner = self._smart_group_owner.get(name)
        if owner is not None and not self._smart_group_state[owner]:
            return self._smart_group_baseline.get(name, True)
        return not self.table.isColumnHidden(index)

    def _apply_data_layout(self, layout: dict[str, Any]) -> None:
        rows = layout.get("columns", ()) if isinstance(layout, dict) else ()
        if not isinstance(rows, list):
            return
        by_key = {str(row.get("key")): row for row in rows if isinstance(row, dict)}
        header = self.table.horizontalHeader()
        assert header is not None
        for logical in range(self.table.columnCount()):
            entry = by_key.get(self._column_key(logical))
            if not entry:
                continue
            visible = bool(entry.get("visible", logical == 0 or not self.table.isColumnHidden(logical)))
            self.table.setColumnHidden(logical, not visible)
            name = self._table_columns[logical] if logical < len(self._table_columns) else ""
            if getattr(self, "_smart_group_owner", None) and name in self._smart_group_owner:
                # Persisted per-column visibility refreshes the mask baseline.
                self._smart_group_baseline[name] = visible
            try:
                self.table.setColumnWidth(logical, max(32, int(entry.get("width", self.table.columnWidth(logical)))))
            except (TypeError, ValueError):
                pass
        for visual, row in enumerate(rows):
            if not isinstance(row, dict):
                continue
            key = str(row.get("key", ""))
            for logical in range(self.table.columnCount()):
                if key == self._column_key(logical) and header.visualIndex(logical) != visual:
                    header.moveSection(header.visualIndex(logical), visual)
                    break
        if hasattr(self, "_smart_group_state"):
            self._apply_smart_group_masks()

    def _capture_data_layout(self) -> dict[str, Any]:
        header = self.table.horizontalHeader()
        assert header is not None
        columns = []
        for visual in range(self.table.columnCount()):
            logical = header.logicalIndex(visual)
            columns.append({
                "key": self._column_key(logical),
                "visible": self._persisted_column_visible(logical),
                "width": self.table.columnWidth(logical),
            })
        self._data_layout = {"columns": columns, "theme": self._data_layout.get("theme", "default")}
        return self._data_layout

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
            self, detail or inspection, card_fields=self._card_field_visibility
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
        destination, _ = QFileDialog.getSaveFileName(self, title, "", "JSON files (*.json)")
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
        # Do not eagerly materialize summaries: the startup loader owns that
        # compatibility seam.  Path-only records preserve behavior for entries
        # that cannot be read, while normal entries retain their persisted
        # size/mtime identity for verification.
        entries = [identities.get(path, {"filepath": path}) for path in paths]
        return verify_cache_entries(entries)

    def _refresh_cache_controls(self) -> None:
        report = self._cache_report()
        availability = report.availability
        label = getattr(self, "cache_counts_label", None)
        if label is not None:
            label.setText(f"Total: {availability.total}  Active: {availability.active}  Historic: {availability.historic}")
        self._refresh_cache_menu_actions()

    def _refresh_cache_menu_actions(self) -> None:
        """Show/hide cache-load actions based on cache population and view state."""
        report = self._cache_report().availability
        view_nonempty = bool(self._results)
        actions = (
            (getattr(self, "_cache_load_active_action", None), report.load_cache),
            (getattr(self, "_cache_load_all_action", None), report.load_cache_all),
            (getattr(self, "_cache_load_archived_action", None), report.load_cache_archived),
        )
        for action, available in actions:
            if action is not None:
                action.setVisible(available)
                action.setEnabled(not view_nonempty)

    def _schedule_cache_sync(self) -> None:
        """Refresh changed, available headers in a worker without blocking Qt."""
        report = self._cache_report()
        paths = [entry.path for entry in report.entries if entry.action == "refresh" and entry.is_active]
        if not paths or getattr(self, "_cache_sync_worker", None) is not None:
            return
        worker = AnalysisWorker(paths, {"allow_filename_alias_detection": self._allow_filename_alias_detection}, 1)
        self._cache_sync_worker = worker
        worker.result_ready.connect(lambda _data, w=worker: w.acknowledge_event())
        worker.error_occurred.connect(lambda _path, _error, w=worker: w.acknowledge_event())
        worker.all_done.connect(lambda: setattr(self, "_cache_sync_worker", None))
        worker.start()

    def _load_cache_status(self, wanted: str | None) -> None:
        report = self._cache_report()
        paths = [entry.path for entry in report.entries if wanted is None or entry.classification == wanted]
        snapshots = self._get_cached_inspection_summary_snapshots(paths)
        loaded_count = 0
        for path in paths:
            data = snapshots.get(path)
            if not data or self._result_for_filepath(path):
                continue
            data.update({"filepath": path, "filename": Path(path).name, "cache_status": "historic" if wanted == "historic" else "snapshot"})
            self._normalize_result_data(data)
            if path not in self._queued_files:
                self._queued_files.append(path)
            self._results.append(data)
            self._add_card(data)
            self._add_table_row(data)
            loaded_count += 1
        if loaded_count:
            self.arch_filter_btn.replace_items(
                data.get("architecture", "Unknown") for data in self._results
            )
            self.tag_filter_btn.replace_items(
                tag for data in self._results for tag in self._filter_tags_for_data(data)
            )
            self.format_filter_btn.replace_items(
                self._format_filter_for_data(data) for data in self._results
            )
            self._apply_arch_filter(
                refresh_raw=False,
                refresh_geometry=False,
                update_selection=False,
            )
        self._refresh_raw_combo_filtered()
        self._sync_selection_visuals()
        self._refresh_card_layout_geometry()
        self._set_progress_status(f"Loaded {loaded_count} cached {'historic ' if wanted == 'historic' else ''}summaries")

    def _load_cache(self) -> None:
        self._load_cache_status("active")

    def _load_cache_all(self) -> None:
        self._load_cache_status(None)

    def _load_cache_archived(self) -> None:
        self._load_cache_status("historic")

    def _verify_cached_file_paths(self) -> None:
        """Verify cached file paths and surface a completion summary.

        Shows initial progress, derives missing/archive vs changed/refresh
        counts from the actual verifier action values, schedules changed
        entries through the existing background cache sync mechanism (without
        inspecting missing historic entries), and refreshes cache controls
        on completion.
        """
        self._set_progress_status("Verifying cached file paths...")
        report = self._cache_report()
        availability = report.availability
        action_plan = report.action_plan
        archived = sum(1 for e in action_plan if e.action == "archive")
        changed = sum(1 for e in action_plan if e.action == "refresh")

        # Schedule changed entries through the existing sync mechanism.
        # _schedule_cache_sync guards against duplicate workers internally.
        if changed:
            self._schedule_cache_sync()
            # Refresh cache controls when the sync worker finishes.
            worker = getattr(self, "_cache_sync_worker", None)
            if worker is not None:
                worker.all_done.connect(self._refresh_cache_controls)

        self._refresh_cache_controls()
        self._set_progress_status(
            f"Verify: {availability.total} total, {availability.active} active, "
            f"{availability.historic} historic | "
            f"{archived} archived/missing, {changed} changed entries scheduled for inspection"
        )
        self._clear_progress_status(delay_ms=8000)
