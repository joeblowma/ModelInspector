"""Focused coverage for the built-in color picker controls."""

from __future__ import annotations

from pathlib import Path

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtGui import QColor
from PyQt6.QtWidgets import QApplication, QMessageBox

from back.theme_loader import BUILTIN_THEME, Theme, ThemeLoadResult
from front.theme_editor_support import color_label
from front.theme_tab import ThemeTab


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.fixture
def theme_data_dir(monkeypatch, tmp_path: Path) -> Path:
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "model-inspector"))
    return tmp_path


def _rgba_channels(value: str) -> tuple[int, int, int, int]:
    digits = value.removeprefix("#")
    if len(digits) == 6:
        digits += "FF"
    return tuple(int(digits[index:index + 2], 16) for index in range(0, 8, 2))


def _picker_theme() -> Theme:
    colors = dict(BUILTIN_THEME.colors)
    colors.update(
        {
            "accent": "#11223344",
            "warning": "#A0B0C0D0",
        }
    )
    return Theme(
        "picker_test",
        "Picker Test",
        colors,
        BUILTIN_THEME.description,
        "user",
        dict(BUILTIN_THEME.variables),
    )


def _install_theme_loader(monkeypatch, theme: Theme) -> None:
    def fake_load(requested: str) -> ThemeLoadResult:
        return ThemeLoadResult(theme if str(requested) == theme.id else BUILTIN_THEME)

    monkeypatch.setattr("front.theme_tab.load_theme", fake_load)


def test_every_theme_color_has_accessible_picker_and_initial_channels(
    app, theme_data_dir, monkeypatch
):
    theme = _picker_theme()
    _install_theme_loader(monkeypatch, theme)
    tab = ThemeTab(theme.id, themes=(theme,))
    calls = []

    def fake_get_color(initial, parent, title, options):
        calls.append((initial, parent, title, options))
        return QColor(initial.red(), initial.green(), initial.blue(), initial.alpha())

    monkeypatch.setattr("front.theme_tab.QColorDialog.getColor", fake_get_color)
    try:
        assert set(tab.color_buttons) == set(tab.color_edits)
        assert len(calls) == 0
        for key, button in tab.color_buttons.items():
            assert button.objectName() == f"themeColorPicker_{key}"
            assert button.accessibleName() == f"Choose {color_label(key)} color"
            assert button.toolTip()
            assert button.focusPolicy() == Qt.FocusPolicy.StrongFocus
            assert button.isEnabled()
            button.click()

        assert len(calls) == len(tab.color_buttons)
        assert [call[2] for call in calls] == [
            f"Choose {color_label(key)} color" for key in tab.color_buttons
        ]
        for key, (initial, parent, _title, options) in zip(tab.color_buttons, calls):
            assert parent is tab
            assert initial.getRgb() == _rgba_channels(theme.colors[key])
            assert options.name == "ShowAlphaChannel"
            assert tab.color_buttons[key].property("colorValue") == theme.colors[key].upper()
    finally:
        tab.close()


def test_picker_preserves_rgba_and_formats_opaque_colors_without_alpha(
    app, theme_data_dir, monkeypatch
):
    theme = _picker_theme()
    _install_theme_loader(monkeypatch, theme)
    tab = ThemeTab(theme.id, themes=(theme,))
    selected = {
        "accent": QColor(1, 2, 3, 4),
        "background": QColor(160, 176, 192, 255),
    }
    calls = []

    def fake_get_color(initial, *_args):
        calls.append(initial)
        key = "accent" if len(calls) == 1 else "background"
        return selected[key]

    saves = []
    monkeypatch.setattr("front.theme_tab.QColorDialog.getColor", fake_get_color)
    monkeypatch.setattr("front.theme_tab.save_user_theme", lambda *args: saves.append(args))
    previews = []
    tab.themePreviewChanged.connect(previews.append)
    try:
        tab.color_buttons["accent"].click()
        assert calls[0].getRgb() == (0x11, 0x22, 0x33, 0x44)
        assert tab.color_edits["accent"].text() == "#01020304"
        assert tab.current_theme().colors["accent"] == "#01020304"
        assert tab.color_buttons["accent"].property("colorValue") == "#01020304"
        assert tab._dirty
        assert previews[-1].colors["accent"] == "#01020304"

        tab.color_buttons["background"].click()
        assert calls[1].getRgb() == (*_rgba_channels(theme.colors["background"]),)
        assert tab.color_edits["background"].text() == "#A0B0C0"
        assert tab.current_theme().colors["background"] == "#A0B0C0"
        assert not saves
    finally:
        tab.close()


