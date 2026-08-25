"""State descriptions and native controls for the Data settings editor."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QTimer, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QApplication,
    QAbstractScrollArea,
    QToolButton,
    QTreeWidget,
    QTreeWidgetItem,
    QSizePolicy,
    QWidget,
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


@dataclass(frozen=True)
class ThemeChoice:
    """Normalized theme option for the combo box."""

    key: str
    label: str


class ColumnTree(QTreeWidget):
    """Top-level-only tree that notifies after native move cleanup."""

    rowsReordered = pyqtSignal()

    def __init__(self) -> None:
        super().__init__()
        self._drop_pending = False
        self.setSizeAdjustPolicy(QAbstractScrollArea.SizeAdjustPolicy.AdjustToContents)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Maximum)
        self.setMinimumHeight(0)
        self.setMaximumHeight(220)

    def refresh_content_height(self) -> None:
        """Size the list to its rows while retaining a bounded scroller."""
        self.setMaximumHeight(min(220, self.sizeHint().height()))
        self.updateGeometry()

    def dropEvent(self, event) -> None:  # pylint: disable=invalid-name  # type: ignore[no-untyped-def]
        self._detach_item_widgets()
        super().dropEvent(event)
        self.queue_post_drop_reconciliation()

    def _detach_item_widgets(self) -> None:
        """Keep Qt's internal move operating on bare items, not child widgets."""
        for index in range(self.topLevelItemCount()):
            item = self.topLevelItem(index)
            if item is None:
                continue
            for column in range(self.columnCount()):
                widget = self.itemWidget(item, column)
                if widget is not None:
                    self.removeItemWidget(item, column)
                    widget.deleteLater()

    def queue_post_drop_reconciliation(self) -> None:
        """Coalesce a completed native move into one queued notification."""
        if not self._drop_pending:
            self._drop_pending = True
            QTimer.singleShot(0, self._emit_reordered)

    def _emit_reordered(self) -> None:
        self._drop_pending = False
        self.rowsReordered.emit()


class DragHandle(QToolButton):
    """Small handle that starts the tree's native internal-move operation."""

    def __init__(self, tree: ColumnTree, item: QTreeWidgetItem, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._tree = tree
        self._item = item
        self._press_position = None

    def mousePressEvent(self, event) -> None:  # pylint: disable=invalid-name  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.LeftButton:
            self._tree.setCurrentItem(self._item)
            self._press_position = event.position().toPoint()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # pylint: disable=invalid-name  # type: ignore[no-untyped-def]
        if self._press_position is not None and event.buttons() & Qt.MouseButton.LeftButton:
            if (event.position().toPoint() - self._press_position).manhattanLength() >= QApplication.startDragDistance():
                self._tree.startDrag(Qt.DropAction.MoveAction)
                self._press_position = None
                return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # pylint: disable=invalid-name  # type: ignore[no-untyped-def]
        self._press_position = None
        super().mouseReleaseEvent(event)


__all__ = ["ColumnDefinition"]
