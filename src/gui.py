#!/usr/bin/env python3
"""
Model Inspector PyQt6 GUI
Dark-mode interface with drag-and-drop, card view, and data table view.
"""

import sys
import os
import json
from time import perf_counter
from pathlib import Path

# for dismissing the Windows exe splash screen
try:
    import pyi_splash  # type: ignore
except ImportError:
    pyi_splash = None

# Suppress Qt DPI awareness warning on Windows
os.environ.setdefault("QT_LOGGING_RULES", "qt.qpa.window=false")

from PyQt6.QtCore import Qt, pyqtSignal, QMimeData, QTimer, QSettings, QEvent
from PyQt6.QtGui import (
    QContextMenuEvent,
    QDragEnterEvent,
    QDropEvent,
    # QFont,
    QKeyEvent,
    QKeySequence,
    QMouseEvent,
    QAction,
    QShortcut,
    QIcon,
    QClipboard,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMainWindow,
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QFileDialog,
    QTabWidget,
    QScrollArea,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFrame,
    QGridLayout,
    QSizePolicy,
    QProgressBar,
    QAbstractItemView,
    QTextEdit,
    QComboBox,
    QCheckBox,
    QToolButton,
    QMenu,
    QWidgetAction,
    QDialog,
    QDialogButtonBox,
    # QTableWidgetSelectionRange,
    QGroupBox,
    QMessageBox,
)

from inspect_model import (
    format_params,
    format_size,
    generate_modelinfo_dump,
    write_modelinfo_dump,
    write_modelinfo_json,
)
from model_readers import (
    CHECKPOINT_FORMAT_WARNING,
    SUPPORTED_MODEL_EXTENSIONS,
    is_checkpoint_model_path,
    is_supported_model_path,
)
from model_cache import (
    clear_inspection_cache,
    get_cached_inspection_summary_snapshots,
    get_cached_raw_dump,
    list_cached_inspection_paths,
    store_raw_dump,
    store_directory_scan,
)
from app_paths import settings_path
from background_tasks import (
    AnalysisWorker,
    DiscoveryWorker,
)
from back.inspection_summary import compact_inspection_summary
from front.scan_projection import ProjectionEvent, ScanProjectionBuffer

MODEL_FORMAT_FILTERS = (".safetensors", ".gguf", ".ckpt", ".onnx", ".pt", ".pth")


def _clipboard() -> QClipboard:
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    return clipboard


def _combo_data_str(value) -> str | None:
    return str(value) if value else None


def _model_file_filter() -> str:
    patterns = " ".join(f"*{ext}" for ext in SUPPORTED_MODEL_EXTENSIONS)
    checkpoint_patterns = " ".join(
        f"*{ext}"
        for ext in MODEL_FORMAT_FILTERS
        if ext not in SUPPORTED_MODEL_EXTENSIONS
    )
    return (
        f"Supported Model Files ({patterns});;"
        f"Checkpoint Files - unsafe/unsupported ({checkpoint_patterns});;"
        "All Files (*)"
    )


def _settings() -> QSettings:
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return QSettings(str(path), QSettings.Format.IniFormat)


def _asset(name: str) -> str:
    """Resolve path to a bundled asset; works both in dev and when frozen by PyInstaller."""
    base = Path(getattr(sys, "_MEIPASS", Path(Path(__file__).parent).parent))
    return str(base / "assets" / name)


# ---------------------------------------------------------------------------
# Dark theme stylesheet
# ---------------------------------------------------------------------------

DARK_STYLE = """
QMainWindow, QWidget {
    background-color: #1e1e2e;
    color: #cdd6f4;
    font-family: "Segoe UI", "Consolas", sans-serif;
    font-size: 13px;
}

QTabWidget::pane {
    border: 1px solid #45475a;
    background-color: #1e1e2e;
    border-radius: 4px;
}
QTabBar::tab {
    background-color: #313244;
    color: #cdd6f4;
    padding: 8px 24px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    min-width: 100px;
}
QTabBar::tab:selected {
    background-color: #45475a;
    color: #f5c2e7;
    font-weight: bold;
}
QTabBar::tab:hover:!selected {
    background-color: #3b3b52;
}

QPushButton {
    background-color: #45475a;
    color: #cdd6f4;
    border: 1px solid #585b70;
    padding: 8px 10px;
    border-radius: 6px;
    font-weight: bold;
}
QPushButton:hover {
    background-color: #585b70;
    border-color: #f5c2e7;
}
QPushButton:pressed {
    background-color: #6c7086;
}
QPushButton#analyzeBtn {
    background-color: #74c7ec;
    color: #1e1e2e;
    border: none;
}
QPushButton#analyzeBtn:hover {
    background-color: #89dceb;
}
QPushButton#clearBtn {
    background-color: #f38ba8;
    color: #1e1e2e;
    border: none;
}
QPushButton#clearBtn:hover {
    background-color: #f5a8be;
}
QToolButton#openBtn {
    background-color: #45475a;
    padding: 0px 10px;
    min-height: 31px;
    max-height: 31px;
    color: #cdd6f4;
    border: 1px solid #585b70;
    border-radius: 6px;
    font-weight: bold;
}
QToolButton#openBtn:hover {
    background-color: #585b70;
    border-color: #f5c2e7;
}
QToolButton#openBtn:pressed {
    background-color: #6c7086;
}
QTableWidget {
    background-color: #181825;
    alternate-background-color: #1e1e2e;
    gridline-color: #313244;
    border: 1px solid #45475a;
    border-radius: 4px;
    selection-background-color: #45475a;
}
QTableWidget::item {
    padding: 3px;
}
QHeaderView::section {
    background-color: #313244;
    color: #f5c2e7;
    padding: 8px;
    border: none;
    border-right: 1px solid #45475a;
    border-bottom: 1px solid #45475a;
    font-weight: bold;
}

QScrollArea {
    border: none;
}
QScrollBar:vertical {
    background-color: #181825;
    width: 10px;
    border-radius: 5px;
}
QScrollBar::handle:vertical {
    background-color: #45475a;
    border-radius: 5px;
    min-height: 30px;
}
QScrollBar::handle:vertical:hover {
    background-color: #585b70;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0;
}

QProgressBar {
    background-color: #313244;
    border: none;
    border-radius: 4px;
    height: 6px;
    text-align: center;
}
QProgressBar::chunk {
    background-color: #74c7ec;
    border-radius: 4px;
}
"""


# ---------------------------------------------------------------------------
# Settings dialog
# ---------------------------------------------------------------------------


class SettingsDialog(QDialog):
    def __init__(
        self,
        parent=None,
        allow_filename_alias_detection=False,
        auto_analyze_on_add=True,
        dump_json_modelinfo=False,
        auto_load_raw_dump=False,
        load_default_libraries_on_startup=False,
        cache_full_data_on_analyze=False,
        analysis_threads=2,
        add_mode="replace",
        default_tab="cards",
        card_fields=None,
        simple_card_fields=None,
        table_column_visibility=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        self.setMinimumWidth(840)
        self.setMinimumHeight(460)

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Display Settings")
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f5c2e7;")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        general_tab = QWidget()
        general_tab_layout = QVBoxLayout(general_tab)
        general_tab_layout.setContentsMargins(0, 0, 0, 0)
        general_tab_layout.setSpacing(10)

        general_group = QGroupBox("General")
        g_layout = QGridLayout(general_group)
        g_layout.setHorizontalSpacing(14)
        g_layout.setVerticalSpacing(14)

        def make_general_cell(widget, desc):
            cell = QWidget()
            v = QVBoxLayout(cell)
            v.setContentsMargins(0, 6, 0, 0)
            v.setSpacing(3)
            v.addWidget(widget)
            d = QLabel(desc)
            d.setWordWrap(True)
            d.setStyleSheet("color: #a6adc8; font-size: 11px;")
            v.addWidget(d)
            return cell

        self.alias_checkbox = QCheckBox("Filename Alias Detection")
        self.alias_checkbox.setChecked(allow_filename_alias_detection)
        alias_cell = make_general_cell(
            self.alias_checkbox,
            "Fallback alias matching by filename for special naming cases. Supports ILXL, Illustrious, Illu, PDXL, Pony, Pony7, NAI, and Qwen Edit.",
        )

        self.auto_analyze_checkbox = QCheckBox("Auto-analyze when files are added")
        self.auto_analyze_checkbox.setChecked(auto_analyze_on_add)
        analyze_cell = make_general_cell(
            self.auto_analyze_checkbox,
            "Immediately start analysis after dropping or browsing files.",
        )

        self.dump_json_checkbox = QCheckBox("Also dump JSON .modelinfo")
        self.dump_json_checkbox.setChecked(dump_json_modelinfo)
        dump_json_cell = make_general_cell(
            self.dump_json_checkbox,
            "When dumping modelinfo, also write a pretty-printed .modelinfo.json file.",
        )

        self.auto_load_raw_checkbox = QCheckBox("Auto-load Raw full dump")
        self.auto_load_raw_checkbox.setChecked(auto_load_raw_dump)
        raw_cell = make_general_cell(
            self.auto_load_raw_checkbox,
            "Automatically generate and cache the full Raw tab dump when the selected model changes.",
        )

        self.cache_full_data_checkbox = QCheckBox(
            "Cache full tensor data during analysis"
        )
        self.cache_full_data_checkbox.setChecked(cache_full_data_on_analyze)
        cache_full_data_cell = make_general_cell(
            self.cache_full_data_checkbox,
            "Store compact metadata and tensor descriptors while scanning so details remain available without the model file.",
        )

        self.default_libraries_checkbox = QCheckBox("Load default libraries on startup")
        self.default_libraries_checkbox.setChecked(load_default_libraries_on_startup)
        default_libraries_cell = make_general_cell(
            self.default_libraries_checkbox,
            "Load cached model summaries and cached folder scans when the app starts.",
        )

        thread_wrap = QWidget()
        thread_row = QHBoxLayout(thread_wrap)
        thread_row.setContentsMargins(0, 0, 0, 0)
        thread_row.setSpacing(6)
        thread_row.addWidget(QLabel("Analysis threads:"))
        self.analysis_threads_combo = QComboBox()
        for value in (1, 2, 4, 8):
            self.analysis_threads_combo.addItem(str(value), value)
        idx = self.analysis_threads_combo.findData(int(analysis_threads or 1))
        if idx >= 0:
            self.analysis_threads_combo.setCurrentIndex(idx)
        thread_row.addWidget(self.analysis_threads_combo)
        thread_row.addStretch()
        thread_cell = make_general_cell(
            thread_wrap,
            "Use bounded worker threads for independent file reads. Keep at 1 if the disk is already busy.",
        )

        mode_wrap = QWidget()
        mode_row = QHBoxLayout(mode_wrap)
        mode_row.setContentsMargins(0, 0, 0, 0)
        mode_row.setSpacing(6)
        mode_row.addWidget(QLabel("File add behavior:"))
        self.add_mode_combo = QComboBox()
        self.add_mode_combo.addItem("Replace current model queue", "replace")
        self.add_mode_combo.addItem("Append to current model queue", "additive")
        idx = self.add_mode_combo.findData(add_mode)
        if idx >= 0:
            self.add_mode_combo.setCurrentIndex(idx)
        mode_row.addWidget(self.add_mode_combo)
        mode_row.addStretch()
        mode_cell = make_general_cell(
            mode_wrap,
            "Replace clears the current model queue before adding new files. Append keeps existing files and adds new ones.",
        )

        tab_wrap = QWidget()
        tab_row = QHBoxLayout(tab_wrap)
        tab_row.setContentsMargins(0, 0, 0, 0)
        tab_row.setSpacing(6)
        tab_row.addWidget(QLabel("Default tab:"))
        self.default_tab_combo = QComboBox()
        self.default_tab_combo.addItem("Cards", "cards")
        self.default_tab_combo.addItem("Data", "data")
        self.default_tab_combo.addItem("Raw", "raw")
        idx = self.default_tab_combo.findData(default_tab)
        if idx >= 0:
            self.default_tab_combo.setCurrentIndex(idx)
        tab_row.addWidget(self.default_tab_combo)
        tab_row.addStretch()
        tab_cell = make_general_cell(
            tab_wrap, "Choose which tab opens by default when the app starts."
        )

        g_layout.addWidget(alias_cell, 0, 0)
        g_layout.addWidget(analyze_cell, 0, 1)
        g_layout.addWidget(mode_cell, 1, 0)
        g_layout.addWidget(tab_cell, 1, 1)
        g_layout.addWidget(dump_json_cell, 1, 2)
        g_layout.addWidget(raw_cell, 2, 0)
        g_layout.addWidget(default_libraries_cell, 2, 1)
        g_layout.addWidget(thread_cell, 2, 2)
        g_layout.addWidget(cache_full_data_cell, 3, 0)
        general_tab_layout.addWidget(general_group)

        cache_group = QGroupBox("Cache")
        cache_layout = QHBoxLayout(cache_group)
        cache_layout.setSpacing(10)
        cache_note = QLabel("Clear parsed model summaries and cached tensor data.")
        cache_note.setStyleSheet("color: #a6adc8; font-size: 11px;")
        cache_layout.addWidget(cache_note, 1)
        self.clear_cache_btn = QPushButton("Clear Cache")
        cache_layout.addWidget(self.clear_cache_btn)
        general_tab_layout.addWidget(cache_group)
        general_tab_layout.addStretch()
        tabs.addTab(general_tab, "General")

        cards_tab = QWidget()
        cards_tab_layout = QVBoxLayout(cards_tab)
        cards_tab_layout.setContentsMargins(0, 0, 0, 0)
        cards_tab_layout.setSpacing(10)
        cards_row = QHBoxLayout()
        cards_row.setSpacing(10)

        simple_group = QGroupBox("Simple Cards")
        s_layout = QVBoxLayout(simple_group)
        self.simple_card_field_checks = {}
        simple_card_fields = simple_card_fields or {}
        simple_field_labels = {
            "parameters": "Show Parameters",
            "precision": "Show Precision",
            "file_size": "Show File Size",
            "tensors": "Show Tensor Count",
            "lora_rank": "Show LoRA Rank",
            "extra_meta": "Show Extra Metadata",
            "training_meta": "Show Training Metadata",
        }
        for key, label in simple_field_labels.items():
            cb = QCheckBox(label)
            cb.setChecked(bool(simple_card_fields.get(key, False)))
            self.simple_card_field_checks[key] = cb
            s_layout.addWidget(cb)
        s_layout.addStretch()
        cards_row.addWidget(simple_group, 1)

        detailed_group = QGroupBox("Detailed Cards")
        d_layout = QVBoxLayout(detailed_group)
        self.card_field_checks = {}
        card_fields = card_fields or {}
        card_field_labels = {
            "parameters": "Show Parameters",
            "file_size": "Show File Size",
            "precision": "Show Precision",
            "tensors": "Show Tensor Count",
            "lora_rank": "Show LoRA Rank",
            "extra_meta": "Show Extra Metadata",
            "training_meta": "Show Training Metadata",
        }
        for key, label in card_field_labels.items():
            cb = QCheckBox(label)
            cb.setChecked(bool(card_fields.get(key, True)))
            self.card_field_checks[key] = cb
            d_layout.addWidget(cb)
        d_layout.addStretch()
        cards_row.addWidget(detailed_group, 1)
        cards_tab_layout.addLayout(cards_row)
        cards_tab_layout.addStretch()
        tabs.addTab(cards_tab, "Cards")

        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(0, 0, 0, 0)
        data_tab_layout.setSpacing(10)
        data_group = QGroupBox("Data Columns")
        data_layout = QGridLayout(data_group)
        data_layout.setHorizontalSpacing(18)
        data_layout.setVerticalSpacing(4)
        self.table_column_checks = {}
        entries = list((table_column_visibility or {}).items())
        cols_count = 3
        rows_count = (len(entries) + cols_count - 1) // cols_count if entries else 0
        for idx, (col_name, visible) in enumerate(entries):
            cb = QCheckBox(col_name)
            cb.setChecked(bool(visible))
            self.table_column_checks[col_name] = cb
            row = idx % rows_count if rows_count else 0
            col = idx // rows_count if rows_count else 0
            data_layout.addWidget(cb, row, col)
        data_tab_layout.addWidget(data_group)
        data_tab_layout.addStretch()
        tabs.addTab(data_tab, "Data Columns")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)


