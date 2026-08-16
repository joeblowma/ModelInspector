"""Reusable settings widget for Data-table columns and themes.

State is JSON-friendly and persistence remains outside this widget.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping, Sequence
from typing import Any, cast

from PyQt6.QtCore import QSignalBlocker, Qt, pyqtSignal
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QCheckBox,
    QComboBox,
    QFormLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSpinBox,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from front.settings_data_support import ColumnDefinition, ColumnState, ColumnTree, DragHandle, ThemeChoice


class SettingsDataTab(QWidget):
    """Edit Data-column visibility, ordering, widths, and the active theme.

    Parameters
    ----------
    columns:
        Column definitions.  Each item may be a :class:`ColumnDefinition`, a
        mapping with ``key``/``label`` fields, a ``(key, label)`` pair, or a
        bare string (used as both key and label).
    themes / theme_list:
        Optional theme choices.  Theme objects from ``back.theme_loader`` and
        mappings with ``id``/``name`` fields are accepted.  If omitted, the
        loader's ``list_themes`` function is called safely.
    validation_message_hook:
        Optional callback receiving user-readable validation/fallback text.
        The same text is emitted by :attr:`validationMessage` and shown in the
        widget's status label.
    """

    configurationChanged = pyqtSignal(dict)
    themeChanged = pyqtSignal(str)
    validationMessage = pyqtSignal(str)
    configuration_changed = configurationChanged
    theme_changed = themeChanged
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

        self._theme_choices = self._normalise_themes(
            theme_list if theme_list is not None else themes,
            theme_loader,
        )
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
        self.column_tree.setHeaderLabels(["", "Visible", "Column", "Width"])
        self.column_tree.setRootIsDecorated(False)
        self.column_tree.setIndentation(0)
        self.column_tree.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.column_tree.setDragEnabled(True)
        self.column_tree.setAcceptDrops(True)
        self.column_tree.setDropIndicatorShown(True)
        self.column_tree.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.column_tree.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.column_tree.setToolTip("Drag the handle at the left to reorder columns.")
        self.column_tree.rowsReordered.connect(self._on_rows_reordered)
        columns_layout.addWidget(self.column_tree)

        reset_button = QPushButton("Reset columns")
        reset_button.setObjectName("resetDataColumnsButton")
        reset_button.setToolTip("Restore default visibility, widths, and column order.")
        reset_button.clicked.connect(self.reset_to_default)
        columns_layout.addWidget(reset_button, 0, Qt.AlignmentFlag.AlignLeft)
        root.addWidget(columns_group, 1)

        theme_group = QGroupBox("Theme")
        theme_group.setToolTip("Select the visual theme used by the application.")
        theme_layout = QFormLayout(theme_group)
        self.theme_combo = QComboBox()
        self.theme_combo.setObjectName("themeSelector")
        self.theme_combo.setToolTip("Select a validated built-in or external JSONC theme.")
        for choice in self._theme_choices:
            self.theme_combo.addItem(choice.label, choice.key)
        self.theme_combo.currentIndexChanged.connect(self._on_theme_changed)
        theme_layout.addRow("Theme:", self.theme_combo)
        root.addWidget(theme_group)

        self.message_label = QLabel("")
        self.message_label.setObjectName("settingsValidationMessage")
        self.message_label.setWordWrap(True)
        self.message_label.setToolTip("Validation and fallback messages appear here.")
        root.addWidget(self.message_label)

    def _add_row(self, column: ColumnDefinition) -> None:
        item = QTreeWidgetItem(self.column_tree)
        item.setData(0, Qt.ItemDataRole.UserRole, column.key)
        item.setFlags(item.flags() | Qt.ItemFlag.ItemIsDragEnabled | Qt.ItemFlag.ItemIsDropEnabled)
        self._rows[column.key] = item
        self._states[column.key] = ColumnState(column.visible, self._clamp_width(column.width, column))
        self._attach_row_controls(item)

    def _attach_row_controls(self, item: QTreeWidgetItem) -> None:
        key = str(item.data(0, Qt.ItemDataRole.UserRole))
        column = self._columns_by_key[key]
        state = self._states[key]

        handle = DragHandle(self.column_tree, item)
        handle.setText("⋮⋮")
        handle.setAutoRaise(True)
        handle.setToolTip(f"Drag to reorder the {column.label} column.")
        self.column_tree.setItemWidget(item, 0, handle)

        checkbox = QCheckBox()
        checkbox.setChecked(state.visible)
        checkbox.setToolTip(f"Show the {column.label} column in the Data table.")
        checkbox.stateChanged.connect(lambda value, key=key: self._on_visibility_changed(key, value))
        self.column_tree.setItemWidget(item, 1, checkbox)
        self._checks[column.key] = checkbox

        label = QLabel(column.label)
        label.setToolTip(f"Stable key: {column.key}")
        self.column_tree.setItemWidget(item, 2, label)

        width = QSpinBox()
        width.setRange(self._column_minimum(column), self._maximum_width)
        width.setValue(state.width)
        width.setSuffix(" px")
        width.setToolTip(
            f"Width of {column.label} in pixels; minimum {width.minimum()} px."
        )
        width.valueChanged.connect(lambda value, key=key: self._on_width_changed(key, value))
        self.column_tree.setItemWidget(item, 3, width)
        self._widths[column.key] = width

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

    def _normalise_themes(self, supplied: Iterable[Any] | None, loader: Any) -> list[ThemeChoice]:
        values: Iterable[Any] | None = supplied
        if values is None:
            try:
                if loader is None:
                    from back.theme_loader import list_themes

                    values = list_themes()
                elif callable(loader):
                    loaded = loader()
                    values = cast(Iterable[Any], loaded)
                else:
                    values = cast(Iterable[Any], loader.list_themes())
            except (ImportError, OSError, TypeError, ValueError, AttributeError) as exc:
                self._report(f"Theme list unavailable; using Default Dark: {exc}")
                values = ()
        choices: list[ThemeChoice] = []
        seen: set[str] = set()
        for value in values or ():
            try:
                if isinstance(value, Mapping):
                    key = str(value.get("id", "")).strip()
                    label = str(value.get("name", key)).strip() or key
                elif isinstance(value, str):
                    key = label = value.strip()
                else:
                    key = str(getattr(value, "id")).strip()
                    label = str(getattr(value, "name", key)).strip() or key
                if key and key not in seen:
                    choices.append(ThemeChoice(key, label))
                    seen.add(key)
            except (AttributeError, TypeError, ValueError):
                continue
        if not choices:
            choices.append(ThemeChoice("default", "Default Dark"))
        return choices

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

    def _on_rows_reordered(self) -> None:
        self._rebuild_row_controls()
        self._emit_configuration()

    def _on_theme_changed(self, _index: int) -> None:
        if not self._updating:
            key = self.current_theme_id()
            self.themeChanged.emit(key)
            self._emit_configuration()

    # --------------------------------------------------------------- public
    def column_keys(self) -> list[str]:
        """Return current row order by stable key."""
        keys: list[str] = []
        for index in range(self.column_tree.topLevelItemCount()):
            item = self.column_tree.topLevelItem(index)
            if item is not None:
                keys.append(str(item.data(0, Qt.ItemDataRole.UserRole)))
        return keys

    def current_theme_id(self) -> str:
        value = self.theme_combo.currentData()
        return str(value) if value is not None else "default"

    def _default_theme_id(self) -> str:
        return "default" if self.theme_combo.findData("default") >= 0 else self._theme_choices[0].key

    def set_theme(self, theme_id: str, *, emit: bool = True) -> bool:
        index = self.theme_combo.findData(str(theme_id))
        if index < 0:
            self._report(f"Theme {theme_id!r} is unavailable; using Default Dark.")
            index = self.theme_combo.findData("default")
            index = max(index, 0)
        changed = index != self.theme_combo.currentIndex()
        blocker = QSignalBlocker(self.theme_combo)
        self.theme_combo.setCurrentIndex(index)
        del blocker
        if emit and changed:
            self.themeChanged.emit(self.current_theme_id())
            self._emit_configuration()
        return changed

    def _rebuild_row_controls(self) -> None:
        """Replace Qt-owned cell controls after a native row move or load."""
        self._checks.clear()
        self._widths.clear()
        self._rows.clear()
        for index in range(self.column_tree.topLevelItemCount()):
            item = self.column_tree.topLevelItem(index)
            if item is not None:
                key = str(item.data(0, Qt.ItemDataRole.UserRole))
                self._rows[key] = item
                self._attach_row_controls(item)

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
        return {"columns": columns, "theme": self.current_theme_id()}

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
        self._updating = True
        try:
            self._reorder_keys(ordered)
            for key, column in self._columns_by_key.items():
                entry = by_key.get(key, {})
                visible = bool(entry.get("visible", column.visible))
                width = self._clamp_width(entry.get("width", column.width), column)
                self._states[key] = ColumnState(visible, width)
            self._rebuild_row_controls()
            requested_theme = configuration.get("theme", "default")
            self.set_theme(str(requested_theme), emit=False)
        finally:
            self._updating = False
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
            self._updating = not emit
            try:
                self._reorder_keys(keys)
            finally:
                self._updating = False
            if emit:
                self._emit_configuration()
        return True

    def reset_to_default(self, *, emit: bool = True) -> None:
        """Restore the initial column definitions and the first theme choice."""
        self._updating = True
        try:
            for key in list(self._rows):
                item = self._rows.pop(key)
                self.column_tree.takeTopLevelItem(self.column_tree.indexOfTopLevelItem(item))
            self._checks.clear()
            self._widths.clear()
            self._states.clear()
            for column in self._defaults:
                self._add_row(column)
            self.set_theme(self._default_theme_id(), emit=False)
        finally:
            self._updating = False
        if emit:
            self._emit_configuration()

    export_state = export_configuration
    load_state = load_configuration
    reset_defaults = reset_to_default


__all__ = ["ColumnDefinition", "SettingsDataTab"]
