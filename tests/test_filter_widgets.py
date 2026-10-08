"""Focused interaction and geometry checks for filter popup widgets."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QMainWindow, QVBoxLayout, QWidget

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

    assert len(button._menu.actions()) == 4  # Select All, two indicators, one scroll widget.
    assert button._items_scroll.verticalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAsNeeded
    assert button._items_scroll.horizontalScrollBarPolicy() == Qt.ScrollBarPolicy.ScrollBarAlwaysOff
    assert button._menu.maximumHeight() <= window.height()
    assert button._items_scroll.maximumHeight() < window.height()
    assert all(
        checkbox.focusPolicy() == Qt.FocusPolicy.StrongFocus
        for checkbox in button._arch_checks.values()
    )
    window.close()


@pytest.mark.parametrize("item_count", [2, 80])
def test_popup_opens_upward_inside_owner_for_short_and_scrolling_lists(
    app: QApplication, item_count: int
):
    window = QMainWindow()
    window.resize(640, 360)
    button = CheckFilterButton("Tags")
    button.setFixedSize(180, 32)
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addStretch()
    layout.addWidget(button)
    window.setCentralWidget(central)
    button.add_items(f"Tag {index}" for index in range(item_count))
    window.show()
    app.processEvents()

    button._menu.popup(button.mapToGlobal(QPoint(0, button.height())))
    QTest.qWait(20)

    owner_top_left = window.mapToGlobal(window.rect().topLeft())
    menu_rect = button._menu.frameGeometry()
    button_top = button.mapToGlobal(QPoint(0, 0)).y()
    assert button._menu.isVisible()
    assert menu_rect.top() < button_top
    assert menu_rect.left() >= owner_top_left.x()
    assert menu_rect.right() < owner_top_left.x() + window.width()
    assert menu_rect.top() >= owner_top_left.y()
    assert menu_rect.bottom() < owner_top_left.y() + window.height()
    if item_count == 2:
        assert menu_rect.bottom() < button_top
        assert not button._top_indicator.isVisible()
        assert not button._bottom_indicator.isVisible()
    window.close()


def test_scroll_indicators_follow_the_scroll_edge(app: QApplication):
    window = QMainWindow()
    window.resize(640, 360)
    button = CheckFilterButton("Tags")
    button.setFixedSize(180, 32)
    central = QWidget()
    layout = QVBoxLayout(central)
    layout.addStretch()
    layout.addWidget(button)
    window.setCentralWidget(central)
    button.add_items(f"Tag {index}" for index in range(80))
    window.show()
    app.processEvents()
    button._menu.popup(button.mapToGlobal(QPoint(0, button.height())))
    QTest.qWait(20)

    scrollbar = button._items_scroll.verticalScrollBar()
    assert scrollbar.maximum() > scrollbar.minimum()
    assert not button._top_indicator.isVisible()
    assert button._bottom_indicator.isVisible()
    scrollbar.setValue(scrollbar.maximum())
    app.processEvents()
    assert button._top_indicator.isVisible()
    assert not button._bottom_indicator.isVisible()
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
