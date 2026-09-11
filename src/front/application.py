"""Application-wide Qt configuration used by the thin :mod:`gui` launcher."""

import os

# Set before Qt is imported so packaged Windows launches stay quiet.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

from PyQt6.QtCore import QTimer
from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication, QMessageBox

from app_paths import asset_path
from back.theme_loader import BUILTIN_THEME, Theme, ThemeLoadResult, load_theme

try:
    import pyi_splash  # type: ignore[import-not-found]
except ImportError:
    pyi_splash = None


DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 100px;
}
QTabBar::tab:selected {
    background-color: #45475a;
    color: #f5c2e7;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #3b3b52;
}

QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    padding: 8px 10px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #585b70;
    border-color: #f5c2e7;
}
QPushButton:pressed {
    background-color: #6c7086;
}
QPushButton#analyzeBtn {
    background-color: #74c7ec;
    color: #1e1e2e;
    border: none;
}
QPushButton#analyzeBtn:hover {
    background-color: #89dceb;
}
QPushButton#clearBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}
QPushButton#clearBtn:hover {
    background-color: #f5a8be;
}
QToolButton#openBtn {
    background-color: #45475a;
    padding: 0px 10px;
    min-height: 31px;
    max-height: 31px;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 6px;
    font-weight: bold;
}
QToolButton#openBtn:hover {
    background-color: #585b70;
    border-color: #f5c2e7;
}
QToolButton#openBtn:pressed {
    background-color: #6c7086;
}
QTableWidget {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 3px;
}
QHeaderView::section {
    background-color: #313244;
    color: #f5c2e7;
    padding: 8px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}

QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background-color: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #74c7ec;
    border-radius: 4px;
}
"""


def _theme_stylesheet(theme_id: str | Theme | None) -> str:
    """Return a complete safe stylesheet using validated external theme colors."""
    loaded = ThemeLoadResult(theme_id) if isinstance(theme_id, Theme) else load_theme(theme_id)
    colors = {**BUILTIN_THEME.colors, **loaded.theme.colors}
    return DARK_STYLE + "\n" + loaded.theme.stylesheet() + (
        "\nQMainWindow, QWidget { background-color: %(background)s; color: %(text)s; }"
        "\nQTableWidget { background-color: %(surface)s; alternate-background-color: %(background)s;"
        " selection-background-color: %(surface_alt)s; }"
        "\nQHeaderView::section, QTabBar::tab { background-color: %(surface)s; color: %(accent)s; }"
        "\nQTabBar::tab:!selected { color: %(accent)s; }"
        "\nQTabBar::tab:!selected:hover { background-color: %(tab_inactive_hover)s; color: %(accent)s; }"
        "\nQPushButton { background-color: %(surface)s; border-color: %(border)s; color: %(text)s; }"
        "\nQPushButton:hover { background-color: %(surface_alt)s; border-color: %(accent)s; }"
        "\nQLabel[themeRole=muted] { color: %(muted)s; }"
        "\nQLabel[themeRole=success] { color: %(success)s; }"
        "\nQLabel[themeRole=warning] { color: %(warning)s; }"
        "\nQLabel[themeRole=error] { color: %(error)s; }"
        "\nQLabel[themeRole=highlight] { color: %(highlight)s; }"
        "\nQLabel[themeRole=highlight_selected] { color: %(highlight_selected)s; }"
        "\nQLabel[themeRole=stat_label] { color: %(stat_label)s; }"
        "\nQLabel[themeRole=accent_adapter] { color: %(accent_adapter)s; }"
        "\nQLabel[themeRole=accent_moe] { color: %(accent_moe)s; }"
        "\nQLabel[themeRole=accent_component] { color: %(accent_component)s; }"
        "\nQLabel[themeRole=accent_display] { color: %(accent_display)s; }"
        "\nQTabBar::tab:selected { background-color: %(surface_alt)s; color: %(accent_display)s; font-weight: bold; }"
        "\nQPushButton#clearBtn { background-color: %(surface_alt)s; color: %(text)s; border: none; }"
        "\nQPushButton#clearBtn:hover { background-color: %(surface)s; }"
    ) % colors


_THEME_DIAGNOSTIC_KEYS: set[tuple[str, tuple[str, ...]]] = set()


def _show_theme_diagnostics(parent, requested: str, diagnostics: tuple[str, ...]) -> None:
    """Show one concise fallback warning per requested failure in this process."""
    key = (requested, diagnostics)
    if key in _THEME_DIAGNOSTIC_KEYS:
        return
    _THEME_DIAGNOSTIC_KEYS.add(key)
    QMessageBox.warning(
        parent,
        "Theme unavailable",
        f"Theme {requested!r} could not be loaded. The safe default remains active.\n"
        + "; ".join(diagnostics),
    )


def apply_theme(
    application: QApplication,
    theme_id: str | None = None,
    *,
    theme: Theme | None = None,
    parent=None,
    notify: bool = True,
) -> tuple[str, tuple[str, ...]]:
    """Apply a validated external theme, retaining the default style on failure."""
    loaded = ThemeLoadResult(theme) if theme is not None else load_theme(theme_id)
    application.setStyleSheet(_theme_stylesheet(loaded.theme))
    # Set global theme colors for widget construction
    try:
        from back.theme_loader import set_global_theme_colors
        set_global_theme_colors(dict(loaded.theme.colors))
    except ImportError:
        pass
    if loaded.used_fallback and theme_id is not None and notify:
        _show_theme_diagnostics(parent, str(theme_id), loaded.diagnostics)
    return loaded.theme.id, loaded.diagnostics


def configure_application(application: QApplication) -> None:
    """Apply the desktop look and bundled icon before showing a window."""
    application.setStyle("Fusion")
    try:
        from app_paths import legacy_settings_path, settings_path
        from back.settings_store import open_settings
        selected = str(
            open_settings(settings_path(), legacy_settings_path())
            .value("data_layout", {})
            .get("theme", "default")
            or "default"
        )
    except (ImportError, AttributeError, OSError, TypeError, ValueError):
        selected = "default"
    theme_id, diagnostics = apply_theme(application, selected, notify=False)
    application.setWindowIcon(QIcon(str(asset_path("icon.ico"))))
    if diagnostics and selected.lower() not in {"default", "builtin"}:
        # The persisted theme failed to load; the safe default is already
        # applied.  Defer the deduplicated warning until the event loop can
        # present a window so the user actually sees it.
        QTimer.singleShot(
            0, lambda: _show_theme_diagnostics(None, selected, diagnostics)
        )


def close_startup_splash() -> None:
    """Dismiss PyInstaller's optional splash screen after the window is shown."""
    if pyi_splash is not None:
        pyi_splash.close()
