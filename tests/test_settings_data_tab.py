# pyright: reportReturnType=false
"""Headless coverage for the reusable Data settings widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QTreeWidget

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
    assert state["theme"] == "github"

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
    assert widget.current_theme_id() == "default"
    assert any("Invalid width" in message for message in messages)
    assert any("unavailable" in message for message in messages)


def test_reset_restores_initial_state_and_exposes_drag_handle(app):
    widget = SettingsDataTab(_columns(), themes=["default", "other"])
    initial = widget.export_configuration()
    widget.move_column("architecture", 0)
    widget.load_configuration(
        {"columns": [{"key": "architecture", "visible": False, "width": 300}], "theme": "other"}
    )
    widget.reset_to_default()

    assert widget.export_configuration() == initial
    assert widget.column_tree.dragDropMode().name == "InternalMove"
    item = widget.column_tree.topLevelItem(0)
    handle = widget.column_tree.itemWidget(item, 0)
    assert handle is not None
    assert handle.toolTip()


def test_loader_themes_keep_builtin_default_as_reset_theme(app):
    widget = SettingsDataTab([ColumnDefinition("file", "File")])
    assert widget.theme_combo.findData("default") >= 0
    assert widget.current_theme_id() == "default"


def test_export_uses_durable_state_after_qt_deletes_owned_cell_widget(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)
    checkbox = widget._checks["size"]
    checkbox.setChecked(True)
    widget._widths["size"].setValue(123)
    assert emissions[-1]["columns"][1] == {"key": "size", "visible": True, "width": 123}
    item = widget._rows["size"]
    widget.column_tree.removeItemWidget(item, 1)
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


def test_post_drop_reconciliation_stress_preserves_state_and_emits_once(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    emissions: list[dict] = []
    widget.configurationChanged.connect(emissions.append)
    expected_by_key = {entry["key"]: entry for entry in widget.export_configuration()["columns"]}

    for _ in range(20):
        key = widget.column_keys()[-1]
        item = widget.column_tree.takeTopLevelItem(widget.column_tree.topLevelItemCount() - 1)
        assert item is not None
        checkbox = widget._checks[key]
        widget.column_tree.removeItemWidget(item, 1)
        checkbox.deleteLater()
        widget.column_tree.insertTopLevelItem(0, item)
        widget.column_tree.queue_post_drop_reconciliation()
        widget.column_tree.queue_post_drop_reconciliation()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        QTest.qWait(1)

        exported = widget.export_configuration()
        assert sorted(widget.column_keys()) == sorted(expected_by_key)
        assert {entry["key"]: entry for entry in exported["columns"]} == expected_by_key

    assert len(emissions) == 20


def test_native_drop_detaches_cell_widgets_before_moving_bottom_row(app, monkeypatch):
    widget = SettingsDataTab(_columns(), themes=["default"])
    tree = widget.column_tree

    def fake_native_drop(view, _event):
        source = view.topLevelItem(view.topLevelItemCount() - 1)
        assert source is not None
        assert all(view.itemWidget(source, column) is None for column in range(view.columnCount()))
        moved = view.takeTopLevelItem(view.topLevelItemCount() - 1)
        assert moved is source
        view.insertTopLevelItem(0, moved)

    monkeypatch.setattr(QTreeWidget, "dropEvent", fake_native_drop)
    tree.dropEvent(object())
    QTest.qWait(1)

    assert widget.column_keys() == ["architecture", "file", "size"]
    assert [entry["key"] for entry in widget.export_configuration()["columns"]] == [
        "architecture",
        "file",
        "size",
    ]


def test_data_column_tree_has_no_persistent_blank_viewport_row(app):
    widget = SettingsDataTab(_columns(), themes=["default"])
    widget.show()
    app.processEvents()
    tree = widget.column_tree
    last_row = tree.visualItemRect(tree.topLevelItem(tree.topLevelItemCount() - 1))

    assert tree.viewport().height() <= last_row.bottom() + 1
    assert not tree.verticalScrollBar().isVisible()
