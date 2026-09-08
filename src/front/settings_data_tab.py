"""Reusable settings widget for Data-table columns.

State is JSON-friendly and persistence remains outside this widget.
Theme editing lives in the dedicated Theme settings tab, not here.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, cast

from PyQt6.QtCore import QEvent, QObject, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSpinBox,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from front.settings_data_support import ColumnDefinition, ColumnState, ColumnTree


class SettingsDataTab(QWidget):
    """Edit Data-column visibility, ordering, and widths.

    Parameters
    ----------
    columns:
        Column definitions.  Each item may be a :class:`ColumnDefinition`, a
        mapping with ``key``/``label`` fields, a ``(key, label)`` pair, or a
        bare string (used as both key and label).
    themes / theme_list / theme_loader:
        Deprecated compatibility arguments.  Theme editing now lives in the
        dedicated Theme settings tab, but old callers may still supply them.
    validation_message_hook:
        Optional callback receiving user-readable validation/fallback text.
        The same text is emitted by :attr:`validationMessage` and shown in the
        widget's status label.
    """

    configurationChanged = pyqtSignal(dict)
    validationMessage = pyqtSignal(str)
    configuration_changed = configurationChanged
    validation_message = validationMessage

    def __init__(
        self,
        columns: Iterable[ColumnDefinition | Mapping[str, Any] | Sequence[Any] | str],
        themes: Iterable[Any] | None = None,
        *,
        theme_list: Iterable[Any] | None = None,
        theme_loader: Any | None = None,
        minimum_width: int = 32,
        maximum_width: int = 4096,
        validation_message_hook: Callable[[str], None] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._minimum_width = max(1, int(minimum_width))
        self._maximum_width = max(self._minimum_width, int(maximum_width))
        self._message_hook = validation_message_hook
        self._defaults: list[ColumnDefinition] = self._normalise_columns(columns)
        self._columns_by_key = {column.key: column for column in self._defaults}
        self._rows: dict[str, QTreeWidgetItem] = {}
        self._checks: dict[str, QCheckBox] = {}
        self._widths: dict[str, QSpinBox] = {}
        self._states: dict[str, ColumnState] = {}
        self._updating = False

        self._build_ui()
        self.reset_to_default(emit=False)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        columns_group = QGroupBox("Data Columns")
        columns_group.setToolTip("Choose visible columns, widths, and their order.")
        columns_layout = QVBoxLayout(columns_group)
        columns_layout.setContentsMargins(8, 8, 8, 8)

        self.column_tree = ColumnTree()
        self.column_tree.setObjectName("dataColumnList")
        self.column_tree.setHeaderLabels(["Visible", "Column", "Width"])
        header = self.column_tree.headerItem()
        if header is not None:
            header.setToolTip(0, "Toggle column visibility in the Data table.")
            header.setToolTip(1, "Column item name in Data table.")
            header.setToolTip(2, "Set column width in pixels.")
        self.column_tree.setRootIsDecorated(False)
        self.column_tree.setIndentation(0)
        self.column_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.column_tree.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.column_tree.setDragEnabled(False)
        self.column_tree.setAcceptDrops(False)
        self.column_tree.setDropIndicatorShown(False)
        self.column_tree.setDragDropMode(QAbstractItemView.DragDropMode.NoDragDrop)
        self.column_tree.setAccessibleName("Data columns")
        self.column_tree.setToolTip(
            "Select one Data column, then use Move Up or Move Down to reorder it."
        )
        self.column_tree.setColumnWidth(0, 60)
        self.column_tree.setColumnWidth(1, 170)
        self.column_tree.setColumnWidth(2, 60) # takes whatever is left
        self.column_tree.setMaximumWidth(400)
        self.column_tree.currentItemChanged.connect(self._on_current_item_changed)
        self.column_tree.itemSelectionChanged.connect(self._refresh_move_buttons)

        list_layout = QHBoxLayout()
        list_layout.setContentsMargins(0, 0, 0, 0)
        list_layout.addWidget(self.column_tree, 1)

        move_layout = QVBoxLayout()
        move_layout.setContentsMargins(0, 0, 0, 0)
        move_layout.addStretch(1)
        self.move_up_button = QPushButton("Move Up")
        self.move_up_button.setObjectName("moveDataColumnUpButton")
        self.move_up_button.setAccessibleName("Move selected Data column up")
        self.move_up_button.setToolTip("Move the selected Data column up one position.")
        self.move_up_button.clicked.connect(lambda: self._move_selected(-1))
        self.move_up_button.setMaximumWidth(200)
        move_layout.addWidget(self.move_up_button)

        self.move_down_button = QPushButton("Move Down")
        self.move_down_button.setObjectName("moveDataColumnDownButton")
        self.move_down_button.setAccessibleName("Move selected Data column down")
        self.move_down_button.setToolTip("Move the selected Data column down one position.")
        self.move_down_button.clicked.connect(lambda: self._move_selected(1))
        self.move_down_button.setMaximumWidth(200)
        move_layout.addWidget(self.move_down_button)
        move_layout.addStretch(1)
        list_layout.addLayout(move_layout)
        columns_layout.addLayout(list_layout)

        reset_button = QPushButton("Reset columns")
        reset_button.setObjectName("resetDataColumnsButton")
        reset_button.setToolTip("Restore default visibility, widths, and column order.")
        reset_button.clicked.connect(self.reset_to_default)
        columns_layout.addWidget(reset_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(columns_group, 1)

        self.message_label = QLabel("")
        self.message_label.setObjectName("settingsValidationMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setToolTip("Validation and fallback messages appear here.")
        root.addWidget(self.message_label)

    def _add_row(self, column: ColumnDefinition) -> None:
        item = QTreeWidgetItem(self.column_tree)
        item.setData(0, Qt.ItemDataRole.UserRole, column.key)
        item.setText(1, column.label)
        item.setToolTip(1, f"Stable key: {column.key}")
        flags = item.flags() & ~(
            Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled
        )
        item.setFlags(flags)
        self._rows[column.key] = item
        self._states[column.key] = ColumnState(column.visible, self._clamp_width(column.width, column))
        self._attach_row_controls(item)

    def _attach_row_controls(self, item: QTreeWidgetItem) -> None:
        key = str(item.data(0, Qt.ItemDataRole.UserRole))
        column = self._columns_by_key[key]
        state = self._states[key]

        checkbox = QCheckBox()
        checkbox.setAccessibleName(f"Show {column.label} column")
        checkbox.setChecked(state.visible)
        checkbox.setToolTip(f"Show the {column.label} column in the Data table.")
        checkbox.stateChanged.connect(lambda value, key=key: self._on_visibility_changed(key, value))
        self.column_tree.setItemWidget(item, 0, checkbox)
        self._install_selection_filter(checkbox, key)
        self._checks[column.key] = checkbox

        width = QSpinBox()
        width.setAccessibleName(f"Width of {column.label} column")
        width.setRange(self._column_minimum(column), self._maximum_width)
        width.setValue(state.width)
        width.setSuffix(" px")
        width.setToolTip(
            f"Width of {column.label} in pixels; minimum {width.minimum()} px."
        )
        width.valueChanged.connect(lambda value, key=key: self._on_width_changed(key, value))
        self.column_tree.setItemWidget(item, 2, width)
        self._install_selection_filter(width, key)
        self._widths[column.key] = width

    def _install_selection_filter(self, widget: QWidget, key: str) -> None:
        """Let clicks on embedded editors select their owning row first."""
        targets = [widget, *widget.findChildren(QWidget)]
        for target in targets:
            target.setProperty("_settings_data_column_key", key)
            target.installEventFilter(self)

    def eventFilter(self, a0: QObject | None, a1: QEvent | None) -> bool:
        obj = a0
        event = a1
        if event is None:
            return super().eventFilter(obj, event)
        select_on_click = (
            event.type() == QEvent.Type.MouseButtonRelease
            and getattr(event, "button", lambda: Qt.MouseButton.NoButton)()
            == Qt.MouseButton.LeftButton
        )
        if select_on_click and isinstance(obj, QWidget):
            key = obj.property("_settings_data_column_key")
            if key:
                self._select_key(str(key))
        return super().eventFilter(obj, event)

    # ------------------------------------------------------------ normalise
    def _normalise_columns(self, values: Iterable[Any]) -> list[ColumnDefinition]:
        if isinstance(values, Mapping):
            values = [
                {"key": key, "label": value}
                for key, value in values.items()
            ]
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
                        int(value.get("minimum_width", self._minimum_width)),
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
                result.append(
                    ColumnDefinition(
                        column.key.strip(),
                        column.label.strip() or column.key.strip(),
                        bool(column.visible),
                        int(column.width),
                        max(1, int(column.minimum_width)),
                    )
                )
            except (TypeError, ValueError, AttributeError) as exc:
                self._report(f"Ignored invalid column {index + 1}: {exc}")
        if not result:
            self._report("No valid Data columns were supplied.")
        return result

    # --------------------------------------------------------------- helpers
    def _column_minimum(self, column: ColumnDefinition) -> int:
        return max(self._minimum_width, min(self._maximum_width, column.minimum_width))

    def _clamp_width(self, value: Any, column: ColumnDefinition) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            self._report(f"Invalid width for {column.label}; using {column.width} px.")
            parsed = column.width
        minimum = self._column_minimum(column)
        clamped = max(minimum, min(self._maximum_width, parsed))
        if clamped != parsed:
            self._report(
                f"Width for {column.label} adjusted to {clamped} px "
                f"(allowed range {minimum}-{self._maximum_width})."
            )
        return clamped

    def _report(self, message: str) -> None:
        if hasattr(self, "message_label"):
            self.message_label.setText(message)
        if self._message_hook is not None:
            self._message_hook(message)
        self.validationMessage.emit(message)

    def _emit_configuration(self) -> None:
        if not self._updating:
            self.configurationChanged.emit(self.export_configuration())

    def _on_visibility_changed(self, key: str, value: int) -> None:
        self._states[key].visible = bool(value)
        self._emit_configuration()

    def _on_width_changed(self, key: str, value: int) -> None:
        self._states[key].width = self._clamp_width(value, self._columns_by_key[key])
        self._emit_configuration()

    def _selected_key(self) -> str | None:
        item = self.column_tree.currentItem()
        if item is None:
            selected = self.column_tree.selectedItems()
            item = selected[0] if selected else None
        if item is None:
            return None
        key = str(item.data(0, Qt.ItemDataRole.UserRole))
        return key if key in self._rows else None

    def _select_key(self, key: str) -> None:
        item = self._rows.get(key)
        if item is None:
            return
        self.column_tree.setCurrentItem(item)
        item.setSelected(True)
        self.column_tree.scrollToItem(item, QAbstractItemView.ScrollHint.EnsureVisible)
        self._refresh_move_buttons()

    def _restore_selection(self, key: str | None) -> None:
        if key is None or key not in self._rows:
            self.column_tree.clearSelection()
            self.column_tree.setCurrentItem(None)
            self._refresh_move_buttons()
            return
        self._select_key(key)

    def _refresh_move_buttons(self) -> None:
        key = self._selected_key()
        index = self.column_keys().index(key) if key is not None else -1
        count = self.column_tree.topLevelItemCount()
        self.move_up_button.setEnabled(index > 0)
        self.move_down_button.setEnabled(0 <= index < count - 1)

    def _on_current_item_changed(
        self, _current: QTreeWidgetItem | None, _previous: QTreeWidgetItem | None
    ) -> None:
        self._refresh_move_buttons()

    def _move_selected(self, offset: int) -> None:
        key = self._selected_key()
        if key is None:
            self._refresh_move_buttons()
            return
        current = self.column_keys().index(key)
        target = current + offset
        if target < 0 or target >= len(self.column_keys()):
            self._refresh_move_buttons()
            return
        self.move_column(key, target)

    # --------------------------------------------------------------- public
    def column_keys(self) -> list[str]:
        """Return current row order by stable key."""
        keys: list[str] = []
        for index in range(self.column_tree.topLevelItemCount()):
            item = self.column_tree.topLevelItem(index)
            if item is not None:
                keys.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return keys

    def _rebuild_row_controls(self, *, widgets_detached: bool = False) -> None:
        """Replace Qt-owned cell controls after a row move or configuration load."""
        selected_key = self._selected_key()
        if not widgets_detached:
            self.column_tree._detach_item_widgets()
        self._checks.clear()
        self._widths.clear()
        self._rows.clear()
        for index in range(self.column_tree.topLevelItemCount()):
            item = self.column_tree.topLevelItem(index)
            if item is not None:
                key = str(item.data(0, Qt.ItemDataRole.UserRole))
                self._rows[key] = item
                self._attach_row_controls(item)
        self.column_tree.refresh_content_height()
        self._restore_selection(selected_key)

    def export_configuration(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot of the current widget state."""
        columns = []
        for key in self.column_keys():
            columns.append(
                {
                    "key": key,
                    "visible": self._states[key].visible,
                    "width": self._states[key].width,
                }
            )
        return {"columns": columns}

    def load_configuration(self, configuration: Mapping[str, Any] | None) -> None:
        """Apply a saved snapshot, safely falling back for invalid entries."""
        if not isinstance(configuration, Mapping):
            self._report("Invalid Data settings; restored defaults.")
            self.reset_to_default()
            return
        raw_columns = configuration.get("columns", ())
        by_key: dict[str, Mapping[str, Any]] = {}
        if isinstance(raw_columns, Mapping):
            for key, value in raw_columns.items():
                by_key[str(key)] = value if isinstance(value, Mapping) else {"visible": value}
        elif isinstance(raw_columns, Sequence) and not isinstance(raw_columns, (str, bytes)):
            for value in raw_columns:
                if isinstance(value, Mapping) and "key" in value:
                    by_key[str(value["key"])] = value
        else:
            self._report("Invalid Data columns configuration; restored defaults.")
        unknown = sorted(set(by_key) - set(self._columns_by_key))
        if unknown:
            self._report("Ignored unknown Data columns: " + ", ".join(unknown))
        ordered = [key for key in by_key if key in self._columns_by_key]
        ordered.extend(key for key in self._columns_by_key if key not in ordered)
        selected_key = self._selected_key()
        self._updating = True
        try:
            self.column_tree._detach_item_widgets()
            self._reorder_keys(ordered)
            for key, column in self._columns_by_key.items():
                entry = by_key.get(key, {})
                visible = bool(entry.get("visible", column.visible))
                width = self._clamp_width(entry.get("width", column.width), column)
                self._states[key] = ColumnState(visible, width)
            self._rebuild_row_controls(widgets_detached=True)
        finally:
            self._updating = False
        self._restore_selection(selected_key)
        self._emit_configuration()

    def _reorder_keys(self, keys: Sequence[str]) -> None:
        for target, key in enumerate(keys):
            current = self.column_keys().index(key)
            if current == target:
                continue
            item = self.column_tree.takeTopLevelItem(current)
            if item is not None:
                self.column_tree.insertTopLevelItem(target, item)

    def move_column(self, key: str, target_index: int, *, emit: bool = True) -> bool:
        """Move a row by stable key; useful for keyboard actions and tests."""
        if key not in self._rows:
            self._report(f"Unknown Data column: {key}")
            return False
        keys = self.column_keys()
        target = max(0, min(len(keys) - 1, int(target_index)))
        current = keys.index(key)
        if current != target:
            keys.insert(target, keys.pop(current))
            previous_updating = self._updating
            self._updating = True
            try:
                self.column_tree._detach_item_widgets()
                self._reorder_keys(keys)
                self._rebuild_row_controls(widgets_detached=True)
            finally:
                self._updating = previous_updating
            if emit:
                self._emit_configuration()
        self._select_key(key)
        return True

    def reset_to_default(self, *, emit: bool = True) -> None:
        """Restore the initial column definitions."""
        selected_key = self._selected_key()
        self._updating = True
        try:
            self.column_tree._detach_item_widgets()
            self.column_tree.clear()
            self._rows.clear()
            self._checks.clear()
            self._widths.clear()
            self._states.clear()
            for column in self._defaults:
                self._add_row(column)
            self.column_tree.refresh_content_height()
        finally:
            self._updating = False
        self._restore_selection(selected_key)
        if emit:
            self._emit_configuration()

    export_state = export_configuration
    load_state = load_configuration
    reset_defaults = reset_to_default


__all__ = ["ColumnDefinition", "SettingsDataTab"]
