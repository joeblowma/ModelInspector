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


def test_card_body_opens_exact_model_while_checkbox_owns_selection(tmp_path, monkeypatch):
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
        card.select_cb.click()
        assert window._selected_paths == {path}

        cast(Any, QTest).mouseClick(
            card,
            Qt.MouseButton.LeftButton,
            Qt.KeyboardModifier.NoModifier,
            QPoint(4, card.height() - 4),
        )
        assert opened == [path]
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
        assert opened == [path, second]
    finally:
        window.close()
