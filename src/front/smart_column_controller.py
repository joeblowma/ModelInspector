# pyright: reportAttributeAccessIssue=false, reportArgumentType=false
"""Runtime-only smart Data-column groups and their masking engine.

Owns the LLM/Diffusion/Adapter column groups, the per-column baseline
precedence, and auto-detection from loaded results.  Group state is never
persisted: it lives for one application/session only.  ``MainWindow`` composes
this mixin explicitly; ``window_layout`` imports ``SMART_COLUMN_GROUPS`` from
here so the pinned toolbar toggles and the masking engine share one source of
truth.
"""

from __future__ import annotations

from typing import Any


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


# Runtime-only smart Data-column groups.  Membership is exact: each entry lists
# the ``_table_columns`` labels it toggles.  Group state is never persisted;
# it lives for one application/session only.
def _group_tooltip(summary: str) -> str:
    return (
        f"{summary}\n\n"
        "Turns on automatically while loaded results genuinely use these "
        "columns. Unchecked masks every column in the group; checked reveals "
        "only columns that are visible in Settings > Data (the per-column "
        "baseline always wins: a column hidden there stays hidden). Your "
        "manual choice sticks for the rest of the session and is not reset "
        "by Clear All; only auto-enabled groups reset on Clear All."
    )


SMART_COLUMN_GROUPS: dict[str, dict[str, str]] = {
    "llm": {
        "label": "LLM",
        "columns": ("MoE", "Experts", "Active Experts"),
        "tooltip": _group_tooltip(
            "Show LLM columns: MoE, Experts, Active Experts."
        ),
    },
    "diffusion": {
        "label": "Diffusion",
        "columns": (
            "UNet Precision",
            "VAE Precision",
            "Text Encoder Precision",
            "Transformer Precision",
        ),
        "tooltip": _group_tooltip(
            "Show Diffusion columns: UNet Precision, VAE Precision, "
            "Text Encoder Precision, Transformer Precision."
        ),
    },
    "adapter": {
        "label": "Adapter",
        "columns": ("Adapter", "LoRA Rank"),
        "tooltip": _group_tooltip(
            "Show Adapter columns: Adapter, LoRA Rank."
        ),
    },
}


class SmartColumnControllerMixin:
    """Smart-column masking, baseline precedence, and auto-detection."""

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

    def _column_key(self, index: int) -> str:
        return "selection" if index == 0 else f"column_{index}"

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


SmartColumnMixin = SmartColumnControllerMixin


__all__ = [
    "SMART_COLUMN_GROUPS",
    "SmartColumnControllerMixin",
    "SmartColumnMixin",
]
