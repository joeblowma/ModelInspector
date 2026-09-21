"""Settings dialog widget used by the Model Inspector GUI."""

import os

from PyQt6.QtCore import QSize, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QApplication,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from front.settings_data_tab import ColumnDefinition, SettingsDataTab
from front.theme_tab import ThemeTab
from back.theme_loader import get_global_theme_colors

__all__ = ["SettingsDialog"]

_DIALOG_DEFAULT_WIDTH = 900
_DIALOG_DEFAULT_HEIGHT = 640
_DIALOG_MINIMUM_WIDTH = 640
_DIALOG_MINIMUM_HEIGHT = 480
_DIALOG_SCREEN_MARGIN = 24
_DIALOG_DEFAULT_SIZE = (_DIALOG_DEFAULT_WIDTH, _DIALOG_DEFAULT_HEIGHT)
_DIALOG_MINIMUM_SIZE = (_DIALOG_MINIMUM_WIDTH, _DIALOG_MINIMUM_HEIGHT)


def _cache_task_running(window: object) -> bool:
    """True while a worker that reads/writes the model cache is active."""
    for name in ("_worker", "_cache_load_worker", "_cache_sync_worker"):
        worker = getattr(window, name, None)
        if worker is not None and getattr(worker, "isRunning", lambda: False)():
            return True
    return False


def _normalise_size(value: object) -> tuple[int, int] | None:
    """Parse a remembered dialog size from settings; None when unusable."""
    if isinstance(value, dict):
        first, second = value.get("width"), value.get("height")
    elif isinstance(value, (list, tuple)) and len(value) == 2:
        first, second = value[0], value[1]
    else:
        return None
    if first is None or second is None:
        return None
    try:
        width, height = int(first), int(second)
    except (TypeError, ValueError):
        return None
    return (width, height) if width > 0 and height > 0 else None


