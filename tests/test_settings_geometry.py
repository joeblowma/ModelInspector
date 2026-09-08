"""Regression contracts for the compact Settings dialog geometry."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QAbstractScrollArea, QTabWidget

from front.settings_data_support import ColumnDefinition
from front.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _large_column_set() -> list[ColumnDefinition]:
    return [
        ColumnDefinition(
            f"column_{index}",
            f"Long column label {index} for geometry regression coverage",
            width=280,
        )
        for index in range(18)
    ]


def _process_events(app: QApplication) -> None:
    app.processEvents()
    app.processEvents()


def test_data_tree_ignores_row_content_when_reporting_its_size_hint(app):
    dialog = SettingsDialog(data_columns=_large_column_set())
    try:
        dialog.show()
        _process_events(app)

        tree = dialog.data_settings_tab.column_tree
        last_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
        assert last_item is not None
        content_height = tree.header().height() + tree.visualItemRect(last_item).bottom() + 1

        assert tree.sizeAdjustPolicy() == QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored
        assert tree.sizeHint().height() < content_height
    finally:
        dialog.close()


def test_large_data_settings_remain_fixed_across_tabs_move_and_reopen(app):
    dialog = SettingsDialog(data_columns=_large_column_set())
    dialog.setStyleSheet("QTreeWidget { font-size: 16px; }")
    try:
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None

        dialog.show()
        _process_events(app)
        expected_size = dialog.size()
        assert expected_size == dialog.minimumSize() == dialog.maximumSize()

        for index in range(tabs.count()):
            tabs.setCurrentIndex(index)
            _process_events(app)
            assert dialog.size() == expected_size

        dialog.move(120, 100)
        _process_events(app)
        assert dialog.size() == expected_size

        dialog.hide()
        _process_events(app)
        dialog.show()
        _process_events(app)
        assert dialog.size() == expected_size
    finally:
        dialog.close()


def test_data_tree_uses_fixed_dialog_viewport_and_scrolls_overflow(app):
    dialog = SettingsDialog(data_columns=_large_column_set())
    try:
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None
        tabs.setCurrentWidget(dialog.data_settings_tab.parentWidget())
        dialog.show()
        _process_events(app)

        tree = dialog.data_settings_tab.column_tree
        last_item = tree.topLevelItem(tree.topLevelItemCount() - 1)
        assert last_item is not None
        content_height = tree.header().height() + tree.visualItemRect(last_item).bottom() + 1
        assert tree.height() < content_height
        assert tree.verticalScrollBar().maximum() > 0
        assert tree.verticalScrollBar().isVisible()
    finally:
        dialog.close()
