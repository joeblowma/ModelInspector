"""Reusable filter and sorting widgets for the Model Inspector GUI.

The filter button owns the menu checkboxes and emits the active architecture
set for its parent view.  The table item keeps numeric sort metadata in Qt's
user-data role while preserving normal text sorting for other values.

Both widgets are deliberately independent of the main window so they can be
embedded in card and table views without importing the application module.
They expose the same public names and signal contracts as the original GUI.
"""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import (
    QCheckBox,
    QMenu,
    QTableWidgetItem,
    QToolButton,
    QScrollArea,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
)

__all__ = ["CheckFilterButton", "SortableTableWidgetItem"]


class CheckFilterButton(QToolButton):
    filter_changed = pyqtSignal(object)

    def __init__(self, label: str):
        super().__init__()
        self._label = label
        self.setText(f"{self._label}: All")
        self.setToolTip(f"Filter by {self._label.lower()} model family.")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self.setMenu(self._menu)
        self._menu.aboutToShow.connect(self._prepare_menu)

        self._all_cb = QCheckBox("Select All")
        self._all_cb.setToolTip("Select or deselect all model family filters.")
        self._all_cb.setChecked(True)
        self._all_cb.stateChanged.connect(self._toggle_all)
        all_action = QWidgetAction(self)
        all_action.setDefaultWidget(self._all_cb)
        self._menu.addAction(all_action)

        self._items_panel = QWidget()
        self._items_panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self._items_layout = QVBoxLayout(self._items_panel)
        self._items_layout.setContentsMargins(4, 2, 4, 2)
        self._items_layout.setSpacing(2)
        self._items_scroll = QScrollArea()
        self._items_scroll.setWidgetResizable(True)
        self._items_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        self._items_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self._items_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self._items_scroll.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self._items_scroll.setWidget(self._items_panel)
        self._items_action = QWidgetAction(self)
        self._items_action.setDefaultWidget(self._items_scroll)
        self._menu.addAction(self._items_action)

        self._arch_checks: dict[str, QCheckBox] = {}
        self._counts: dict[str, int] = {}
        self._active: set[str] = set()
        self._item_actions: list[QWidgetAction | QAction] = [self._items_action]

    def clear_items(self):
        self._clear_item_actions()
        self._all_cb.blockSignals(True)
        self._all_cb.setChecked(True)
        self._all_cb.blockSignals(False)
        self._counts.clear()
        self._arch_checks.clear()
        self._active.clear()
        self._update_label()
        self.filter_changed.emit(None)

    def _clear_item_actions(self):
        while self._items_layout.count():
            item = self._items_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._arch_checks.clear()

    def _filter_sort_key(self, value: str):
        if value == "ERROR":
            return (0, "")
        if value == "Unknown":
            return (1, "")
        return (2, value.lower())

    def _rebuild_item_actions(self):
        checked_state = {arch: cb.isChecked() for arch, cb in self._arch_checks.items()}
        self._clear_item_actions()
        ordered = sorted(self._counts.keys(), key=self._filter_sort_key)
        for arch in ordered:
            checked = checked_state.get(arch, arch in self._active)
            cb = QCheckBox(f"{arch} ({self._counts.get(arch, 0)})")
            cb.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
            cb.setChecked(checked)
            cb.setToolTip(f"Filter by {arch} model family.")
            cb.stateChanged.connect(self._on_arch_toggled)
            self._arch_checks[arch] = cb
            self._items_layout.addWidget(cb)
        self._items_layout.addStretch()
        self._prepare_menu()

    def remove_item(self, arch: str):
        cb = self._arch_checks.pop(arch, None)
        self._counts.pop(arch, None)
        if not cb:
            return
        if arch in self._active:
            self._active.remove(arch)
        self._rebuild_item_actions()

    def add_item(self, arch: str):
        if not arch:
            return
        if arch in self._counts:
            self._counts[arch] = self._counts.get(arch, 1) + 1
            self._rebuild_item_actions()
            self._update_label()
            return
        self._counts[arch] = 1
        self._active.add(arch)
        self._rebuild_item_actions()
        self._update_label()

    def add_items(self, values):
        changed = False
        for value in values:
            if not value:
                continue
            if value not in self._counts:
                self._active.add(value)
            self._counts[value] = self._counts.get(value, 0) + 1
            changed = True
        if changed:
            self._rebuild_item_actions()
            self._update_label()

    def replace_items(self, values):
        """Atomically refresh discovered values without discarding a filter."""
        previous = set(self._arch_checks)
        preserve_all = not previous or self._active == previous
        counts: dict[str, int] = {}
        for value in values:
            if value:
                counts[value] = counts.get(value, 0) + 1
        self._counts = counts
        self._active = set(counts) if preserve_all else self._active & set(counts)
        self._rebuild_item_actions()
        self._update_label()

    def ensure_item(self, arch: str, count: int = 0):
        if not arch or arch in self._counts:
            return
        self._counts[arch] = count
        self._active.add(arch)
        self._rebuild_item_actions()
        self._update_label()

    def set_all_checked(self, checked: bool):
        self._all_cb.blockSignals(True)
        self._all_cb.setChecked(checked)
        self._all_cb.blockSignals(False)
        for cb in self._arch_checks.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._active = set(self._arch_checks.keys()) if checked else set()
        self._update_label()
        self.filter_changed.emit(self.active_filter())

    def active_filter(self):
        # None means "show all"; an empty set means "show none".
        if not self._arch_checks or len(self._active) == len(self._arch_checks):
            return None
        return set(self._active)

    def _toggle_all(self, state):
        checked = state == Qt.CheckState.Checked.value
        for cb in self._arch_checks.values():
            cb.blockSignals(True)
            cb.setChecked(checked)
            cb.blockSignals(False)
        self._active = set(self._arch_checks.keys()) if checked else set()
        self._update_label()
        self.filter_changed.emit(self.active_filter())

    def _on_arch_toggled(self, _):
        self._active = {a for a, cb in self._arch_checks.items() if cb.isChecked()}
        all_checked = (
            len(self._active) == len(self._arch_checks) and len(self._arch_checks) > 0
        )
        self._all_cb.blockSignals(True)
        self._all_cb.setChecked(all_checked)
        self._all_cb.blockSignals(False)
        self._update_label()
        self.filter_changed.emit(self.active_filter())

    def _update_label(self):
        if not self._arch_checks:
            self.setText(f"{self._label}: All")
            return
        if len(self._active) == len(self._arch_checks):
            self.setText(f"{self._label}: All")
            return
        self.setText(f"{self._label}: {len(self._active)}/{len(self._arch_checks)}")

    def _prepare_menu(self):
        """Constrain the embedded list to the owning window, never the screen."""
        owner = self.window()
        owner_width = owner.width() if owner is not None else self.width()
        owner_height = owner.height() if owner is not None else self.height()
        menu_width = max(1, min(max(220, self.width() * 2), owner_width - 24))
        menu_height = max(1, min(owner_height - 24, 560))
        scroll_height = max(1, menu_height - 40)
        self._items_scroll.setMinimumWidth(max(1, menu_width - 12))
        self._items_scroll.setMaximumHeight(scroll_height)
        self._items_scroll.setMinimumHeight(min(64, max(1, scroll_height)))
        self._menu.setFixedWidth(menu_width)
        self._menu.setMaximumHeight(menu_height)
        self._menu.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Preferred)


class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) or isinstance(right, (int, float)):
            return (left or 0) < (right or 0)
        return super().__lt__(other)
