"""Offscreen linkage checks for compact cards and exact Advanced Viewer paths."""

import os
import sys
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from front import selection_controller
from gui import MainWindow


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
        assert card.maximumWidth() <= viewport.width() - 16

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


def test_explorer_inspect_preserves_loaded_models_in_replace_mode(tmp_path, monkeypatch):
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

        assert window._queued_files == [existing, str(inspected)]
        assert [result["filepath"] for result in window._results] == [existing]
        assert started == [([str(inspected)], False)]
    finally:
        window.close()
        app.processEvents()
