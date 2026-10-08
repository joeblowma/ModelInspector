"""Regression contracts for the compact Settings dialog geometry."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication, QAbstractScrollArea, QTabWidget

from front.settings_data_support import ColumnDefinition
from front.settings_dialog import (
    _DIALOG_DEFAULT_SIZE,
    _DIALOG_MINIMUM_SIZE,
    SettingsDialog,
    _clamp_size_to_screen,
)


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
        for index in range(30)
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


def test_large_data_settings_stay_resizable_across_tabs_move_and_reopen(app):
    dialog = SettingsDialog(data_columns=_large_column_set())
    dialog.setStyleSheet("QTreeWidget { font-size: 16px; }")
    try:
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None
        # Release feature: the dialog is resizable, not fixed.
        assert dialog.minimumSize() != dialog.maximumSize()

        dialog.show()
        _process_events(app)
        expected_size = dialog.size()
        assert expected_size.width() > 0 and expected_size.height() > 0

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


def test_settings_dialog_defaults_to_900x640_clamped_to_screen(app):
    dialog = SettingsDialog(data_columns=_large_column_set())
    try:
        screen = QApplication.primaryScreen()
        expected = _clamp_size_to_screen(_DIALOG_DEFAULT_SIZE, screen)
        minimum = _clamp_size_to_screen(_DIALOG_MINIMUM_SIZE, screen)
        assert (dialog.size().width(), dialog.size().height()) == (
            max(expected[0], minimum[0]),
            max(expected[1], minimum[1]),
        )
        assert (dialog.minimumSize().width(), dialog.minimumSize().height()) == minimum
    finally:
        dialog.close()


def test_remembered_settings_size_is_used_and_clamped(app):
    dialog = SettingsDialog(
        data_columns=_large_column_set(), dialog_size={"width": 700, "height": 500}
    )
    try:
        screen = QApplication.primaryScreen()
        expected = _clamp_size_to_screen((700, 500), screen)
        minimum = _clamp_size_to_screen(_DIALOG_MINIMUM_SIZE, screen)
        assert (dialog.size().width(), dialog.size().height()) == (
            max(expected[0], minimum[0]),
            max(expected[1], minimum[1]),
        )
    finally:
        dialog.close()


def test_remembered_settings_size_above_screen_is_clamped(app):
    dialog = SettingsDialog(
        data_columns=_large_column_set(), dialog_size={"width": 100000, "height": 100000}
    )
    try:
        available = QApplication.primaryScreen().availableGeometry()
        assert dialog.size().width() <= available.width()
        assert dialog.size().height() <= available.height()
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
