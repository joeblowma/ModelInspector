"""Cards scroll geometry regressions with synthetic summaries only."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QPoint, QRect
from PyQt6.QtWidgets import QApplication, QLayout

from gui import MainWindow


def _summary(index: int) -> dict:
    return {
        "filepath": f"R:/synthetic/card-{index}.safetensors",
        "filename": f"card-{index}.safetensors",
        "format": "SAFETENSORS",
        "file_size_friendly": "1 B",
        "total_params_friendly": "1",
        "tensor_count": 1,
        "architecture": "Keep" if index < 2 else "Other",
        "model_type": "Checkpoint",
        "components": {},
        "component_precisions": {},
        "named_text_encoders": {},
        "training_meta": {},
    }


def test_cards_layout_scroll_geometry_survives_projection_and_removal(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    paths = []
    try:
        assert (
            window.cards_layout.sizeConstraint()
            == QLayout.SizeConstraint.SetDefaultConstraint
        )
        for index in range(12):
            data = _summary(index)
            paths.append(data["filepath"])
            window._results.append(data)
            window._add_card(data)
            window._add_table_row(data)

        window.resize(1100, 730)
        window.show()
        app.processEvents()
        assert window.cards_scroll.verticalScrollBar().maximum() > 0

        window._on_arch_filter_changed({"Keep"})
        app.processEvents()
        assert sum(card.isVisible() for card in window._cards) == 2
        assert window.cards_scroll.verticalScrollBar().maximum() == 0

        window._on_arch_filter_changed(None)
        window.resize(1050, 720)
        app.processEvents()
        viewport = window.cards_scroll.viewport()
        assert viewport is not None
        assert window.cards_scroll.verticalScrollBar().maximum() > 0
        assert window.cards_scroll.horizontalScrollBar().maximum() == 0
        assert window.cards_container.width() == viewport.width()

        scrollbar = window.cards_scroll.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())
        app.processEvents()
        last_card = window._cards[-1]
        visible_card = QRect(last_card.mapTo(viewport, QPoint()), last_card.size())
        assert viewport.rect().contains(visible_card)

        window._selected_paths.update(paths)
        window._remove_selected_results()
        assert window._results == []
        assert window.cards_placeholder is not None
    finally:
        window.close()
        app.processEvents()