# ---------------------------------------------------------------------------
# Architecture filter button
# ---------------------------------------------------------------------------


class CheckFilterButton(QToolButton):
    filter_changed = pyqtSignal(object)

    def __init__(self, label: str):
        super().__init__()
        self._label = label
        self.setText(f"{self._label}: All")
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self._menu = QMenu(self)
        self.setMenu(self._menu)

        self._all_cb = QCheckBox("Select All")
        self._all_cb.setChecked(True)
        self._all_cb.stateChanged.connect(self._toggle_all)
        all_action = QWidgetAction(self)
        all_action.setDefaultWidget(self._all_cb)
        self._menu.addAction(all_action)

        self._arch_checks: dict[str, QCheckBox] = {}
        self._counts: dict[str, int] = {}
        self._active: set[str] = set()
        self._item_actions: list[QWidgetAction | QAction] = []

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
        for action in self._item_actions:
            if isinstance(action, QWidgetAction):
                widget = action.defaultWidget()
                action.setDefaultWidget(None)
                if widget is not None:
                    widget.deleteLater()
            self._menu.removeAction(action)
        self._item_actions.clear()

    def _filter_sort_key(self, value: str):
        if value == "ERROR":
            return (0, "")
        if value == "Unknown":
            return (1, "")
        return (2, value.lower())

    def _rebuild_item_actions(self):
        checked_state = {arch: cb.isChecked() for arch, cb in self._arch_checks.items()}
        self._clear_item_actions()
        self._arch_checks.clear()
        ordered = sorted(self._counts.keys(), key=self._filter_sort_key)
        inserted_divider = False
        for arch in ordered:
            if (
                not inserted_divider
                and arch != "ERROR"
                and "ERROR" in self._arch_checks
            ):
                sep = self._menu.addSeparator()
                if sep is not None:
                    self._item_actions.append(sep)
                inserted_divider = True
            checked = checked_state.get(arch, arch in self._active)
            cb = QCheckBox(f"{arch} ({self._counts.get(arch, 0)})")
            cb.setChecked(checked)
            cb.stateChanged.connect(self._on_arch_toggled)
            self._arch_checks[arch] = cb
            act = QWidgetAction(self)
            act.setDefaultWidget(cb)
            self._menu.addAction(act)
            self._item_actions.append(act)

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


class SortableTableWidgetItem(QTableWidgetItem):
    def __lt__(self, other):
        left = self.data(Qt.ItemDataRole.UserRole)
        right = other.data(Qt.ItemDataRole.UserRole)
        if isinstance(left, (int, float)) or isinstance(right, (int, float)):
            return (left or 0) < (right or 0)
        return super().__lt__(other)


# ---------------------------------------------------------------------------
# Model card widget
# ---------------------------------------------------------------------------


