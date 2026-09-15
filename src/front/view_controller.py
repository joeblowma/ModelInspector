# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportGeneralTypeIssues=false, reportOperatorIssue=false
# pylint: disable=no-member
from pathlib import Path; from time import perf_counter
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import QCheckBox, QLabel
from front.filter_widgets import SortableTableWidgetItem; from front.model_card import ModelCard
from back.theme_loader import get_global_theme_colors
def _combo_data_str(value): return str(value) if value else None
_QUANT_DTYPE_CANON = {
    "F32": "f32", "F16": "f16", "BF16": "bf16",
    "float32": "f32", "float16": "f16", "bfloat16": "bf16",
    "blfloat16": "bf16",  # historical typo tolerated
}
def _data_quantization_display(data):
    label = str(data.get("quantization") or "").strip()
    if label:
        return label
    items = data.get("dtypes") or [{"dtype": data.get("precision_summary")}]
    dtypes = {
        str(item.get("dtype")).strip()
        for item in items
        if isinstance(item, dict) and item.get("dtype")
    }
    # Only a uniform standard float dtype is trustworthy; mixed/unknown -> "-".
    return _QUANT_DTYPE_CANON.get(dtypes.pop(), "-") if len(dtypes) == 1 else "-"

class ViewControllerMixin:
    """Render and rebuild result views using ``WindowCoreMixin`` state."""

    _card_rebuild_generation: int
    _selected_paths: set[str]

    def _dump_modelinfo_targets(self) -> list[str]:
        selected = self._visible_selected_paths()
        if selected:
            return selected
        if self.tabs.currentIndex() == 2:
            current = _combo_data_str(self.raw_combo.currentData())
            if current:
                return [current]
        return []
    def _clear_cards(self):
        if not self._results:
            # Real clear transitions drain results before clearing cards;
            # rebuild passes keep ``_results`` populated.
            self._reset_auto_smart_groups()
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_placeholder.setStyleSheet(
            "color: %(surface_alt)s; font-size: 14px; padding: 60px;" % get_global_theme_colors()
        )
        self.cards_layout.insertWidget(0, self.cards_placeholder)
        self._refresh_card_layout_geometry()

    def _add_card(self, data: dict):
        fp = str(data.get("filepath") or "")
        if fp and fp in self._path_to_card:
            return
        placeholder = self.cards_placeholder
        if placeholder:
            self.cards_layout.removeWidget(placeholder)
            placeholder.deleteLater()
            self.cards_placeholder = None
        card = ModelCard(data, simple_view=True)
        card.advanced_requested.connect(self._show_advanced_viewer_for_path)
        card.checkbox_toggled.connect(self._on_card_checkbox_toggled)
        card.drag_over_requested.connect(self._on_card_drag_over)
        card.context_requested.connect(self._on_card_context_menu)
        if fp:
            self._path_to_card[fp] = card
        self._cards.append(card)
        self.cards_layout.addWidget(card)
    def _rebuild_active_cards_time_sliced(self):
        self._card_rebuild_generation += 1
        generation = self._card_rebuild_generation
        self._cards.clear(); self._path_to_card.clear()
        pending = list(self._results); index = 0
        def build_batch():
            nonlocal index
            if generation != self._card_rebuild_generation or getattr(self, "_lifecycle_closed", False):
                return
            started = perf_counter(); built = 0
            while index < len(pending) and built < 8:
                data = pending[index]; self._add_card(data)
                filepath = str(data.get("filepath") or "")
                card = self._path_to_card.get(filepath)
                if card:
                    card.set_selected(filepath in self._selected_paths); card.set_filter_visible(self._is_data_visible(data))
                index += 1; built += 1
                if (perf_counter() - started) * 1000.0 >= 12.0:
                    break
            self._refresh_card_layout_geometry()
            if index < len(pending):
                QTimer.singleShot(0, build_batch)
        def clear_batch():
            nonlocal index
            if generation != self._card_rebuild_generation or getattr(self, "_lifecycle_closed", False):
                return
            started = perf_counter(); removed = 0
            while self.cards_layout.count() and removed < 8:
                item = self.cards_layout.takeAt(0)
                if item is None:
                    continue
                widget = item.widget()
                if widget is not None: widget.deleteLater()
                removed += 1
                if (perf_counter() - started) * 1000.0 >= 12.0:
                    break
            self._refresh_card_layout_geometry()
            if self.cards_layout.count(): QTimer.singleShot(0, clear_batch); return
            self._clear_cards()
            QTimer.singleShot(0, build_batch)
        QTimer.singleShot(0, clear_batch)
    def _refresh_card_layout_geometry(self):
        self.cards_layout.invalidate()
        self.cards_container.adjustSize()
        self.cards_container.updateGeometry()
        cards_viewport = self.cards_scroll.viewport()
        assert cards_viewport is not None
        margins = self.cards_layout.contentsMargins()
        maximum_width = max(1, cards_viewport.width() - margins.left() - margins.right())
        for card in self._path_to_card.values():
            card.setMaximumWidth(maximum_width)
        cards_viewport.update()
    def _add_table_row(self, data: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)
        comps = data.get("components", {})
        component_precisions = data.get("component_precisions") or {}
        training_meta = data.get("training_meta", {})
        filepath = data.get("filepath", "")
        unet_str = component_precisions.get("unet") or (
            "Yes" if comps.get("unet") else "-"
        )
        trans_str = component_precisions.get("transformer") or (
            "Yes" if comps.get("transformer") else "-"
        )
        vae_str = component_precisions.get("vae") or (
            "Yes" if comps.get("vae") else "-"
        )
        text_enc_parts = []
        te1 = component_precisions.get("text_encoder")
        te2 = component_precisions.get("text_encoder_2")
        if te1:
            text_enc_parts.append(f"TE1: {te1}")
        if te2:
            text_enc_parts.append(f"TE2: {te2}")
        if not text_enc_parts:
            for enc_name in data.get("named_text_encoders", {}):
                text_enc_parts.append(enc_name)
            if not text_enc_parts:
                if comps.get("text_encoder") and comps.get("text_encoder_2"):
                    text_enc_parts = ["CLIP, CLIP 2"]
                elif comps.get("text_encoder"):
                    text_enc_parts = ["Yes"]
                elif comps.get("text_encoder_2"):
                    text_enc_parts = ["Text Enc 2"]
        text_enc_str = ", ".join(text_enc_parts) if text_enc_parts else "-"
        lora_rank = data.get("lora_rank")
        rank_str = str(lora_rank) if lora_rank else "-"
        is_moe = bool(data.get("is_moe"))
        expert_count = data.get("expert_count")
        expert_used_count = data.get("expert_used_count")
        moe_str = "Yes" if is_moe else "-"
        expert_count_str = str(expert_count) if expert_count is not None else "-"
        expert_used_count_str = (
            str(expert_used_count) if expert_used_count is not None else "-"
        )
        values = [
            data["filename"], data.get("format", "-"), data["file_size_friendly"],
            data["architecture"], data["model_type"], data.get("adapter_type") or "-",
            _data_quantization_display(data), data.get("precision_summary", "-"),
            unet_str, vae_str, text_enc_str, trans_str, data["total_params_friendly"],
            str(data["tensor_count"]), rank_str, moe_str, expert_count_str,
            expert_used_count_str, training_meta.get("software", "-"),
            training_meta.get("train_images", "-"), training_meta.get("resolution", "-"),
            training_meta.get("epochs", "-"), training_meta.get("steps", "-"),
        ]
        cb = QCheckBox()
        # Center only the selection cell; keep a native QCheckBox so
        # isinstance(cellWidget(...), QCheckBox) checks and accessibility hold.
        # ponytail: QSS indicator positioning, switch to a delegate if themes fight it.
        cb.setStyleSheet("QCheckBox::indicator { subcontrol-position: center; }")
        cb.clicked.connect(
            lambda checked, fp=filepath: self._on_table_checkbox_toggled(fp, checked)
        )
        self.table.setCellWidget(row, 0, cb)
        for col, val in enumerate(values, start=1):
            if col == 1 and self._show_full_paths and filepath:
                val = filepath
            item = SortableTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            column_name = self._table_columns[col]
            if col == 1:
                item.setToolTip(filepath)
                item.setData(Qt.ItemDataRole.UserRole, filepath)
            else:
                item.setToolTip(str(val))
            if column_name == "File Size":
                item.setData(Qt.ItemDataRole.UserRole, int(data.get("file_size") or 0))
            elif column_name == "Parameters":
                item.setData(Qt.ItemDataRole.UserRole, int(data.get("total_params") or 0))
            elif column_name == "Tensors":
                item.setData(Qt.ItemDataRole.UserRole, int(data.get("tensor_count") or 0))
            elif column_name == "LoRA Rank":
                item.setData(Qt.ItemDataRole.UserRole, int(lora_rank or 0))
            elif column_name == "MoE":
                item.setData(Qt.ItemDataRole.UserRole, 1 if is_moe else 0)
            elif column_name == "Experts":
                item.setData(Qt.ItemDataRole.UserRole, int(expert_count or 0))
            elif column_name == "Exp Act":
                item.setData(Qt.ItemDataRole.UserRole, int(expert_used_count or 0))
            elif column_name in ("Images", "Epochs", "Steps"):
                try:
                    numeric_value = int(str(val).replace(",", ""))
                except (TypeError, ValueError):
                    numeric_value = 0
                item.setData(Qt.ItemDataRole.UserRole, numeric_value)
            self.table.setItem(row, col, item)
        if filepath:
            self._path_to_row[filepath] = row
        self._note_result_for_smart_groups(data)
        self._refresh_cache_menu_enabled()
    def _visible_paths(self) -> list[str]:
        paths = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            item = self.table.item(row, 1)
            fp = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not fp:
                continue
            paths.append(fp)
        return paths
    def _visible_selected_paths(self) -> list[str]:
        return [p for p in self._visible_paths() if p in self._selected_paths]
    def _row_for_filepath(self, filepath: str) -> int | None:
        row = self._path_to_row.get(filepath)
        if row is not None and 0 <= row < self.table.rowCount():
            item = self.table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == filepath:
                return row
        for scan_row in range(self.table.rowCount()):
            item = self.table.item(scan_row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == filepath:
                self._path_to_row[filepath] = scan_row
                return scan_row
        return None
    def _on_table_sort_changed(self, *_):
        QTimer.singleShot(0, self._sync_order_from_table)
    def _sync_order_from_table(
        self, *, refresh_raw: bool = True, refresh_geometry: bool = True
    ):
        ordered_paths = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            fp = item.data(Qt.ItemDataRole.UserRole) if item else None
            if fp:
                ordered_paths.append(fp)
                self._path_to_row[fp] = row
        for fp in ordered_paths:
            card = self._path_to_card.get(fp)
            if card:
                self.cards_layout.removeWidget(card)
                self.cards_layout.addWidget(card)
        if refresh_geometry:
            self._refresh_card_layout_geometry()
        if refresh_raw and hasattr(self, "raw_combo"):
            self._refresh_raw_combo_filtered()
    def _on_arch_filter_changed(self, active):
        self._active_arch_filter = None if active is None else set(active)
        self._apply_arch_filter()
    def _on_tag_filter_changed(self, active):
        self._active_tag_filter = None if active is None else set(active)
        self._apply_arch_filter()
    def _on_format_filter_changed(self, active):
        self._active_format_filter = None if active is None else set(active)
        self._apply_arch_filter()
    def _apply_arch_filter(
        self, *, refresh_raw: bool = True, refresh_geometry: bool = True,
        update_selection: bool = True,
    ):
        for data in self._results:
            fp = str(data.get("filepath") or "")
            if not fp:
                continue
            visible = self._is_data_visible(data)
            card = self._path_to_card.get(fp)
            if card:
                card.set_filter_visible(visible)
            row = self._row_for_filepath(fp)
            if row is not None and 0 <= row < self.table.rowCount():
                self.table.setRowHidden(row, not visible)
        self._sync_order_from_table(refresh_raw=refresh_raw, refresh_geometry=refresh_geometry)
        if update_selection:
            self._update_selection_ui_state()
    def _is_data_visible(self, data: dict) -> bool:
        active_arch = self._active_arch_filter
        active_tags = self._active_tag_filter
        active_formats = self._active_format_filter
        arch = data.get("architecture", "")
        tags = set(self._filter_tags_for_data(data))
        file_format = self._format_filter_for_data(data)
        return (
            ((active_arch is None) or (arch in active_arch))
            and ((active_tags is None) or bool(tags & active_tags))
            and ((active_formats is None) or (file_format in active_formats))
        )
    def _filter_tags_for_data(self, data: dict) -> list[str]:
        tags = []
        if data.get("architecture") == "ERROR":
            tags.append("ERROR")
            return list(dict.fromkeys(tags))
        model_type = data.get("model_type")
        if model_type:
            tags.append(str(model_type))
        adapter_type = data.get("adapter_type")
        if adapter_type:
            tags.append(str(adapter_type))
        if data.get("is_moe"):
            tags.append("MoE")
        quantization = data.get("quantization")
        if quantization:
            tags.append(str(quantization))
        return list(dict.fromkeys(tags))
    def _format_filter_for_data(self, data: dict) -> str:
        filepath = str(data.get("filepath") or "")
        suffix = Path(filepath).suffix.lower()
        if suffix:
            return suffix
        file_format = str(data.get("format") or "").strip().lower()
        if not file_format:
            return ".unknown"
        if file_format.startswith("."):
            return file_format
        return "." + file_format
    def _refresh_raw_combo_filtered(self, *, load_current: bool = True):
        prev_fp = _combo_data_str(self.raw_combo.currentData())
        self.raw_combo.blockSignals(True)
        self.raw_combo.clear()
        for fp in self._visible_paths():
            data = self._result_for_filepath(fp)
            if not data:
                continue
            self.raw_combo.addItem(data.get("filename", Path(fp).name), fp)
        if prev_fp:
            idx = self.raw_combo.findData(prev_fp)
            if idx >= 0:
                self.raw_combo.setCurrentIndex(idx)
        self.raw_combo.blockSignals(False)
        if self.raw_combo.count() == 0:
            self.raw_text.clear()
            self._raw_loaded_filepath = None
        elif self.raw_combo.currentIndex() < 0:
            self.raw_combo.setCurrentIndex(0)
        else:
            current_fp = _combo_data_str(self.raw_combo.currentData())
            if load_current and current_fp != self._raw_loaded_filepath:
                if current_fp is not None:
                    self._show_raw_for_current_setting(current_fp)
        self._update_raw_controls()
    def _show_raw_for_filepath(self, filepath: str):
        if not filepath:
            return
        # Same routing as the RAW dropdown so the auto-load setting is honored;
        # suppress the refresh's own load to avoid loading a non-target file.
        self._refresh_raw_combo_filtered(load_current=False)
        idx = self.raw_combo.findData(filepath)
        if idx >= 0:
            self.raw_combo.blockSignals(True)
            self.raw_combo.setCurrentIndex(idx)
            self.raw_combo.blockSignals(False)
        self.tabs.setCurrentIndex(2)
        self._show_raw_for_current_setting(filepath)
    def _step_raw_selection(self, delta: int):
        count = self.raw_combo.count()
        if count <= 0:
            return
        current = self.raw_combo.currentIndex()
        if current < 0:
            current = 0
        next_index = max(0, min(count - 1, current + delta))
        if next_index != current:
            self.raw_combo.setCurrentIndex(next_index)
    def _update_raw_controls(self):
        has_multiple = self.raw_combo.count() > 1
        self.raw_prev_btn.setEnabled(has_multiple and self.raw_combo.currentIndex() > 0)
        self.raw_next_btn.setEnabled(
            has_multiple and self.raw_combo.currentIndex() < self.raw_combo.count() - 1
        )
        self.raw_load_btn.setVisible(True)
    def _on_cards_select_all_changed(self, state):
        if self._syncing_selection:
            return
        checked = state == Qt.CheckState.Checked.value
        visible = set(self._visible_paths())
        if checked:
            self._selected_paths |= visible
        else:
            self._selected_paths -= visible
        self._sync_selection_visuals()
    def _on_table_select_all_changed(self, state):
        if self._syncing_selection:
            return
        checked = state == Qt.CheckState.Checked.value
        visible = set(self._visible_paths())
        if checked:
            self._selected_paths |= visible
        else:
            self._selected_paths -= visible
        self._sync_selection_visuals()


ViewMixin = ViewControllerMixin