def test_cancel_keeps_manual_preview_and_uses_working_color_when_text_is_invalid(
    app, theme_data_dir, monkeypatch
):
    tab = ThemeTab("default")
    calls = []
    previews = []
    tab.themePreviewChanged.connect(previews.append)

    def cancel_picker(initial, *_args):
        calls.append(initial)
        return QColor()

    monkeypatch.setattr("front.theme_tab.QColorDialog.getColor", cancel_picker)
    try:
        tab.color_edits["accent"].setText("#123456")
        before_cancel_preview_count = len(previews)
        before_cancel_text = tab.color_edits["accent"].text()
        before_cancel_color = tab.current_theme().colors["accent"]
        before_cancel_swatch = tab.color_buttons["accent"].property("colorValue")
        assert tab._dirty

        tab.color_edits["accent"].setText("#12")
        assert tab.current_theme().colors["accent"] == before_cancel_color
        assert len(previews) == before_cancel_preview_count
        tab.color_buttons["accent"].click()

        assert calls[-1].getRgb() == _rgba_channels(before_cancel_color)
        assert tab.color_edits["accent"].text() == "#12"
        assert tab.current_theme().colors["accent"] == before_cancel_color
        assert tab.color_buttons["accent"].property("colorValue") == before_cancel_swatch
        assert len(previews) == before_cancel_preview_count
        assert before_cancel_text == "#123456"
    finally:
        tab.close()


def test_manual_valid_edits_update_swatch_but_invalid_edits_do_not_preview(
    app, theme_data_dir
):
    tab = ThemeTab("default")
    previews = []
    tab.themePreviewChanged.connect(previews.append)
    try:
        tab.color_edits["warning"].setText("#abcdef12")
        assert tab.current_theme().colors["warning"] == "#abcdef12"
        assert tab.color_buttons["warning"].property("colorValue") == "#ABCDEF12"
        valid_preview_count = len(previews)

        tab.color_edits["warning"].setText("#abc")
        assert tab.current_theme().colors["warning"] == "#abcdef12"
        assert tab.color_buttons["warning"].property("colorValue") == "#ABCDEF12"
        assert len(previews) == valid_preview_count
    finally:
        tab.close()


def test_swatch_values_follow_theme_load_and_reset(
    app, theme_data_dir, monkeypatch
):
    theme = _picker_theme()
    _install_theme_loader(monkeypatch, theme)
    tab = ThemeTab("default", themes=(theme,))
    monkeypatch.setattr("front.theme_tab.reset_user_themes", lambda: None)
    monkeypatch.setattr("front.theme_tab.ensure_bundled_themes", lambda: None)
    monkeypatch.setattr(
        "front.theme_tab.QMessageBox.question",
        lambda *args, **kwargs: QMessageBox.StandardButton.Yes,
    )
    try:
        assert tab.set_theme(theme.id)
        for key, value in theme.colors.items():
            assert tab.color_buttons[key].property("colorValue") == value.upper()

        assert tab.reset_to_defaults()
        for key, value in BUILTIN_THEME.colors.items():
            assert tab.color_buttons[key].property("colorValue") == value.upper()
    finally:
        tab.close()
