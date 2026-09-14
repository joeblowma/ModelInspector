"""Focused Qt contracts for the dedicated Theme settings UI."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt6.QtCore import QRect
from PyQt6.QtWidgets import (
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QTabWidget,
    QWidget,
)

from front.settings_data_support import ColumnDefinition
from front.settings_dialog import SettingsDialog
from front.theme_tab import ThemeTab


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def theme_data_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "model-inspector"))
    return tmp_path


def test_theme_editor_is_dedicated_and_data_has_none(app, theme_data_dir):
    dialog = SettingsDialog(
        data_columns=[ColumnDefinition("file", "File")],
        data_configuration={"columns": [], "theme": "github"},
    )
    try:
        dialog.show()
        app.processEvents()
        assert dialog.current_theme_id() == "github"
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None
        assert [tabs.tabText(index) for index in range(tabs.count())] == [
            "General",
            "Data Columns",
            "Theme",
        ]
        assert not hasattr(dialog, "theme_combo")
        assert not hasattr(dialog, "general_theme_combo")
        assert not hasattr(dialog, "card_field_checks")
        assert not hasattr(dialog, "simple_card_field_checks")
        assert dialog.findChild(QComboBox, "generalThemeSelector") is None
        assert dialog.findChild(QDialogButtonBox) is not None
        assert dialog.findChild(QComboBox, "themeEditorSelector") is dialog.theme_tab.theme_combo
        assert dialog.theme_tab.theme_combo.currentData() == "github"
        assert not dialog.data_settings_tab.findChildren(QComboBox)
        assert "theme" not in dialog.data_settings_tab.export_configuration()
    finally:
        dialog.close()


def test_settings_dialog_is_fixed_and_bottom_controls_are_visible(app, theme_data_dir):
    dialog = SettingsDialog(data_columns=[ColumnDefinition("file", "File")])
    try:
        dialog.show()
        app.processEvents()
        assert dialog.minimumSize() == dialog.maximumSize()
        assert dialog.size() == dialog.minimumSize()
        screen = dialog.screen()
        assert screen is not None
        available = screen.availableGeometry()
        assert dialog.width() == min(900, max(1, available.width() - 48))
        assert dialog.height() == min(640, max(1, available.height() - 48))

        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None
        assert buttons.isVisible()
        assert buttons.geometry().bottom() <= dialog.contentsRect().bottom()

        assert dialog.width() <= available.width() - 48
        assert dialog.height() <= available.height() - 48
    finally:
        dialog.close()


def test_settings_data_tree_uses_available_dialog_height(app, theme_data_dir):
    dialog = SettingsDialog(
        data_columns=[
            ColumnDefinition(f"column_{index}", f"Column {index}")
            for index in range(30)
        ]
    )
    try:
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None
        data_page = dialog.data_settings_tab.parentWidget()
        assert data_page is not None
        tabs.setCurrentWidget(data_page)
        dialog.show()
        app.processEvents()

        tree = dialog.data_settings_tab.column_tree
        last_row = tree.visualItemRect(tree.topLevelItem(tree.topLevelItemCount() - 1))
        assert tree.height() > 220
        assert tree.height() <= data_page.contentsRect().height()
        assert tree.sizePolicy().verticalPolicy() == QSizePolicy.Policy.Expanding
        assert tree.viewport().height() <= last_row.bottom() + 1
        assert tree.verticalScrollBar().isVisible()
        reset_button = dialog.data_settings_tab.findChild(QPushButton, "resetDataColumnsButton")
        assert reset_button is not None and reset_button.isVisible()
    finally:
        dialog.close()


def test_settings_size_clamp_keeps_controls_usable_on_small_screen(app, theme_data_dir):
    class SmallScreenParent(QWidget):
        def screen(self):
            class SmallScreen:
                @staticmethod
                def availableGeometry():
                    return QRect(0, 0, 800, 500)

            return SmallScreen()

    parent = SmallScreenParent()
    dialog = SettingsDialog(
        parent=parent,
        data_columns=[
            ColumnDefinition("file", "File"),
            ColumnDefinition("size", "Size"),
            ColumnDefinition("architecture", "Architecture"),
        ],
    )
    try:
        tabs = dialog.findChild(QTabWidget)
        assert tabs is not None
        data_page = dialog.data_settings_tab.parentWidget()
        assert data_page is not None
        tabs.setCurrentWidget(data_page)
        dialog.show()
        app.processEvents()

        assert dialog.width() == 752
        assert dialog.height() == 452
        assert dialog.minimumSize() == dialog.maximumSize()
        buttons = dialog.findChild(QDialogButtonBox)
        assert buttons is not None and buttons.isVisible()
        reset_button = dialog.data_settings_tab.findChild(QPushButton, "resetDataColumnsButton")
        assert reset_button is not None and reset_button.isVisible()
    finally:
        dialog.close()
        parent.close()


def test_color_editing_previews_only_valid_palettes_and_exposes_all_required_colors(app, theme_data_dir):
    tab = ThemeTab("default")
    previews = []
    tab.themePreviewChanged.connect(previews.append)
    try:
        assert set(tab.color_edits) >= {
            "background", "surface", "surface_alt", "text", "muted", "accent",
            "accent_text", "border", "success", "warning", "error",
            "tab_inactive_hover",
        }
        original = tab.current_theme().colors["accent"]
        tab.color_edits["accent"].setText("#123456")
        assert previews[-1].colors["accent"] == "#123456"
        tab.color_edits["accent"].setText("#12")
        assert tab.current_theme().colors["accent"] == "#123456"
        assert original != tab.current_theme().colors["accent"]
    finally:
        tab.close()


def test_save_as_refreshes_theme_list_and_writes_valid_user_theme(app, theme_data_dir, monkeypatch):
    monkeypatch.setattr(
        "front.theme_tab.QInputDialog.getText",
        lambda *args, **kwargs: ("my_custom", True),
    )
    tab = ThemeTab("github")
    try:
        tab.color_edits["accent"].setText("#123456")
        assert tab.save_as()
        assert tab.current_theme_id() == "my_custom"
        assert (theme_data_dir / "model-inspector" / "themes" / "my_custom.jsonc").is_file()
        assert tab.theme_combo.findData("my_custom") >= 0
        assert tab.save_current()
    finally:
        tab.close()


def test_new_theme_uses_bundled_default_and_skips_existing_disk_names(app, theme_data_dir):
    theme_dir = theme_data_dir / "model-inspector" / "themes"
    theme_dir.mkdir(parents=True)
    (theme_dir / "new_theme_1.jsonc").write_text("{ malformed", encoding="utf-8")
    tab = ThemeTab("github")
    default_tab = ThemeTab("default")
    try:
        assert tab.new_button.objectName() == "newThemeButton"
        assert tab.new_theme()
        assert tab.current_theme_id() == "new_theme_2"
        assert tab.current_theme().colors == default_tab.current_theme().colors
        assert (theme_dir / "new_theme_2.jsonc").is_file()
    finally:
        default_tab.close()
        tab.close()


def test_theme_editor_uses_friendly_color_labels(app, theme_data_dir):
    tab = ThemeTab("default")
    try:
        muted_label = tab._color_form.labelForField(tab.color_edits["muted"].parentWidget())
        assert muted_label is not None and muted_label.text() == "Status Text:"
        assert "Inactive Tabs" in tab.color_buttons["accent"].accessibleName()
        hover_label = tab._color_form.labelForField(tab.color_edits["tab_inactive_hover"].parentWidget())
        assert hover_label is not None and hover_label.text() == "Inactive Tab Hover Background:"
    finally:
        tab.close()


def test_malformed_requested_theme_falls_back_and_warns_once(app, theme_data_dir, monkeypatch):
    theme_dir = theme_data_dir / "model-inspector" / "themes"
    theme_dir.mkdir(parents=True)
    (theme_dir / "broken.jsonc").write_text("{ invalid", encoding="utf-8")
    warnings = []
    monkeypatch.setattr("front.settings_dialog.QMessageBox.warning", lambda *args: warnings.append(args))
    dialog = SettingsDialog(theme_id="broken", data_columns=[])
    try:
        app.processEvents()
        assert dialog.current_theme_id() == "default"
        assert len(warnings) == 1
        dialog.theme_tab.set_theme("broken")
        assert dialog.current_theme_id() == "default"
        assert len(warnings) == 1
    finally:
        dialog.close()


def test_reset_requires_confirmation_reextracts_and_selects_default(app, theme_data_dir, monkeypatch):
    tab = ThemeTab("github")
    calls = []
    monkeypatch.setattr(
        "front.theme_tab.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr("front.theme_tab.reset_user_themes", lambda: calls.append("reset"))
    monkeypatch.setattr("front.theme_tab.ensure_bundled_themes", lambda: calls.append("ensure"))
    try:
        assert tab.reset_to_defaults()
        assert calls[:2] == ["reset", "ensure"]
        assert calls.count("ensure") >= 2
        assert tab.current_theme_id() == "default"
    finally:
        tab.close()


def test_cancel_restores_live_selection_but_accept_keeps_it(app, theme_data_dir):
    dialog = SettingsDialog(theme_id="github", data_columns=[])
    changes = []
    dialog.themeChanged.connect(changes.append)
    dialog.theme_tab.set_theme("catppuccin")
    assert changes[-1] == "catppuccin"
    assert dialog.current_theme_id() == "catppuccin"
    dialog.reject()
    assert dialog.current_theme_id() == "github"

    accepted = SettingsDialog(theme_id="github", data_columns=[])
    accepted.theme_tab.set_theme("catppuccin")
    accepted.accept()
    assert accepted.current_theme_id() == "catppuccin"


def test_configure_application_warns_once_for_malformed_persisted_theme(app, monkeypatch, tmp_path):
    """A malformed persisted theme falls back safely and warns once at startup."""
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "model-inspector"))
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    (tmp_path / "settings.jsonc").write_text(
        '{"data_layout": {"theme": "broken"}}', encoding="utf-8"
    )
    theme_dir = tmp_path / "model-inspector" / "themes"
    theme_dir.mkdir(parents=True)
    (theme_dir / "broken.jsonc").write_text("{ invalid", encoding="utf-8")

    from front import application as application_module

    application_module._THEME_DIAGNOSTIC_KEYS.clear()
    warnings = []
    monkeypatch.setattr(
        "front.application.QMessageBox.warning", lambda *args: warnings.append(args)
    )
    application_module.configure_application(app)
    assert app.styleSheet()  # safe default stylesheet applied
    app.processEvents()
    assert len(warnings) == 1
    # A second startup pass must not re-warn for the same failure.
    application_module.configure_application(app)
    app.processEvents()
    assert len(warnings) == 1
