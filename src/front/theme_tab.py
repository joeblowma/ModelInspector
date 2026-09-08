"""Live theme editing controls used by :mod:`front.settings_dialog`.

The widget deliberately keeps editing state in memory until an explicit Save
action.  Every preview is built from a validated ``Theme`` so a partially
typed or otherwise invalid color can never replace the application's current
stylesheet or corrupt a user theme file.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import re
from typing import Any

from PyQt6.QtCore import QRegularExpression, QSignalBlocker, pyqtSignal
from PyQt6.QtGui import QRegularExpressionValidator
from PyQt6.QtWidgets import (
    QFormLayout,
    QFrame,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
)

from back.theme_loader import BUILTIN_THEME, Theme, ThemeLoadResult, validate_theme
from back.theme_store import (
    ensure_bundled_themes,
    list_themes,
    load_theme,
    reset_user_themes,
    save_user_theme,
)

_THEME_ID_RE = re.compile(r"[a-z0-9][a-z0-9_-]{1,63}\Z")
_COLOR_RE = QRegularExpression(r"^#[0-9A-Fa-f]{0,8}$")
_REQUIRED_COLOR_ORDER = (
    "background",
    "surface",
    "surface_alt",
    "text",
    "muted",
    "accent",
    "accent_text",
    "border",
    "success",
    "warning",
    "error",
)


class ThemeTab(QWidget):
    """Select, preview, validate, and persist user-editable theme palettes."""

    themeChanged = pyqtSignal(str)
    themePreviewChanged = pyqtSignal(object)
    themesChanged = pyqtSignal()
    themeLoadFailed = pyqtSignal(str, object)
    themePersisted = pyqtSignal(str)
    validationMessage = pyqtSignal(str)

    theme_changed = themeChanged
    theme_preview_changed = themePreviewChanged
    themes_changed = themesChanged
    theme_load_failed = themeLoadFailed
    theme_persisted = themePersisted
    validation_message = validationMessage

    def __init__(
        self,
        selected_theme_id: str = "default",
        *,
        themes: Iterable[Any] | None = None,
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        self._supplied_themes = tuple(themes) if themes is not None else None
        self._themes: list[Theme] = []
        self._working_theme = BUILTIN_THEME
        self._last_load_result = ThemeLoadResult(BUILTIN_THEME)
        self._color_edits: dict[str, QLineEdit] = {}
        self._updating = False
        self._dirty = False
        self._reported_failures: set[tuple[str, tuple[str, ...]]] = set()
        self._build_ui()
        self.refresh_themes(selected_theme_id, emit=False)

    # ------------------------------------------------------------------ UI
    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(10)

        selection_group = QGroupBox("Theme selection")
        selection_group.setToolTip("Choose a validated built-in or writable user theme to preview and edit.")
        selection_layout = QFormLayout(selection_group)
        self.theme_combo = QComboBox()
        self.theme_selector = self.theme_combo
        self.theme_combo.setObjectName("themeEditorSelector")
        self.theme_combo.setToolTip("Select a theme. Changes are previewed immediately and saved only with an explicit action.")
        self.theme_combo.currentIndexChanged.connect(self._on_theme_combo_changed)
        selection_layout.addRow("Theme:", self.theme_combo)
        root.addWidget(selection_group)

        colors_group = QGroupBox("Theme colors")
        colors_group.setToolTip("Edit every required theme color as #RRGGBB or #RRGGBBAA. Invalid edits are previewed nowhere and are never saved.")
        colors_group_layout = QVBoxLayout(colors_group)
        colors_group_layout.setContentsMargins(8, 8, 8, 8)
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setToolTip("Scroll through the complete validated theme palette.")
        self._color_form_widget = QWidget()
        self._color_form = QFormLayout(self._color_form_widget)
        self._color_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
        scroll.setWidget(self._color_form_widget)
        colors_group_layout.addWidget(scroll, 1)
        root.addWidget(colors_group, 1)

        preview_group = QGroupBox("Live preview")
        preview_group.setToolTip("A representative preview of the current valid palette; the main application is updated at the same time.")
        preview_layout = QVBoxLayout(preview_group)
        self.preview_panel = QFrame()
        self.preview_panel.setObjectName("themePreviewPanel")
        self.preview_panel.setMinimumHeight(74)
        preview_row = QHBoxLayout(self.preview_panel)
        self.preview_title = QLabel("Model Inspector")
        self.preview_title.setObjectName("themePreviewTitle")
        self.preview_title.setToolTip("Preview title using the current accent color.")
        preview_row.addWidget(self.preview_title)
        self.preview_text = QLabel("Readable text")
        self.preview_text.setObjectName("themePreviewText")
        self.preview_text.setToolTip("Preview body text using the current text color.")
        preview_row.addWidget(self.preview_text)
        self.preview_status = QLabel("Success  •  Warning  •  Error")
        self.preview_status.setObjectName("themePreviewStatus")
        self.preview_status.setToolTip("Preview status colors from the current palette.")
        preview_row.addWidget(self.preview_status, 1)
        preview_layout.addWidget(self.preview_panel)
        root.addWidget(preview_group)

        actions = QHBoxLayout()
        self.save_button = QPushButton("Save")
        self.save_button.setObjectName("saveThemeButton")
        self.save_button.setToolTip("Save the current valid palette to its writable user theme file.")
        self.save_button.clicked.connect(self.save_current)
        self.save_btn = self.save_button
        actions.addWidget(self.save_button)
        self.save_as_button = QPushButton("Save As")
        self.save_as_button.setObjectName("saveAsThemeButton")
        self.save_as_button.setToolTip("Ask for a safe new theme id and create a separate writable user theme.")
        self.save_as_button.clicked.connect(self.save_as)
        self.save_as_btn = self.save_as_button
        actions.addWidget(self.save_as_button)
        self.reset_button = QPushButton("Reset to Defaults")
        self.reset_button.setObjectName("resetThemesButton")
        self.reset_button.setToolTip("Delete editable user themes and re-extract the bundled defaults after confirmation.")
        self.reset_button.clicked.connect(self.reset_to_defaults)
        self.reset_btn = self.reset_button
        actions.addWidget(self.reset_button)
        actions.addStretch()
        root.addLayout(actions)

        self.status_label = QLabel("")
        self.status_label.setObjectName("themeValidationMessage")
        self.status_label.setWordWrap(True)
        self.status_label.setToolTip("Theme validation, loading, and persistence messages appear here.")
        root.addWidget(self.status_label)

    # ------------------------------------------------------------ discovery
    @staticmethod
    def _coerce_theme(value: Any) -> Theme | None:
        if isinstance(value, Theme):
            return value
        if not isinstance(value, Mapping):
            return None
        raw = dict(value)
        valid, _errors = validate_theme(raw)
        if not valid:
            return None
        return Theme(
            str(raw["id"]),
            str(raw["name"]),
            {str(key): str(item) for key, item in raw["colors"].items()},
            str(raw.get("description") or ""),
            "user",
            {str(key): str(item) for key, item in (raw.get("variables") or {}).items()},
        )

    def _discover_themes(self) -> list[Theme]:
        try:
            ensure_bundled_themes()
            values = self._supplied_themes if self._supplied_themes is not None else list_themes()
            themes = [theme for value in values for theme in (self._coerce_theme(value),) if theme]
        except (OSError, TypeError, ValueError, AttributeError) as exc:
            self._report(f"Theme list unavailable; using Default Dark: {exc}")
            themes = []
        if not any(theme.id == BUILTIN_THEME.id for theme in themes):
            themes.append(BUILTIN_THEME)
        unique: dict[str, Theme] = {theme.id: theme for theme in themes}
        return sorted(unique.values(), key=lambda theme: (theme.name.casefold(), theme.id))

    def theme_choices(self) -> tuple[tuple[str, str], ...]:
        return tuple((theme.id, theme.name) for theme in self._themes)

    def refresh_themes(self, selected_theme_id: str | None = None, *, emit: bool = True) -> None:
        requested = str(selected_theme_id or self.current_theme_id() or "default")
        self._themes = self._discover_themes()
        blocker = QSignalBlocker(self.theme_combo)
        self.theme_combo.clear()
        for theme in self._themes:
            self.theme_combo.addItem(theme.name, theme.id)
        del blocker
        self._load_requested_theme(requested, emit=emit)
        self.themesChanged.emit()

    def _load_requested_theme(self, requested: str, *, emit: bool) -> None:
        result = load_theme(requested)
        self._last_load_result = result
        if result.used_fallback:
            self._report_theme_failure(requested, result)
        theme = result.theme
        if self.theme_combo.findData(theme.id) < 0:
            self.theme_combo.addItem(theme.name, theme.id)
        blocker = QSignalBlocker(self.theme_combo)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(theme.id))
        del blocker
        self._set_working_theme(theme)
        if emit:
            self.themeChanged.emit(theme.id)
            self.themePreviewChanged.emit(self._working_theme)

    def _report_theme_failure(self, requested: str, result: ThemeLoadResult) -> None:
        diagnostics = tuple(result.diagnostics) or ("the requested theme is unavailable",)
        key = (str(requested), diagnostics)
        self._report("Theme fallback: " + "; ".join(diagnostics))
        if key not in self._reported_failures:
            self._reported_failures.add(key)
            self.themeLoadFailed.emit(str(requested), diagnostics)

    # --------------------------------------------------------------- editing
    def _set_working_theme(self, theme: Theme) -> None:
        self._working_theme = Theme(
            theme.id,
            theme.name,
            dict(theme.colors),
            theme.description,
            theme.source,
            dict(theme.variables),
        )
        self._dirty = False
        self._updating = True
        try:
            while self._color_form.count():
                item = self._color_form.takeAt(0)
                if item is not None:
                    widget = item.widget()
                    if widget is not None:
                        widget.deleteLater()
            self._color_edits.clear()
            keys = [key for key in _REQUIRED_COLOR_ORDER if key in theme.colors]
            keys.extend(key for key in theme.colors if key not in keys)
            for key in keys:
                edit = QLineEdit(str(theme.colors[key]))
                edit.setObjectName(f"themeColor_{key}")
                edit.setMaxLength(9)
                edit.setValidator(QRegularExpressionValidator(_COLOR_RE, edit))
                edit.setToolTip(f"{key}: a validated #RRGGBB or #RRGGBBAA color. Invalid text is not applied or saved.")
                edit.textChanged.connect(lambda value, color_key=key: self._color_edited(color_key, value))
                self._color_edits[key] = edit
                self._color_form.addRow(f"{key.replace('_', ' ').title()}:", edit)
        finally:
            self._updating = False
        self._apply_preview()
        self.save_button.setEnabled(theme.id != BUILTIN_THEME.id)
        self.save_button.setToolTip(
            "Save the current valid palette to its writable user theme file."
            if theme.id != BUILTIN_THEME.id
            else "The built-in default cannot be overwritten; use Save As to create a user theme."
        )

    def _color_edited(self, key: str, value: str) -> None:
        if self._updating:
            return
        colors = dict(self._working_theme.colors)
        colors[key] = value.strip()
        raw = {
            "id": self._working_theme.id,
            "name": self._working_theme.name,
            "colors": colors,
            "description": self._working_theme.description,
            "variables": dict(self._working_theme.variables),
        }
        valid, errors = validate_theme(raw)
        if not valid:
            self._report("Invalid color edit: " + "; ".join(errors))
            return
        self._working_theme = Theme(
            self._working_theme.id,
            self._working_theme.name,
            colors,
            self._working_theme.description,
            self._working_theme.source,
            dict(self._working_theme.variables),
        )
        self._dirty = True
        self._apply_preview()
        self.themePreviewChanged.emit(self._working_theme)

    def _apply_preview(self) -> None:
        colors = self._working_theme.colors
        self.preview_panel.setStyleSheet(
            "QFrame#themePreviewPanel { background-color: %(background)s; border: 1px solid %(border)s; }"
            " QLabel#themePreviewTitle { color: %(accent)s; font-weight: bold; }"
            " QLabel#themePreviewText { color: %(text)s; }"
            " QLabel#themePreviewStatus { color: %(muted)s; }" % colors
        )
        self.preview_title.setStyleSheet("color: %s; font-weight: bold;" % colors["accent"])
        self.preview_text.setStyleSheet("color: %s;" % colors["text"])
        self.preview_status.setText(
            "<span style='color:%s'>Success</span>  " % colors["success"]
            + "<span style='color:%s'>Warning</span>  " % colors["warning"]
            + "<span style='color:%s'>Error</span>" % colors["error"]
        )
        self.preview_status.setStyleSheet("background-color: %s;" % colors["surface_alt"])

    # -------------------------------------------------------------- actions
    def current_theme_id(self) -> str:
        value = self.theme_combo.currentData()
        return str(value) if value is not None else self._working_theme.id

    def current_theme(self) -> Theme:
        return self._working_theme

    def set_theme(self, theme_id: str, *, emit: bool = True) -> bool:
        previous = self.current_theme_id()
        self._load_requested_theme(str(theme_id), emit=emit)
        return previous != self.current_theme_id()

    def save_current(self) -> bool:
        if self.current_theme_id() == BUILTIN_THEME.id:
            self._report("The built-in default is read-only; use Save As for a writable theme.")
            return False
        return self._persist_theme(self._working_theme)

    def save_as(self) -> bool:
        default_id = f"{self.current_theme_id()}_copy" if self.current_theme_id() else "custom_theme"
        theme_id, accepted = QInputDialog.getText(
            self,
            "Save Theme As",
            "New theme id (2-64 lowercase letters, digits, '_' or '-'): ",
            text=default_id,
        )
        if not accepted:
            return False
        theme_id = str(theme_id).strip()
        if not _THEME_ID_RE.fullmatch(theme_id):
            self._report("Theme id is invalid; nothing was saved.")
            QMessageBox.warning(self, "Save Theme As", "Use 2-64 lowercase letters, digits, '_' or '-'.")
            return False
        if theme_id in {key for key, _label in self.theme_choices()} and theme_id != self.current_theme_id():
            overwrite = QMessageBox.question(
                self,
                "Replace Theme",
                f"A user theme named {theme_id!r} already exists. Replace it?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if overwrite != QMessageBox.StandardButton.Yes:
                return False
        name = theme_id.replace("_", " ").replace("-", " ").title()
        candidate = Theme(
            theme_id,
            name,
            dict(self._working_theme.colors),
            self._working_theme.description,
            "user",
            dict(self._working_theme.variables),
        )
        return self._persist_theme(candidate)

    def _persist_theme(self, theme: Theme) -> bool:
        valid, errors = validate_theme({"id": theme.id, "name": theme.name, "colors": dict(theme.colors), "variables": dict(theme.variables)})
        if not valid:
            self._report("Theme was not saved: " + "; ".join(errors))
            return False
        try:
            save_user_theme(theme)
        except (OSError, TypeError, ValueError) as exc:
            self._report(f"Could not save theme: {exc}")
            QMessageBox.warning(self, "Theme Save", f"Could not save the theme: {exc}")
            return False
        self.refresh_themes(theme.id)
        self.themePersisted.emit(theme.id)
        return True

    def reset_to_defaults(self) -> bool:
        answer = QMessageBox.question(
            self,
            "Reset Themes",
            "This permanently deletes all editable user themes and restores bundled defaults. Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return False
        try:
            reset_user_themes()
            ensure_bundled_themes()
        except (OSError, TypeError, ValueError) as exc:
            self._report(f"Could not reset themes: {exc}")
            QMessageBox.warning(self, "Reset Themes", f"Could not reset themes: {exc}")
            return False
        self.refresh_themes("default")
        self.themePersisted.emit("default")
        return True

    def _on_theme_combo_changed(self, index: int) -> None:
        if self._updating or index < 0:
            return
        value = self.theme_combo.itemData(index)
        if value is not None:
            self.set_theme(str(value))

    def _report(self, message: str) -> None:
        self.status_label.setText(message)
        self.validationMessage.emit(message)

    @property
    def color_edits(self) -> dict[str, QLineEdit]:
        """Expose the live editor controls for focused Qt tests and callers."""
        return self._color_edits

    @property
    def last_load_result(self) -> ThemeLoadResult:
        return self._last_load_result
__all__ = ["ThemeTab"]
