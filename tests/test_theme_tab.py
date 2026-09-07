"""Focused Qt contracts for the General and dedicated Theme settings UI."""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from pathlib import Path

import pytest
from PyQt6.QtWidgets import QApplication, QComboBox, QMessageBox, QWidget

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


def test_general_theme_selector_is_compact_bottom_right_and_data_has_none(app, theme_data_dir):
    dialog = SettingsDialog(
        data_columns=[ColumnDefinition("file", "File")],
        data_configuration={"columns": [], "theme": "github"},
    )
    try:
        dialog.show()
        app.processEvents()
        assert dialog.current_theme_id() == "github"
        assert dialog.theme_combo.objectName() == "generalThemeSelector"
        assert dialog.theme_combo.maximumWidth() <= 130
        assert dialog.findChild(type(dialog.theme_combo), "themeEditorSelector") is dialog.theme_tab.theme_combo
        assert dialog.findChild(QWidget, "generalThemeCell") is not None
        assert not dialog.data_settings_tab.findChildren(QComboBox)
        assert "theme" not in dialog.data_settings_tab.export_configuration()
    finally:
        dialog.close()


def test_color_editing_previews_only_valid_palettes_and_exposes_all_required_colors(app, theme_data_dir):
    tab = ThemeTab("default")
    previews = []
    tab.themePreviewChanged.connect(previews.append)
    try:
        assert set(tab.color_edits) >= {
            "background", "surface", "surface_alt", "text", "muted", "accent",
            "accent_text", "border", "success", "warning", "error",
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
    dialog.theme_tab.set_theme("catppuccin")
    dialog.reject()
    assert dialog.current_theme_id() == "github"

    accepted = SettingsDialog(theme_id="github", data_columns=[])
    accepted.theme_tab.set_theme("catppuccin")
    accepted.accept()
    assert accepted.current_theme_id() == "catppuccin"
