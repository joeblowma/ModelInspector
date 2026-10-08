"""Targeted result-view removal without rebuilding unaffected widgets."""

from __future__ import annotations

from collections.abc import Iterable

from PyQt6.QtCore import Qt

from front.layout_batch import cards_layout_batch


def _counts(values) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        if value:
            counts[value] = counts.get(value, 0) + 1
    return counts


def _refresh_filter_items(owner) -> None:
    results = owner._results
    owner.arch_filter_btn.set_counts(
        _counts(data.get("architecture", "Unknown") for data in results)
    )
    owner.tag_filter_btn.set_counts(
        _counts(tag for data in results for tag in owner._filter_tags_for_data(data))
    )
    owner.format_filter_btn.set_counts(
        _counts(owner._format_filter_for_data(data) for data in results)
    )


def _remove_cards(owner, paths: set[str]) -> None:
    removed = set()
    for mapping in (owner._path_to_card, owner._path_to_simple_card):
        for path in paths:
            card = mapping.pop(path, None)
            if card is not None:
                removed.add(card)
    for card in removed:
        owner.cards_layout.removeWidget(card)
        card.deleteLater()
    owner._cards = [card for card in owner._cards if card not in removed]


def _remove_rows(owner, paths: set[str]) -> None:
    header = owner.table.horizontalHeader()
    assert header is not None
    sorting_enabled = owner.table.isSortingEnabled()
    sort_column = header.sortIndicatorSection()
    sort_order = header.sortIndicatorOrder()
    owner.table.setSortingEnabled(False)
    try:
        rows = {
            row
            for path in paths
            if (row := owner._row_for_filepath(path)) is not None
        }
        for row in sorted(rows, reverse=True):
            owner.table.removeRow(row)
    finally:
        header.setSortIndicator(sort_column, sort_order)
        owner.table.setSortingEnabled(sorting_enabled)

    owner._path_to_row.clear()
    for row in range(owner.table.rowCount()):
        item = owner.table.item(row, 1)
        filepath = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        if filepath:
            owner._path_to_row[filepath] = row


def remove_result_paths(owner, paths: Iterable[str]) -> None:
    """Remove exact lexical paths while retaining all unaffected view objects."""
    removed = {str(path) for path in paths}
    if not removed:
        return

    owner._queued_files = [path for path in owner._queued_files if path not in removed]
    owner._results = [
        data for data in owner._results if data.get("filepath") not in removed
    ]
    owner._selected_paths.difference_update(removed)

    with cards_layout_batch(owner):
        _remove_cards(owner, removed)
        _remove_rows(owner, removed)
        if not owner._results:
            owner._cards.clear()
            owner._path_to_card.clear()
            owner._path_to_simple_card.clear()
            owner._path_to_row.clear()
            owner._clear_cards()
        _refresh_filter_items(owner)
        owner._apply_arch_filter()
        owner._refresh_raw_combo_filtered()
        owner._sync_selection_visuals()


def rebuild_views_from_results(owner) -> None:
    """Rebuild every result view as one layout and filter batch."""
    current_results = list(owner._results)
    header = owner.table.horizontalHeader()
    assert header is not None
    sorting_enabled = owner.table.isSortingEnabled()
    sort_column = header.sortIndicatorSection()
    sort_order = header.sortIndicatorOrder()

    with cards_layout_batch(owner):
        owner.table.setSortingEnabled(False)
        try:
            owner._cards.clear()
            owner._path_to_card.clear()
            owner._path_to_simple_card.clear()
            owner._path_to_row.clear()
            owner._clear_cards()
            owner.table.setRowCount(0)
            owner._reset_format_filter_items()
            owner.raw_combo.clear()
            formats = []
            for data in current_results:
                owner._normalize_result_data(data)
                owner._add_card(data)
                owner._add_table_row(data)
                formats.append(owner._format_filter_for_data(data))
            owner.format_filter_btn.add_items(formats)
            _refresh_filter_items(owner)
        finally:
            header.setSortIndicator(sort_column, sort_order)
            owner.table.setSortingEnabled(sorting_enabled)
        owner._apply_arch_filter()
        owner._refresh_raw_combo_filtered()
        owner._sync_selection_visuals()
