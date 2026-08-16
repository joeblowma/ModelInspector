# pyright: reportReturnType=false
"""Headless coverage for the reusable Data settings widget."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
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
