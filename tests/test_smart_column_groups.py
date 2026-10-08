# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Smart column group auto-enable contracts for cached inspection results."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

from conftest import _summary


def test_cache_load_auto_enables_llm_smart_group(monkeypatch, tmp_path: Path) -> None:
    """Loading cached results that use MoE data auto-enables the LLM group."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    _ = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        cached = "R:/cached/moe.safetensors"
        summary = _summary(cached, "Architecture C", "MoE LLM")
        summary.update({"is_moe": True, "expert_count": 8, "expert_used_count": 2})
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[SimpleNamespace(path=cached, classification="active")],
                availability=SimpleNamespace(
                    total=1, active=1, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=True, load_cache_archived=False,
                    total_count=1, active_count=1, historic_count=0,
                ),
            ),
        )
        monkeypatch.setattr(
            window, "_get_cached_inspection_summary_snapshots", lambda _paths: {cached: summary}
        )
        window._load_cache_all()
        assert window._smart_group_state["llm"] is True
        assert window._smart_group_checkboxes["llm"].isChecked()
        assert not window.table.isColumnHidden(window._table_columns.index("MoE"))
        # Groups without usage stay off.
        assert window._smart_group_state["diffusion"] is False
        assert window._smart_group_state["adapter"] is False
    finally:
        window.close()


def test_smart_column_engine_is_extracted_as_a_composed_mixin() -> None:
    """The smart-column engine lives in its own mixin, composed into MainWindow."""
    from front.smart_column_controller import (
        SMART_COLUMN_GROUPS,
        SmartColumnControllerMixin,
        SmartColumnMixin,
    )
    from gui import MainWindow

    assert SmartColumnMixin is SmartColumnControllerMixin
    assert SmartColumnControllerMixin in MainWindow.__mro__
    # window_layout re-exports the moved table for backward-compatible imports.
    from front.window_layout import SMART_COLUMN_GROUPS as reexported

    assert reexported is SMART_COLUMN_GROUPS
    assert set(SMART_COLUMN_GROUPS) == {"llm", "diffusion", "adapter"}


def test_smart_group_tooltip_manual_choice_survives_clear_all() -> None:
    """The group tooltip states manual choice is not reset by Clear All."""
    from front.smart_column_controller import SMART_COLUMN_GROUPS

    tooltip = SMART_COLUMN_GROUPS["llm"]["tooltip"].lower()
    assert "not reset" in tooltip
    assert "clear all" in tooltip
    assert "only auto-enabled groups reset" in tooltip


def test_hidden_columns_keep_last_valid_width(monkeypatch, tmp_path: Path) -> None:
    """A hidden column must not persist Qt's reported 0 width as its width."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    _ = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        index = window._table_columns.index("File")
        window.table.setColumnWidth(index, 432)
        window.table.setColumnHidden(index, True)
        entry = next(
            e for e in window._capture_data_layout()["columns"]
            if e["key"] == window._column_key(index)
        )
        assert entry["width"] == 432
    finally:
        window.close()


def test_apply_data_layout_keeps_selection_first_and_visible(monkeypatch, tmp_path: Path) -> None:
    """Legacy configs cannot hide or move the locked selection column."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    _ = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window._apply_data_layout(
            {
                "columns": [
                    {"key": "column_5", "visible": True, "width": 90},
                    {"key": "selection", "visible": False, "width": 0},
                ]
            }
        )
        header = window.table.horizontalHeader()
        assert not window.table.isColumnHidden(0)
        assert header.visualIndex(0) == 0
        assert window._capture_data_layout()["columns"][0]["key"] == "selection"
    finally:
        window.close()


def test_canonical_widths_seeded_for_every_column(monkeypatch, tmp_path: Path) -> None:
    """Construction/reset widths come from one canonical definition source."""
    from front.data_columns import DATA_COLUMNS

    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    _ = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        for index, column in enumerate(DATA_COLUMNS):
            window.table.setColumnHidden(index, False)
            assert window.table.columnWidth(index) == column.width
    finally:
        window.close()