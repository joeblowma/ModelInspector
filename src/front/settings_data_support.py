"""State descriptions and reusable row cleanup for the Data settings editor."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtWidgets import (
    QAbstractScrollArea,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
)


@dataclass(frozen=True)
class ColumnDefinition:
    """Stable description of one Data-table column."""

    key: str
    label: str
    visible: bool = True
    width: int = 100
    minimum_width: int = 32


@dataclass
class ColumnState:
    """Durable editable state, independent of Qt-owned cell widgets."""

    visible: bool
    width: int


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


__all__ = ["ColumnDefinition", "ColumnState", "ColumnTree"]
