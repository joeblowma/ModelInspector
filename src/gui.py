#!/usr/bin/env python3
# pyright: reportIncompatibleMethodOverride=false
"""Qt bootstrap and backwards-compatible public facade for Model Inspector.

The application behavior lives in the focused modules under :mod:`front`.
This module deliberately owns only composition, public compatibility exports,
cache test seams, and the standalone Qt entry point.
"""

import sys

from app_paths import asset_path as _asset
from front.application import (
    DARK_STYLE,
    close_startup_splash,
    configure_application,
    finish_startup_splash,
    show_startup_splash,
)
from PyQt6.QtWidgets import QApplication, QMainWindow

from front.analysis_controller import AnalysisMixin
from front.discovery_controller import DiscoveryMixin
from front.filter_widgets import CheckFilterButton, SortableTableWidgetItem
from front.integration_controller import IntegrationMixin
from front.model_card import ModelCard
from front.selection_controller import SelectionMixin
from front.settings_dialog import SettingsDialog
from front.smart_column_controller import SmartColumnMixin
from front.startup_cache_controller import StartupCacheMixin
from front.view_controller import ViewMixin
from front.window_core import (
    CoreMixin,
    _clipboard,
    _combo_data_str,
    _model_file_filter,
    _settings,
)
from front.window_layout import WindowLayoutMixin
from front.window_lifecycle import LifecycleMixin
from model_cache import (
    get_cached_inspection_summary_snapshots,
    get_cached_raw_dump,
    list_cached_inspection_paths,
)

__all__ = [
    "CheckFilterButton",
    "DARK_STYLE",
    "MainWindow",
    "ModelCard",
    "SettingsDialog",
    "SortableTableWidgetItem",
    "main",
]


class MainWindow(
    CoreMixin,
    WindowLayoutMixin,
    SmartColumnMixin,
    DiscoveryMixin,
    IntegrationMixin,
    StartupCacheMixin,
    AnalysisMixin,
    ViewMixin,
    SelectionMixin,
    LifecycleMixin,
    QMainWindow,
):
    """Concrete cooperative composition of the Model Inspector window."""

    # These bridge hooks deliberately resolve this module's globals at call
    # time. Tests and extensions that monkeypatch ``gui`` retain the exact
    # seams that existed before the frontend extraction.
    def _list_cached_inspection_paths(self) -> list[str]:
        return list_cached_inspection_paths()

    def _get_cached_inspection_summary_snapshots(
        self, paths: list[str]
    ) -> dict[str, dict]:
        return get_cached_inspection_summary_snapshots(paths)

    def _get_cached_raw_dump(self, filepath: str) -> str | None:
        return get_cached_raw_dump(filepath)


def main() -> int:
    """Launch the desktop application (thin delegation to front.application)."""
    from front.application import run

    return run()


if __name__ == "__main__":
    sys.exit(main())
