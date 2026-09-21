"""Offscreen linkage checks for compact cards and exact Advanced Viewer paths."""

import os
import sys
import json
import struct
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication
import pytest

from front import selection_controller
from front.advanced_viewer import AdvancedViewerDialog
from front.explorer_data import detect_embedded_content
from front.explorer_metadata import raw_metadata_bytes
from gui import MainWindow
from model_cache import store_cached_inspection


def _summary(path: str) -> dict:
    return {
        "filepath": path, "filename": Path(path).name, "format": "SAFETENSORS",
        "file_size": 10, "file_size_friendly": "10 B", "tensor_count": 1,
        "total_params": 1, "total_params_friendly": "1", "architecture": "Test",
        "model_type": "Checkpoint", "components": {}, "named_text_encoders": {},
        "precision_summary": "FP16", "component_precision_summary": "FP16",
        "component_precisions": {}, "precision_display": "FP16", "training_meta": {},
        "extra": {},
    }


def test_card_actions_open_exact_model_while_checkbox_owns_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    opened: list[str] = []
    monkeypatch.setattr(window, "_show_advanced_viewer_for_path", opened.append)
    path = "R:/synthetic/card.safetensors"
    data = _summary(path)
    try:
        window._results.append(data)
        window._add_card(data)
        window._add_table_row(data)
        window.show()
        app.processEvents()
        window._refresh_card_layout_geometry()
        card = window._path_to_card[path]

        def choose_advanced_viewer(menu: Any, _global_pos: QPoint) -> Any:
            return next(
                action
                for action in menu.actions()
                if action.text() == "Advanced Viewer"
            )

        monkeypatch.setattr(selection_controller.QMenu, "exec", choose_advanced_viewer)
        window._on_card_context_menu(path, False, QPoint(0, 0))
        assert opened == [path]

        card.select_cb.click()
        assert window._selected_paths == {path}
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "1 selected"

        cast(Any, QTest).mouseClick(
            card,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(4, card.height() - 4),
        )
        assert opened == [path, path]
        assert window._selected_paths == {path}
        assert not hasattr(window, "advanced_viewer_btn")
        assert not hasattr(window, "cards_simple_view_cb")
        assert window.cards_layout.alignment() & Qt.AlignmentFlag.AlignTop
        viewport = window.cards_scroll.viewport()
        assert viewport is not None
        assert card.width() == viewport.width() - 16

        second = "R:/synthetic/second.safetensors"
        second_data = _summary(second)
        window._results.append(second_data)
        window._add_table_row(second_data)
        window._open_table_row_in_advanced_viewer(1)
        assert opened == [path, path, second]
        second_checkbox = window.table.cellWidget(1, 0)
        assert second_checkbox is not None
        cast(Any, second_checkbox).click()
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "2 selected"
        window.cards_select_all_cb.setChecked(False)
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "0 selected"
        card.select_cb.click()
        window._remove_selected_results()
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "0 selected"
    finally:
        window.close()


def test_advanced_viewer_reuses_existing_dialog_for_repeat_entry(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    path = str(tmp_path / "repeat.safetensors")
    data = _summary(path)
    monkeypatch.setattr(AdvancedViewerDialog, "exec", lambda _dialog: 0)
    try:
        window._results.append(data)
        window._show_advanced_viewer_for_path(path)
        first = window._advanced_dialog
        window._show_advanced_viewer_for_path(path)

        assert window._advanced_dialog is first
        assert first.explorer_tab.dump_json_modelinfo is False
    finally:
        window.close()
        app.processEvents()


def test_advanced_viewer_keeps_live_result_and_exports_real_cached_source(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    source = tmp_path / "dragged.safetensors"
    values = [f"token-{index}" for index in range(60)]
    header = json.dumps({"__metadata__": {"tokenizer": {"tokens": values}}}).encode()
    source.write_bytes(struct.pack("<Q", len(header)) + header + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ")
    stale = str(tmp_path / "stale.safetensors")
    preview = {"count": len(values), "preview": values[:50], "truncated": True}
    cached = _summary(stale) | {"resolved_filepath": stale, "metadata": {"tokenizer": {"tokens": preview}}}
    store_cached_inspection(str(source), cached)
    window = MainWindow()
    monkeypatch.setattr(AdvancedViewerDialog, "exec", lambda _dialog: 0)
    try:
        window._results.append(_summary(str(source)))
        results_before = list(window._results)
        window._show_advanced_viewer_for_path(str(source))
        dialog = window._advanced_dialog
        assert dialog is not None
        assert dialog._inspection["filepath"] == str(source)
        assert dialog._inspection["requested_filepath"] == str(source)
        candidate = detect_embedded_content(dialog._inspection)[0]
        assert b"token-59" in raw_metadata_bytes(dialog._inspection, candidate)

        window._show_advanced_viewer_for_path(str(source))
        assert window._advanced_dialog is dialog
        assert window._results == results_before
    finally:
        window.close()
        app.processEvents()


def test_explorer_inspect_does_not_reanalyze_or_change_model_list(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    existing = str(tmp_path / "existing.safetensors")
    inspected = tmp_path / "inspected.safetensors"
    inspected.touch()
    started = []
    monkeypatch.setattr(
        window,
        "_analyze_all",
        lambda paths=None, *, clear_existing=True: started.append((paths, clear_existing)),
    )
    try:
        data = _summary(existing)
        window._queued_files = [existing]
        window._results.append(data)
        window._add_card(data)
        window._add_table_row(data)

        window._handle_explorer_inspect({"inspection": {"filepath": str(inspected)}})

        assert window._queued_files == [existing]
        assert [result["filepath"] for result in window._results] == [existing]
        assert started == []
    finally:
        window.close()
        app.processEvents()


@pytest.mark.parametrize("add_mode", ("replace", "additive"))
def test_explorer_inspect_keeps_loaded_model_without_reentering_advanced_viewer(
    tmp_path, monkeypatch, add_mode
):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    first = tmp_path / "first.safetensors"
    second = tmp_path / "second.safetensors"
    first.touch()
    second.touch()
    opened: list[str] = []
    analyzed: list[object] = []
    monkeypatch.setattr(window, "_show_advanced_viewer_for_path", opened.append)
    monkeypatch.setattr(window, "_analyze_all", lambda *args, **kwargs: analyzed.append(args))
    try:
        window._add_mode = add_mode
        for path in (str(first), str(second)):
            data = _summary(path)
            window._queued_files.append(path)
            window._results.append(data)
            window._add_card(data)
            window._add_table_row(data)
        window._selected_paths = {str(second)}
        queued_before = list(window._queued_files)
        results_before = [result["filepath"] for result in window._results]
        cards_before = list(window._path_to_card)
        rows_before = [
            str(window.table.item(row, 1).data(Qt.ItemDataRole.UserRole))
            for row in range(window.table.rowCount())
        ]

        window._handle_explorer_inspect({"inspection": {"filepath": str(first)}})

        assert opened == []
        assert analyzed == []
        assert window._queued_files == queued_before
        assert [result["filepath"] for result in window._results] == results_before
        assert list(window._path_to_card) == cards_before
        assert [
            str(window.table.item(row, 1).data(Qt.ItemDataRole.UserRole))
            for row in range(window.table.rowCount())
        ] == rows_before
        assert window._selected_paths == {str(second)}
    finally:
        window.close()
        app.processEvents()
