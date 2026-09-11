"""Focused contracts for live theme QSS and cached-view refresh linkage."""

from __future__ import annotations

import os
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PyQt6.QtWidgets import QApplication

from back.theme_loader import BUILTIN_THEME, Theme
from front.application import _theme_stylesheet
from front.integration_controller import IntegrationMixin
from front.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_inactive_tab_hover_uses_its_own_non_selected_theme_color() -> None:
    colors = dict(BUILTIN_THEME.colors)
    colors["tab_inactive_hover"] = "#123456"
    stylesheet = _theme_stylesheet(Theme("test", "Test", colors))

    assert "QTabBar::tab:!selected:hover { background-color: #123456; color:" in stylesheet
    assert "QTabBar::tab:selected { background-color:" in stylesheet


def test_cached_labels_and_open_advanced_viewer_refresh_with_live_theme() -> None:
    class Label:
        def __init__(self) -> None:
            self.stylesheet = ""

        def setStyleSheet(self, stylesheet: str) -> None:
            self.stylesheet = stylesheet

    class AdvancedDialog:
        def __init__(self) -> None:
            self.refreshed = 0

        @staticmethod
        def isVisible() -> bool:
            return True

        def refresh_theme(self) -> None:
            self.refreshed += 1

    class CachedSettingsDialog:
        def __init__(self) -> None:
            self.theme_colors = None

        def refresh_theme(self, theme_colors) -> None:
            self.theme_colors = dict(theme_colors)

    advanced = AdvancedDialog()
    settings = CachedSettingsDialog()
    target = SimpleNamespace(
        progress_label=Label(),
        selected_count_label=Label(),
        table_selected_count_label=Label(),
        cards_placeholder=Label(),
        _advanced_dialog=advanced,
        _settings_dialog=settings,
    )

    IntegrationMixin._refresh_theme_colors(target)

    assert "color:" in target.progress_label.stylesheet
    assert "padding: 60px" in target.cards_placeholder.stylesheet
    assert advanced.refreshed == 1
    assert settings.theme_colors is not None


def test_settings_dialog_refreshes_title_and_muted_descriptions_live(app, monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "model-inspector"))
    colors = dict(BUILTIN_THEME.colors)
    colors.update({"accent_display": "#123456", "muted": "#654321"})
    dialog = SettingsDialog(data_columns=[])
    try:
        dialog.refresh_theme(colors)
        assert "#123456" in dialog._theme_title.styleSheet()
        assert dialog._muted_theme_labels
        assert all("#654321" in label.styleSheet() for label in dialog._muted_theme_labels)
    finally:
        dialog.close()
