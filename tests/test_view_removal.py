"""Targeted Cards/Data removal regressions using only temporary paths."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from gui import MainWindow


def _summary(path: str, architecture: str) -> dict:
    return {
        "filepath": path,
        "filename": Path(path).name,
        "format": "SAFETENSORS",
        "file_size": 10,
        "file_size_friendly": "10 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": architecture,
        "model_type": "Checkpoint",
        "adapter_type": None,
        "quantization": None,
        "components": {},
        "named_text_encoders": {},
        "lora_rank": None,
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }


def _populate(window: MainWindow, path: str, architecture: str) -> dict:
    data = _summary(path, architecture)
    window._results.append(data)
    window._add_card(data)
    window._add_table_row(data)
    window._selected_paths.add(path)
    return data


def test_cancelled_move_removes_only_completed_widgets(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    moved, failed, skipped = (
        str(tmp_path / name)
        for name in ("a.safetensors", "b.safetensors", "c.safetensors")
    )
    window = MainWindow()
    try:
        data = {
            path: _populate(window, path, architecture)
            for path, architecture in ((moved, "Alpha"), (failed, "Beta"), (skipped, "Gamma"))
        }
        window.arch_filter_btn.replace_items(item["architecture"] for item in data.values())
        window.format_filter_btn.replace_items(
            window._format_filter_for_data(item) for item in data.values()
        )
        window._queued_files = [moved, failed, skipped]
        window._refresh_raw_combo_filtered(load_current=False)
        window.raw_combo.setCurrentIndex(window.raw_combo.findData(failed))
        header = window.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(1, Qt.SortOrder.DescendingOrder)
        window.table.setSortingEnabled(True)
        app.processEvents()
        window._sync_order_from_table(refresh_raw=False, refresh_geometry=False)
        retained_cards = {path: window._path_to_card[path] for path in (failed, skipped)}
        retained_items = {
            path: window.table.item(window._row_for_filepath(path), 1)
            for path in (failed, skipped)
        }

        window._finish_move_operation(
            {
                "moved": [moved],
                "failed": [(failed, "simulated failure")],
                "skipped": [(skipped, "simulated skip")],
                "cancelled": True,
            }
        )

        assert [item["filepath"] for item in window._results] == [failed, skipped]
        for path in (failed, skipped):
            assert window._path_to_card[path] is retained_cards[path]
            assert window.table.item(window._row_for_filepath(path), 1) is retained_items[path]
        assert window._selected_paths == {failed, skipped}
        assert set(window._visible_selected_paths()) == {failed, skipped}
        assert window._queued_files == [failed, skipped]
        assert set(window._path_to_row) == {failed, skipped}
        assert window._visible_paths() == [skipped, failed]
        assert window.raw_combo.currentData() == failed
        assert window.arch_filter_btn._counts["Alpha"] == 0
        assert window.arch_filter_btn._counts["Beta"] == 1
        assert data[failed] is window._result_for_filepath(failed)
        assert window.cards_placeholder is None
    finally:
        window.close()


def test_remove_selected_last_result_restores_placeholder(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    QApplication.instance() or QApplication([])
    window = MainWindow()
    path = str(tmp_path / "only.safetensors")
    try:
        _populate(window, path, "Only")
        window._queued_files = [path]

        window._remove_selected_results()

        assert window._results == []
        assert window._queued_files == []
        assert window._selected_paths == set()
        assert window.table.rowCount() == 0
        assert not window._cards
        assert not window._path_to_card
        assert not window._path_to_simple_card
        assert not window._path_to_row
        assert window.cards_placeholder is not None
    finally:
        window.close()
