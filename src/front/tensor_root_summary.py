"""Searchable, header-only summaries of tensor name roots.

The advanced viewer can receive thousands of tensor descriptors.  A compact
root summary keeps the useful high-level structure visible without pretending
that tensor payloads were inspected.  This module only consumes names and
never accepts or renders descriptor values.
"""

from __future__ import annotations

from collections import Counter
from collections.abc import Iterable, Mapping
from typing import Any

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QGroupBox,
    QHeaderView,
    QLabel,
    QLineEdit,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

__all__ = [
    "TensorRootSummary",
    "root_name",
    "summarize_tensor_roots",
]

_MAX_ROOT_CHARS = 500
_UNKNOWN_ROOT = "(unnamed)"


def root_name(value: Any) -> str:
    """Return the first path component of one tensor name.

    Tensor headers in the supported formats generally use dotted names, while
    a few exporters use slash-separated paths.  Treating both separators as
    roots makes the summary useful across formats and leaves names without a
    separator unchanged.  The result is bounded before it reaches Qt.
    """
    text = str(value or "").strip()
    if not text:
        return _UNKNOWN_ROOT
    for separator in (".", "/"):
        if separator in text:
            text = text.split(separator, 1)[0].strip()
    if not text:
        return _UNKNOWN_ROOT
    return text[:_MAX_ROOT_CHARS]


def summarize_tensor_roots(names: Iterable[Any]) -> tuple[dict[str, Any], ...]:
    """Group tensor names into deterministic root-name/count rows."""
    counts = Counter(root_name(name) for name in names)
    return tuple(
        {"name": name, "count": count}
        for name, count in sorted(counts.items(), key=lambda item: item[0].casefold())
    )


class TensorRootSummary(QGroupBox):
    """A read-only searchable table containing root names and counts only."""

    def __init__(self, parent=None):
        super().__init__("Tensor root summary (names only)", parent)
        self._rows: tuple[dict[str, Any], ...] = ()
        self.setToolTip(
            "Searchable top-level tensor-name roots. Only header names and counts "
            "are shown; tensor values are never loaded."
        )

        layout = QVBoxLayout(self)
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search tensor root names")
        self.search.setToolTip("Filter the root-name summary; this does not inspect tensor values.")
        self.search.setAccessibleName("Tensor root name search")
        self.search.textChanged.connect(self._filter_rows)
        layout.addWidget(self.search)

        self.table = QTableWidget(0, 2)
        self.table.setHorizontalHeaderLabels(("Root name", "Tensor count"))
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.table.setWordWrap(False)
        self.table.setSortingEnabled(False)
        self.table.setToolTip(
            "Header-only root names grouped from tensor names; no tensor values are displayed."
        )
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        layout.addWidget(self.table)

        self.status = QLabel("No tensor roots")
        self.status.setToolTip("Number of visible header-only tensor roots.")
        layout.addWidget(self.status)

        # These aliases keep the control easy to discover for hosts and tests.
        self.root_search = self.search
        self.root_table = self.table

    @property
    def rows(self) -> tuple[dict[str, Any], ...]:
        """Return the current bounded root rows without exposing descriptors."""
        return self._rows

    def set_tensor_names(self, names: Iterable[Any]) -> None:
        """Replace the summary from names supplied by a header reader."""
        self._rows = summarize_tensor_roots(names)
        self._render_rows()

    def set_records(self, records: Iterable[Mapping[str, Any]]) -> None:
        """Build the summary from normalized records without retaining them."""
        self.set_tensor_names(
            record.get("name", "") for record in records if isinstance(record, Mapping)
        )

    def clear(self) -> None:
        """Remove the summary and its search text."""
        self._rows = ()
        self.search.clear()
        self._render_rows()

    def _render_rows(self) -> None:
        self.table.setRowCount(len(self._rows))
        for row_index, row in enumerate(self._rows):
            name_item = QTableWidgetItem(str(row["name"]))
            count_item = QTableWidgetItem(f"{int(row['count']):,}")
            name_item.setToolTip("Root name derived from the tensor header key.")
            count_item.setToolTip("Number of header tensor names in this root.")
            count_item.setData(Qt.ItemDataRole.UserRole, int(row["count"]))
            self.table.setItem(row_index, 0, name_item)
            self.table.setItem(row_index, 1, count_item)
        self._filter_rows(self.search.text())

    def _filter_rows(self, text: str) -> None:
        needle = str(text or "").casefold().strip()
        visible = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            matches = not needle or (item is not None and needle in item.text().casefold())
            self.table.setRowHidden(row, not matches)
            visible += int(matches)
        total = len(self._rows)
        self.status.setText(
            f"{visible:,} of {total:,} tensor roots" if needle else f"{total:,} tensor roots"
        )