class ModelCard(QFrame):
    selection_requested = pyqtSignal(str, object)
    checkbox_toggled = pyqtSignal(str, bool)
    drag_over_requested = pyqtSignal(str)
    context_requested = pyqtSignal(str, bool, object)

    def __init__(self, data: dict, simple_view=False, card_fields=None):
        super().__init__()
        self.data = data
        self.filepath = data.get("filepath", "")
        self._selected = False
        self._filter_visible = True
        self._simple_view = bool(simple_view)
        self._card_fields = card_fields or {}
        precision_text = (
            data.get("precision_display")
            or data.get("component_precision_summary")
            or data.get("precision_summary", "-")
        )
        component_precisions = data.get("component_precisions") or {}
        component_precision_labels = [
            ("unet", "UNet Precision"),
            ("transformer", "Transformer Precision"),
            ("vae", "VAE Precision"),
            ("text_encoder", "Text Encoder Precision"),
            ("text_encoder_2", "Text Encoder 2 Precision"),
        ]
        self.setStyleSheet("""
            ModelCard {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 10px;
            }
            ModelCard:hover {
                border-color: #74c7ec;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Filename header
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.select_cb = QCheckBox()
        self.select_cb.setToolTip("Select model")
        self.select_cb.clicked.connect(self._on_checkbox_clicked)
        header_row.addWidget(self.select_cb)

        name_label = QLabel(data["filename"])
        name_label.setWordWrap(True)
        name_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #f5c2e7; background: transparent; border: none;"
        )
        header_row.addWidget(name_label, stretch=1)
        layout.addLayout(header_row)

        # Architecture + model type row
        arch_row = QHBoxLayout()
        file_format = data.get("format")
        if file_format:
            arch_row.addWidget(
                self._make_tag(str(file_format).upper(), "#f38ba8", "#1e1e2e")
            )
        arch_tag = self._make_tag(data["architecture"], "#74c7ec", "#1e1e2e")
        type_tag = self._make_tag(data["model_type"], "#a6e3a1", "#1e1e2e")
        arch_row.addWidget(arch_tag)
        arch_row.addWidget(type_tag)
        quantization = data.get("quantization")
        if quantization:
            arch_row.addWidget(self._make_tag(str(quantization), "#cba6f7", "#1e1e2e"))
        adapter_type = data.get("adapter_type")
        if adapter_type:
            arch_row.addWidget(self._make_tag(adapter_type, "#f9e2af", "#1e1e2e"))
        if data.get("is_moe"):
            expert_count = data.get("expert_count")
            expert_used_count = data.get("expert_used_count")
            moe_label = "MoE"
            if expert_count:
                moe_label += f" {expert_count}"
                if expert_used_count:
                    moe_label += f"/{expert_used_count}"
            arch_row.addWidget(self._make_tag(moe_label, "#fab387", "#1e1e2e"))

        # Component tags at top
        comp_colors = {
            "unet": ("#fab387", "#1e1e2e"),
            "transformer": ("#fab387", "#1e1e2e"),
            "vae": ("#cba6f7", "#1e1e2e"),
            "text_encoder": ("#94e2d5", "#1e1e2e"),
            "text_encoder_2": ("#89dceb", "#1e1e2e"),
        }
        comp_labels = {
            "unet": "UNet",
            "transformer": "Transformer",
            "vae": "VAE",
            "text_encoder": "Text Enc",
            "text_encoder_2": "Text Enc 2",
        }
        for key, label in comp_labels.items():
            if data["components"].get(key):
                fg, bg = comp_colors.get(key, ("#cdd6f4", "#1e1e2e"))
                arch_row.addWidget(self._make_tag(label, fg, bg))

        for enc_name in data.get("named_text_encoders", {}):
            arch_row.addWidget(self._make_tag(enc_name, "#94e2d5", "#1e1e2e"))
        arch_row.addStretch()
        layout.addLayout(arch_row)

        if self._simple_view:
            simple_stats = []
            if self._card_fields.get("parameters", True):
                simple_stats.append(("Parameters", data["total_params_friendly"]))
            if self._card_fields.get("precision", True):
                added_component_precision = False
                for comp_key, comp_label in component_precision_labels:
                    comp_precision = component_precisions.get(comp_key)
                    if not comp_precision:
                        continue
                    simple_stats.append((comp_label, comp_precision))
                    added_component_precision = True
                if not added_component_precision:
                    simple_stats.append(("Precision", precision_text))
            if self._card_fields.get("file_size", False):
                simple_stats.append(("File Size", data["file_size_friendly"]))
            if self._card_fields.get("tensors", False):
                simple_stats.append(("Tensors", str(data["tensor_count"])))
            lora_rank = data.get("lora_rank")
            if lora_rank and self._card_fields.get("lora_rank", False):
                simple_stats.append(("LoRA Rank", str(lora_rank)))
            if self._card_fields.get("extra_meta", False):
                for key, val in data.get("extra", {}).items():
                    simple_stats.append((key.replace("_", " ").title(), str(val)))
            if self._card_fields.get("training_meta", False):
                for key, val in data.get("training_meta", {}).items():
                    simple_stats.append((key.replace("_", " ").title(), str(val)))

            if simple_stats:
                mini_grid = QGridLayout()
                mini_grid.setSpacing(6)
                for i, (label, value) in enumerate(simple_stats):
                    lbl = QLabel(label)
                    lbl.setStyleSheet(
                        "color: #6c7086; font-size: 11px; background: transparent; border: none;"
                    )
                    val = QLabel(value)
                    if "Precision" in label:
                        val.setWordWrap(True)
                    val.setStyleSheet(
                        "color: #cdd6f4; font-size: 13px; font-weight: bold; background: transparent; border: none;"
                    )
                    mini_grid.addWidget(lbl, i // 2, (i % 2) * 2)
                    mini_grid.addWidget(val, i // 2, (i % 2) * 2 + 1)
                layout.addLayout(mini_grid)
            return

        # Stats grid
        grid = QGridLayout()
        grid.setSpacing(6)

        stats = []
        if self._card_fields.get("parameters", True):
            stats.append(("Parameters", data["total_params_friendly"]))
        if self._card_fields.get("file_size", True):
            stats.append(("File Size", data["file_size_friendly"]))
        if self._card_fields.get("precision", True):
            added_component_precision = False
            for comp_key, comp_label in component_precision_labels:
                comp_precision = component_precisions.get(comp_key)
                if not comp_precision:
                    continue
                stats.append((comp_label, comp_precision))
                added_component_precision = True
            if not added_component_precision:
                stats.append(("Precision", precision_text))
        if self._card_fields.get("tensors", True):
            stats.append(("Tensors", str(data["tensor_count"])))
        # Add LoRA rank if present
        lora_rank = data.get("lora_rank")
        if lora_rank and self._card_fields.get("lora_rank", True):
            stats.append(("LoRA Rank", str(lora_rank)))
        # Add extra metadata
        if self._card_fields.get("extra_meta", True):
            for key, val in data.get("extra", {}).items():
                label = key.replace("_", " ").title()
                stats.append((label, str(val)))
        # Training metadata
        if self._card_fields.get("training_meta", True):
            for key, val in data.get("training_meta", {}).items():
                label = key.replace("_", " ").title()
                stats.append((label, str(val)))

        for i, (label, value) in enumerate(stats):
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; background: transparent; border: none;"
            )
            val = QLabel(value)
            if "Precision" in label:
                val.setWordWrap(True)
            val.setStyleSheet(
                "color: #cdd6f4; font-size: 13px; font-weight: bold; background: transparent; border: none;"
            )
            grid.addWidget(lbl, i // 2, (i % 2) * 2)
            grid.addWidget(val, i // 2, (i % 2) * 2 + 1)

        layout.addLayout(grid)

        # no bottom tags; tags are intentionally kept at top

    def mousePressEvent(self, a0: QMouseEvent | None):
        if a0 is None:
            return
        event = a0
        if event.button() == Qt.MouseButton.LeftButton and self.filepath:
            self.selection_requested.emit(self.filepath, event.modifiers())
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self.filepath and (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self.drag_over_requested.emit(self.filepath)
        super().enterEvent(event)

    def contextMenuEvent(self, a0: QContextMenuEvent | None):
        if a0 is None:
            return
        event = a0
        if self.filepath:
            self.context_requested.emit(
                self.filepath, self._simple_view, event.globalPos()
            )
            event.accept()
            return
        super().contextMenuEvent(event)

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self.select_cb.blockSignals(True)
        self.select_cb.setChecked(selected)
        self.select_cb.blockSignals(False)
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet("""
                ModelCard {
                    background-color: #181825;
                    border: 2px solid #a6e3a1;
                    border-radius: 10px;
                }
                ModelCard:hover {
                    border-color: #89dceb;
                }
            """)
        else:
            self.setStyleSheet("""
                ModelCard {
                    background-color: #181825;
                    border: 1px solid #313244;
                    border-radius: 10px;
                }
                ModelCard:hover {
                    border-color: #74c7ec;
                }
            """)

    def set_filter_visible(self, visible: bool):
        visible = bool(visible)
        if self._filter_visible == visible:
            return
        self._filter_visible = visible
        self.setVisible(visible)
        self.setMaximumHeight(16777215 if visible else 0)
        self.updateGeometry()

    def _on_checkbox_clicked(self, checked):
        if self.filepath:
            self.checkbox_toggled.emit(self.filepath, bool(checked))

    @staticmethod
    def _make_tag(text: str, fg: str, bg: str) -> QLabel:
        tag = QLabel(text)
        tag.setStyleSheet(
            f"background-color: {fg}; color: {bg}; padding: 3px 10px; "
            f"border-radius: 4px; font-size: 11px; font-weight: bold; border: none;"
        )
        tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return tag


# ---------------------------------------------------------------------------
# Main window
# ---------------------------------------------------------------------------


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Model Inspector")
        # self.setWindowIcon(QIcon(_asset("icon.ico")))
        self.setWindowIcon(QIcon(_asset("icon.ico")))
        self.setMinimumSize(1050, 720)
        self.resize(1200, 790)
        QTimer.singleShot(0, self._center_window)

        self._queued_files: list[str] = []
        self._results: list[dict] = []
        self._worker: AnalysisWorker | None = None
        self._discovery_worker: DiscoveryWorker | None = None
        self._scan_generation = 0
        self._discovery_generation = 0
        self._discovery_paths: list[str] = []
        self._discovery_roots: list[str] = []
        self._discovery_auto_analyze = False
        self._discovery_terminal: dict | None = None
        self._table_sort_restore: tuple[bool, int, Qt.SortOrder] | None = None
        self._card_rebuild_generation = 0
        self._close_pending = False
        self._close_waiting_workers: set[object] = set()
        self._pending_filter_arches: list[str] = []
        self._pending_filter_tags: list[str] = []
        self._pending_filter_formats: list[str] = []
        self._raw_loaded_filepath: str | None = None
        self._cards: list[ModelCard] = []
        self._path_to_card: dict[str, ModelCard] = {}
        self._path_to_simple_card: dict[str, ModelCard] = {}
        self._path_to_row: dict[str, int] = {}
        self._selected_paths: set[str] = set()
        self._syncing_selection = False
        self._last_selected_card_index = -1
        self._last_selected_row = -1
        self._active_arch_filter: set[str] | None = None
        self._active_tag_filter: set[str] | None = None
        self._active_format_filter: set[str] | None = None
        self._analysis_done_count = 0
        self._analysis_error_count = 0
        self._analysis_total_count = 0
        self._analysis_bytes_scanned = 0
        self._scan_cancel_requested = False
        self._startup_cache_load_cancelled = False
        self._startup_sort_restore: tuple[bool, int, Qt.SortOrder] | None = None
        self._progress_status_generation = 0
        self._allow_filename_alias_detection = False
        self._show_full_paths = False
        self._auto_analyze_on_add = True
        self._dump_json_modelinfo = False
        self._auto_load_raw_dump = False
        self._load_default_libraries_on_startup = False
        self._cache_full_data_on_analyze = False
        self._selected_action = "copy_files"
        self._analysis_threads = 2
        self._add_mode = "replace"  # replace | additive
        self._default_tab = "cards"  # cards | data | raw
        self._simple_cards_view = False
        self._card_field_visibility = {
            "parameters": True,
            "file_size": True,
            "precision": True,
            "tensors": True,
            "lora_rank": True,
            "extra_meta": True,
            "training_meta": True,
        }
        self._simple_card_field_visibility = {
            "parameters": True,
            "precision": True,
            "file_size": True,
            "tensors": True,
            "lora_rank": True,
            "extra_meta": False,
            "training_meta": False,
        }
        self._table_column_visibility_pref: dict[str, bool] = {}
        self._load_ui_settings()

        self._projection = ScanProjectionBuffer(
            self._project_scan_event,
            self._reconcile_projected_results,
            self._finish_analysis_projection,
            parent=self,
        )

        central = QWidget()
        self.setCentralWidget(central)
        self.setAcceptDrops(True)
        root = QVBoxLayout(central)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        # --- Top controls row -----------------------------------------------
        controls_container = QWidget()
        self.controls_container = controls_container
        controls_layout = QVBoxLayout(controls_container)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(8)

        btn_row_1 = QHBoxLayout()
        btn_row_1.setSpacing(10)

        button_height = 35
        settings_btn = QPushButton("Settings")
        settings_btn.setToolTip("Settings")
        settings_btn.setFixedHeight(35)
        settings_btn.clicked.connect(self._open_settings)
        btn_row_1.addWidget(settings_btn)

        self.open_btn = QToolButton()
        self.open_btn.setObjectName("openBtn")
        self.open_btn.setText("Open ▼")
        self.open_btn.setToolTip("Open model files or scan a folder")
        self.open_btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        self.open_btn.setMenu(self._build_open_menu())
        self.open_btn.setMinimumWidth(130)
        self.open_btn.setFixedHeight(button_height)
        btn_row_1.addWidget(self.open_btn)

        btn_row_1.addStretch()

        self.cancel_btn = QPushButton("Cancel")
        self.cancel_btn.setEnabled(False)
        self.cancel_btn.setVisible(False)
        self.cancel_btn.clicked.connect(self._cancel_current_operation)
        btn_row_1.addWidget(self.cancel_btn)

        self.progress_label = QLabel("")
        self.progress_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        self.progress_label.setWordWrap(False)
        self.progress_label.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self.progress_label.setMinimumHeight(22)
        self.progress_label.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        btn_row_1.addWidget(self.progress_label, 1)

        self.analyze_btn = QPushButton("Analyze")
        self.analyze_btn.setObjectName("analyzeBtn")
        self.analyze_btn.clicked.connect(self._analyze_all)
        self.analyze_btn.setStyleSheet("font-weight: 800;")
        self.analyze_btn.setMinimumWidth(260)
        self.analyze_btn.setSizePolicy(
            QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed
        )

        self.progress = QProgressBar()
        self.progress.setFixedSize(260, 28)
        self.progress.setVisible(False)

        self.action_slot = QWidget()
        self.action_slot.setFixedWidth(260)
        action_slot_layout = QVBoxLayout(self.action_slot)
        action_slot_layout.setContentsMargins(0, 0, 0, 0)
        action_slot_layout.setSpacing(0)
        action_slot_layout.addWidget(self.analyze_btn)
        action_slot_layout.addWidget(self.progress)
        btn_row_1.addWidget(self.action_slot)

        controls_layout.addLayout(btn_row_1)
        self._set_idle_status()
        self._update_analyze_slot()

        root.addWidget(controls_container)

        # --- Tab widget (Cards / Data) -------------------------------------
        self.tabs = QTabWidget()

        # Cards tab
        cards_tab = QWidget()
        cards_tab_layout = QVBoxLayout(cards_tab)
        cards_tab_layout.setContentsMargins(0, 0, 0, 0)
        cards_tab_layout.setSpacing(6)

        cards_toolbar = QHBoxLayout()
        self.cards_select_all_cb = QCheckBox("Select All")
        self.cards_select_all_cb.stateChanged.connect(self._on_cards_select_all_changed)
        cards_toolbar.addWidget(self.cards_select_all_cb)
        self.cards_simple_view_cb = QCheckBox("Simple View")
        self.cards_simple_view_cb.stateChanged.connect(self._on_cards_view_changed)
        cards_toolbar.addWidget(self.cards_simple_view_cb)
        self.selected_count_label = QLabel("0 selected")
        self.selected_count_label.setStyleSheet("color: #a6adc8; font-size: 11px;")
        cards_toolbar.addWidget(self.selected_count_label)
        cards_toolbar.addStretch()
        cards_tab_layout.addLayout(cards_toolbar)

        self.simple_cards_scroll = QScrollArea()
        self.simple_cards_scroll.setWidgetResizable(True)
        self.simple_cards_container = QWidget()
        self.simple_cards_layout = QVBoxLayout(self.simple_cards_container)
        self.simple_cards_layout.setSpacing(12)
        self.simple_cards_layout.setContentsMargins(8, 8, 8, 8)
        self.simple_cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.simple_cards_scroll.setWidget(self.simple_cards_container)

        self.simple_cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.simple_cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.simple_cards_placeholder.setStyleSheet(
            "color: #45475a; font-size: 14px; padding: 60px;"
        )
        self.simple_cards_layout.insertWidget(0, self.simple_cards_placeholder)

        self.cards_scroll = QScrollArea()
        self.cards_scroll.setWidgetResizable(True)
        self.cards_container = QWidget()
        self.cards_layout = QVBoxLayout(self.cards_container)
        self.cards_layout.setSpacing(12)
        self.cards_layout.setContentsMargins(8, 8, 8, 8)
        self.cards_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.cards_scroll.setWidget(self.cards_container)

        self.cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_placeholder.setStyleSheet(
            "color: #45475a; font-size: 14px; padding: 60px;"
        )
        self.cards_layout.insertWidget(0, self.cards_placeholder)

        cards_tab_layout.addWidget(self.cards_scroll)
        cards_tab_layout.addWidget(self.simple_cards_scroll)
        self.tabs.addTab(cards_tab, "Cards")
        self._apply_cards_view_mode()

        # Data table tab
        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(0, 0, 0, 0)
        data_tab_layout.setSpacing(6)

        data_toolbar = QHBoxLayout()
        self.table_select_all_cb = QCheckBox("Select All")
        self.table_select_all_cb.stateChanged.connect(self._on_table_select_all_changed)
        data_toolbar.addWidget(self.table_select_all_cb)
        self.show_full_path_cb = QCheckBox("Show Full Path")
        self.show_full_path_cb.stateChanged.connect(self._on_show_full_path_changed)
        data_toolbar.addWidget(self.show_full_path_cb)
        data_toolbar.addStretch()
        data_tab_layout.addLayout(data_toolbar)

        self.table = QTableWidget()
        self.table.setAlternatingRowColors(True)
        self.table.setSortingEnabled(True)
        self.table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectItems)
        self.table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        vertical_header = self.table.verticalHeader()
        assert vertical_header is not None
        vertical_header.setVisible(False)
        self.table.itemSelectionChanged.connect(self._on_table_item_selection_changed)
        self.table.cellClicked.connect(self._on_table_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_table_context_menu)
        horizontal_header = self.table.horizontalHeader()
        assert horizontal_header is not None
        horizontal_header.sortIndicatorChanged.connect(self._on_table_sort_changed)

        self._table_columns = [
            "",
            "File",
            "Format",
            "File Size",
            "Architecture",
            "Model Type",
            "Adapter",
            "Quantization",
            "Precision",
            "UNet Precision",
            "VAE Precision",
            "Text Encoder Precision",
            "Transformer Precision",
            "Parameters",
            "Tensors",
            "LoRA Rank",
            "MoE",
            "Experts",
            "Active Experts",
            "Software",
            "Images",
            "Resolution",
            "Epochs",
            "Steps",
        ]
        self.table.setColumnCount(len(self._table_columns))
        self.table.setHorizontalHeaderLabels(self._table_columns)

        header = self.table.horizontalHeader()
        assert header is not None
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(0, 34)
        for i in range(1, len(self._table_columns)):
            header.setSectionResizeMode(i, QHeaderView.ResizeMode.Interactive)
        self.table.setColumnWidth(1, 280)  # File
        self.table.setColumnWidth(2, 70)  # Format
        self.table.setColumnWidth(3, 90)  # File Size
        self.table.setColumnWidth(4, 140)  # Architecture
        self.table.setColumnWidth(5, 100)  # Model Type
        self.table.setColumnWidth(6, 90)  # Adapter
        self.table.setColumnWidth(7, 100)  # Quantization
        self.table.setColumnWidth(8, 100)  # Precision
        self.table.setColumnWidth(9, 115)  # UNet
        self.table.setColumnWidth(10, 115)  # VAE
        self.table.setColumnWidth(11, 160)  # Text Encoder
        self.table.setColumnWidth(12, 120)  # Transformer
        self.table.setColumnWidth(13, 95)  # Parameters
        self.table.setColumnWidth(14, 70)  # Tensors
        self.table.setColumnWidth(15, 85)  # LoRA Rank
        self.table.setColumnWidth(16, 60)  # MoE
        self.table.setColumnWidth(17, 80)  # Experts
        self.table.setColumnWidth(18, 105)  # Active Experts
        self.table.setColumnWidth(19, 150)  # Software
        self.table.setColumnWidth(20, 70)  # Images
        self.table.setColumnWidth(21, 100)  # Resolution
        self.table.setColumnWidth(22, 70)  # Epochs
        self.table.setColumnWidth(23, 80)  # Steps
        self._apply_table_column_visibility()
        data_tab_layout.addWidget(self.table)
        self.tabs.addTab(data_tab, "Data")

        # Raw data tab
        raw_container = QWidget()
        raw_layout = QVBoxLayout(raw_container)
        raw_layout.setContentsMargins(8, 8, 8, 8)
        raw_layout.setSpacing(6)

        # File selector for raw view
        raw_top = QHBoxLayout()
        raw_top.addWidget(QLabel("Select model:"))
        self.raw_combo = QComboBox()
        self.raw_combo.setMinimumWidth(300)
        self.raw_combo.installEventFilter(self)
        self.raw_combo.currentIndexChanged.connect(self._on_raw_selection_changed)
        raw_top.addWidget(self.raw_combo, stretch=1)
        self.raw_prev_btn = QToolButton()
        self.raw_prev_btn.setText("▲")
        self.raw_prev_btn.setToolTip("Previous model")
        self.raw_prev_btn.clicked.connect(lambda: self._step_raw_selection(-1))
        raw_top.addWidget(self.raw_prev_btn)
        self.raw_next_btn = QToolButton()
        self.raw_next_btn.setText("▼")
        self.raw_next_btn.setToolTip("Next model")
        self.raw_next_btn.clicked.connect(lambda: self._step_raw_selection(1))
        raw_top.addWidget(self.raw_next_btn)
        self.raw_load_btn = QPushButton("Load Full Dump")
        self.raw_load_btn.clicked.connect(self._load_selected_raw_dump)
        raw_top.addWidget(self.raw_load_btn)
        self._update_raw_controls()
        raw_layout.addLayout(raw_top)

        self.raw_text = QTextEdit()
        self.raw_text.setReadOnly(True)
        self.raw_text.setStyleSheet(
            "QTextEdit { background-color: #11111b; color: #a6adc8; "
            "font-family: 'Consolas', 'Courier New', monospace; font-size: 12px; "
            "border: 1px solid #313244; border-radius: 4px; padding: 8px; }"
        )
        self.raw_text.setPlaceholderText(
            "Analyze models to see raw tensor key data here."
        )
        raw_layout.addWidget(self.raw_text)

        self.tabs.addTab(raw_container, "Raw")
        self.tabs.currentChanged.connect(self._on_tab_changed)
        self._apply_default_tab()

        root.addWidget(self.tabs, stretch=1)

        bottom_actions = QHBoxLayout()
        bottom_actions.setSpacing(10)

        self.arch_filter_btn = CheckFilterButton("Architecture")
        self.arch_filter_btn.filter_changed.connect(self._on_arch_filter_changed)
        self.arch_filter_btn.setMinimumHeight(34)
        self.arch_filter_btn.setMinimumWidth(170)
        self.arch_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.arch_filter_btn, 1)

        self.tag_filter_btn = CheckFilterButton("Tags")
        self.tag_filter_btn.filter_changed.connect(self._on_tag_filter_changed)
        self.tag_filter_btn.setMinimumHeight(34)
        self.tag_filter_btn.setMinimumWidth(150)
        self.tag_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.tag_filter_btn, 1)

        self.format_filter_btn = CheckFilterButton("Format")
        self.format_filter_btn.filter_changed.connect(self._on_format_filter_changed)
        self.format_filter_btn.setMinimumHeight(34)
        self.format_filter_btn.setMinimumWidth(150)
        self.format_filter_btn.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        bottom_actions.addWidget(self.format_filter_btn, 1)
        self._reset_format_filter_items()

        self.selected_action_btn = QPushButton()
        self.selected_action_btn.setEnabled(False)
        self.selected_action_btn.clicked.connect(self._run_selected_action)
        bottom_actions.addWidget(self.selected_action_btn)

        self.selected_action_menu_btn = QToolButton()
        self.selected_action_menu_btn.setText("▼")
        self.selected_action_menu_btn.setToolTip("Selected model actions")
        self.selected_action_menu_btn.setPopupMode(
            QToolButton.ToolButtonPopupMode.InstantPopup
        )
        self.selected_action_menu_btn.setMenu(self._build_selected_action_menu())
        bottom_actions.addWidget(self.selected_action_menu_btn)

        self.clear_results_btn = QPushButton("Clear All")
        self.clear_results_btn.setObjectName("clearBtn")
        self.clear_results_btn.clicked.connect(self._clear_all)
        bottom_actions.addWidget(self.clear_results_btn)
        self._refresh_selected_action_button()
        root.addLayout(bottom_actions)

        self.copy_shortcut = QShortcut(QKeySequence.StandardKey.Copy, self)
        self.copy_shortcut.activated.connect(self._on_copy_shortcut)
        QTimer.singleShot(0, self._load_default_libraries_from_cache_on_startup)

    def _center_window(self):
        screen = QApplication.primaryScreen()
        if not screen:
            return
        geo = screen.availableGeometry()
        frame = self.frameGeometry()
        frame.moveCenter(geo.center())
        self.move(frame.topLeft())

    def _add_menu_action(self, menu: QMenu, text: str, callback) -> QAction | None:
        action = menu.addAction(text)
        if action is not None:
            action.triggered.connect(callback)
        return action

    def _build_open_menu(self) -> QMenu:
        menu = QMenu(self)
        self._add_menu_action(menu, "Open Files", self._browse_files)
        self._add_menu_action(menu, "Open Folder", self._browse_folder_recursive)
        return menu

    def _selected_actions(self):
        return {
            "copy_files": ("Copy Files", self._copy_selected_files_to_clipboard),
            "move_files": ("Move Files", self._move_selected_files),
            "copy_names": ("Copy Names", self._copy_selected_names),
            "copy_paths": ("Copy Paths", self._copy_selected_paths),
            "dump_modelinfo": ("Dump .modelinfo", self._dump_all),
            "remove_selected": ("Remove Selected", self._remove_selected_results),
        }

    def _build_selected_action_menu(self) -> QMenu:
        menu = QMenu(self)
        for key, (label, _) in self._selected_actions().items():
            self._add_menu_action(
                menu,
                label,
                lambda checked=False, action_key=key: self._select_selected_action(
                    action_key
                ),
            )
        return menu

    def _select_selected_action(self, action_key: str):
        if action_key not in self._selected_actions():
            return
        self._selected_action = action_key
        self._refresh_selected_action_button()

    def _refresh_selected_action_button(self):
        label, _ = self._selected_actions().get(
            self._selected_action, self._selected_actions()["copy_files"]
        )
        self.selected_action_btn.setText(label)
        self.selected_action_btn.setToolTip(
            "Run the selected action on visible selected models"
        )

    def _run_selected_action(self):
        _, callback = self._selected_actions().get(
            self._selected_action, self._selected_actions()["copy_files"]
        )
        callback()

    def _on_copy_shortcut(self):
        tab = self.tabs.currentIndex()
        if tab == 0:
            self._copy_selected_cards_info(self._simple_cards_view)
            return
        if tab == 1:
            self._copy_selected_table_cells()
            return
        if tab == 2:
            if self.raw_text.textCursor().hasSelection():
                self.raw_text.copy()
            else:
                _clipboard().setText(self.raw_text.toPlainText())
            return

    def eventFilter(self, a0, a1: QEvent | None):
        obj = a0
        event = a1
        if obj is self.raw_combo and isinstance(event, QKeyEvent):
            key = event.key()
            if key == Qt.Key.Key_Up:
                self._step_raw_selection(-1)
                return True
            if key == Qt.Key.Key_Down:
                self._step_raw_selection(1)
                return True
            if key == Qt.Key.Key_PageUp:
                self._step_raw_selection(-10)
                return True
            if key == Qt.Key.Key_PageDown:
                self._step_raw_selection(10)
                return True
        return super().eventFilter(a0, a1)

    def dragEnterEvent(self, a0: QDragEnterEvent | None):
        if a0 is None:
            return
        mime_data = a0.mimeData()
        if mime_data is not None and mime_data.hasUrls():
            a0.acceptProposedAction()

    def dropEvent(self, a0: QDropEvent | None):
        if a0 is None:
            return
        mime_data = a0.mimeData()
        if mime_data is None:
            return
        paths = []
        folders = []
        unsupported = []
        for url in mime_data.urls():
            fp = url.toLocalFile()
            if not fp:
                continue
            path = Path(fp)
            if path.is_dir():
                folders.append(fp)
            elif is_supported_model_path(fp):
                paths.append(fp)
            elif is_checkpoint_model_path(fp):
                unsupported.append(fp)
        if unsupported:
            self._warn_unsupported_checkpoint_files(unsupported)
        if folders:
            self._start_discovery(folders, paths)
            a0.acceptProposedAction()
        elif paths:
            self._add_files(paths)
            a0.acceptProposedAction()

    def _on_tab_changed(self, index):
        if index == 2:
            self._refresh_raw_combo_filtered()

    def _load_ui_settings(self):
        s = _settings()
        self._allow_filename_alias_detection = (
            str(s.value("allow_filename_alias_detection", "false")).lower() == "true"
        )
        self._auto_analyze_on_add = (
            str(s.value("auto_analyze_on_add", "true")).lower() == "true"
        )
        self._dump_json_modelinfo = (
            str(s.value("dump_json_modelinfo", "false")).lower() == "true"
        )
        self._auto_load_raw_dump = (
            str(s.value("auto_load_raw_dump", "false")).lower() == "true"
        )
        self._load_default_libraries_on_startup = (
            str(s.value("load_default_libraries_on_startup", "false")).lower() == "true"
        )
        self._cache_full_data_on_analyze = (
            str(s.value("cache_full_data_on_analyze", "false")).lower() == "true"
        )
        try:
            self._analysis_threads = max(
                1, min(8, int(s.value("analysis_threads", "2")))
            )
        except (TypeError, ValueError):
            self._analysis_threads = 2
        self._add_mode = str(s.value("add_mode", "replace")).lower()
        self._default_tab = str(s.value("default_tab", "cards")).lower()
        if self._default_tab in ("simple", "detailed"):
            self._default_tab = "cards"
        if self._add_mode not in ("replace", "additive"):
            self._add_mode = "replace"
        if self._default_tab not in ("cards", "data", "raw"):
            self._default_tab = "cards"
        raw_detailed = s.value("detailed_card_fields", "")
        if raw_detailed:
            try:
                obj = json.loads(raw_detailed)
                if isinstance(obj, dict):
                    self._card_field_visibility.update(
                        {k: bool(v) for k, v in obj.items()}
                    )
            except Exception:
                pass
        raw_simple = s.value("simple_card_fields", "")
        if raw_simple:
            try:
                obj = json.loads(raw_simple)
                if isinstance(obj, dict):
                    self._simple_card_field_visibility.update(
                        {k: bool(v) for k, v in obj.items()}
                    )
            except Exception:
                pass
        raw_cols = s.value("table_columns", "")
        if raw_cols:
            try:
                obj = json.loads(raw_cols)
                if isinstance(obj, dict):
                    self._table_column_visibility_pref = {
                        str(k): bool(v) for k, v in obj.items()
                    }
            except Exception:
                pass

    def _save_ui_settings(self):
        s = _settings()
        s.setValue(
            "allow_filename_alias_detection",
            str(self._allow_filename_alias_detection).lower(),
        )
        s.setValue("auto_analyze_on_add", str(self._auto_analyze_on_add).lower())
        s.setValue("dump_json_modelinfo", str(self._dump_json_modelinfo).lower())
        s.setValue("auto_load_raw_dump", str(self._auto_load_raw_dump).lower())
        s.setValue(
            "load_default_libraries_on_startup",
            str(self._load_default_libraries_on_startup).lower(),
        )
        s.setValue(
            "cache_full_data_on_analyze", str(self._cache_full_data_on_analyze).lower()
        )
        s.setValue("analysis_threads", str(self._analysis_threads))
        s.setValue("add_mode", self._add_mode)
        s.setValue("default_tab", self._default_tab)
        s.setValue("detailed_card_fields", json.dumps(self._card_field_visibility))
        s.setValue("simple_card_fields", json.dumps(self._simple_card_field_visibility))
        col_vis = {}
        for idx, name in enumerate(self._table_columns):
            if idx == 0:
                continue
            col_vis[name] = not self.table.isColumnHidden(idx)
        s.setValue("table_columns", json.dumps(col_vis))

    def _apply_table_column_visibility(self):
        if not self._table_column_visibility_pref:
            return
        for name, visible in self._table_column_visibility_pref.items():
            if name in self._table_columns:
                idx = self._table_columns.index(name)
                self.table.setColumnHidden(idx, not bool(visible))

    # -- File management ---------------------------------------------------

    def _format_bytes(self, size: int) -> str:
        value = float(size)
        for unit in ("B", "KB", "MB", "GB", "TB"):
            if value < 1024 or unit == "TB":
                return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
            value /= 1024
        return f"{value:.1f} TB"

    def _set_progress_status(self, text: str):
        self._progress_status_generation += 1
        self.progress_label.setText(text or self._idle_status_text())
        self.progress_label.setToolTip(text or "")

    def _idle_status_text(self) -> str:
        result_count = len(self._results)
        if result_count:
            return f"{result_count} model{'s' if result_count != 1 else ''} analyzed"
        queued_count = len(self._queued_files)
        if queued_count:
            return f"{queued_count} model{'s' if queued_count != 1 else ''} queued"
        return "Drop models anywhere or choose Open"

    def _set_idle_status(self):
        self._set_progress_status("")

    def _has_unanalyzed_queue(self) -> bool:
        result_paths = {
            str(data.get("filepath") or "")
            for data in self._results
            if data.get("filepath")
        }
        return any(path not in result_paths for path in self._queued_files)

    def _update_analyze_slot(self):
        busy = (
            bool(self._worker and self._worker.isRunning())
            or self.progress.isVisible()
        )
        self.progress.setVisible(busy)
        self.analyze_btn.setVisible(
            not busy and (not self._auto_analyze_on_add or self._has_unanalyzed_queue())
        )
        self.action_slot.setVisible(True)

    def _set_cancel_available(self, available: bool):
        self.cancel_btn.setEnabled(available)
        self.cancel_btn.setVisible(available)
        self._update_analyze_slot()

    def _cancel_current_operation(self):
        self._scan_cancel_requested = True
        self._startup_cache_load_cancelled = True
        self._restore_startup_table_sorting()
        if self._discovery_worker and self._discovery_worker.isRunning():
            self._discovery_worker.cancel()
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        self._set_cancel_available(False)
        self._set_progress_status("Cancelling after the current file or directory...")

    def _clear_progress_status(self, delay_ms: int = 0):
        generation = self._progress_status_generation

        def clear():
            if delay_ms and generation != self._progress_status_generation:
                return
            self.progress.setVisible(False)
            self.progress_label.setToolTip("")
            self.progress_label.setText(self._idle_status_text())
            self._set_cancel_available(False)
            self._update_analyze_slot()

        if delay_ms:
            QTimer.singleShot(delay_ms, clear)
        else:
            clear()

    def _start_discovery(self, roots: list[str], seed_paths: list[str] | None = None):
        if self._worker and self._worker.isRunning():
            return
        if self._discovery_worker and self._discovery_worker.isRunning():
            return
        self._discovery_generation += 1
        self._discovery_roots = list(roots)
        self._discovery_paths = list(seed_paths or [])
        self._discovery_auto_analyze = self._auto_analyze_on_add
        self._scan_cancel_requested = False
        self.progress.setVisible(True)
        self.progress.setRange(0, 0)
        self._set_cancel_available(True)
        self._start_next_discovery_root(self._discovery_generation)

    def _start_next_discovery_root(self, generation: int):
        if generation != self._discovery_generation or self._scan_cancel_requested:
            self._finish_discovery(generation, True)
            return
        if not self._discovery_roots:
            self._finish_discovery(generation, False)
            return
        root = self._discovery_roots.pop(0)
        worker = DiscoveryWorker(root, extensions=SUPPORTED_MODEL_EXTENSIONS)
        self._discovery_worker = worker
        worker.progress_updated.connect(
            lambda progress, g=generation: self._on_discovery_progress(g, progress)
        )
        worker.error_occurred.connect(
            lambda path, message, g=generation: self._on_discovery_error(
                g, path, message
            )
        )
        worker.discovery_done.connect(
            lambda terminal, g=generation: self._on_discovery_done(g, terminal)
        )
        worker.finished.connect(
            lambda g=generation, w=worker: self._on_discovery_worker_finished(g, w)
        )
        worker.start()

    def _on_discovery_progress(self, generation: int, progress: dict):
        if generation != self._discovery_generation:
            return
        discovered = int(progress.get("discovered_files") or 0)
        directories = int(progress.get("scanned_directories") or 0)
        current = str(progress.get("current_directory") or progress.get("root") or "")
        self._set_progress_status(
            f"Discovering: {discovered} files | Directories: {directories} | "
            f"Current directory: {current}"
        )

    def _on_discovery_error(self, generation: int, path: str, message: str):
        if generation == self._discovery_generation:
            self._set_progress_status(f"Discovery warning: {path} | {message}")

    def _on_discovery_done(self, generation: int, terminal: dict):
        if generation != self._discovery_generation:
            return
        self._discovery_terminal = terminal

    def _on_discovery_worker_finished(
        self, generation: int, worker: DiscoveryWorker
    ):
        if (
            generation != self._discovery_generation
            or worker is not self._discovery_worker
        ):
            return
        terminal = self._discovery_terminal or {
            "root": worker.root,
            "paths": (),
            "cancelled": True,
        }
        self._discovery_terminal = None
        paths = [str(path) for path in terminal.get("paths") or ()]
        self._discovery_paths.extend(paths)
        root = str(terminal.get("root") or "")
        if paths and not terminal.get("cancelled"):
            store_directory_scan(root, paths)
        if terminal.get("cancelled"):
            self._finish_discovery(generation, True)
        else:
            self._start_next_discovery_root(generation)

    def _finish_discovery(self, generation: int, cancelled: bool):
        if generation != self._discovery_generation:
            return
        unique_paths = list(dict.fromkeys(self._discovery_paths))
        self._set_cancel_available(False)
        if cancelled:
            self._set_progress_status(
                f"Discovery cancelled: {len(unique_paths)} partial files found"
            )
        else:
            self._set_progress_status(f"Discovered {len(unique_paths)} files")
        if unique_paths:
            added = self._queue_files(unique_paths)
            if added and self._discovery_auto_analyze:
                self._analyze_all()
                return
        self._clear_progress_status(delay_ms=3000)

    def _queue_files(self, paths: list[str]) -> list[str]:
        if not paths:
            return []
        added = []
        if self._add_mode == "replace":
            self._queued_files.clear()

        for p in paths:
            if p not in self._queued_files:
                self._queued_files.append(p)
                added.append(p)
        self._update_file_count()
        return added

    def _add_files(self, paths: list[str]):
        added = self._queue_files(paths)
        if not added:
            return
        if self._auto_analyze_on_add:
            self._analyze_all()

    def _update_file_count(self):
        if not self.progress.isVisible():
            self._set_idle_status()
        self._update_analyze_slot()

    def _browse_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Select model files", "", _model_file_filter()
        )
        if not paths:
            return
        supported = [p for p in paths if is_supported_model_path(p)]
        unsupported = [p for p in paths if is_checkpoint_model_path(p)]
        if unsupported:
            self._warn_unsupported_checkpoint_files(unsupported)
        if supported:
            self._add_files(supported)

    def _warn_unsupported_checkpoint_files(self, paths: list[str]):
        if not paths:
            return
        preview = "\n".join(Path(p).name for p in paths[:8])
        if len(paths) > 8:
            preview += f"\n...and {len(paths) - 8} more"
        QMessageBox.warning(
            self,
            "Checkpoint Format Not Inspected",
            f"{CHECKPOINT_FORMAT_WARNING}\n\nIgnored file(s):\n{preview}",
        )

    def _browse_folder_recursive(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Select folder to scan recursively"
        )
        if not folder:
            return
        self._start_discovery([folder])

    def _load_default_libraries_from_cache_on_startup(self):
        if not self._load_default_libraries_on_startup:
            return

        cached_paths = []
        seen = set()
        for path in list_cached_inspection_paths():
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            cached_paths.append(path)
        if not cached_paths:
            return

        self._startup_cache_load_cancelled = False
        snapshot_count = 0
        snapshots = get_cached_inspection_summary_snapshots(cached_paths)
        total = len(cached_paths)
        batch_size = 20
        header = self.table.horizontalHeader()
        assert header is not None
        self._startup_sort_restore = (
            self.table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        self.table.setSortingEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self._set_cancel_available(True)

        def load_batch(start_index: int):
            nonlocal snapshot_count
            if self._startup_cache_load_cancelled:
                self._restore_startup_table_sorting()
                self._set_progress_status(
                    f"Startup cache load cancelled: {snapshot_count}/{total} summaries loaded"
                )
                self._clear_progress_status(delay_ms=4000)
                return

            end_index = min(start_index + batch_size, total)
            for path in cached_paths[start_index:end_index]:
                cached = snapshots.get(path)
                if cached is not None:
                    cached["filepath"] = path
                    cached["filename"] = Path(path).name
                    self._normalize_result_data(cached)
                    if path not in self._queued_files:
                        self._queued_files.append(path)
                    self._results.append(cached)
                    self._add_card(cached)
                    self._add_table_row(cached)
                    self.arch_filter_btn.add_item(cached.get("architecture", "Unknown"))
                    for tag in self._filter_tags_for_data(cached):
                        self.tag_filter_btn.add_item(tag)
                    self.format_filter_btn.add_item(
                        self._format_filter_for_data(cached)
                    )
                    snapshot_count += 1

            self.progress.setValue(end_index)
            self._set_progress_status(
                f"Loading startup cache: {end_index}/{total} paths | "
                f"{snapshot_count} cached summaries"
            )

            if end_index < total:
                QTimer.singleShot(0, lambda: load_batch(end_index))
                return

            self._restore_startup_table_sorting()
            if snapshot_count:
                self._apply_arch_filter()
                self._refresh_raw_combo_filtered()
                self._sync_selection_visuals()

            self._set_cancel_available(False)
            self._set_progress_status(
                f"Loaded {snapshot_count} cached summary"
                f"{'ies' if snapshot_count != 1 else 'y'}"
            )
            self._clear_progress_status(delay_ms=5000)

        load_batch(0)

    def _restore_startup_table_sorting(self):
        if self._startup_sort_restore is None:
            return
        sorting_enabled, column, order = self._startup_sort_restore
        self._startup_sort_restore = None
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(column, order)
        self.table.setSortingEnabled(sorting_enabled)

    def _open_settings(self):
        col_vis = {
            name: not self.table.isColumnHidden(idx)
            for idx, name in enumerate(self._table_columns)
            if idx != 0  # checkbox column stays visible
        }
        dlg = SettingsDialog(
            self,
            allow_filename_alias_detection=self._allow_filename_alias_detection,
            auto_analyze_on_add=self._auto_analyze_on_add,
            dump_json_modelinfo=self._dump_json_modelinfo,
            auto_load_raw_dump=self._auto_load_raw_dump,
            load_default_libraries_on_startup=self._load_default_libraries_on_startup,
            cache_full_data_on_analyze=self._cache_full_data_on_analyze,
            analysis_threads=self._analysis_threads,
            add_mode=self._add_mode,
            default_tab=self._default_tab,
            card_fields=self._card_field_visibility,
            simple_card_fields=self._simple_card_field_visibility,
            table_column_visibility=col_vis,
        )
        dlg.clear_cache_btn.clicked.connect(self._clear_inspection_cache_from_settings)
        if dlg.exec():
            self._allow_filename_alias_detection = dlg.alias_checkbox.isChecked()
            self._auto_analyze_on_add = dlg.auto_analyze_checkbox.isChecked()
            self._dump_json_modelinfo = dlg.dump_json_checkbox.isChecked()
            self._auto_load_raw_dump = dlg.auto_load_raw_checkbox.isChecked()
            self._load_default_libraries_on_startup = (
                dlg.default_libraries_checkbox.isChecked()
            )
            self._cache_full_data_on_analyze = dlg.cache_full_data_checkbox.isChecked()
            threads = _combo_data_str(dlg.analysis_threads_combo.currentData())
            self._analysis_threads = int(threads or 1)
            self._add_mode = _combo_data_str(dlg.add_mode_combo.currentData()) or "replace"
            self._default_tab = (
                _combo_data_str(dlg.default_tab_combo.currentData()) or "cards"
            )
            for key, cb in dlg.card_field_checks.items():
                self._card_field_visibility[key] = cb.isChecked()
            for key, cb in dlg.simple_card_field_checks.items():
                self._simple_card_field_visibility[key] = cb.isChecked()
            for name, cb in dlg.table_column_checks.items():
                if name in self._table_columns:
                    idx = self._table_columns.index(name)
                    self.table.setColumnHidden(idx, not cb.isChecked())
            self._save_ui_settings()
            self._rebuild_views_from_results()
            self._update_raw_controls()
            self._update_analyze_slot()
            self._apply_default_tab()

    def _clear_inspection_cache_from_settings(self):
        reply = QMessageBox.question(
            self,
            "Clear Cache",
            "Clear all cached inspection summaries? Existing analyzed results stay visible.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if reply != QMessageBox.StandardButton.Yes:
            return
        removed = clear_inspection_cache()
        QMessageBox.information(
            self,
            "Cache Cleared",
            f"Removed {removed} cached file{'s' if removed != 1 else ''}.",
        )

    def _apply_default_tab(self):
        tab_idx = {
            "cards": 0,
            "data": 1,
            "raw": 2,
        }.get(self._default_tab, 0)
        self.tabs.setCurrentIndex(tab_idx)

    def _clear_all(self):
        self._startup_cache_load_cancelled = True
        if self._worker and self._worker.isRunning():
            self._worker.cancel()
        if self._discovery_worker and self._discovery_worker.isRunning():
            self._discovery_worker.cancel()
        self._discovery_generation += 1
        self._projection.invalidate()
        self._scan_generation = self._projection.generation
        self._card_rebuild_generation += 1
        self._restore_table_sorting()
        self._restore_startup_table_sorting()
        self._pending_filter_arches.clear()
        self._pending_filter_tags.clear()
        self._pending_filter_formats.clear()
        self._queued_files.clear()
        self._results.clear()
        self._cards.clear()
        self._path_to_card.clear()
        self._path_to_simple_card.clear()
        self._path_to_row.clear()
        self._selected_paths.clear()
        self._active_arch_filter = None
        self._active_tag_filter = None
        self._active_format_filter = None
        self._update_file_count()
        self._clear_cards()
        self.arch_filter_btn.clear_items()
        self.tag_filter_btn.clear_items()
        self._reset_format_filter_items()
        self.table.setRowCount(0)
        self.raw_combo.clear()
        self.raw_text.clear()
        self._raw_loaded_filepath = None
        self._update_raw_controls()
        self._update_selection_ui_state()

    # -- Analysis ----------------------------------------------------------

    def _analyze_all(self):
        if not self._queued_files:
            return
        self._start_analysis(list(self._queued_files), clear_existing=True)

    def _start_analysis(self, paths: list[str], clear_existing: bool):
        if not paths:
            return
        if self._worker and self._worker.isRunning():
            return

        self._scan_generation = self._projection.begin()
        self.analyze_btn.setEnabled(False)
        self.progress.setVisible(True)
        self.progress.setRange(0, len(paths))
        self.progress.setMaximum(len(paths))
        self.progress.setValue(0)
        self._set_cancel_available(True)
        self._analysis_done_count = 0
        self._analysis_error_count = 0
        self._analysis_total_count = len(paths)
        self._analysis_bytes_scanned = 0
        self._set_progress_status(
            f"Scanning 0/{self._analysis_total_count} | Bytes scanned: 0 B"
        )
        header = self.table.horizontalHeader()
        assert header is not None
        self._table_sort_restore = (
            self.table.isSortingEnabled(),
            header.sortIndicatorSection(),
            header.sortIndicatorOrder(),
        )
        self.table.setSortingEnabled(False)

        if clear_existing:
            self._pending_filter_arches.clear()
            self._pending_filter_tags.clear()
            self._pending_filter_formats.clear()
            self._results.clear()
            self._cards.clear()
            self._path_to_card.clear()
            self._path_to_simple_card.clear()
            self._path_to_row.clear()
            self._selected_paths.clear()
            self._active_arch_filter = None
            self._active_tag_filter = None
            self._active_format_filter = None
            self._clear_cards()
            self.arch_filter_btn.clear_items()
            self.tag_filter_btn.clear_items()
            self._reset_format_filter_items()
            self.table.setRowCount(0)
            self.raw_combo.clear()
            self.raw_text.clear()
            self._raw_loaded_filepath = None
            self._update_raw_controls()
            self._update_selection_ui_state()

        self._worker = AnalysisWorker(
            list(paths),
            inspect_options={
                "allow_filename_alias_detection": self._allow_filename_alias_detection,
                "cache_full_data": self._cache_full_data_on_analyze,
            },
            threads=self._analysis_threads,
        )
        worker = self._worker
        generation = self._scan_generation
        worker.result_ready.connect(
            lambda data, g=generation, w=worker: self._on_result(g, w, data)
        )
        worker.error_occurred.connect(
            lambda filepath, error, g=generation, w=worker: self._on_error(
                g, w, filepath, error
            )
        )
        worker.all_done.connect(
            lambda g=generation, w=worker: self._on_all_done(g, w)
        )
        worker.start()

    def _on_result(self, *args):
        if len(args) == 1:
            generation = self._scan_generation
            worker = None
            data = args[0]
        else:
            generation, worker, data = args
        summary = compact_inspection_summary(data)
        self._projection.enqueue(
            ProjectionEvent(
                generation,
                "result",
                summary,
                worker.acknowledge_event if worker is not None else None,
            )
        )

    def _on_error(self, *args):
        if len(args) == 2:
            generation = self._scan_generation
            worker = None
            filepath, error = args
        else:
            generation, worker, filepath, error = args
        self._projection.enqueue(
            ProjectionEvent(
                generation,
                "error",
                (filepath, error),
                worker.acknowledge_event if worker is not None else None,
            )
        )

    def _project_scan_event(self, kind: str, payload: object):
        if kind == "result":
            self._project_result(payload)
        else:
            filepath, error = payload
            self._project_error(str(filepath), str(error))

    def _project_result(self, data: dict):
        self._normalize_result_data(data)
        self._results.append(data)
        self._analysis_done_count += 1
        self._analysis_bytes_scanned += int(data.get("file_size") or 0)
        self._update_analysis_progress(data.get("filepath", ""))
        self._add_card(data)
        self._add_table_row(data)
        self._apply_visibility_to_projected_item(data)
        self._pending_filter_arches.append(data.get("architecture", "Unknown"))
        self._pending_filter_tags.extend(self._filter_tags_for_data(data))
        self._pending_filter_formats.append(self._format_filter_for_data(data))

    def _project_error(self, filepath: str, error: str):
        self._analysis_done_count += 1
        self._analysis_error_count += 1
        try:
            self._analysis_bytes_scanned += Path(filepath).stat().st_size
        except OSError:
            pass
        self._update_analysis_progress(filepath)
        # Add an error card
        err_data = {
            "filepath": filepath,
            "filename": Path(filepath).name,
            "format": Path(filepath).suffix.lower().lstrip(".").upper() or "UNKNOWN",
            "architecture": "ERROR",
            "model_type": error,
            "adapter_type": None,
            "quantization": None,
            "total_params_friendly": "-",
            "file_size_friendly": "-",
            "precision_summary": "-",
            "component_precision_summary": "-",
            "component_precisions": {},
            "precision_display": "-",
            "tensor_count": 0,
            "components": {},
            "named_text_encoders": {},
            "lora_rank": None,
            "training_meta": {},
            "extra": {},
            "is_moe": False,
            "expert_count": None,
            "expert_used_count": None,
        }
        self._results.append(err_data)
        self._add_card(err_data)
        self._add_table_row(err_data)
        self._apply_visibility_to_projected_item(err_data)
        self._pending_filter_arches.append(err_data.get("architecture", "Unknown"))
        self._pending_filter_tags.extend(self._filter_tags_for_data(err_data))
        self._pending_filter_formats.append(self._format_filter_for_data(err_data))

    def _on_all_done(self, generation: int, worker: AnalysisWorker):
        self._projection.mark_terminal(generation, worker)

    def _reconcile_projected_results(self, final: bool):
        self.arch_filter_btn.add_items(self._pending_filter_arches)
        self.tag_filter_btn.add_items(self._pending_filter_tags)
        self.format_filter_btn.add_items(self._pending_filter_formats)
        self._pending_filter_arches.clear()
        self._pending_filter_tags.clear()
        self._pending_filter_formats.clear()
        if not final:
            return
        self._apply_arch_filter(
            refresh_raw=False,
            refresh_geometry=False,
            update_selection=False,
        )
        self._refresh_raw_combo_filtered()
        self._sync_selection_visuals()
        self._refresh_card_layout_geometry()

    def _apply_visibility_to_projected_item(self, data: dict):
        fp = str(data.get("filepath") or "")
        if not fp:
            return
        visible = self._is_data_visible(data)
        card = self._path_to_card.get(fp)
        if card is None:
            card = self._path_to_simple_card.get(fp)
        if card:
            card.set_filter_visible(visible)
        row = self._row_for_filepath(fp)
        if row is not None:
            self.table.setRowHidden(row, not visible)

    def _finish_analysis_projection(self, terminal: object):
        worker = terminal
        if worker is not self._worker:
            return
        self._restore_table_sorting()
        self.analyze_btn.setEnabled(True)
        self._set_cancel_available(False)
        was_cancelled = bool(worker.was_cancelled)
        error_text = (
            f" | Errors: {self._analysis_error_count}"
            if self._analysis_error_count
            else ""
        )
        if was_cancelled:
            self._set_progress_status(
                f"Analysis cancelled: {self._analysis_done_count}/{self._analysis_total_count} "
                f"parsed | Partial results remain visible{error_text}"
            )
        else:
            self._set_progress_status(
                f"Scanned {self._analysis_done_count}/{self._analysis_total_count} | "
                f"Bytes scanned: {self._format_bytes(self._analysis_bytes_scanned)}{error_text}"
            )
        self._clear_progress_status(delay_ms=4000)

    def _restore_table_sorting(self):
        if self._table_sort_restore is None:
            return
        sorting_enabled, column, order = self._table_sort_restore
        self._table_sort_restore = None
        header = self.table.horizontalHeader()
        assert header is not None
        header.setSortIndicator(column, order)
        self.table.setSortingEnabled(sorting_enabled)

    def _reset_format_filter_items(self):
        self.format_filter_btn.blockSignals(True)
        try:
            self.format_filter_btn.clear_items()
            for ext in MODEL_FORMAT_FILTERS:
                self.format_filter_btn.ensure_item(ext)
        finally:
            self.format_filter_btn.blockSignals(False)

    def _update_analysis_progress(self, filepath: str):
        total = self._analysis_total_count
        self.progress.setValue(self._analysis_done_count)
        filename = Path(filepath).name if filepath else "-"
        error_text = (
            f" | Errors: {self._analysis_error_count}"
            if self._analysis_error_count
            else ""
        )
        self._set_progress_status(
            f"Scanning {self._analysis_done_count}/{total} | "
            f"Bytes scanned: {self._format_bytes(self._analysis_bytes_scanned)} | "
            f"{filepath or filename}{error_text}"
        )

    def _normalize_result_data(self, data: dict):
        arch = str(data.get("architecture") or "Unknown")
        if arch.startswith("GGUF "):
            data["architecture"] = arch[5:]
        try:
            data["file_size_friendly"] = format_size(int(data.get("file_size") or 0))
        except (TypeError, ValueError):
            data.setdefault("file_size_friendly", "-")
        try:
            data["total_params_friendly"] = format_params(
                int(data.get("total_params") or 0)
            )
        except (TypeError, ValueError):
            data.setdefault("total_params_friendly", "-")
        if not data.get("format"):
            suffix = Path(str(data.get("filepath") or "")).suffix.lower().lstrip(".")
            data["format"] = suffix.upper() if suffix else "UNKNOWN"
        if "is_moe" not in data:
            metadata = data.get("metadata") or {}
            arch_text = str(data.get("architecture") or "").lower()
            expert_count = None
            expert_used_count = None
            is_moe = "moe" in arch_text
            for key, value in metadata.items():
                lk = str(key).lower()
                if "expert" in lk or "moe" in lk:
                    is_moe = True
                try:
                    int_value = int(value)
                except (TypeError, ValueError):
                    int_value = None
                if lk.endswith(".expert_count"):
                    expert_count = int_value
                elif lk.endswith(".expert_used_count"):
                    expert_used_count = int_value
            data["is_moe"] = is_moe
            data["expert_count"] = expert_count
            data["expert_used_count"] = expert_used_count

    def _dump_modelinfo_targets(self) -> list[str]:
        selected = self._visible_selected_paths()
        if selected:
            return selected
        if self.tabs.currentIndex() == 2:
            current = _combo_data_str(self.raw_combo.currentData())
            if current:
                return [current]
        return []

    def _dump_all(self):
        """Write .modelinfo files for selected models or the current Raw model."""
        targets = self._dump_modelinfo_targets()
        if not targets:
            self._set_progress_status(
                "Select one or more models to dump, or open a model in Raw."
            )
            self._clear_progress_status(delay_ms=3500)
            return
        count = 0
        output_paths = []
        total = len(targets)
        self.progress.setVisible(True)
        self.progress.setRange(0, total)
        self.progress.setValue(0)
        self._set_progress_status(f"Writing .modelinfo: 0/{total}")
        QApplication.processEvents()
        for filepath in targets:
            if not filepath:
                continue
            data = self._result_for_filepath(filepath) or {}
            try:
                self._set_progress_status(
                    f"Writing .modelinfo: {count}/{total} | Current file: {Path(filepath).name}"
                )
                QApplication.processEvents()
                outputs = [write_modelinfo_dump(filepath)]
                if self._dump_json_modelinfo:
                    outputs.append(
                        write_modelinfo_json(
                            filepath,
                            options={
                                "allow_filename_alias_detection": self._allow_filename_alias_detection
                            },
                        )
                    )
                if data:
                    data["modelinfo_outputs"] = outputs
                output_paths.extend(outputs)
                count += 1
                self.progress.setValue(count)
            except Exception:
                pass
        if self._selected_action == "dump_modelinfo":
            self.selected_action_btn.setText(f"Dumped {count} file(s)")
        self._set_progress_status(f"Wrote .modelinfo for {count}/{total} file(s)")
        self._clear_progress_status(delay_ms=4000)
        if output_paths:
            preview = "\n".join(output_paths[:20])
            if len(output_paths) > 20:
                preview += f"\n...and {len(output_paths) - 20} more"
            self.selected_action_btn.setToolTip(
                f"Last .modelinfo output paths:\n{preview}"
            )
        QTimer.singleShot(3000, self._refresh_selected_action_button)

    # -- Cards view --------------------------------------------------------

    def _clear_cards(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.cards_placeholder.setStyleSheet(
            "color: #45475a; font-size: 14px; padding: 60px;"
        )
        self.cards_layout.insertWidget(0, self.cards_placeholder)

        while self.simple_cards_layout.count():
            item = self.simple_cards_layout.takeAt(0)
            if item is None:
                continue
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self.simple_cards_placeholder = QLabel(
            "No models analyzed yet.\nDrop files anywhere or click Open."
        )
        self.simple_cards_placeholder.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.simple_cards_placeholder.setStyleSheet(
            "color: #45475a; font-size: 14px; padding: 60px;"
        )
        self.simple_cards_layout.insertWidget(0, self.simple_cards_placeholder)
        self._refresh_card_layout_geometry()

    def _on_cards_view_changed(self, state):
        self._simple_cards_view = state == Qt.CheckState.Checked.value
        self._apply_cards_view_mode()
        self._rebuild_active_cards_time_sliced()

    def _apply_cards_view_mode(self):
        if not hasattr(self, "cards_scroll") or not hasattr(
            self, "simple_cards_scroll"
        ):
            return
        self.cards_scroll.setVisible(not self._simple_cards_view)
        self.simple_cards_scroll.setVisible(self._simple_cards_view)
        self._refresh_card_layout_geometry()

    def _add_card(self, data: dict):
        simple_view = self._simple_cards_view
        layout = self.simple_cards_layout if simple_view else self.cards_layout
        cards = self._path_to_simple_card if simple_view else self._path_to_card
        fp = str(data.get("filepath") or "")
        if fp and fp in cards:
            return
        placeholder_name = (
            "simple_cards_placeholder" if simple_view else "cards_placeholder"
        )
        placeholder = getattr(self, placeholder_name)
        if placeholder:
            layout.removeWidget(placeholder)
            placeholder.deleteLater()
            setattr(self, placeholder_name, None)

        card = ModelCard(
            data,
            simple_view=simple_view,
            card_fields=(
                self._simple_card_field_visibility
                if simple_view
                else self._card_field_visibility
            ),
        )
        card.selection_requested.connect(self._on_card_selection_requested)
        card.checkbox_toggled.connect(self._on_card_checkbox_toggled)
        card.drag_over_requested.connect(self._on_card_drag_over)
        card.context_requested.connect(self._on_card_context_menu)
        if fp:
            cards[fp] = card
        self._cards.append(card)
        layout.addWidget(card)

    def _rebuild_active_cards_time_sliced(self):
        self._card_rebuild_generation += 1
        generation = self._card_rebuild_generation
        self._cards.clear()
        self._path_to_card.clear()
        self._path_to_simple_card.clear()
        self._clear_cards()
        pending = list(self._results)
        index = 0

        def build_batch():
            nonlocal index
            if generation != self._card_rebuild_generation:
                return
            started = perf_counter()
            built = 0
            while index < len(pending) and built < 8:
                self._add_card(pending[index])
                index += 1
                built += 1
                if (perf_counter() - started) * 1000.0 >= 12.0:
                    break
            self._refresh_card_layout_geometry()
            if index < len(pending):
                QTimer.singleShot(0, build_batch)
            else:
                self._apply_arch_filter()
                self._sync_selection_visuals()

        QTimer.singleShot(0, build_batch)

    def _refresh_card_layout_geometry(self):
        self.cards_layout.invalidate()
        self.simple_cards_layout.invalidate()
        self.cards_container.adjustSize()
        self.simple_cards_container.adjustSize()
        self.cards_container.updateGeometry()
        self.simple_cards_container.updateGeometry()
        cards_viewport = self.cards_scroll.viewport()
        simple_cards_viewport = self.simple_cards_scroll.viewport()
        assert cards_viewport is not None
        assert simple_cards_viewport is not None
        cards_viewport.update()
        simple_cards_viewport.update()

    # -- Data table view ---------------------------------------------------

    def _add_table_row(self, data: dict):
        row = self.table.rowCount()
        self.table.insertRow(row)

        comps = data.get("components", {})
        component_precisions = data.get("component_precisions") or {}
        training_meta = data.get("training_meta", {})
        filepath = data.get("filepath", "")

        # UNet column
        unet_str = component_precisions.get("unet") or (
            "Yes" if comps.get("unet") else "-"
        )

        # Transformer column
        trans_str = component_precisions.get("transformer") or (
            "Yes" if comps.get("transformer") else "-"
        )

        # VAE column
        vae_str = component_precisions.get("vae") or (
            "Yes" if comps.get("vae") else "-"
        )

        # Text encoder column - precision labels for TE1/TE2 where available.
        text_enc_parts = []
        te1 = component_precisions.get("text_encoder")
        te2 = component_precisions.get("text_encoder_2")
        if te1:
            text_enc_parts.append(f"TE1: {te1}")
        if te2:
            text_enc_parts.append(f"TE2: {te2}")
        if not text_enc_parts:
            for enc_name in data.get("named_text_encoders", {}):
                text_enc_parts.append(enc_name)
            if not text_enc_parts:
                if comps.get("text_encoder") and comps.get("text_encoder_2"):
                    text_enc_parts = ["CLIP, CLIP 2"]
                elif comps.get("text_encoder"):
                    text_enc_parts = ["Yes"]
                elif comps.get("text_encoder_2"):
                    text_enc_parts = ["Text Enc 2"]
        text_enc_str = ", ".join(text_enc_parts) if text_enc_parts else "-"

        # LoRA rank
        lora_rank = data.get("lora_rank")
        rank_str = str(lora_rank) if lora_rank else "-"
        is_moe = bool(data.get("is_moe"))
        expert_count = data.get("expert_count")
        expert_used_count = data.get("expert_used_count")
        moe_str = "Yes" if is_moe else "-"
        expert_count_str = str(expert_count) if expert_count is not None else "-"
        expert_used_count_str = (
            str(expert_used_count) if expert_used_count is not None else "-"
        )

        values = [
            data["filename"],
            data.get("format", "-"),
            data["file_size_friendly"],
            data["architecture"],
            data["model_type"],
            data.get("adapter_type") or "-",
            data.get("quantization") or "-",
            data.get("precision_summary", "-"),
            unet_str,
            vae_str,
            text_enc_str,
            trans_str,
            data["total_params_friendly"],
            str(data["tensor_count"]),
            rank_str,
            moe_str,
            expert_count_str,
            expert_used_count_str,
            training_meta.get("software", "-"),
            training_meta.get("train_images", "-"),
            training_meta.get("resolution", "-"),
            training_meta.get("epochs", "-"),
            training_meta.get("steps", "-"),
        ]

        cb = QCheckBox()
        cb.clicked.connect(
            lambda checked, fp=filepath: self._on_table_checkbox_toggled(fp, checked)
        )
        self.table.setCellWidget(row, 0, cb)

        for col, val in enumerate(values, start=1):
            if col == 1 and self._show_full_paths and filepath:
                val = filepath
            item = SortableTableWidgetItem(val)
            item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
            column_name = self._table_columns[col]
            if col == 1:
                item.setToolTip(filepath)
                item.setData(Qt.ItemDataRole.UserRole, filepath)
            else:
                item.setToolTip(str(val))
            if column_name == "File Size":
                item.setData(Qt.ItemDataRole.UserRole, int(data.get("file_size") or 0))
            elif column_name == "Parameters":
                item.setData(
                    Qt.ItemDataRole.UserRole, int(data.get("total_params") or 0)
                )
            elif column_name == "Tensors":
                item.setData(
                    Qt.ItemDataRole.UserRole, int(data.get("tensor_count") or 0)
                )
            elif column_name == "LoRA Rank":
                item.setData(Qt.ItemDataRole.UserRole, int(lora_rank or 0))
            elif column_name == "MoE":
                item.setData(Qt.ItemDataRole.UserRole, 1 if is_moe else 0)
            elif column_name == "Experts":
                item.setData(Qt.ItemDataRole.UserRole, int(expert_count or 0))
            elif column_name == "Active Experts":
                item.setData(Qt.ItemDataRole.UserRole, int(expert_used_count or 0))
            elif column_name in ("Images", "Epochs", "Steps"):
                try:
                    numeric_value = int(str(val).replace(",", ""))
                except (TypeError, ValueError):
                    numeric_value = 0
                item.setData(Qt.ItemDataRole.UserRole, numeric_value)
            self.table.setItem(row, col, item)

        if filepath:
            self._path_to_row[filepath] = row

    def _visible_paths(self) -> list[str]:
        paths = []
        for row in range(self.table.rowCount()):
            if self.table.isRowHidden(row):
                continue
            item = self.table.item(row, 1)
            fp = item.data(Qt.ItemDataRole.UserRole) if item else None
            if not fp:
                continue
            paths.append(fp)
        return paths

    def _visible_selected_paths(self) -> list[str]:
        return [p for p in self._visible_paths() if p in self._selected_paths]

    def _row_for_filepath(self, filepath: str) -> int | None:
        row = self._path_to_row.get(filepath)
        if row is not None and 0 <= row < self.table.rowCount():
            item = self.table.item(row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == filepath:
                return row
        for scan_row in range(self.table.rowCount()):
            item = self.table.item(scan_row, 1)
            if item and item.data(Qt.ItemDataRole.UserRole) == filepath:
                self._path_to_row[filepath] = scan_row
                return scan_row
        return None

    def _on_table_sort_changed(self, *_):
        QTimer.singleShot(0, self._sync_order_from_table)

    def _sync_order_from_table(
        self, *, refresh_raw: bool = True, refresh_geometry: bool = True
    ):
        ordered_paths = []
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            fp = item.data(Qt.ItemDataRole.UserRole) if item else None
            if fp:
                ordered_paths.append(fp)
                self._path_to_row[fp] = row

        for layout, cards in (
            (self.cards_layout, self._path_to_card),
            (self.simple_cards_layout, self._path_to_simple_card),
        ):
            for fp in ordered_paths:
                card = cards.get(fp)
                if card:
                    layout.removeWidget(card)
                    layout.addWidget(card)
        if refresh_geometry:
            self._refresh_card_layout_geometry()
        if refresh_raw and hasattr(self, "raw_combo"):
            self._refresh_raw_combo_filtered()

    def _on_arch_filter_changed(self, active):
        self._active_arch_filter = None if active is None else set(active)
        self._apply_arch_filter()

    def _on_tag_filter_changed(self, active):
        self._active_tag_filter = None if active is None else set(active)
        self._apply_arch_filter()

    def _on_format_filter_changed(self, active):
        self._active_format_filter = None if active is None else set(active)
        self._apply_arch_filter()

    def _apply_arch_filter(
        self,
        *,
        refresh_raw: bool = True,
        refresh_geometry: bool = True,
        update_selection: bool = True,
    ):
        for data in self._results:
            fp = str(data.get("filepath") or "")
            if not fp:
                continue
            visible = self._is_data_visible(data)
            card = self._path_to_card.get(fp)
            if card:
                card.set_filter_visible(visible)
            scard = self._path_to_simple_card.get(fp)
            if scard:
                scard.set_filter_visible(visible)
            row = self._row_for_filepath(fp)
            if row is not None and 0 <= row < self.table.rowCount():
                self.table.setRowHidden(row, not visible)
        self._sync_order_from_table(
            refresh_raw=refresh_raw,
            refresh_geometry=refresh_geometry,
        )
        if update_selection:
            self._update_selection_ui_state()

    def _is_data_visible(self, data: dict) -> bool:
        active_arch = self._active_arch_filter
        active_tags = self._active_tag_filter
        active_formats = self._active_format_filter
        arch = data.get("architecture", "")
        tags = set(self._filter_tags_for_data(data))
        file_format = self._format_filter_for_data(data)
        return (
            ((active_arch is None) or (arch in active_arch))
            and ((active_tags is None) or bool(tags & active_tags))
            and ((active_formats is None) or (file_format in active_formats))
        )

    def _filter_tags_for_data(self, data: dict) -> list[str]:
        tags = []
        if data.get("architecture") == "ERROR":
            tags.append("ERROR")
            return list(dict.fromkeys(tags))
        model_type = data.get("model_type")
        if model_type:
            tags.append(str(model_type))
        adapter_type = data.get("adapter_type")
        if adapter_type:
            tags.append(str(adapter_type))
        if data.get("is_moe"):
            tags.append("MoE")
        quantization = data.get("quantization")
        if quantization:
            tags.append(str(quantization))
        return list(dict.fromkeys(tags))

    def _format_filter_for_data(self, data: dict) -> str:
        filepath = str(data.get("filepath") or "")
        suffix = Path(filepath).suffix.lower()
        if suffix:
            return suffix
        file_format = str(data.get("format") or "").strip().lower()
        if not file_format:
            return ".unknown"
        if file_format.startswith("."):
            return file_format
        return "." + file_format

    def _refresh_raw_combo_filtered(self):
        prev_fp = _combo_data_str(self.raw_combo.currentData())
        self.raw_combo.blockSignals(True)
        self.raw_combo.clear()
        for fp in self._visible_paths():
            data = self._result_for_filepath(fp)
            if not data:
                continue
            self.raw_combo.addItem(data.get("filename", Path(fp).name), fp)
        if prev_fp:
            idx = self.raw_combo.findData(prev_fp)
            if idx >= 0:
                self.raw_combo.setCurrentIndex(idx)
        self.raw_combo.blockSignals(False)
        if self.raw_combo.count() == 0:
            self.raw_text.clear()
        elif self.raw_combo.currentIndex() < 0:
            self.raw_combo.setCurrentIndex(0)
        else:
            current_fp = _combo_data_str(self.raw_combo.currentData())
            if current_fp != self._raw_loaded_filepath:
                if current_fp is not None:
                    self._show_raw_for_current_setting(current_fp)
        self._update_raw_controls()

    def _show_raw_for_filepath(self, filepath: str):
        if not filepath:
            return
        self._refresh_raw_combo_filtered()
        idx = self.raw_combo.findData(filepath)
        if idx >= 0:
            self.raw_combo.setCurrentIndex(idx)
        self.tabs.setCurrentIndex(2)
        self._show_raw_summary(filepath)

    def _step_raw_selection(self, delta: int):
        count = self.raw_combo.count()
        if count <= 0:
            return
        current = self.raw_combo.currentIndex()
        if current < 0:
            current = 0
        next_index = max(0, min(count - 1, current + delta))
        if next_index != current:
            self.raw_combo.setCurrentIndex(next_index)

    def _update_raw_controls(self):
        has_multiple = self.raw_combo.count() > 1
        self.raw_prev_btn.setEnabled(has_multiple and self.raw_combo.currentIndex() > 0)
        self.raw_next_btn.setEnabled(
            has_multiple and self.raw_combo.currentIndex() < self.raw_combo.count() - 1
        )
        self.raw_load_btn.setVisible(True)

    def _on_cards_select_all_changed(self, state):
        if self._syncing_selection:
            return
        checked = state == Qt.CheckState.Checked.value
        visible = set(self._visible_paths())
        if checked:
            self._selected_paths |= visible
        else:
            self._selected_paths -= visible
        self._sync_selection_visuals()

    def _on_table_select_all_changed(self, state):
        if self._syncing_selection:
            return
        checked = state == Qt.CheckState.Checked.value
        visible = set(self._visible_paths())
        if checked:
            self._selected_paths |= visible
        else:
            self._selected_paths -= visible
        self._sync_selection_visuals()

    def _on_card_checkbox_toggled(self, filepath: str, checked: bool):
        if self._syncing_selection or not filepath:
            return
        if checked:
            self._selected_paths.add(filepath)
        else:
            self._selected_paths.discard(filepath)
        self._sync_selection_visuals()

    def _on_card_selection_requested(self, filepath: str, modifiers):
        if not filepath:
            return
        visible = self._visible_paths()
        if filepath not in visible:
            return
        idx = visible.index(filepath)

        ctrl = bool(modifiers & Qt.KeyboardModifier.ControlModifier)
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        if (
            shift
            and self._last_selected_card_index >= 0
            and self._last_selected_card_index < len(visible)
        ):
            lo = min(self._last_selected_card_index, idx)
            hi = max(self._last_selected_card_index, idx)
            for fp in visible[lo : hi + 1]:
                self._selected_paths.add(fp)
        elif ctrl:
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_card_index = idx
        else:
            # Single-click behaves like ctrl-click toggle.
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_card_index = idx
        self._sync_selection_visuals()

    def _on_card_drag_over(self, filepath: str):
        if not filepath:
            return
        # Drag-over selection should only add to selection.
        if filepath not in self._selected_paths:
            self._selected_paths.add(filepath)
            self._sync_selection_visuals()

    def _find_result_by_path(self, filepath: str):
        for d in self._results:
            if d.get("filepath") == filepath:
                return d
        return None

    def _build_card_info_text(self, data: dict, simple_view: bool) -> str:
        lines = []
        lines.append(f"File: {data.get('filename', '')}")
        lines.append(f"Path: {data.get('filepath', '')}")
        lines.append(f"Architecture: {data.get('architecture', '')}")
        lines.append(f"Model Type: {data.get('model_type', '')}")
        if data.get("adapter_type"):
            lines.append(f"Adapter: {data.get('adapter_type')}")

        components = data.get("components", {})
        comp_labels = {
            "unet": "UNet",
            "transformer": "Transformer",
            "vae": "VAE",
            "text_encoder": "Text Encoder",
            "text_encoder_2": "Text Encoder 2",
        }
        comp_on = [lbl for k, lbl in comp_labels.items() if components.get(k)]
        if comp_on:
            lines.append("Tags: " + ", ".join(comp_on))

        fields = (
            self._simple_card_field_visibility
            if simple_view
            else self._card_field_visibility
        )
        if fields.get("parameters", True):
            lines.append(f"Parameters: {data.get('total_params_friendly', '-')}")
        if fields.get("precision", True):
            component_precisions = data.get("component_precisions") or {}
            added_component_precision = False
            component_precision_labels = [
                ("unet", "UNet Precision"),
                ("transformer", "Transformer Precision"),
                ("vae", "VAE Precision"),
                ("text_encoder", "Text Encoder Precision"),
                ("text_encoder_2", "Text Encoder 2 Precision"),
            ]
            for comp_key, comp_label in component_precision_labels:
                comp_precision = component_precisions.get(comp_key)
                if not comp_precision:
                    continue
                lines.append(f"{comp_label}: {comp_precision}")
                added_component_precision = True
            if not added_component_precision:
                precision_text = (
                    data.get("precision_display")
                    or data.get("component_precision_summary")
                    or data.get("precision_summary", "-")
                )
                lines.append(f"Precision: {precision_text}")
        if fields.get("file_size", True):
            lines.append(f"File Size: {data.get('file_size_friendly', '-')}")
        if fields.get("tensors", True):
            lines.append(f"Tensors: {data.get('tensor_count', '-')}")
        if fields.get("lora_rank", True):
            lr = data.get("lora_rank")
            if lr:
                lines.append(f"LoRA Rank: {lr}")
        if fields.get("extra_meta", True):
            for k, v in data.get("extra", {}).items():
                lines.append(f"{k.replace('_', ' ').title()}: {v}")
        if fields.get("training_meta", True):
            for k, v in data.get("training_meta", {}).items():
                lines.append(f"{k.replace('_', ' ').title()}: {v}")

        return "\n".join(lines)

    def _copy_selected_cards_info(self, simple_view: bool):
        paths = self._visible_selected_paths()
        if not paths:
            return
        blocks = []
        for fp in paths:
            d = self._find_result_by_path(fp)
            if not d:
                continue
            blocks.append(self._build_card_info_text(d, simple_view))
        if blocks:
            _clipboard().setText(("\n\n" + ("-" * 50) + "\n\n").join(blocks))

    def _on_card_context_menu(self, filepath: str, simple_view: bool, global_pos):
        data = self._find_result_by_path(filepath)
        if not data:
            return
        menu = QMenu(self)
        view_raw = menu.addAction("View Raw")
        copy_info = menu.addAction("Copy Info")
        copy_selected = None
        visible = set(self._visible_paths())
        selected_visible = [p for p in self._selected_paths if p in visible]
        if filepath in self._selected_paths and len(selected_visible) > 1:
            copy_selected = menu.addAction(
                f"Copy Info from selected files [{len(selected_visible)}]"
            )
        chosen = menu.exec(global_pos)
        if chosen == view_raw:
            self._show_raw_for_filepath(filepath)
        elif chosen == copy_info:
            _clipboard().setText(self._build_card_info_text(data, simple_view))
        elif copy_selected is not None and chosen == copy_selected:
            self._copy_selected_cards_info(simple_view)

    def _on_table_checkbox_toggled(self, filepath: str, checked: bool):
        if self._syncing_selection or not filepath:
            return
        if checked:
            self._selected_paths.add(filepath)
        else:
            self._selected_paths.discard(filepath)
        self._sync_selection_visuals()

    def _on_table_cell_clicked(self, row: int, col: int):
        if self._syncing_selection:
            return
        if row < 0 or row >= self.table.rowCount():
            return
        item = self.table.item(row, 1)
        if not item:
            return
        filepath = item.data(Qt.ItemDataRole.UserRole)
        if not filepath:
            return
        mods = QApplication.keyboardModifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        visible = self._visible_paths()
        if filepath not in visible:
            return
        idx = visible.index(filepath)
        if (
            shift
            and self._last_selected_row >= 0
            and self._last_selected_row < len(visible)
        ):
            lo = min(self._last_selected_row, idx)
            hi = max(self._last_selected_row, idx)
            for fp in visible[lo : hi + 1]:
                self._selected_paths.add(fp)
        elif ctrl:
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_row = idx
        else:
            # Single-click behaves like ctrl-click toggle.
            if filepath in self._selected_paths:
                self._selected_paths.remove(filepath)
            else:
                self._selected_paths.add(filepath)
            self._last_selected_row = idx
        self._sync_selection_visuals()

    def _on_table_item_selection_changed(self):
        # Keep this lightweight: item selection is mainly for Ctrl+C cells.
        pass

    def _on_table_context_menu(self, pos):
        item = self.table.itemAt(pos)
        if not item:
            return
        row = item.row()
        fp_item = self.table.item(row, 1)
        filepath = fp_item.data(Qt.ItemDataRole.UserRole) if fp_item else None

        menu = QMenu(self)
        view_raw = menu.addAction("View Raw")
        copy_folder_path = menu.addAction("Copy Folder Path")
        copy_sel = menu.addAction("Copy Selected Entries")
        viewport = self.table.viewport()
        assert viewport is not None
        chosen = menu.exec(viewport.mapToGlobal(pos))
        if chosen == view_raw and filepath:
            self._show_raw_for_filepath(filepath)
        elif chosen == copy_folder_path and filepath:
            _clipboard().setText(str(Path(filepath).parent))
        elif chosen == copy_sel:
            self._copy_selected_table_cells()

    def _sync_selection_visuals(self):
        self._syncing_selection = True
        try:
            for fp, card in self._path_to_card.items():
                card.set_selected(fp in self._selected_paths)
            for fp, card in self._path_to_simple_card.items():
                card.set_selected(fp in self._selected_paths)
            for fp, row in self._path_to_row.items():
                row = self._row_for_filepath(fp)
                if row is None:
                    continue
                if 0 <= row < self.table.rowCount():
                    cb = self.table.cellWidget(row, 0)
                    if isinstance(cb, QCheckBox):
                        cb.blockSignals(True)
                        cb.setChecked(fp in self._selected_paths)
                        cb.blockSignals(False)
        finally:
            self._syncing_selection = False
        self._update_selection_ui_state()

    def _update_selection_ui_state(self):
        visible = set(self._visible_paths())
        visible_selected_count = len(self._selected_paths & visible)
        total_selected_count = len(self._selected_paths)
        if total_selected_count == visible_selected_count:
            self.selected_count_label.setText(f"{visible_selected_count} selected")
        else:
            hidden_count = total_selected_count - visible_selected_count
            self.selected_count_label.setText(
                f"{visible_selected_count} selected ({hidden_count} hidden)"
            )
        enabled = visible_selected_count > 0
        self.selected_action_btn.setEnabled(enabled)
        self.selected_action_menu_btn.setEnabled(True)

        if visible:
            all_selected = visible.issubset(self._selected_paths)
        else:
            all_selected = False

        self.cards_select_all_cb.blockSignals(True)
        self.cards_select_all_cb.setChecked(all_selected)
        self.cards_select_all_cb.blockSignals(False)

        self.table_select_all_cb.blockSignals(True)
        self.table_select_all_cb.setChecked(all_selected)
        self.table_select_all_cb.blockSignals(False)

    def _copy_selected_files_to_clipboard(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        mime = QMimeData()
        from PyQt6.QtCore import QUrl

        urls = [QUrl.fromLocalFile(p) for p in selected]
        mime.setUrls(urls)
        _clipboard().setMimeData(mime)

    def _move_selected_files(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        target = QFileDialog.getExistingDirectory(self, "Select destination folder")
        if not target:
            return
        import shutil

        moved = set()
        for src in selected:
            try:
                dst = str(Path(target) / Path(src).name)
                shutil.move(src, dst)
                moved.add(src)
            except Exception:
                pass
        if moved:
            self._queued_files = [p for p in self._queued_files if p not in moved]
            self._results = [r for r in self._results if r.get("filepath") not in moved]
            self._selected_paths -= moved
            self._rebuild_views_from_results()
            self._update_file_count()

    def _remove_selected_results(self):
        selected = set(self._visible_selected_paths())
        if not selected:
            return
        self._queued_files = [p for p in self._queued_files if p not in selected]
        self._results = [r for r in self._results if r.get("filepath") not in selected]
        self._selected_paths -= selected
        self._rebuild_views_from_results()
        self._update_file_count()

    def _copy_selected_names(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        text = "\n".join(Path(p).name for p in selected)
        _clipboard().setText(text)

    def _copy_selected_paths(self):
        selected = self._visible_selected_paths()
        if not selected:
            return
        text = "\n".join(selected)
        _clipboard().setText(text)

    def _rebuild_views_from_results(self):
        current_results = list(self._results)
        header = self.table.horizontalHeader()
        assert header is not None
        sorting_enabled = self.table.isSortingEnabled()
        sort_column = header.sortIndicatorSection()
        sort_order = header.sortIndicatorOrder()
        self.table.setSortingEnabled(False)
        self._cards.clear()
        self._path_to_card.clear()
        self._path_to_simple_card.clear()
        self._path_to_row.clear()
        self._clear_cards()
        self.table.setRowCount(0)
        self.arch_filter_btn.clear_items()
        self.tag_filter_btn.clear_items()
        self._reset_format_filter_items()
        self.raw_combo.clear()
        for data in current_results:
            self._normalize_result_data(data)
            self._add_card(data)
            self._add_table_row(data)
            self.arch_filter_btn.add_item(data.get("architecture", "Unknown"))
            for tag in self._filter_tags_for_data(data):
                self.tag_filter_btn.add_item(tag)
            self.format_filter_btn.add_item(self._format_filter_for_data(data))
        header.setSortIndicator(sort_column, sort_order)
        self.table.setSortingEnabled(sorting_enabled)
        self._apply_arch_filter()
        self._refresh_raw_combo_filtered()
        self._sync_selection_visuals()

    def _on_show_full_path_changed(self, state):
        self._show_full_paths = state == Qt.CheckState.Checked.value
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 1)
            if not item:
                continue
            fp = item.data(Qt.ItemDataRole.UserRole) or ""
            if self._show_full_paths and fp:
                item.setText(fp)
            else:
                item.setText(Path(fp).name if fp else item.text())

    def _copy_selected_table_cells(self):
        indexes = [
            i
            for i in self.table.selectedIndexes()
            if not self.table.isRowHidden(i.row())
        ]
        if not indexes:
            return
        indexes.sort(key=lambda x: (x.row(), x.column()))

        by_row = {}
        for i in indexes:
            by_row.setdefault(i.row(), []).append(i.column())

        lines = []
        for row in sorted(by_row.keys()):
            cols = sorted(set(by_row[row]))
            vals = []
            for c in cols:
                if c == 0:
                    cb = self.table.cellWidget(row, c)
                    vals.append(
                        "1" if isinstance(cb, QCheckBox) and cb.isChecked() else "0"
                    )
                else:
                    it = self.table.item(row, c)
                    vals.append(it.text() if it else "")
            lines.append("\t".join(vals))
        _clipboard().setText("\n".join(lines))

    # -- Raw data view -----------------------------------------------------

    def _on_raw_selection_changed(self, index):
        if index < 0:
            self.raw_text.clear()
            self._raw_loaded_filepath = None
            return
        filepath = _combo_data_str(self.raw_combo.itemData(index))
        if not filepath:
            return
        self._update_raw_controls()
        self._show_raw_for_current_setting(filepath)

    def _show_raw_for_current_setting(self, filepath: str):
        analysis_running = bool(self._worker and self._worker.isRunning())
        if self._auto_load_raw_dump and not analysis_running:
            self._load_raw_dump(filepath)
        else:
            self._show_raw_summary(filepath)

    def _result_for_filepath(self, filepath: str) -> dict | None:
        for data in self._results:
            if data.get("filepath") == filepath:
                return data
        return None

    def _show_raw_summary(self, filepath: str):
        data = self._result_for_filepath(filepath)
        if not data:
            self.raw_text.setPlainText(
                "No inspection summary is available for this model."
            )
            self._raw_loaded_filepath = None
            return
        lines = [
            f"File: {data.get('filename', Path(filepath).name)}",
            f"Path: {filepath}",
        ]
        resolved = data.get("resolved_filepath")
        if resolved and resolved != filepath:
            lines.append(f"Resolved path: {resolved}")
        lines.extend(
            [
                f"Architecture: {data.get('architecture', 'Unknown')}",
                f"Model type: {data.get('model_type', 'Unknown')}",
                f"Size: {data.get('file_size_friendly', '-')}",
                f"Parameters: {data.get('total_params_friendly', '-')}",
                f"Tensors: {data.get('tensor_count', 0)}",
                f"Precision: {data.get('precision_display') or data.get('precision_summary', '-')}",
                "",
                "Full tensor key dump is not loaded automatically for large files.",
                "Click Load Full Dump to generate it.",
            ]
        )
        self.raw_text.setPlainText("\n".join(lines))
        self._raw_loaded_filepath = None

    def _load_selected_raw_dump(self):
        filepath = _combo_data_str(self.raw_combo.currentData())
        if not filepath:
            return
        self._load_raw_dump(filepath)

    def _load_raw_dump(self, filepath: str):
        cached_dump = get_cached_raw_dump(filepath)
        if cached_dump is not None:
            self.raw_text.setPlainText(cached_dump)
            self._raw_loaded_filepath = filepath
            self._set_progress_status(f"Loaded cached full dump: {Path(filepath).name}")
            self._clear_progress_status(delay_ms=1500)
            return

        try:
            self.progress.setVisible(True)
            self.progress.setRange(0, 0)
            self._set_progress_status(f"Loading full dump: {Path(filepath).name}")
            QApplication.processEvents()
            self.raw_load_btn.setEnabled(False)
            self.raw_load_btn.setText("Loading...")
            dump = generate_modelinfo_dump(filepath)
            store_raw_dump(filepath, dump)
            self.raw_text.setPlainText(dump)
            self._raw_loaded_filepath = filepath
        except Exception as e:
            if not Path(filepath).exists():
                self._show_raw_summary(filepath)
                self._set_progress_status(
                    f"No cached full dump/tensor data for unavailable file: {Path(filepath).name}"
                )
            else:
                self.raw_text.setPlainText(f"Error reading file:\n{e}")
            self._raw_loaded_filepath = None
        finally:
            self.raw_load_btn.setEnabled(True)
            self.raw_load_btn.setText("Load Full Dump")
            self._clear_progress_status(delay_ms=1500)

    def closeEvent(self, event):
        running_workers = {
            worker
            for worker in (self._worker, self._discovery_worker)
            if worker is not None and worker.isRunning()
        }
        if running_workers:
            event.ignore()
            if self._close_pending:
                return
            self._close_pending = True
            self._projection.invalidate()
            self._card_rebuild_generation += 1
            self._discovery_generation += 1
            self._startup_cache_load_cancelled = True
            self._restore_table_sorting()
            self._restore_startup_table_sorting()
            self._close_waiting_workers = running_workers
            for worker in running_workers:
                worker.finished.connect(
                    lambda w=worker: self._on_close_worker_finished(w)
                )
                worker.cancel()
                if not worker.isRunning():
                    self._on_close_worker_finished(worker)
            return

        self._close_pending = False
        self._close_waiting_workers.clear()
        self._projection.invalidate()
        self._card_rebuild_generation += 1
        self._discovery_generation += 1
        self._startup_cache_load_cancelled = True
        self._restore_table_sorting()
        self._restore_startup_table_sorting()
        super().closeEvent(event)

    def _on_close_worker_finished(self, worker):
        if worker not in self._close_waiting_workers:
            return
        self._close_waiting_workers.discard(worker)
        if self._close_pending and not self._close_waiting_workers:
            QTimer.singleShot(0, self.close)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(DARK_STYLE)
    app.setWindowIcon(QIcon(_asset("icon.ico")))

    window = MainWindow()
    window.show()
    if pyi_splash:
        pyi_splash.close()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
