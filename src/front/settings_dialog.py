"""Settings dialog widget used by the Model Inspector GUI."""

from PyQt6.QtCore import QSize, QTimer, pyqtSignal
from PyQt6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QApplication,
    QDialog,
    QDialogButtonBox,
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

__all__ = ["SettingsDialog"]

_DIALOG_FIXED_WIDTH = 900
_DIALOG_FIXED_HEIGHT = 640
_DIALOG_SCREEN_MARGIN = 12


class SettingsDialog(QDialog):
    themeChanged = pyqtSignal(str)
    themePreviewChanged = pyqtSignal(object)

    def __init__(
        self,
        parent=None,
        allow_filename_alias_detection=False,
        auto_analyze_on_add=True,
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
        title.setStyleSheet("font-size: 16px; font-weight: bold; color: #f5c2e7;")
        root.addWidget(title)

        tabs = QTabWidget()
        root.addWidget(tabs, 1)

        saved_data_configuration = data_configuration if isinstance(data_configuration, dict) else {}
        selected_theme_id = str(theme_id or saved_data_configuration.get("theme", "default"))
        self._accepted = False
        self._theme_restored = False
        self._theme_restore_id = selected_theme_id
        self.theme_tab = ThemeTab(selected_theme_id, parent=self)
        self.theme_editor_tab = self.theme_tab
        self._theme_restore_id = self.theme_tab.current_theme_id()
        self.theme_tab.themeChanged.connect(self._on_theme_tab_changed)
        self.theme_tab.themePreviewChanged.connect(self.themePreviewChanged.emit)
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
        g_layout.addWidget(analyze_cell, 0, 1)
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
        cache_note.setStyleSheet("color: #a6adc8; font-size: 11px;")
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
        self._set_fixed_initial_size()

        initial_result = self.theme_tab.last_load_result
        if initial_result.used_fallback and selected_theme_id not in {"default", "builtin"}:
            QTimer.singleShot(
                0,
                lambda requested=selected_theme_id, result=initial_result: self._on_theme_load_failed(
                    requested, result.diagnostics
                ),
            )

    def _set_fixed_initial_size(self) -> None:
        """Set the compact target, reducing it only for a small screen."""
        width = _DIALOG_FIXED_WIDTH
        height = _DIALOG_FIXED_HEIGHT

        parent = self.parentWidget()
        screen = parent.screen() if parent is not None else None
        if screen is None:
            screen = self.screen()
        if screen is None:
            application = QApplication.instance()
            if isinstance(application, QApplication):
                screen = application.primaryScreen()
        if screen is not None:
            available = screen.availableGeometry()
            horizontal_margin = min(_DIALOG_SCREEN_MARGIN, available.width() // 12)
            vertical_margin = min(_DIALOG_SCREEN_MARGIN, available.height() // 12)
            width = min(width, max(1, available.width() - 2 * horizontal_margin))
            height = min(height, max(1, available.height() - 2 * vertical_margin))

        self.setFixedSize(QSize(width, height))

    # ----------------------------------------------------------- theme bridge

    def _on_theme_tab_changed(self, theme_id: str) -> None:
        self.themeChanged.emit(theme_id)

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
        self._accepted = True
        super().accept()

    def _restore_live_theme(self) -> None:
        if self._theme_restored:
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
