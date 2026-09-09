# pyright: reportAttributeAccessIssue=false, reportArgumentType=false, reportCallIssue=false, reportGeneralTypeIssues=false
"""Core state, chrome, and file-management mixin for the main window.

This module intentionally has no dependency on ``gui.py``.  It is a
cooperative mixin: the eventual ``MainWindow`` must provide the remaining
analysis/view methods referenced by the signal callbacks and include
``WindowLayoutMixin`` somewhere in its base list.
"""

import json
import sys
from pathlib import Path

from PyQt6.QtCore import QEvent, QTimer, Qt
from PyQt6.QtGui import (
    QAction,
    QClipboard,
    QDragEnterEvent,
    QDropEvent,
    QIcon,
    QKeyEvent,
)
from PyQt6.QtWidgets import (
    QApplication,
    QMenu,
)

from app_paths import legacy_settings_path, settings_path
from back.settings_store import open_settings
from back.checkpoint_reader import CHECKPOINT_SAFETY_METADATA
from background_tasks import AnalysisWorker, DiscoveryWorker
from front.model_card import ModelCard
from front.scan_projection import ScanProjectionBuffer
# Keep these imports local to the extracted GUI layer.  The model reader is
# the single source of format policy.
from model_readers import (
    SUPPORTED_MODEL_EXTENSIONS,
    is_checkpoint_model_path,
    is_supported_model_path,
)


MODEL_FORMAT_FILTERS = (".safetensors", ".gguf", ".ckpt", ".onnx", ".pt", ".pth")


def _clipboard() -> QClipboard:
    clipboard = QApplication.clipboard()
    assert clipboard is not None
    return clipboard


def _combo_data_str(value) -> str | None:
    return str(value) if value else None


def _model_file_filter() -> str:
    patterns = " ".join((*[f"*{ext}" for ext in SUPPORTED_MODEL_EXTENSIONS], "*.safetensors.index.json"))
    checkpoint_patterns = " ".join(
        f"*{ext}" for ext in MODEL_FORMAT_FILTERS if ext not in SUPPORTED_MODEL_EXTENSIONS
    )
    return (
        f"Supported Model Files ({patterns});;"
        f"Checkpoint Files - metadata-only inspection ({checkpoint_patterns});;"
        "All Files (*)"
    )


def _settings():
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return open_settings(path, legacy_settings_path())


def _asset(name: str) -> str:
    """Resolve an asset in development and in a PyInstaller bundle."""
    if getattr(sys, "_MEIPASS", None):
        base = Path(sys._MEIPASS)
    else:
        base = Path(__file__).parent.parent.parent
    return str(base / "assets" / name)


class WindowCoreMixin:
    """Initialize shared state and implement shell-level window behavior."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle("Model Inspector")
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
        # Compatibility state for lifecycle/cache code; compact Cards no longer
        # materialize a second detailed-card view.
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
        self._progress_status_generation = 0
        self._allow_filename_alias_detection = False
        self._show_full_paths = False
        self._auto_analyze_on_add = True
        self._dump_json_modelinfo = False
        self._auto_load_raw_dump = False
        self._cache_full_data_on_analyze = False
        self._selected_action = "copy_files"
        self._analysis_threads = 2
        self._add_mode = "replace"
        self._default_tab = "cards"
        self._table_column_visibility_pref: dict[str, bool] = {}
        self._load_ui_settings()

        self._projection = ScanProjectionBuffer(
            self._project_scan_event,
            self._reconcile_projected_results,
            self._finish_analysis_projection,
            parent=self,
        )
        self._build_window_layout()
        self._configure_extended_ui()

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
        menu.addSeparator()
        self._cache_load_active_action = self._add_menu_action(
            menu, "Load Cache", self._load_cache
        )
        self._cache_load_all_action = self._add_menu_action(
            menu, "Load Cache All", self._load_cache_all
        )
        self._cache_load_archived_action = self._add_menu_action(
            menu, "Load Cache Archived", self._load_cache_archived
        )
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
            self._copy_selected_cards_info(True)
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
        checkpoints = []
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
                checkpoints.append(fp)
        paths.extend(checkpoints)
        if folders:
            self._start_discovery(
                folders,
                paths,
                checkpoint_safety=CHECKPOINT_SAFETY_METADATA,
            )
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
            "cache_full_data_on_analyze", str(self._cache_full_data_on_analyze).lower()
        )
        s.setValue("analysis_threads", str(self._analysis_threads))
        s.setValue("add_mode", self._add_mode)
        s.setValue("default_tab", self._default_tab)
        col_vis = {}
        for idx, name in enumerate(self._table_columns):
            if idx == 0:
                continue
            col_vis[name] = self._persisted_column_visible(idx)
        s.setValue("table_columns", json.dumps(col_vis))

    def _apply_table_column_visibility(self):
        if not self._table_column_visibility_pref:
            return
        for name, visible in self._table_column_visibility_pref.items():
            if name in self._table_columns:
                idx = self._table_columns.index(name)
                self.table.setColumnHidden(idx, not bool(visible))

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
        busy = bool(self._worker and self._worker.isRunning()) or self.progress.isVisible()
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


# Short names make the intended cooperative base order explicit to callers.
CoreMixin = WindowCoreMixin
