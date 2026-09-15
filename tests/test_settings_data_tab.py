# pyright: reportReturnType=false
"""Headless coverage for the reusable Data settings widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication

from front.settings_data_tab import ColumnDefinition, SettingsDataTab


@pytest.fixture(scope="module")
def app() -> QApplication:
    """Share one off-screen Qt application across widget tests."""
    return QApplication.instance() or QApplication([])


def _columns() -> list[ColumnDefinition]:
    return [
        ColumnDefinition("file", "Display name", width=280),
        ColumnDefinition("size", "Display name", visible=False, width=90),
        ColumnDefinition("architecture", "Architecture", width=140),
    ]


def test_configuration_round_trip_preserves_keys_order_visibility_and_width(app):
    widget = SettingsDataTab(
        _columns(),
        themes=[{"id": "default", "name": "Default"}, {"id": "github", "name": "GitHub"}],
    )

    assert widget.move_column("architecture", 0)
    widget.load_configuration(
        {
            "columns": [
                {"key": "architecture", "visible": False, "width": 222},
                {"key": "file", "visible": True, "width": 333},
                {"key": "size", "visible": True, "width": 77},
            ],
            "theme": "github",
        }
    )

    state = widget.export_configuration()
    assert [entry["key"] for entry in state["columns"]] == [
        "architecture",
        "file",
        "size",
    ]
    assert state["columns"][0]["visible"] is False
    assert state["columns"][0]["width"] == 222
    restored = SettingsDataTab(_columns(), themes=[{"id": "default", "name": "Default"}, {"id": "github", "name": "GitHub"}])
    restored.load_configuration(state)
    assert restored.export_configuration() == state


def test_duplicate_labels_do_not_confuse_stable_keys(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    assert widget.column_keys() == ["file", "size", "architecture"]
    assert widget.move_column("size", 0)
    assert widget.column_keys() == ["size", "file", "architecture"]
    assert widget.export_configuration()["columns"][0]["key"] == "size"


def test_width_validation_clamps_and_reports_fallback(app):
    messages: list[str] = []
    widget = SettingsDataTab(
        [ColumnDefinition("file", "File", width=100, minimum_width=48)],
        themes=["default"],
        validation_message_hook=messages.append,
        minimum_width=32,
        maximum_width=250,
    )

    widget.load_configuration(
        {"columns": [{"key": "file", "visible": True, "width": "not-a-width"}], "theme": "missing"}
    )
    entry = widget.export_configuration()["columns"][0]
    assert entry["width"] == 100
    assert any("Invalid width" in message for message in messages)


def test_reset_restores_initial_state_and_uses_button_reordering(app):
    widget = SettingsDataTab(_columns(), themes=["default", "other"])
    initial = widget.export_configuration()
    widget.move_column("architecture", 0)
    widget.load_configuration(
        {"columns": [{"key": "architecture", "visible": False, "width": 300}], "theme": "other"}
    )
    widget.reset_to_default()

    assert widget.export_configuration() == initial
    assert widget.column_tree.dragDropMode().name == "NoDragDrop"
    assert not widget.column_tree.dragEnabled()
    assert not widget.column_tree.acceptDrops()
    assert widget.column_tree.columnCount() == 3
    assert widget.column_tree.currentItem() is widget._rows["architecture"]
    assert widget.move_up_button.isEnabled()
    assert widget.move_down_button.isEnabled() is False


def test_data_tab_has_no_theme_selector_or_theme_configuration(app):
    widget = SettingsDataTab([ColumnDefinition("file", "File")])
    assert not hasattr(widget, "theme_combo")
    assert "theme" not in widget.export_configuration()


def test_export_uses_durable_state_after_qt_deletes_owned_cell_widget(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)
    checkbox = widget._checks["size"]
    checkbox.setChecked(True)
    widget._widths["size"].setValue(123)
    assert emissions[-1]["columns"][1] == {"key": "size", "visible": True, "width": 123}
    item = widget._rows["size"]
    widget.column_tree.removeItemWidget(item, 0)
    checkbox.deleteLater()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)

    with pytest.raises(RuntimeError):
        checkbox.isChecked()

    exported = widget.export_configuration()
    size = next(entry for entry in exported["columns"] if entry["key"] == "size")
    assert size == {"key": "size", "visible": True, "width": 123}

    widget.load_configuration(exported)
    assert widget._checks["size"] is not checkbox
    assert widget.export_configuration() == exported


def test_embedded_controls_preserve_durable_state_after_cleanup(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)
    expected_by_key = {entry["key"]: entry for entry in widget.export_configuration()["columns"]}
    widget._checks["size"].setChecked(True)
    widget._widths["size"].setValue(123)
    assert emissions[-1]["columns"][1] == {"key": "size", "visible": True, "width": 123}

    widget.move_column("architecture", 0)
    widget.move_column("architecture", 2)
    assert {entry["key"]: entry for entry in widget.export_configuration()["columns"]} == {
        **expected_by_key,
        "size": {"key": "size", "visible": True, "width": 123},
    }


def test_dragging_is_disabled_and_item_flags_are_not_draggable(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    widget.show()
    app.processEvents()
    tree = widget.column_tree
    assert tree.dragDropMode().name == "NoDragDrop"
    assert not tree.dragEnabled()
    assert not tree.acceptDrops()
    assert all(
        not tree.topLevelItem(index).flags() & Qt.ItemFlag.ItemIsDragEnabled
        and not tree.topLevelItem(index).flags() & Qt.ItemFlag.ItemIsDropEnabled
        for index in range(tree.topLevelItemCount())
    )
    assert all(tree.itemWidget(tree.topLevelItem(index), 1) is None for index in range(tree.topLevelItemCount()))


def test_empty_and_single_row_settings_disable_both_move_buttons(app):
    empty = SettingsDataTab([])
    assert empty.column_keys() == []
    assert not empty.move_up_button.isEnabled()
    assert not empty.move_down_button.isEnabled()

    single = SettingsDataTab([ColumnDefinition("file", "File")])
    assert single.column_keys() == ["file"]
    assert not single.move_up_button.isEnabled()
    assert not single.move_down_button.isEnabled()


def test_label_and_embedded_control_clicks_select_their_row(app):
    widget = SettingsDataTab(_columns())
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)
    widget.show()
    app.processEvents()
    tree = widget.column_tree

    label_item = tree.topLevelItem(0)
    assert label_item is not None
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(label_item).center())
    assert tree.currentItem() is label_item
    assert widget.move_down_button.isEnabled()
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Down)
    assert tree.currentItem() is widget._rows["size"]
    assert emissions == []

    checkbox = widget._checks["size"]
    QTest.mouseClick(
        checkbox,
        Qt.MouseButton.LeftButton,
        pos=QPoint(7, checkbox.height() // 2),
    )
    assert tree.currentItem() is widget._rows["size"]
    assert checkbox.isChecked()
    QTest.keyClick(checkbox, Qt.Key.Key_Space)
    assert not checkbox.isChecked()
    assert tree.currentItem() is widget._rows["size"]

    width = widget._widths["architecture"]
    line_edit = width.lineEdit()
    assert line_edit is not None
    QTest.mouseClick(line_edit, Qt.MouseButton.LeftButton)
    assert tree.currentItem() is widget._rows["architecture"]
    previous_width = width.value()
    line_edit.setFocus()
    app.processEvents()
    QTest.keyClick(line_edit, Qt.Key.Key_Up)
    assert width.value() == previous_width + 1


def test_move_buttons_update_selection_boundaries_and_emit_once(app):
    widget = SettingsDataTab(_columns())
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)

    assert not widget.move_up_button.isEnabled()
    assert not widget.move_down_button.isEnabled()
    widget.move_column("file", 0)
    assert emissions == []
    assert widget.column_tree.currentItem() is widget._rows["file"]
    assert not widget.move_up_button.isEnabled()
    assert widget.move_down_button.isEnabled()

    widget.move_down_button.click()
    assert widget.column_keys() == ["size", "file", "architecture"]
    assert widget.column_tree.currentItem() is widget._rows["file"]
    assert widget.move_up_button.isEnabled()
    assert widget.move_down_button.isEnabled()
    assert len(emissions) == 1

    widget.move_column("file", 2)
    assert widget.column_tree.currentItem() is widget._rows["file"]
    assert widget.move_down_button.isEnabled() is False
    assert widget.move_up_button.isEnabled()
    count = len(emissions)
    widget.move_column("file", 2)
    assert len(emissions) == count


def test_move_selection_survives_repeated_moves_load_and_reset(app):
    widget = SettingsDataTab(_columns())
    widget.show()
    app.processEvents()
    widget.move_column("architecture", 0)
    for target in (2, 0, 1, 0, 2, 0):
        assert widget.move_column("architecture", target)
        assert widget.column_tree.currentItem() is widget._rows["architecture"]
        assert widget.column_tree.visualItemRect(widget._rows["architecture"]).isValid()

    widget.load_configuration(
        {
            "columns": [
                {"key": "size", "visible": True, "width": 111},
                {"key": "architecture", "visible": False, "width": 222},
                {"key": "file", "visible": True, "width": 333},
            ]
        }
    )
    assert widget.column_tree.currentItem() is widget._rows["architecture"]
    widget.reset_to_default()
    assert widget.column_tree.currentItem() is widget._rows["architecture"]
    assert widget.column_keys() == ["file", "size", "architecture"]


def test_repeated_loads_hide_obsolete_controls_and_keep_new_controls_live(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    widget.show()
    app.processEvents()
    configuration = {
        "columns": [
            {"key": "architecture", "visible": False, "width": 222},
            {"key": "file", "visible": True, "width": 333},
            {"key": "size", "visible": True, "width": 123},
        ]
    }

    def is_visible(control) -> bool:
        if control is None:
            return False
        try:
            return control.isVisible()
        except RuntimeError:
            return False

    def embedded_controls():
        tree = widget.column_tree
        return [
            tree.itemWidget(tree.topLevelItem(index), column)
            for index in range(tree.topLevelItemCount())
            for column in (0, 2)
        ]

    for _ in range(3):
        obsolete = embedded_controls()
        widget.load_configuration(configuration)
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()

        assert all(not is_visible(control) for control in obsolete)
        assert widget.column_keys() == ["architecture", "file", "size"]
        assert all(is_visible(control) for control in embedded_controls())

    widget.move_column("size", 0)
    obsolete = embedded_controls()
    widget.reset_to_default()
    QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert widget.column_keys() == ["file", "size", "architecture"]
    assert all(not is_visible(control) for control in obsolete)
    assert all(is_visible(control) for control in embedded_controls())


def test_data_column_tree_expands_beyond_old_cap_without_unneeded_scrollbar(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    widget.resize(700, 640)
    widget.show()
    app.processEvents()
    tree = widget.column_tree
    last_row = tree.visualItemRect(tree.topLevelItem(tree.topLevelItemCount() - 1))

    assert tree.maximumHeight() > 220
    assert tree.height() > 220
    assert tree.viewport().height() > last_row.bottom() + 1
    assert not tree.verticalScrollBar().isVisible()


def test_empty_data_column_tree_keeps_usable_space_without_scrollbar(app):
    widget = SettingsDataTab([])
    widget.resize(700, 640)
    widget.show()
    app.processEvents()

    assert widget.column_tree.height() >= 120
    assert not widget.column_tree.verticalScrollBar().isVisible()


def _locked_columns() -> list[ColumnDefinition]:
    return [
        ColumnDefinition("selection", "", width=32, hideable=False, reorderable=False),
        ColumnDefinition("file", "File", width=530),
        ColumnDefinition("size", "Size", width=90),
    ]


def test_locked_selection_column_is_always_visible_and_first(app):
    widget = SettingsDataTab(_locked_columns())
    assert widget.column_keys()[0] == "selection"
    selection_check = widget._checks["selection"]
    assert selection_check.isChecked()
    assert not selection_check.isEnabled()

    # A legacy configuration cannot hide or move the locked column.
    widget.load_configuration(
        {
            "columns": [
                {"key": "file", "visible": True, "width": 500},
                {"key": "selection", "visible": False, "width": 0},
            ]
        }
    )
    assert widget.export_configuration()["columns"][0] == {
        "key": "selection",
        "visible": True,
        "width": 32,
    }
    assert widget.move_column("selection", 2) is False
    assert widget.column_keys()[0] == "selection"
    assert widget.move_column("file", 0) is True
    assert widget.column_keys()[:2] == ["selection", "file"]


def test_locked_selection_disables_move_buttons(app):
    widget = SettingsDataTab(_locked_columns())
    widget._select_key("selection")
    assert not widget.move_up_button.isEnabled()
    assert not widget.move_down_button.isEnabled()
    widget._select_key("file")
    assert not widget.move_up_button.isEnabled()  # cannot move above selection
    assert widget.move_down_button.isEnabled()


def test_zero_or_missing_width_falls_back_to_canonical_default(app):
    messages: list[str] = []
    widget = SettingsDataTab(
        [ColumnDefinition("file", "File", width=530), ColumnDefinition("size", "Size", width=90)],
        validation_message_hook=messages.append,
    )
    widget.load_configuration(
        {
            "columns": [
                {"key": "file", "visible": True, "width": 0},
                {"key": "size", "visible": False, "width": "bad"},
            ]
        }
    )
    widths = {entry["key"]: entry["width"] for entry in widget.export_configuration()["columns"]}
    assert widths == {"file": 530, "size": 90}
    assert any("Missing width" in message or "Invalid width" in message for message in messages)


def test_reset_restores_locked_selection_visible_and_first(app):
    widget = SettingsDataTab(_locked_columns())
    widget.move_column("file", 0)
    widget.load_configuration({"columns": [{"key": "size", "visible": False, "width": 0}]})
    widget.reset_to_default()
    assert widget.export_configuration()["columns"][0] == {
        "key": "selection",
        "visible": True,
        "width": 32,
    }
