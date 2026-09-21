"""Read-only inspection explorer widget.

The widget accepts ordinary mappings and sequences instead of depending on the
cache or inspection worker. It displays headers, never reads or writes tensor
payloads, and emits host-handled requests for candidate actions.
"""
from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any
from PyQt6.QtCore import QRegularExpression, Qt, QSortFilterProxyModel, pyqtSignal
from PyQt6.QtGui import QColor, QStandardItem, QStandardItemModel
from PyQt6.QtWidgets import (
    QAbstractItemView,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QHeaderView,
    QTabWidget,
    QTableView,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from .explorer_data import bucket_label, detect_embedded_content, display_count, flatten_metadata, friendly_bytes, natural_name_key, normalize_tensor_descriptors, safe_display
from .explorer_metadata import _inspect_text, perform_metadata_action, raw_metadata_status
from .tensor_root_summary import TensorRootSummary
__all__ = ["ExplorerTab", "TENSOR_COLUMNS", "normalize_tensor_descriptors", "detect_embedded_content"]
TENSOR_COLUMNS = ("Name", "Shape", "Dtype", "Bucket", "Shard", "Size", "Parameters")
class _TensorProxy(QSortFilterProxyModel):
    """Proxy that combines free-text filtering, bucket filtering, and sorting."""

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._bucket = ""
        self.setFilterKeyColumn(-1)
    def set_bucket(self, bucket: str) -> None:
        self._bucket = bucket.strip().lower()
        self.invalidateFilter()

    def filterAcceptsRow(self, source_row: int, source_parent) -> bool:
        if not super().filterAcceptsRow(source_row, source_parent):
            return False
        if not self._bucket:
            return True
        source_model = self.sourceModel()
        if source_model is None:
            return False
        index = source_model.index(source_row, 3, source_parent)
        return str(index.data(Qt.ItemDataRole.DisplayRole) or "").lower() == self._bucket

    def lessThan(self, left, right) -> bool:
        left_value = left.data(Qt.ItemDataRole.UserRole)
        right_value = right.data(Qt.ItemDataRole.UserRole)
        if isinstance(left_value, (int, float)) or isinstance(right_value, (int, float)):
            return (left_value is None, left_value or 0) < (right_value is None, right_value or 0)
        return natural_name_key(str(left.data() or "")) < natural_name_key(str(right.data() or ""))
class ExplorerTab(QWidget):
    """Reusable header-only model explorer for the desktop application.

    Signals emit dictionaries with ``candidate``, ``inspection``,
    ``read_only=True``, and ``payload_available`` keys. Request receivers own
    any actual inspection, export, or extraction operation.
    """

    inspect_requested = pyqtSignal(object)
    export_requested = pyqtSignal(object)
    extraction_requested = pyqtSignal(object)
    tensor_selected = pyqtSignal(object)
    inspection_requested = inspect_requested
    extract_requested = extraction_requested
    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)
        self._inspection: dict[str, Any] = {}
        self._records: list[dict[str, Any]] = []
        self._all_records: list[dict[str, Any]] = []
        self._metadata_rows: list[dict[str, Any]] = []
        self._embedded_candidates: list[dict[str, Any]] = []
        self._payload_available = False
        self._loading = False
        self._build_ui()
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        self.status_label = QLabel("Read-only header view. No tensor payloads are loaded.")
        self.status_label.setToolTip("Explorer status: this widget reads headers and emits requests only.")
        root.addWidget(self.status_label)

        self.work_area = QTabWidget()
        self.work_area.setToolTip("Browse Metadata, Tensors, and Embedded Content pages from the inspection header.")
        root.addWidget(self.work_area, 1)
        self.metadata_page = QWidget()
        metadata_page_layout = QVBoxLayout(self.metadata_page)
        metadata_group = QGroupBox("Metadata")
        metadata_group.setToolTip("Searchable metadata from the inspection header; values are safely previewed.")
        metadata_layout = QVBoxLayout(metadata_group)
        self.metadata_search = QLineEdit()
        self.metadata_search.setPlaceholderText("Search metadata keys and values")
        self.metadata_search.setToolTip("Filter metadata rows by key or value.")
        self.metadata_search.textChanged.connect(self._filter_metadata)
        metadata_layout.addWidget(self.metadata_search)
        self.metadata_table = QTableWidget(0, 2)
        self.metadata_table.setHorizontalHeaderLabels(("Key", "Value"))
        meta_header = self.metadata_table.horizontalHeader()
        assert meta_header is not None
        for i in range(1, 2):
            meta_header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self.metadata_table.setColumnWidth(0, 300)
        self.metadata_table.setColumnWidth(1, 2000)
        self.metadata_table.setSortingEnabled(False)
        self.metadata_table.setWordWrap(True)
        self.metadata_table.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
        vertical_header = self.metadata_table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)
        self.metadata_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.metadata_table.itemSelectionChanged.connect(self._metadata_selection_changed)
        self.metadata_table.setToolTip("Read-only compact metadata rows. Select a row for the stored bounded preview.")
        metadata_layout.addWidget(self.metadata_table)
        self.metadata_detail = QTextEdit()
        self.metadata_detail.setReadOnly(True)
        self.metadata_detail.setPlaceholderText("Select a metadata row to view its stored bounded preview.")
        metadata_layout.addWidget(self.metadata_detail, 1)
        metadata_page_layout.addWidget(metadata_group)

        self.tensors_page = QWidget()
        tensor_page_layout = QVBoxLayout(self.tensors_page)
        self.tensor_root_summary = TensorRootSummary()
        tensor_page_layout.addWidget(self.tensor_root_summary)
        tensor_group = QGroupBox("Tensors (header descriptors)")
        tensor_group.setToolTip("Sortable tensor headers only; no tensor payload is loaded by Explorer.")
        tensor_layout = QVBoxLayout(tensor_group)
        tensor_controls = QHBoxLayout()
        self.tensor_search = QLineEdit()
        self.tensor_search.setPlaceholderText("Filter tensor names, shapes, or dtypes")
        self.tensor_search.setToolTip("Filter tensor rows across all logical columns.")
        self.tensor_search.textChanged.connect(self._filter_tensors)
        tensor_controls.addWidget(self.tensor_search, 1)
        self.tensor_bucket_filter = QComboBox()
        self.tensor_bucket_filter.addItem("All buckets", "")
        self.tensor_bucket_filter.setToolTip("Limit tensor rows to one detected bucket.")
        self.tensor_bucket_filter.setMinimumWidth(130)
        self.tensor_bucket_filter.currentIndexChanged.connect(self._filter_tensor_bucket)
        tensor_controls.addWidget(self.tensor_bucket_filter)
        self.tensor_order_combo = QComboBox()
        self.tensor_order_combo.addItem("Sorted", "sorted")
        self.tensor_order_combo.addItem("Original order", "original")
        self.tensor_order_combo.setToolTip("Sorted mode remains sortable; original mode preserves header order and shades shard groups.")
        self.tensor_order_combo.setMinimumWidth(130)
        self.tensor_order_combo.currentIndexChanged.connect(self._render_tensors)
        tensor_controls.addWidget(self.tensor_order_combo)
        tensor_layout.addLayout(tensor_controls)
        self.tensor_model = QStandardItemModel(0, len(TENSOR_COLUMNS), self)
        self.tensor_model.setHorizontalHeaderLabels(list(TENSOR_COLUMNS))
        self.tensor_proxy = _TensorProxy(self)
        self.tensor_proxy.setSourceModel(self.tensor_model)
        self.tensor_table = QTableView()
        self.tensor_table.setModel(self.tensor_proxy)
        self.tensor_table.setSortingEnabled(True)
        tensor_vert_header = self.tensor_table.verticalHeader()
        if tensor_vert_header is not None:
            tensor_vert_header.hide()
        self.tensor_table.sortByColumn(0, Qt.SortOrder.AscendingOrder)
        self.tensor_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tensor_table.setColumnWidth(0, 325) # name
        self.tensor_table.setColumnWidth(1, 120) # shape
        self.tensor_table.setColumnWidth(2, 60) # dtype
        self.tensor_table.setColumnWidth(3, 75) # bucket
        self.tensor_table.setColumnWidth(4, 60) # shard
        self.tensor_table.setColumnWidth(5, 75) # size
        self.tensor_table.setColumnWidth(6, 120) # parameters
        self.tensor_table.setToolTip("Sortable, filterable tensor headers; selecting a row shows a bounded preview.")
        tensor_selection = self.tensor_table.selectionModel()
        if tensor_selection is not None:
            tensor_selection.selectionChanged.connect(self._tensor_selection_changed)
        tensor_layout.addWidget(self.tensor_table, 3)
        self.tensor_detail = QTextEdit()
        self.tensor_detail.setReadOnly(True)
        self.tensor_detail.setPlaceholderText("Select a tensor row to preview its descriptor.")
        self.tensor_detail.setToolTip("Read-only bounded preview of the selected tensor descriptor.")
        tensor_layout.addWidget(self.tensor_detail, 1)
        tensor_page_layout.addWidget(tensor_group)

        self.embedded_page = QWidget()
        embedded_page_layout = QVBoxLayout(self.embedded_page)
        embedded_group = QGroupBox("Embedded content candidates")
        embedded_group.setToolTip("Detected VAE, LoRA, text-encoder, and template candidates from headers and metadata.")
        embedded_layout = QVBoxLayout(embedded_group)
        self.embedded_table = QTableWidget(0, 3)
        self.embedded_table.setHorizontalHeaderLabels(("Type", "Name", "Summary"))
        self.embedded_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.embedded_table.setToolTip("Select a candidate to inspect it or emit a host-handled request.")
        self.embedded_table.setColumnWidth(0, 150)
        self.embedded_table.setColumnWidth(1, 250)
        self.embedded_table.setColumnWidth(2, 500)
        self.embedded_table.itemSelectionChanged.connect(self._embedded_selection_changed)
        embedded_layout.addWidget(self.embedded_table, 2)
        self.embedded_detail = QTextEdit()
        self.embedded_detail.setReadOnly(True)
        self.embedded_detail.setPlaceholderText("No embedded candidates detected.")
        self.embedded_detail.setToolTip("Details for the selected embedded-content candidate.")
        embedded_layout.addWidget(self.embedded_detail, 1)
        actions = QHBoxLayout()
        self.inspect_button = QPushButton("Inspect")
        self.inspect_button.setToolTip("Open readable embedded metadata; tensor payloads are never read.")
        self.inspect_button.clicked.connect(lambda: self._emit_candidate(self.inspect_requested, "inspect"))
        self.export_button = QPushButton("Save readable artifact")
        self.export_button.setToolTip("Save readable text or JSON for the selected embedded metadata.")
        self.export_button.clicked.connect(lambda: self._emit_candidate(self.export_requested, "save"))
        self.extract_button = QPushButton("Extract raw original bytes")
        self.extract_button.setToolTip("Save exact source JSON bytes only when the selected metadata is locatable.")
        self.extract_button.clicked.connect(lambda: self._emit_candidate(self.extraction_requested, "extract"))
        for button in (self.inspect_button, self.export_button, self.extract_button):
            button.setEnabled(False)
            actions.addWidget(button)
        actions.addStretch()
        embedded_layout.addLayout(actions)
        embedded_page_layout.addWidget(embedded_group)
        self.work_area.addTab(self.metadata_page, "Metadata")
        self.work_area.addTab(self.tensors_page, "Tensors")
        self.work_area.addTab(self.embedded_page, "Embedded Content")

    def detach_pages(self) -> list[tuple[str, QWidget]]:
        """Transfer Explorer's existing read-only pages into a host tab bar."""
        pages: list[tuple[str, QWidget]] = []
        while self.work_area.count():
            title = self.work_area.tabText(0)
            page = self.work_area.widget(0)
            self.work_area.removeTab(0)
            if page is not None:
                pages.append((title, page))
        self.status_label.setVisible(False)
        self.work_area.setVisible(False)
        return pages

    def set_inspection(self, inspection: Mapping[str, Any] | None, tensor_data: Any = None, *, payload_available: bool | None = None) -> None:
        """Display an inspection result and optional header tensor descriptors."""
        self._loading = False
        self._inspection = dict(inspection or {})
        if tensor_data is None:
            for key in ("tensor_info", "tensors", "tensor_data", "descriptors", "headers"):
                if key in self._inspection:
                    tensor_data = self._inspection[key]
                    break
        if payload_available is None:
            payload_available = bool(self._inspection.get("payload_available", False))
        self._payload_available = bool(payload_available)
        metadata: dict[str, Any] = {}
        if isinstance(self._inspection.get("metadata"), Mapping):
            metadata.update(self._inspection["metadata"])
        if isinstance(self._inspection.get("extra"), Mapping):
            metadata.update({f"extra.{key}": value for key, value in self._inspection["extra"].items()})
        for key in ("architecture", "model_type", "format", "quantization", "tensor_count", "total_params", "precision_summary"):
            if key in self._inspection:
                metadata[f"inspection.{key}"] = self._inspection[key]
        for key in ("sidecar_roles", "sidecar_paths", "sidecar_identities", "sidecars", "sidecar_records", "sidecar_inspections"):
            if key in self._inspection:
                metadata[f"associated_sidecars.{key}"] = self._inspection[key]
        self._metadata_rows = flatten_metadata(metadata)
        self._render_metadata()
        self.set_tensor_data(
            tensor_data if tensor_data is not None else {},
            original_tensor_order=self._inspection.get("original_tensor_order"),
            sorted_tensor_order=self._inspection.get("sorted_tensor_order"),
        )
        self._embedded_candidates = detect_embedded_content(self._inspection, self._records)
        self._render_embedded()
        self._update_status()

    def set_loading(self, loading: bool) -> None:
        """Show whether a header-only tensor descriptor read is in progress."""
        self._loading = bool(loading)
        self._update_status()

    def set_tensor_data(
        self,
        tensor_data: Any,
        *,
        payload_available: bool | None = None,
        original_tensor_order: Any = None,
        sorted_tensor_order: Any = None,
    ) -> None:
        """Replace displayed tensor headers; this never reads tensor payloads."""
        if payload_available is not None:
            self._payload_available = bool(payload_available)
        self._all_records = normalize_tensor_descriptors(tensor_data)
        self.tensor_root_summary.set_tensor_names(
            record.get("name", "") for record in self._all_records
        )
        original_positions = self._order_positions(original_tensor_order)
        sorted_positions = self._order_positions(sorted_tensor_order)
        shard_positions: dict[int, int] = {}
        for index, record in enumerate(self._all_records):
            record["original_index"] = record["original_index"] if record["original_index"] is not None else original_positions.get(record["name"], index)
            record["sorted_index"] = sorted_positions.get(record["name"], index)
            record["source_index"] = index
            record["shard_source_index"] = shard_positions.setdefault(int(record["shard_id"]), len(shard_positions))
        buckets = sorted({str(record["component_bucket"]) for record in self._all_records if record.get("component_bucket")})
        self.tensor_bucket_filter.blockSignals(True)
        self.tensor_bucket_filter.clear()
        self.tensor_bucket_filter.addItem("All buckets", "")
        for bucket in buckets:
            self.tensor_bucket_filter.addItem(bucket, bucket)
        self.tensor_bucket_filter.blockSignals(False)
        self._render_tensors()
        self._embedded_candidates = detect_embedded_content(self._inspection, self._records)
        self._render_embedded()
        self._update_status()

    @staticmethod
    def _order_positions(order: Any) -> dict[str, int]:
        if not isinstance(order, (list, tuple)):
            return {}
        return {str(name): index for index, name in enumerate(order)}

    def _render_tensors(self, *_args: Any) -> None:
        original_mode = self.tensor_order_combo.currentData() == "original"
        if original_mode:
            self._records = sorted(self._all_records, key=lambda row: (int(row["shard_source_index"]), int(row["original_index"]), int(row["source_index"])))
        else:
            self._records = sorted(self._all_records, key=lambda row: (int(row["sorted_index"]), natural_name_key(row["name"])))
        self.tensor_table.setSortingEnabled(not original_mode)
        self.tensor_model.removeRows(0, self.tensor_model.rowCount())
        for record in self._records:
            values = (
                record["name"],
                safe_display(list(record["shape"]), 240) if record["shape"] else "-",
                record["dtype"],
                bucket_label(record["component_bucket"]),
                "None" if record["shard_id"] == 0 else f"Shard {record['shard_id']}",
                friendly_bytes(record["n_bytes"]),
                display_count(record["parameter_count"]),
            )
            items = [QStandardItem(str(value)) for value in values]
            for index, item in enumerate(items):
                sort_value = record["parameter_count"] if index == 6 else record["n_bytes"] if index == 5 else record["shard_id"] if index == 4 else values[index]
                item.setData(sort_value, Qt.ItemDataRole.UserRole)
                item.setData(record["shard_id"], Qt.ItemDataRole.UserRole + 1)
                item.setData(record["component_bucket"], Qt.ItemDataRole.UserRole + 2)
                raw_bytes = record["n_bytes"]
                size_detail = "Raw bytes: unavailable" if raw_bytes is None else f"Raw bytes: {raw_bytes:,} bytes; display: {friendly_bytes(raw_bytes)}"
                item.setToolTip(f"{size_detail}. Header-derived value; payload is not loaded.")
                if original_mode:
                    item.setBackground(QColor("#25303b") if record["shard_id"] % 2 else QColor("#202a34"))
            self.tensor_model.appendRow(items)
        self.tensor_proxy.invalidateFilter()

    def clear(self) -> None:
        """Clear all displayed inspection, header, and candidate state."""
        self._inspection = {}
        self._records = []
        self._all_records = []
        self._metadata_rows = []
        self._embedded_candidates = []
        self._payload_available = False
        self._loading = False
        self.metadata_search.clear()
        self.tensor_search.clear()
        self._render_metadata()
        self.tensor_model.removeRows(0, self.tensor_model.rowCount())
        self.tensor_bucket_filter.blockSignals(True)
        self.tensor_bucket_filter.clear()
        self.tensor_bucket_filter.addItem("All buckets", "")
        self.tensor_bucket_filter.blockSignals(False)
        self.tensor_proxy.set_bucket("")
        self.tensor_root_summary.clear()
        self._render_embedded()
        self.tensor_detail.clear()
        self._update_status()

    def _render_metadata(self) -> None:
        self.metadata_detail.clear()
        self.metadata_table.setSortingEnabled(False)
        self.metadata_table.setRowCount(len(self._metadata_rows))
        for row_index, row in enumerate(self._metadata_rows):
            for column, key in enumerate(("key", "value")):
                item = QTableWidgetItem(str(row[key]))
                item.setToolTip("Stored bounded metadata preview; no full source value is loaded.")
                self.metadata_table.setItem(row_index, column, item)
        self.metadata_table.setSortingEnabled(True)
        self._filter_metadata(self.metadata_search.text())

    def _metadata_selection_changed(self) -> None:
        selection_model = self.metadata_table.selectionModel()
        rows = selection_model.selectedRows() if selection_model is not None else []
        if not rows:
            self.metadata_detail.clear()
            return
        row = rows[0].row()
        if not 0 <= row < len(self._metadata_rows):
            self.metadata_detail.clear()
            return
        value = self._metadata_rows[row].get("raw", self._metadata_rows[row].get("value"))
        self.metadata_detail.setPlainText(_inspect_text({"value": value}))

    def _filter_metadata(self, text: str) -> None:
        needle = text.casefold().strip()
        for row in range(self.metadata_table.rowCount()):
            key = self.metadata_table.item(row, 0)
            value = self.metadata_table.item(row, 1)
            haystack = f"{key.text() if key else ''} {value.text() if value else ''}".casefold()
            self.metadata_table.setRowHidden(row, bool(needle and needle not in haystack))

    def _filter_tensors(self, text: str) -> None:
        self.tensor_proxy.setFilterRegularExpression(QRegularExpression(re.escape(text)))

    def _filter_tensor_bucket(self, index: int) -> None:
        self.tensor_proxy.set_bucket(str(self.tensor_bucket_filter.itemData(index) or ""))

    def _tensor_selection_changed(self, selected, _deselected) -> None:
        if not selected.indexes():
            self.tensor_detail.clear()
            return
        source_index = self.tensor_proxy.mapToSource(selected.indexes()[0])
        row = source_index.row()
        if 0 <= row < len(self._records):
            record = self._records[row]
            self.tensor_detail.setPlainText(safe_display(record))
            self.tensor_selected.emit(dict(record))

    def _render_embedded(self) -> None:
        self.embedded_table.setRowCount(len(self._embedded_candidates))
        for row, candidate in enumerate(self._embedded_candidates):
            for column, key in enumerate(("kind", "name", "summary")):
                item = QTableWidgetItem(str(candidate.get(key, "")))
                item.setToolTip("Detected from headers or metadata; selecting it does not read payloads.")
                self.embedded_table.setItem(row, column, item)
        enabled = bool(self._embedded_candidates)
        self.inspect_button.setEnabled(enabled)
        self.export_button.setEnabled(enabled)
        self.extract_button.setEnabled(False)
        self.embedded_detail.clear()
        if enabled:
            self.embedded_table.selectRow(0)

    def _embedded_selection_changed(self) -> None:
        selection_model = self.embedded_table.selectionModel()
        rows = selection_model.selectedRows() if selection_model is not None else []
        if rows:
            row = rows[0].row()
            if 0 <= row < len(self._embedded_candidates):
                candidate = self._embedded_candidates[row]
                self.embedded_detail.setPlainText(safe_display(candidate.get("value")))
                available, message = raw_metadata_status(self._inspection, candidate)
                self.extract_button.setEnabled(available)
                self.extract_button.setToolTip(message)

    def _selected_candidate(self) -> dict[str, Any] | None:
        selection_model = self.embedded_table.selectionModel()
        rows = selection_model.selectedRows() if selection_model is not None else []
        if not rows and self._embedded_candidates:
            return self._embedded_candidates[0]
        row = rows[0].row() if rows else -1
        return self._embedded_candidates[row] if 0 <= row < len(self._embedded_candidates) else None

    def _emit_candidate(self, signal, action: str) -> None:
        candidate = self._selected_candidate()
        if candidate is not None:
            signal.emit({
                "candidate": dict(candidate),
                "inspection": dict(self._inspection),
                "read_only": True,
                "payload_available": self._payload_available,
            })
            if getattr(self, "dump_json_modelinfo", False):
                feedback = perform_metadata_action(
                    self, self._inspection, candidate, action, dump_json_modelinfo=True
                )
            else:
                feedback = perform_metadata_action(self, self._inspection, candidate, action)
            if feedback:
                self.embedded_detail.setPlainText(feedback)

    def _update_status(self) -> None:
        if self._loading:
            self.status_label.setText("Read-only header view. Loading tensor descriptors...")
        elif not self._inspection and not self._records:
            self.status_label.setText("Read-only header view. No inspection loaded.")
        elif self._payload_available:
            self.status_label.setText("Read-only header view. Host supplied a payload source; requests still emit signals only.")
        else:
            self.status_label.setText("Read-only header view. Tensor payloads are not loaded; extraction requires a host-provided source.")

    def refresh_theme(self, theme_colors: Mapping[str, str] | None = None) -> None:
        """Refresh Explorer's cached status/detail styling after a theme change."""
        if theme_colors is None:
            from back.theme_loader import get_global_theme_colors

            theme_colors = get_global_theme_colors()
        self.status_label.setStyleSheet(
            "color: %(muted)s; font-size: 11px;" % dict(theme_colors)
        )
        self.tensor_detail.setStyleSheet(
            "background-color: %(background)s; color: %(text)s;" % dict(theme_colors)
        )
