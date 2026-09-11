"""Advanced model facts and resource projection viewer.

The viewer deliberately has no application-startup side effects.  A caller can
construct it with a normal :class:`QDialog` parent, provide inspection metadata
through :meth:`set_inspection`, and either call ``exec()`` or embed the widget
in a test harness.  Qt for Python is preferred when installed; this project
currently ships PyQt6, so a compatibility fallback keeps the public widget
usable in the existing application.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any, cast

if TYPE_CHECKING:
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import (
        QApplication,
        QComboBox,
        QDialog,
        QDialogButtonBox,
        QDoubleSpinBox,
        QFormLayout,
        QGridLayout,
        QGroupBox,
        QHBoxLayout,
        QLabel,
        QPushButton,
        QScrollArea,
        QSizePolicy,
        QSpinBox,
        QTabWidget,
        QVBoxLayout,
        QWidget,
    )
else:
    # Dynamic imports keep static Qt types coherent while allowing a PyQt6
    # installation to run the same widget when PySide6 is unavailable.
    import importlib
    import sys

    # Reuse whichever binding the host application already loaded.  This is
    # important when both bindings happen to be installed: Qt widget objects
    # from the two bindings cannot be mixed in one QApplication.
    _prefer_pyqt = "PyQt6.QtWidgets" in sys.modules and "PySide6.QtWidgets" not in sys.modules
    try:
        _binding = "PyQt6" if _prefer_pyqt else "PySide6"
        _qt_core = importlib.import_module(f"{_binding}.QtCore")
        _qt_widgets = importlib.import_module(f"{_binding}.QtWidgets")
    except ImportError:  # pragma: no cover - exercised on the project's PyQt6 env.
        _qt_core = importlib.import_module("PyQt6.QtCore")
        _qt_widgets = importlib.import_module("PyQt6.QtWidgets")
    Qt = _qt_core.Qt
    QApplication = _qt_widgets.QApplication
    QComboBox = _qt_widgets.QComboBox
    QDialog = _qt_widgets.QDialog
    QDialogButtonBox = _qt_widgets.QDialogButtonBox
    QDoubleSpinBox = _qt_widgets.QDoubleSpinBox
    QFormLayout = _qt_widgets.QFormLayout
    QGridLayout = _qt_widgets.QGridLayout
    QGroupBox = _qt_widgets.QGroupBox
    QHBoxLayout = _qt_widgets.QHBoxLayout
    QLabel = _qt_widgets.QLabel
    QPushButton = _qt_widgets.QPushButton
    QScrollArea = _qt_widgets.QScrollArea
    QSizePolicy = _qt_widgets.QSizePolicy
    QSpinBox = _qt_widgets.QSpinBox
    QTabWidget = _qt_widgets.QTabWidget
    QVBoxLayout = _qt_widgets.QVBoxLayout
    QWidget = _qt_widgets.QWidget

    # ExplorerTab is PyQt6-based because it is also hosted by the main window.
    # Keep this dialog in that same binding rather than mixing QWidget types.
    _qt_core = importlib.import_module("PyQt6.QtCore")
    _qt_widgets = importlib.import_module("PyQt6.QtWidgets")
    Qt = _qt_core.Qt
    QApplication = _qt_widgets.QApplication
    QComboBox = _qt_widgets.QComboBox
    QDialog = _qt_widgets.QDialog
    QDialogButtonBox = _qt_widgets.QDialogButtonBox
    QDoubleSpinBox = _qt_widgets.QDoubleSpinBox
    QFormLayout = _qt_widgets.QFormLayout
    QGridLayout = _qt_widgets.QGridLayout
    QGroupBox = _qt_widgets.QGroupBox
    QHBoxLayout = _qt_widgets.QHBoxLayout
    QLabel = _qt_widgets.QLabel
    QPushButton = _qt_widgets.QPushButton
    QScrollArea = _qt_widgets.QScrollArea
    QSizePolicy = _qt_widgets.QSizePolicy
    QSpinBox = _qt_widgets.QSpinBox
    QTabWidget = _qt_widgets.QTabWidget
    QVBoxLayout = _qt_widgets.QVBoxLayout
    QWidget = _qt_widgets.QWidget

from back.estimator import (
    ModelFacts,
    ResourceProjection,
    facts_from_inspection,
    project_resources,
    runtime_configuration,
)
from back.theme_loader import get_global_theme_colors
from front.advanced_viewer_layout import build_advanced_viewer_ui
from front.explorer_tab import ExplorerTab, normalize_tensor_descriptors
from front.metadata_ui import (
    HeaderInspectionController, capability_badge_values, domain_badge_values,
)
from front.model_card import ModelCard

__all__ = ["AdvancedViewer", "AdvancedViewerDialog", "AdvancedViewerPopup"]


_ADVANCED_VIEWER_COLORS: dict[str, tuple[str, str]] | None = None


def _get_advanced_viewer_colors() -> dict[str, tuple[str, str]]:
    """Return badge colors derived from the current theme."""
    global _ADVANCED_VIEWER_COLORS
    if _ADVANCED_VIEWER_COLORS is None:
        tc = get_global_theme_colors()
        _ADVANCED_VIEWER_COLORS = {
            "capability": (tc["accent"], tc["accent_text"]),
            "domain": (tc["success"], tc["accent_text"]),
            "missing": (tc["border"], tc["text"]),
        }
    return _ADVANCED_VIEWER_COLORS


_UNKNOWN = "Unknown"
_MINIMUM_OVERVIEW_CARD_HEIGHT = 72
_BADGE_COLORS = {
    "capability": ("#89b4fa", "#11111b"),
    "domain": ("#a6e3a1", "#11111b"),
    "missing": ("#585b70", "#cdd6f4"),
}


class AdvancedViewerDialog(QDialog):
    """Parent-owned, window-modal viewer for model facts and exploration."""

    def __init__(
        self,
        parent: QWidget | Mapping[str, Any] | None = None,
        inspection: Mapping[str, Any] | None = None,
        *,
        card_fields: Mapping[str, bool] | None = None,
    ):
        # Accept ``AdvancedViewerDialog(inspection)`` as a convenient, safe
        # shorthand while retaining normal QDialog(parent, ...) semantics.
        if inspection is None and isinstance(parent, Mapping):
            inspection = parent
            parent = None
        super().__init__(cast(QWidget | None, parent))
        self.setWindowTitle("Advanced Model Viewer")
        self.setWindowModality(Qt.WindowModality.WindowModal)
        self.setMinimumSize(620, 620)
        self.resize(840, 760)
        self._inspection: dict[str, Any] = {}
        self._facts = ModelFacts()
        self._projection: ResourceProjection | None = None
        # Keep this keyword accepted for compatibility with older callers.
        # Card rendering now has a fixed all-statistics advanced policy.
        del card_fields
        self._card_details_card: ModelCard | None = None
        self._capability_badges: list[QLabel] = []
        self._domain_badges: list[QLabel] = []
        self._build_ui()
        self.set_inspection(dict(inspection) if isinstance(inspection, Mapping) else {})

    def _build_ui(self) -> None:
        build_advanced_viewer_ui(self)

    def set_inspection(self, inspection: Mapping[str, Any] | None) -> None:
        """Replace inspected metadata and refresh facts, badges, and projection."""
        self._inspection = dict(inspection) if isinstance(inspection, Mapping) else {}
        self._header_controller.replace_inspection()
        self._facts = facts_from_inspection(self._inspection)
        self._update_card_details()
        tensors = self._tensor_data_from_inspection(self._inspection)
        self.explorer_tab.set_inspection(
            self._inspection, tensors, payload_available=False
        )
        self._header_controller.request_if_needed()
        self._update_summary()
        self._replace_badges(self._capability_row, self._capability_badges, capability_badge_values(self._inspection, self._facts.capabilities), "capability")
        self._replace_badges(self._domain_row, self._domain_badges, domain_badge_values(self._inspection, self._facts.domains), "domain")

        context = self._facts.max_context or 4096
        self.context_spin.blockSignals(True)
        self.context_spin.setValue(max(1, min(int(context), self.context_spin.maximum())))
        self.context_spin.blockSignals(False)
        self.batch_spin.blockSignals(True)
        self.batch_spin.setValue(1)
        self.batch_spin.blockSignals(False)
        self._set_initial_quantization()
        self._recalculate()

    @staticmethod
    def _tensor_data_from_inspection(inspection: Mapping[str, Any]) -> Any:
        """Select the first usable descriptor container from any safe reader."""
        for key in ("tensor_info", "tensors", "tensor_data", "descriptors", "headers"):
            candidate = inspection.get(key)
            if normalize_tensor_descriptors(candidate):
                return candidate
        return {}

    def _update_card_details(self) -> None:
        if self._card_details_card is not None:
            self._card_details_content_layout.removeWidget(cast(Any, self._card_details_card))
            self._card_details_card.deleteLater()
        data = dict(self._inspection)
        data.setdefault("filename", str(data.get("filepath") or "Unknown model").replace("\\", "/").rsplit("/", 1)[-1])
        data.setdefault("architecture", "Unknown")
        data.setdefault("model_type", "Unknown")
        data.setdefault("components", {})
        data.setdefault("named_text_encoders", {})
        data.setdefault("total_params_friendly", self._facts.total_params_display)
        data.setdefault("file_size_friendly", "-")
        data.setdefault("tensor_count", "-")
        data.setdefault("training_meta", {})
        data.setdefault("extra", {})
        self._card_details_card = ModelCard(data, vertical_stats=True)
        self._card_details_card.select_cb.hide()
        self._card_details_content_layout.addWidget(cast(Any, self._card_details_card))

    def _update_summary(self) -> None:
        facts = self._facts
        values = {
            "architecture": facts.architecture,
            "layer_count": self._number_text(facts.layer_count),
            "block_counts": self._mapping_text(facts.block_counts),
            "experts_total": self._number_text(facts.expert_count),
            "experts_active": self._number_text(facts.active_expert_count),
            "trained_context": self._context_text(facts.trained_context),
            "max_context": self._context_text(facts.max_context),
            "rope": self._mapping_text(facts.rope),
            "mtp": self._mapping_text(facts.mtp),
        }
        for key, value in values.items():
            self._summary_values[key].setText(str(value) if value not in (None, "") else _UNKNOWN)

    def _set_initial_quantization(self) -> None:
        raw = self._inspection.get("quantization")
        text = str(raw or "").lower()
        if not text:
            self.quantization_combo.setCurrentIndex(0)
            self.weight_bits_spin.setValue(16.0)
            return
        index = 0
        for candidate in range(1, self.quantization_combo.count()):
            data = self.quantization_combo.itemData(candidate)
            if data and (f"q{data:g}" in text or (data == 16 and "16" in text) or (data == 32 and "32" in text)):
                index = candidate
                break
        self.quantization_combo.blockSignals(True)
        self.quantization_combo.setCurrentIndex(index)
        self.quantization_combo.blockSignals(False)
        bits = self.quantization_combo.itemData(index) or 16
        self.weight_bits_spin.setValue(float(bits))

    def _quantization_changed(self, index: int) -> None:
        bits = self.quantization_combo.itemData(index)
        if bits is not None:
            self.weight_bits_spin.blockSignals(True)
            self.weight_bits_spin.setValue(float(bits))
            self.weight_bits_spin.blockSignals(False)
        self._recalculate()

    def _recalculate(self, *_args: Any) -> None:
        self._projection = project_resources(
            self._inspection,
            context_length=self.context_spin.value(),
            batch_size=self.batch_spin.value(),
            weight_bits=self.weight_bits_spin.value(),
            kv_cache_bits=self.kv_cache_bits_combo.currentData(),
            kv_cache_dtype=self.kv_cache_bits_combo.currentText(),
        )
        projection = self._projection
        for key, value in (("weight", projection.weight_display), ("kv_cache", projection.kv_cache_display), ("vram", projection.vram_display), ("ram", projection.ram_display)):
            self._projection_values[key].setText(value)
        self.assumptions_label.setText("; ".join(projection.assumptions) if projection.assumptions else "None")

    def copy_configuration(self) -> str:
        """Copy and return the current human-readable runtime configuration."""
        if self._projection is None:
            self._recalculate()
        assert self._projection is not None
        text = runtime_configuration(self._projection, self._facts, self._inspection)
        self._last_configuration = text
        app = cast(QApplication | None, QApplication.instance())
        if app is not None and app.clipboard() is not None:
            app.clipboard().setText(text)
        return text

    @staticmethod
    def _number_text(value: int | None) -> str:
        return f"{value:,}" if value is not None else _UNKNOWN

    @classmethod
    def _context_text(cls, value: int | None) -> str:
        return f"{value:,} tokens" if value is not None else _UNKNOWN

    @staticmethod
    def _mapping_text(value: Mapping[str, Any]) -> str:
        if not value:
            return _UNKNOWN
        return ", ".join(f"{key}={item}" for key, item in value.items())

    @staticmethod
    def _make_badge(text: str, kind: str) -> QLabel:
        colors = _get_advanced_viewer_colors()
        foreground, background = colors.get(kind, colors["missing"])
        badge = QLabel(text)
        badge.setProperty("badge_kind", kind)
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        badge.setStyleSheet(
            f"background-color: {foreground}; color: {background}; padding: 3px 9px; "
            "border-radius: 5px; font-size: 11px; font-weight: bold;"
        )
        badge.setToolTip(f"Detected {kind}: {text}.")
        return badge

    @staticmethod
    def _refresh_badge_style(badge: QLabel, kind: str) -> None:
        foreground, background = _get_advanced_viewer_colors().get(
            kind, _get_advanced_viewer_colors()["missing"]
        )
        badge.setStyleSheet(
            f"background-color: {foreground}; color: {background}; padding: 3px 9px; "
            "border-radius: 5px; font-size: 11px; font-weight: bold;"
        )

    def _replace_badges(self, row: QHBoxLayout, old: list[QLabel], values: tuple[str, ...], kind: str) -> None:
        for badge in old:
            row.removeWidget(badge)
            badge.deleteLater()
        old.clear()
        entries = values or (_UNKNOWN,)
        for value in entries:
            badge = self._make_badge(value, kind if value != _UNKNOWN else "missing")
            row.insertWidget(max(0, row.count() - 1), badge)
            old.append(badge)

    def _refresh_style(self, theme_colors: dict[str, str] | None = None) -> None:
        """Re-apply theme colors to summary/projection labels."""
        tc = theme_colors or get_global_theme_colors()
        for label in getattr(self, "_overview_muted_labels", ()):
            label.setStyleSheet("color: %(muted)s; font-size: 11px;" % tc)
        for key, value in self._summary_values.items():
            if key in ("architecture", "layer_count", "block_counts", "experts_total", "experts_active", "trained_context", "max_context", "rope", "mtp"):
                value.setStyleSheet("color: %(text)s; font-size: 13px; font-weight: bold;" % tc)
        for key, value in self._projection_values.items():
            if key == "weight":
                value.setStyleSheet("color: %(accent_display)s; font-size: 13px; font-weight: bold;" % tc)
            elif key == "kv_cache":
                value.setStyleSheet("color: %(accent_display)s; font-size: 13px; font-weight: bold;" % tc)
            elif key == "vram":
                value.setStyleSheet("color: %(accent_display)s; font-size: 13px; font-weight: bold;" % tc)
            elif key == "ram":
                value.setStyleSheet("color: %(accent_display)s; font-size: 13px; font-weight: bold;" % tc)
        self.assumptions_label.setStyleSheet("color: %(warning)s; font-size: 11px;" % tc)

    def refresh_theme(self) -> None:
        """Refresh cached viewer colors, badges, inline labels, and Explorer."""
        global _ADVANCED_VIEWER_COLORS
        _ADVANCED_VIEWER_COLORS = None
        theme_colors = get_global_theme_colors()
        self._refresh_style(theme_colors)
        for badge in (*self._capability_badges, *self._domain_badges):
            kind = str(badge.property("badge_kind") or "missing")
            self._refresh_badge_style(badge, kind)
        card = self._card_details_card
        if card is not None and hasattr(card, "_refresh_style"):
            card._refresh_style()
        explorer = getattr(self, "explorer_tab", None)
        if explorer is not None and hasattr(explorer, "refresh_theme"):
            explorer.refresh_theme(theme_colors)


AdvancedViewerPopup = AdvancedViewerDialog
AdvancedViewer = AdvancedViewerDialog
