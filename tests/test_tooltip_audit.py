# pyright: reportOptionalMemberAccess=false, reportAttributeAccessIssue=false
"""Parametrized smoke audit: every actionable control in owned modules has a
nonempty tooltip or nearby explanatory content.

This test instantiates each owned widget, walks its tree of children, and
collects controls that users interact with.  It does NOT assert exact text —
only that the tooltip or a sibling description label is present and nonempty.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractButton,
    QApplication,
    QComboBox,
    QDialogButtonBox,
    QDoubleSpinBox,
    QGroupBox,
    QLabel,
    QLineEdit,
    QSpinBox,
    QTabWidget,
    QTableView,
    QTableWidget,
    QToolButton,
    QTreeWidget,
    QWidget,
)

from front.filter_widgets import CheckFilterButton
from front.model_card import ModelCard
from front.explorer_tab import ExplorerTab
from front.advanced_viewer import AdvancedViewerDialog
from front.settings_dialog import SettingsDialog
from front.settings_data_tab import ColumnDefinition, SettingsDataTab
from front.theme_tab import ThemeTab


# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

_CONTROL_TYPES = (
    QAbstractButton,
    QComboBox,
    QSpinBox,
    QDoubleSpinBox,
    QTableView,
    QTableWidget,
    QTreeWidget,
    QLineEdit,
)


def _is_actionable(widget: QWidget) -> bool:
    """True for widgets a user can click, toggle, type into, or select from."""
    if not widget.isVisible() and not isinstance(widget, QTabWidget):
        return False
    if isinstance(widget, QTabWidget):
        return True
    if isinstance(widget, _CONTROL_TYPES):
        return True
    if isinstance(widget, QToolButton):
        return True
    return False


def _has_tooltip_or_sibling_description(widget: QWidget) -> bool:
    """Check the widget's own tooltip or a nearby description label."""
    tip = widget.toolTip()
    if tip and tip.strip():
        return True
    # Check sibling labels in the direct parent layout
    parent = widget.parentWidget()
    if parent is not None:
        layout = parent.layout()
        if layout is not None:
            for index in range(layout.count()):
                item = layout.itemAt(index)
                if item is None:
                    continue
                w = item.widget()
                if isinstance(w, QLabel) and w.text() and w.isVisible():
                    text = w.text().strip()
                    if len(text) > 3 and not text.endswith(":") and not text.startswith("⋮"):
                        return True
        # Check grandparent layout (wrappers like make_general_cell)
        grandparent = parent.parentWidget()
        if grandparent is not None:
            glayout = grandparent.layout()
            if glayout is not None:
                for index in range(glayout.count()):
                    item = glayout.itemAt(index)
                    if item is None:
                        continue
                    w = item.widget()
                    if isinstance(w, QLabel) and w.text() and w.isVisible():
                        text = w.text().strip()
                        if len(text) > 3 and not text.endswith(":") and not text.startswith("⋮"):
                            return True
    return False


def _collect_controls(
    widget: QWidget, depth: int = 0, max_depth: int = 8
) -> list[tuple[str, str]]:
    """Return list of (objectName or class, reason) for controls lacking tooltip/description."""
    issues: list[tuple[str, str]] = []
    if depth > max_depth:
        return issues

    if _is_actionable(widget):
        if not _has_tooltip_or_sibling_description(widget):
            name = widget.objectName() or type(widget).__name__
            # Skip internal Qt widgets (corner buttons, spinbox line edits, etc.)
            if name.startswith("qt_"):
                pass
            # QTabWidget tabs are described by their tab text
            elif isinstance(widget, QTabWidget):
                pass
            # QLineEdit with placeholder text is acceptable
            elif isinstance(widget, QLineEdit) and widget.placeholderText():
                pass
            # QGroupBox title is descriptive enough
            elif isinstance(widget, QGroupBox):
                pass
            # QDialogButtonBox and its standard buttons have implicit roles
            elif isinstance(widget, QDialogButtonBox):
                pass
            elif isinstance(widget, QAbstractButton) and isinstance(widget.parent(), QDialogButtonBox):
                pass
            else:
                issues.append((name, "no tooltip or sibling description"))

    for child in widget.findChildren(QWidget, options=Qt.FindChildOption.FindDirectChildrenOnly):
        issues.extend(_collect_controls(child, depth + 1, max_depth))

    return issues


# ---------------------------------------------------------------------------
# parametrized audit — one test per owned module
# ---------------------------------------------------------------------------

MODULES: list[tuple[str, Any, dict[str, Any]]] = [
    ("filter_widgets", CheckFilterButton, {"label": "Architecture"}),
    (
        "model_card",
        ModelCard,
        {
            "data": {
                "filepath": "R:/test.safetensors",
                "filename": "test.safetensors",
                "architecture": "TestArch",
                "model_type": "test",
            }
        },
    ),
    ("explorer_tab", ExplorerTab, {}),
    ("advanced_viewer", AdvancedViewerDialog, {"inspection": {"architecture": "Test"}}),
    (
        "settings_dialog",
        SettingsDialog,
        {"data_columns": [ColumnDefinition("file", "File")]},
    ),
    (
        "settings_data_tab",
        SettingsDataTab,
        {"columns": [ColumnDefinition("file", "File")]},
    ),
    ("theme_tab", ThemeTab, {}),
]


@pytest.fixture(scope="session")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


@pytest.mark.parametrize("name,cls,kwargs", MODULES)
def test_actionable_controls_have_tooltip_or_description(
    app: QApplication, name: str, cls: type, kwargs: dict[str, Any]
) -> None:
    """Every actionable control in the widget tree has a nonempty tooltip or sibling description."""
    widget = cls(**kwargs)
    try:
        widget.show()
        app.processEvents()
        issues = _collect_controls(widget)
        assert not issues, (
            f"{name}: {len(issues)} control(s) missing tooltip/description:\n"
            + "\n".join(f"  - {n}: {r}" for n, r in issues)
        )
    finally:
        widget.close()
        widget.deleteLater()