"""Focused interaction and geometry checks for filter popup widgets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QMainWindow

from front.filter_widgets import CheckFilterButton


@pytest.fixture(scope="session")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_popup_uses_one_scrollable_column_bounded_by_owner_window(app: QApplication):
    window = QMainWindow()
    window.resize(640, 360)
    button = CheckFilterButton("Architecture")
    window.setCentralWidget(button)
    button.add_items(f"Family {index}" for index in range(80))

    button._prepare_menu()

    assert len(button._menu.actions()) == 2  # Select All and one scroll widget action.
    assert button._items_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert button._items_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert button._menu.maximumHeight() <= window.height()
    assert button._items_scroll.maximumHeight() < window.height()
    assert all(
        checkbox.focusPolicy() == Qt.FocusPolicy.StrongFocus
        for checkbox in button._arch_checks.values()
    )
    window.close()


def test_popup_retains_selection_and_all_none_signals(app: QApplication):
    window = QMainWindow()
    button = CheckFilterButton("Tags")
    window.setCentralWidget(button)
    button.replace_items(["LoRA", "Text Encoder", "LoRA", "VAE"])
    events: list[object] = []
    button.filter_changed.connect(events.append)

    button._arch_checks["VAE"].setChecked(False)
    assert button.active_filter() == {"LoRA", "Text Encoder"}
    assert events[-1] == {"LoRA", "Text Encoder"}

    button.set_all_checked(False)
    assert button.active_filter() == set()
    assert events[-1] == set()

    button.set_all_checked(True)
    button._all_cb.click()
    assert button.active_filter() == set()
    button._all_cb.click()
    assert button.active_filter() is None

    button._arch_checks["LoRA"].setChecked(False)
    button.replace_items(["LoRA", "Text Encoder", "VAE", "Vision"])
    assert not button._arch_checks["LoRA"].isChecked()
    assert not button._arch_checks["Vision"].isChecked()
    assert button.active_filter() == {"Text Encoder", "VAE"}
    window.close()
