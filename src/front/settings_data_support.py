"""State descriptions and reusable row cleanup for the Data settings editor."""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any, cast

from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
)


@dataclass(frozen=True)
class ColumnDefinition:
    """Stable description of one Data-table column.

    ``hideable`` columns may be hidden by the user; locked columns are always
    visible.  ``reorderable`` columns may be moved; locked columns stay pinned
    at the front so a locked selection column is always first.
    """

    key: str
    label: str
    visible: bool = True
    width: int = 100
    minimum_width: int = 32
    hideable: bool = True
    reorderable: bool = True


@dataclass
class ColumnState:
    """Durable editable state, independent of Qt-owned cell widgets."""

    visible: bool
    width: int


def normalise_columns(
    values: Iterable[Any], minimum_width: int, report: Callable[[str], None]
) -> list[ColumnDefinition]:
    """Coerce arbitrary column descriptions into validated definitions.

    Invalid entries are skipped and reported.  Locked columns are forced
    visible so callers cannot accidentally seed a hidden selection column.
    """
    if isinstance(values, Mapping):
        values = [{"key": key, "label": value} for key, value in values.items()]
    result: list[ColumnDefinition] = []
    seen: set[str] = set()
    for index, value in enumerate(values):
        try:
            if isinstance(value, ColumnDefinition):
                column = value
            elif isinstance(value, Mapping):
                key = str(value.get("key", "")).strip()
                label = str(value.get("label", key)).strip() or key
                column = ColumnDefinition(
                    key,
                    label,
                    bool(value.get("visible", True)),
                    int(value.get("width", 100)),
                    int(value.get("minimum_width", minimum_width)),
                    bool(value.get("hideable", True)),
                    bool(value.get("reorderable", True)),
                )
            elif isinstance(value, str):
                key = value.strip()
                column = ColumnDefinition(key, key)
            else:
                pair = list(cast(Sequence[Any], value))
                if not pair:
                    raise ValueError("empty column description")
                key = str(pair[0]).strip()
                label = str(pair[1] if len(pair) > 1 else key).strip() or key
                column = ColumnDefinition(key, label)
            if not column.key.strip() or column.key in seen:
                raise ValueError("column keys must be non-empty and unique")
            seen.add(column.key)
            key = column.key.strip()
            result.append(
                ColumnDefinition(
                    key,
                    column.label.strip() or key,
                    True if not column.hideable else bool(column.visible),
                    int(column.width),
                    max(1, int(column.minimum_width)),
                    bool(column.hideable),
                    bool(column.reorderable),
                )
            )
        except (TypeError, ValueError, AttributeError) as exc:
            report(f"Ignored invalid column {index + 1}: {exc}")
    if not result:
        report("No valid Data columns were supplied.")
    return result


def locked_keys(columns_by_key: Mapping[str, ColumnDefinition]) -> list[str]:
    """Keys of columns that must stay pinned at the front, in definition order."""
    return [key for key, column in columns_by_key.items() if not column.reorderable]


class ColumnTree(QTreeWidget):
    """Flat, compact tree used to display editable Data-column rows."""

    def __init__(self) -> None:
        super().__init__()
        # Let the parent Data-tab layout allocate the viewport height.  Growing
        # the widget to every row makes the dialog's layout size hint override
        # its fixed initial geometry before a native window is first shown.
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustIgnored)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumHeight(120)

    def refresh_content_height(self) -> None:
        """Refresh geometry while the parent layout supplies available height."""
        self.updateGeometry()

    def _detach_item_widgets(self) -> None:
        """Detach embedded controls before rows are reordered or discarded.

        Qt owns widgets installed with ``setItemWidget``.  Explicitly hiding,
        unparenting, and deferring their deletion prevents stale controls from
        painting over a row after a configuration load or reset.
        """
        items: list[QTreeWidgetItem] = []
        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            if item is not None:
                items.append(item)

        def append_children(item: QTreeWidgetItem) -> None:
            for child_index in range(item.childCount()):
                child = item.child(child_index)
                if child is not None:
                    items.append(child)
                    append_children(child)

        for item in list(items):
            append_children(item)
        for item in items:
            for column in range(self.columnCount()):
                widget = self.itemWidget(item, column)
                if widget is not None:
                    self.removeItemWidget(item, column)
                    widget.hide()
                    widget.setParent(None)
                    widget.deleteLater()


__all__ = [
    "ColumnDefinition",
    "ColumnState",
    "ColumnTree",
    "locked_keys",
    "normalise_columns",
]
