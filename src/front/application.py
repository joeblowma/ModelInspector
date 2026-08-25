"""Application-wide Qt configuration used by the thin :mod:`gui` launcher."""

import os

# Set before Qt is imported so packaged Windows launches stay quiet.
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

from PyQt6.QtGui import QIcon
from PyQt6.QtWidgets import QApplication

from app_paths import asset_path
from back.theme_loader import load_theme

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


def _theme_stylesheet(theme_id: str | None) -> str:
    """Return a complete safe stylesheet using validated external theme colors."""
    loaded = load_theme(theme_id)
    colors = loaded.theme.colors
    return DARK_STYLE + (
        "\nQMainWindow, QWidget { background-color: %(background)s; color: %(text)s; }"
        "\nQTableWidget { background-color: %(surface)s; alternate-background-color: %(background)s;"
        " selection-background-color: %(surface_alt)s; }"
        "\nQHeaderView::section, QTabBar::tab { background-color: %(surface)s; color: %(accent)s; }"
        "\nQPushButton { background-color: %(surface)s; border-color: %(border)s; color: %(text)s; }"
        "\nQPushButton:hover { background-color: %(surface_alt)s; border-color: %(accent)s; }"
    ) % colors


def apply_theme(application: QApplication, theme_id: str | None = None) -> tuple[str, tuple[str, ...]]:
    """Apply a validated external theme, retaining the default style on failure."""
    loaded = load_theme(theme_id)
    application.setStyleSheet(_theme_stylesheet(loaded.theme.id))
    return loaded.theme.id, loaded.diagnostics


def configure_application(application: QApplication) -> None:
    """Apply the desktop look and bundled icon before showing a window."""
    application.setStyle("Fusion")
    try:
        from app_paths import legacy_settings_path, settings_path
        from back.settings_store import open_settings
        selected = open_settings(settings_path(), legacy_settings_path()).value("data_layout", {}).get("theme", "default")
    except (ImportError, AttributeError, OSError, TypeError, ValueError):
        selected = "default"
    apply_theme(application, str(selected))
    application.setWindowIcon(QIcon(str(asset_path("icon.ico"))))


def close_startup_splash() -> None:
    """Dismiss PyInstaller's optional splash screen after the window is shown."""
    if pyi_splash is not None:
        pyi_splash.close()