def _clamp_size_to_screen(size: tuple[int, int], screen) -> tuple[int, int]:
    """Clamp a size to the current screen's available geometry."""
    width, height = size
    if screen is not None:
        available = screen.availableGeometry()
        horizontal_margin = min(_DIALOG_SCREEN_MARGIN, available.width() // 12)
        vertical_margin = min(_DIALOG_SCREEN_MARGIN, available.height() // 12)
        width = min(width, max(1, available.width() - 2 * horizontal_margin))
        height = min(height, max(1, available.height() - 2 * vertical_margin))
    return (width, height)


class SettingsDialog(QDialog):
    themeChanged = pyqtSignal(str)
    themePreviewChanged = pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        allow_filename_alias_detection=False,
        dump_json_modelinfo=False,
        auto_load_raw_dump=False,
        cache_full_data_on_analyze=False,
        analysis_threads=2,
        add_mode="replace",
        default_tab="cards",
        card_fields=None,
        simple_card_fields=None,
        table_column_visibility=None,
        data_columns=None,
        data_configuration=None,
        theme_id=None,
        dialog_size=None,
    ):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setModal(True)
        # These legacy arguments remain accepted for direct callers, but card
        # fields are now fixed by the view mode rather than Settings.
        del card_fields, simple_card_fields

        root = QVBoxLayout(self)
        root.setSpacing(10)

        title = QLabel("Display Settings")
        self._theme_title = title
        self._muted_theme_labels: list[QLabel] = []
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        saved_data_configuration = data_configuration if isinstance(data_configuration, dict) else {}
        selected_theme_id = str(theme_id or saved_data_configuration.get("theme", "default"))
        self._accepted = False
        self._theme_restored = False
        self._theme_previewed = False
        self._theme_restore_id = selected_theme_id
        self.theme_tab = ThemeTab(selected_theme_id, parent=self)
        self.theme_editor_tab = self.theme_tab
        self._theme_restore_id = self.theme_tab.current_theme_id()
        self.theme_tab.themeChanged.connect(self._on_theme_tab_changed)
        self.theme_tab.themePreviewChanged.connect(self._on_theme_preview_changed)
        self.theme_tab.themeLoadFailed.connect(self._on_theme_load_failed)
        self.theme_tab.themePersisted.connect(self._on_theme_persisted)

        general_tab = QWidget()
        general_tab_layout = QVBoxLayout(general_tab)
        general_tab_layout.setContentsMargins(0, 0, 0, 0)
        general_tab_layout.setSpacing(10)

        general_group = QGroupBox("General")
        general_group.setToolTip("General application behavior settings.")
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
            self._muted_theme_labels.append(d)
            v.addWidget(d)
            return cell

        self.alias_checkbox = QCheckBox("Filename Alias Detection")
        self.alias_checkbox.setChecked(allow_filename_alias_detection)
        alias_cell = make_general_cell(
            self.alias_checkbox,
            "Fallback alias matching by filename for special naming cases. Supports ILXL, Illustrious, Illu, PDXL, Pony, Pony7, NAI, and Qwen Edit.",
        )

        self.dump_json_checkbox = QCheckBox("Also save JSON metadata")
        self.dump_json_checkbox.setChecked(dump_json_modelinfo)
        dump_json_cell = make_general_cell(
            self.dump_json_checkbox,
            "When saving readable metadata, also write a pretty-printed JSON file.",
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
        self.add_mode_combo.addItem("Replace", "replace")
        self.add_mode_combo.addItem("Append", "additive")
        self.add_mode_combo.setMinimumWidth(150)
        idx = self.add_mode_combo.findData(add_mode)
        if idx >= 0:
            self.add_mode_combo.setCurrentIndex(idx)
        mode_row.addWidget(self.add_mode_combo)
        mode_row.addStretch()
        mode_cell = make_general_cell(
            mode_wrap,
            "Replace clears the current model and queue. Append keeps existing and adds new ones.",
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
        self.default_tab_combo.setMinimumWidth(150)
        idx = self.default_tab_combo.findData(default_tab)
        if idx >= 0:
            self.default_tab_combo.setCurrentIndex(idx)
        tab_row.addWidget(self.default_tab_combo)
        tab_row.addStretch()
        tab_cell = make_general_cell(
            tab_wrap, "Choose which tab opens by default when the app starts."
        )

        g_layout.addWidget(alias_cell, 0, 0)
        g_layout.addWidget(mode_cell, 1, 0)
        g_layout.addWidget(tab_cell, 1, 1)
        g_layout.addWidget(dump_json_cell, 1, 2)
        g_layout.addWidget(raw_cell, 2, 0)
        g_layout.addWidget(thread_cell, 2, 1)
        g_layout.addWidget(cache_full_data_cell, 2, 2)
        general_tab_layout.addWidget(general_group)

        cache_group = QGroupBox("Cache")
        cache_layout = QHBoxLayout(cache_group)
        cache_layout.setSpacing(10)
        cache_note = QLabel("Clear parsed model summaries and cached tensor data.")
        self._muted_theme_labels.append(cache_note)
        cache_layout.addWidget(cache_note, 1)
        self.clear_cache_btn = QPushButton("Clear Cache")
        self.clear_cache_btn.setToolTip("Permanently remove cached inspection data after confirmation.")
        cache_layout.addWidget(self.clear_cache_btn)
        self.verify_cache_btn = QPushButton("Verify Cached File Paths")
        self.verify_cache_btn.setToolTip("Check cached file paths for availability and changes; no inspection is started for missing files.")
        cache_layout.addWidget(self.verify_cache_btn)
        self.cache_counts_label = QLabel("Total: 0  Active: 0  Historic: 0")
        self.cache_counts_label.setToolTip("Cached summaries by file availability. Historic files remain viewable without loading model payloads.")
        cache_layout.addWidget(self.cache_counts_label)
        general_tab_layout.addWidget(cache_group)

        cache_location_group = QGroupBox("Model Cache Location")
        cl_layout = QVBoxLayout(cache_location_group)
        cl_layout.setSpacing(8)
        cl_row = QHBoxLayout()
        cl_row.setSpacing(6)
        cl_row.addWidget(QLabel("Cache directory:"))
        self.cache_dir_combo = QComboBox()
        self.cache_dir_combo.setEditable(True)
        self.cache_dir_combo.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        self.cache_dir_combo.setMinimumWidth(320)
        self.cache_dir_combo.setToolTip(
            "Directory holding cached inspection summaries. Prior directories "
            "that still exist are listed; the most recently used becomes the "
            "default on next launch."
        )
        cl_row.addWidget(self.cache_dir_combo, 1)
        self.cache_dir_browse_btn = QPushButton("Browse...")
        self.cache_dir_browse_btn.clicked.connect(self._browse_cache_dir)
        cl_row.addWidget(self.cache_dir_browse_btn)
        cl_layout.addLayout(cl_row)
        cache_location_note = QLabel(
            "Changing the cache directory redirects the model cache only; "
            "settings and themes stay where they are."
        )
        cache_location_note.setWordWrap(True)
        self._muted_theme_labels.append(cache_location_note)
        cl_layout.addWidget(cache_location_note)
        general_tab_layout.addWidget(cache_location_group)
        self._populate_cache_dirs()
        general_tab_layout.addStretch()
        tabs.addTab(general_tab, "General")

        data_tab = QWidget()
        data_tab_layout = QVBoxLayout(data_tab)
        data_tab_layout.setContentsMargins(0, 0, 0, 0)
        data_tab_layout.setSpacing(10)
        # Kept as an empty compatibility mapping for callers from older UI code.
        self.table_column_checks = {}
        columns = data_columns or [
            ColumnDefinition(str(name), str(name), bool(visible))
            for name, visible in (table_column_visibility or {}).items()
        ]
        self.data_settings_tab = SettingsDataTab(columns)
        self.data_settings_tab.load_configuration(saved_data_configuration)
        data_tab_layout.addWidget(self.data_settings_tab, 1)
        tabs.addTab(data_tab, "Data Columns")

        tabs.addTab(self.theme_tab, "Theme")

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)
        self._apply_initial_size(dialog_size)
        self.refresh_theme()

        initial_result = self.theme_tab.last_load_result
        if initial_result.used_fallback and selected_theme_id not in {"default", "builtin"}:
            QTimer.singleShot(
                0,
                lambda requested=selected_theme_id, result=initial_result: self._on_theme_load_failed(
                    requested, result.diagnostics
                ),
            )

    def _resolve_screen(self):
        """Parent's screen, else this dialog's, else the primary screen."""
        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else None
        if screen is None:
            screen = self.screen()
        if screen is None:
            application = QApplication.instance()
            if isinstance(application, QApplication):
                screen = application.primaryScreen()
        return screen

    def _apply_initial_size(self, remembered=None) -> None:
        """Resize to the remembered/default size, clamped to the current screen.

        The dialog is resizable; the 900x640 default is kept when no valid
        remembered size exists, and the minimum is reduced on small screens.
        """
        screen = self._resolve_screen()
        minimum = _clamp_size_to_screen(_DIALOG_MINIMUM_SIZE, screen)
        minimum = (max(1, minimum[0]), max(1, minimum[1]))
        self.setMinimumSize(QSize(*minimum))
        width, height = _normalise_size(remembered) or _DIALOG_DEFAULT_SIZE
        width, height = _clamp_size_to_screen((width, height), screen)
        self.resize(QSize(max(width, minimum[0]), max(height, minimum[1])))

    def dialog_size(self) -> tuple[int, int]:
        """Current dialog size, persisted by the caller on close."""
        size = self.size()
        return (size.width(), size.height())

    # ------------------------------------------------------- cache location

    def _populate_cache_dirs(self) -> None:
        """Fill the cache-directory combo with the current and prior valid dirs."""
        from app_paths import legacy_settings_path, model_cache_dir, settings_path
        from back.cache_location import existing_cache_dir_history
        from back.settings_store import open_settings

        current = str(model_cache_dir())
        store = open_settings(
            settings_path(), legacy_settings_path(), defer_initial_save=True
        )
        dirs = list(existing_cache_dir_history(store))
        current_key = os.path.normcase(os.path.normpath(current))
        if current_key not in {
            os.path.normcase(os.path.normpath(raw)) for raw in dirs
        }:
            dirs.insert(0, current)
        self.cache_dir_combo.clear()
        for raw in dirs:
            self.cache_dir_combo.addItem(raw)
        self.cache_dir_combo.setCurrentText(current)

    def _browse_cache_dir(self) -> None:
        start = self.cache_dir_combo.currentText().strip() or os.path.expanduser("~")
        chosen = QFileDialog.getExistingDirectory(
            self, "Choose Model Cache Directory", start
        )
        if chosen:
            self.cache_dir_combo.setCurrentText(chosen)

    def _persist_cache_dir(self) -> bool:
        """Redirect the live model cache and record the selection in history.

        Returns False (and keeps the dialog open) when a cache worker is
        mid-read/write, so the model cache is never switched underneath it.
        The caller surfaces the busy state instead of silently dropping the
        user's selection.
        """
        text = self.cache_dir_combo.currentText().strip()
        if not text:
            return True
        from app_paths import model_cache_dir
        if os.path.normcase(os.path.normpath(text)) == os.path.normcase(
            os.path.normpath(str(model_cache_dir()))
        ):
            return True
        parent = self.parent()
        if parent is not None and _cache_task_running(parent):
            QMessageBox.warning(
                self,
                "Cache busy",
                "Wait for the current scan or cache load to finish before "
                "changing the model cache directory.",
            )
            return False
        from app_paths import legacy_settings_path, settings_path
        from back.cache_location import redirect_model_cache
        from back.settings_store import open_settings

        store = open_settings(
            settings_path(), legacy_settings_path(), defer_initial_save=True
        )
        redirect_model_cache(store, text)
        return True

    # ----------------------------------------------------------- theme bridge

    def refresh_theme(self, theme_colors: dict[str, str] | None = None) -> None:
        """Reapply inline title and explanatory-label colors after a live preview."""
        colors = dict(theme_colors or get_global_theme_colors())
        self._theme_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: %(accent_display)s;" % colors
        )
        for label in self._muted_theme_labels:
            label.setStyleSheet("color: %(muted)s; font-size: 11px;" % colors)

    def _on_theme_tab_changed(self, theme_id: str) -> None:
        self._theme_previewed = theme_id != self._theme_restore_id
        self.themeChanged.emit(theme_id)

    def _on_theme_preview_changed(self, theme) -> None:
        self._theme_previewed = True
        self.themePreviewChanged.emit(theme)

    def _on_theme_load_failed(self, requested: str, diagnostics: object) -> None:
        details = tuple(str(item) for item in (diagnostics if isinstance(diagnostics, (tuple, list)) else (diagnostics,)))
        message = "; ".join(details) or "the requested theme could not be loaded"
        key = (str(requested), message)
        if not hasattr(self, "_theme_diagnostic_keys"):
            self._theme_diagnostic_keys: set[tuple[str, str]] = set()
        if key in self._theme_diagnostic_keys:
            return
        self._theme_diagnostic_keys.add(key)
        QMessageBox.warning(
            self,
            "Theme unavailable",
            f"Theme {requested!r} could not be loaded. The safe default remains active.\n{message}",
        )

    def _on_theme_persisted(self, theme_id: str) -> None:
        """Keep explicit Save actions durable even if the dialog is cancelled."""
        self._theme_restore_id = str(theme_id)
        self._theme_restored = False

    def current_theme_id(self) -> str:
        return self.theme_tab.current_theme_id()

    def accept(self) -> None:  # type: ignore[override]
        if not self._persist_cache_dir():
            # A cache worker is running; keep the dialog open so the user can
            # retry after it finishes instead of silently losing the change.
            return
        self._accepted = True
        super().accept()

    def _restore_live_theme(self) -> None:
        if self._theme_restored or not self._theme_previewed:
            return
        self._theme_restored = True
        self.theme_tab.set_theme(self._theme_restore_id)

    def reject(self) -> None:  # type: ignore[override]
        if not self._accepted:
            self._restore_live_theme()
        super().reject()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if not self._accepted:
            self._restore_live_theme()
        super().closeEvent(event)
