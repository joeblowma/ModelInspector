# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false, reportOperatorIssue=false
# pylint: disable=no-member
from pathlib import Path

from PyQt6.QtCore import QMimeData, Qt
from PyQt6.QtWidgets import QApplication, QCheckBox, QFileDialog, QMenu


def _clipboard():
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    return clipboard


class SelectionControllerMixin:
    """Selection behavior; state is initialized by ``WindowCoreMixin``."""

    _selected_paths: set[str]

    def _on_card_checkbox_toggled(self, filepath: str, checked: bool):
        if self._syncing_selection or not filepath:
            return
        if checked:
            self._selected_paths.add(filepath)
        else:
            self._selected_paths.discard(filepath)
        self._sync_selection_visuals()

    def _on_card_drag_over(self, filepath: str):
        if not filepath:
            return
        # Drag-over selection should only add to selection.
        if filepath not in self._selected_paths:
            self._selected_paths.add(filepath)
            self._sync_selection_visuals()

    def _find_result_by_path(self, filepath: str):
        for d in self._results:
            if d.get("filepath") == filepath:
                return d
        return None

    def _build_card_info_text(self, data: dict, simple_view: bool) -> str:
        lines = []
        lines.append(f"File: {data.get('filename', '')}")
        lines.append(f"Path: {data.get('filepath', '')}")
        lines.append(f"Architecture: {data.get('architecture', '')}")
        lines.append(f"Model Type: {data.get('model_type', '')}")
        if data.get("adapter_type"):
            lines.append(f"Adapter: {data.get('adapter_type')}")

        components = data.get("components", {})
        comp_labels = {
            "unet": "UNet",
            "transformer": "Transformer",
            "vae": "VAE",
            "text_encoder": "Text Encoder",
            "text_encoder_2": "Text Encoder 2",
        }
        comp_on = [lbl for k, lbl in comp_labels.items() if components.get(k)]
        if comp_on:
            lines.append("Tags: " + ", ".join(comp_on))

        fields = (
            self._simple_card_field_visibility
            if simple_view
            else self._card_field_visibility
        )
        if fields.get("parameters", True):
            lines.append(f"Parameters: {data.get('total_params_friendly', '-')}")
        if fields.get("precision", True):
            component_precisions = data.get("component_precisions") or {}
            added_component_precision = False
            component_precision_labels = [
                ("unet", "UNet Precision"),
                ("transformer", "Transformer Precision"),
                ("vae", "VAE Precision"),
                ("text_encoder", "Text Encoder Precision"),
                ("text_encoder_2", "Text Encoder 2 Precision"),
            ]
            for comp_key, comp_label in component_precision_labels:
                comp_precision = component_precisions.get(comp_key)
                if not comp_precision:
                    continue
                lines.append(f"{comp_label}: {comp_precision}")
                added_component_precision = True
            if not added_component_precision:
                precision_text = (
                    data.get("precision_display")
                    or data.get("component_precision_summary")
                    or data.get("precision_summary", "-")
                )
                lines.append(f"Precision: {precision_text}")
        if fields.get("file_size", True):
            lines.append(f"File Size: {data.get('file_size_friendly', '-')}")
        if fields.get("tensors", True):
            lines.append(f"Tensors: {data.get('tensor_count', '-')}")
        if fields.get("lora_rank", True):
            lr = data.get("lora_rank")
            if lr:
                lines.append(f"LoRA Rank: {lr}")
        if fields.get("extra_meta", True):
            for k, v in data.get("extra", {}).items():
                lines.append(f"{k.replace('_', ' ').title()}: {v}")
        if fields.get("training_meta", True):
            for k, v in data.get("training_meta", {}).items():
                lines.append(f"{k.replace('_', ' ').title()}: {v}")

        return "\n".join(lines)

    def _copy_selected_cards_info(self, simple_view: bool):
        paths = self._visible_selected_paths()
        if not paths:
            return
        blocks = []
        for fp in paths:
            d = self._find_result_by_path(fp)
            if not d:
                continue
            blocks.append(self._build_card_info_text(d, simple_view))
        if blocks:
            _clipboard().setText(("\n\n" + ("-" * 50) + "\n\n").join(blocks))

    def _on_card_context_menu(self, filepath: str, simple_view: bool, global_pos):
        data = self._find_result_by_path(filepath)
        if not data:
            return
        menu = QMenu(self)
        advanced_viewer = menu.addAction("Advanced Viewer")
        view_raw = menu.addAction("View Raw")
        copy_info = menu.addAction("Copy Info")
        copy_selected = None
        visible = set(self._visible_paths())
        selected_visible = [p for p in self._selected_paths if p in visible]
        if filepath in self._selected_paths and len(selected_visible) > 1:
            copy_selected = menu.addAction(
                f"Copy Info from selected files [{len(selected_visible)}]"
            )
        chosen = menu.exec(global_pos)
        if chosen == advanced_viewer:
            self._show_advanced_viewer_for_path(filepath)
        elif chosen == view_raw:
            self._show_raw_for_filepath(filepath)
        elif chosen == copy_info:
            _clipboard().setText(self._build_card_info_text(data, simple_view))
        elif copy_selected is not None and chosen == copy_selected:
            self._copy_selected_cards_info(simple_view)

    def _on_table_checkbox_toggled(self, filepath: str, checked: bool):
        if self._syncing_selection or not filepath:
            return
        if checked:
            self._selected_paths.add(filepath)
        else:
            self._selected_paths.discard(filepath)
        self._sync_selection_visuals()

    def _on_table_cell_clicked(self, row: int, col: int):
        if self._syncing_selection:
            return
        if row < 0 or row >= self.table.rowCount():
            return
        item = self.table.item(row, 1)
        if not item:
            return
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not filepath:
            return
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        visible = self._visible_paths()
        if filepath not in visible:
            return
        idx = visible.index(filepath)
        if (
            shift
            and self._last_selected_row >= 0
            and self._last_selected_row < len(visible)
        ):
            lo = min(self._last_selected_row, idx)
            hi = max(self._last_selected_row, idx)
            for fp in visible[lo : hi + 1]:
                self._selected_paths.add(fp)
        elif ctrl:
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_row = idx
        else:
            # Single-click behaves like ctrl-click toggle.
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_row = idx
        self._sync_selection_visuals()

    def _on_table_item_selection_changed(self):
        # Keep this lightweight: item selection is mainly for Ctrl+C cells.
        pass

    def _open_table_row_in_advanced_viewer(self, row: int) -> None:
        """Open the exact model represented by a Data row."""
        item = self.table.item(row, 1)
        filepath = item.data(Qt.ItemDataRole.UserRole) if item else None
        if filepath:
            self._show_advanced_viewer_for_path(str(filepath))

    def _on_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        fp_item = self.table.item(row, 1)
        filepath = fp_item.data(Qt.ItemDataRole.UserRole) if fp_item else None

        menu = QMenu(self)
        advanced_viewer = menu.addAction("Advanced Viewer")
        view_raw = menu.addAction("View Raw")
        copy_folder_path = menu.addAction("Copy Folder Path")
        copy_sel = menu.addAction("Copy Selected Entries")
        viewport = self.table.viewport()
        assert viewport is not None
        chosen = menu.exec(viewport.mapToGlobal(pos))
        if chosen == advanced_viewer and filepath:
            self._open_table_row_in_advanced_viewer(row)
        elif chosen == view_raw and filepath:
            self._show_raw_for_filepath(filepath)
        elif chosen == copy_folder_path and filepath:
            _clipboard().setText(str(Path(filepath).parent))
        elif chosen == copy_sel:
            self._copy_selected_table_cells()

    def _sync_selection_visuals(self):
        self._syncing_selection = True
        try:
            for fp, card in self._path_to_card.items():
                card.set_selected(fp in self._selected_paths)
            for fp, row in self._path_to_row.items():
                row = self._row_for_filepath(fp)
                if row is None:
                    continue
                if 0 <= row < self.table.rowCount():
                    cb = self.table.cellWidget(row, 0)
                    if isinstance(cb, QCheckBox):
                        cb.blockSignals(True)
                        cb.setChecked(fp in self._selected_paths)
                        cb.blockSignals(False)
        finally:
            self._syncing_selection = False
        self._update_selection_ui_state()

    def _update_selection_ui_state(self):
        visible = set(self._visible_paths())
        visible_selected_count = len(self._selected_paths & visible)
        total_selected_count = len(self._selected_paths)
        if total_selected_count == visible_selected_count:
            count_text = f"{visible_selected_count} selected"
        else:
            hidden_count = total_selected_count - visible_selected_count
            count_text = f"{visible_selected_count} selected ({hidden_count} hidden)"
        self.selected_count_label.setText(count_text)
        self.table_selected_count_label.setText(count_text)
        enabled = visible_selected_count > 0
        self.selected_action_btn.setEnabled(enabled)
        self.selected_action_menu_btn.setEnabled(True)

        if visible:
            all_selected = visible.issubset(self._selected_paths)
        else:
            all_selected = False

        self.cards_select_all_cb.blockSignals(True)
        self.cards_select_all_cb.setChecked(all_selected)
        self.cards_select_all_cb.blockSignals(False)

        self.table_select_all_cb.blockSignals(True)
        self.table_select_all_cb.setChecked(all_selected)
        self.table_select_all_cb.blockSignals(False)

    def _copy_selected_files_to_clipboard(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        mime = QMimeData()
        from PyQt6.QtCore import QUrl

        urls = [QUrl.fromLocalFile(p) for p in selected]
        mime.setUrls(urls)
        _clipboard().setMimeData(mime)

    def _move_selected_files(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        target = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not target:
            return
        import shutil

        moved = set()
        for src in selected:
            try:
                dst = str(Path(target) / Path(src).name)
                shutil.move(src, dst)
                moved.add(src)
            except Exception:
                pass
        if moved:
            self._queued_files = [p for p in self._queued_files if p not in moved]
            self._results = [r for r in self._results if r.get("filepath") not in moved]
            self._selected_paths -= moved
            self._rebuild_views_from_results()
            self._update_file_count()

    def _remove_selected_results(self):
        selected = set(self._visible_selected_paths())
        if not selected:
            return
        self._queued_files = [p for p in self._queued_files if p not in selected]
        self._results = [r for r in self._results if r.get("filepath") not in selected]
        self._selected_paths -= selected
        self._rebuild_views_from_results()
        self._update_file_count()

    def _copy_selected_names(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        text = "\n".join(Path(p).name for p in selected)
        _clipboard().setText(text)

    def _copy_selected_paths(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        text = "\n".join(selected)
        _clipboard().setText(text)

    def _rebuild_views_from_results(self):
        current_results = list(self._results)
        header = self.table.horizontalHeader()
        assert header is not None
        sorting_enabled = self.table.isSortingEnabled()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        self._cards.clear()
        self._path_to_card.clear()
        self._path_to_simple_card.clear()
        self._path_to_row.clear()
        self._clear_cards()
        self.table.setRowCount(0)
        self._reset_format_filter_items()
        self.raw_combo.clear()
        for data in current_results:
            self._normalize_result_data(data)
            self._add_card(data)
            self._add_table_row(data)
            self.format_filter_btn.add_item(self._format_filter_for_data(data))
        self.arch_filter_btn.replace_items(
            data.get("architecture", "Unknown") for data in current_results
        )
        self.tag_filter_btn.replace_items(
            tag for data in current_results for tag in self._filter_tags_for_data(data)
        )
        header.setSortIndicator(sort_column, sort_order)
        self.table.setSortingEnabled(sorting_enabled)
        self._apply_arch_filter()
        self._refresh_raw_combo_filtered()
        self._sync_selection_visuals()

    def _on_show_full_path_changed(self, state):
        self._show_full_paths = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item:
                continue
            fp = item.data(Qt.ItemDataRole.UserRole) or ""
            if self._show_full_paths and fp:
                item.setText(fp)
            else:
                item.setText(Path(fp).name if fp else item.text())

    def _copy_selected_table_cells(self):
        indexes = [
            i
            for i in self.table.selectedIndexes()
            if not self.table.isRowHidden(i.row())
        ]
        if not indexes:
            return
        indexes.sort(key=lambda x: (x.row(), x.column()))

        by_row = {}
        for i in indexes:
            by_row.setdefault(i.row(), []).append(i.column())

        lines = []
        for row in sorted(by_row.keys()):
            cols = sorted(set(by_row[row]))
            vals = []
            for c in cols:
                if c == 0:
                    cb = self.table.cellWidget(row, c)
                    vals.append(
                        "1" if isinstance(cb, QCheckBox) and cb.isChecked() else "0"
                    )
                else:
                    it = self.table.item(row, c)
                    vals.append(it.text() if it else "")
            lines.append("\t".join(vals))
        _clipboard().setText("\n".join(lines))


SelectionMixin = SelectionControllerMixin
