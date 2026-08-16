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
    QVBoxLayout = _qt_widgets.QVBoxLayout
    QWidget = _qt_widgets.QWidget

from back.estimator import (
    ModelFacts,
    ResourceProjection,
    facts_from_inspection,
    project_resources,
    runtime_configuration,
)

__all__ = ["AdvancedViewer", "AdvancedViewerDialog", "AdvancedViewerPopup"]


_UNKNOWN = "Unknown"
_BADGE_COLORS = {
    "capability": ("#89b4fa", "#11111b"),
    "domain": ("#a6e3a1", "#11111b"),
    "missing": ("#585b70", "#cdd6f4"),
}


class AdvancedViewerDialog(QDialog):
    """Pinned, modal viewer for model facts and live memory projections."""

    def __init__(self, parent: QWidget | Mapping[str, Any] | None = None, inspection: Mapping[str, Any] | None = None):
        # Accept ``AdvancedViewerDialog(inspection)`` as a convenient, safe
        # shorthand while retaining normal QDialog(parent, ...) semantics.
        if inspection is None and isinstance(parent, Mapping):
            inspection = parent
            parent = None
        super().__init__(cast(QWidget | None, parent))
        self.setWindowTitle("Advanced Model Viewer")
        self.setModal(True)
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self.setMinimumSize(620, 620)
        self.resize(760, 760)
        self._inspection: dict[str, Any] = {}
        self._facts = ModelFacts()
        self._projection: ResourceProjection | None = None
        self._capability_badges: list[QLabel] = []
        self._domain_badges: list[QLabel] = []
        self._build_ui()
        self.set_inspection(dict(inspection) if isinstance(inspection, Mapping) else {})

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.Shape.NoFrame)
        scroll.setToolTip("Scroll through model facts, capabilities, and resource estimates.")
        content = QWidget()
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(2, 2, 2, 2)
        content_layout.setSpacing(10)
        scroll.setWidget(content)
        root.addWidget(scroll, 1)

        summary = QGroupBox("At a glance")
        summary.setToolTip("Facts are extracted from inspected metadata; Unknown means metadata was unavailable.")
        summary_grid = QGridLayout(summary)
        summary_grid.setHorizontalSpacing(16)
        summary_grid.setVerticalSpacing(8)
        self._summary_values: dict[str, QLabel] = {}
        summary_fields = (
            ("architecture", "Architecture"),
            ("layer_count", "Layer Count"),
            ("experts_total", "Experts Total"),
            ("experts_active", "Experts Active"),
            ("trained_context", "Trained Context"),
            ("max_context", "Max Context"),
            ("rope", "RoPE"),
            ("mtp", "MTP"),
        )
        for index, (key, title) in enumerate(summary_fields):
            label = QLabel(title)
            label.setStyleSheet("color: #a6adc8; font-size: 11px;")
            value = QLabel(_UNKNOWN)
            value.setWordWrap(True)
            value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            value.setStyleSheet("color: #cdd6f4; font-size: 13px; font-weight: bold;")
            label.setToolTip(f"Inspected model {title.lower()}.")
            value.setToolTip(f"Inspected model {title.lower()}; unavailable values are shown as Unknown.")
            row, column = divmod(index, 2)
            summary_grid.addWidget(label, row, column * 2)
            summary_grid.addWidget(value, row, column * 2 + 1)
            self._summary_values[key] = value
        content_layout.addWidget(summary)

        badges = QGroupBox("Capabilities and domains")
        badges.setToolTip("Badges are derived by the backend from inspection metadata, never from filenames.")
        badges_layout = QVBoxLayout(badges)
        capability_title = QLabel("Capabilities")
        capability_title.setToolTip("Model capabilities detected in inspected metadata.")
        badges_layout.addWidget(capability_title)
        self._capability_row = QHBoxLayout()
        self._capability_row.setSpacing(6)
        self._capability_row.addStretch()
        badges_layout.addLayout(self._capability_row)
        domain_title = QLabel("Domains")
        domain_title.setToolTip("Model domains detected in inspected metadata.")
        badges_layout.addWidget(domain_title)
        self._domain_row = QHBoxLayout()
        self._domain_row.setSpacing(6)
        self._domain_row.addStretch()
        badges_layout.addLayout(self._domain_row)
        content_layout.addWidget(badges)

        projection = QGroupBox("Runtime resource projection")
        projection.setToolTip("Adjust controls to recalculate the estimator projection immediately.")
        projection_form = QFormLayout(projection)
        projection_form.setHorizontalSpacing(14)
        projection_form.setVerticalSpacing(8)

        self.context_spin = QSpinBox()
        self.context_spin.setRange(1, 1_048_576)
        self.context_spin.setSingleStep(256)
        self.context_spin.setSuffix(" tokens")
        self.context_spin.setToolTip("Runtime context length in tokens; changing it updates KV cache and VRAM/RAM.")
        projection_form.addRow("Context", self.context_spin)

        self.quantization_combo = QComboBox()
        self.quantization_combo.addItem("Auto / inspected", None)
        for label, bits in (("FP32", 32), ("FP16 / BF16", 16), ("Q8", 8), ("Q6", 6), ("Q5", 5), ("Q4", 4), ("Q3", 3), ("Q2", 2)):
            self.quantization_combo.addItem(label, bits)
        self.quantization_combo.setToolTip("Select a weight quantization; this sets the weight-bits control and recalculates estimates.")
        projection_form.addRow("Quantization", self.quantization_combo)

        self.weight_bits_spin = QDoubleSpinBox()
        self.weight_bits_spin.setRange(1.0, 64.0)
        self.weight_bits_spin.setDecimals(1)
        self.weight_bits_spin.setSingleStep(1.0)
        self.weight_bits_spin.setSuffix(" bits")
        self.weight_bits_spin.setToolTip("Explicit weight precision used by the estimator; quantization presets update this value.")
        projection_form.addRow("Weight bits", self.weight_bits_spin)

        self.batch_spin = QSpinBox()
        self.batch_spin.setRange(1, 4096)
        self.batch_spin.setToolTip("Number of concurrent sequences; larger batches increase activation and KV-cache estimates.")
        projection_form.addRow("Batch", self.batch_spin)

        self.kv_cache_bits_combo = QComboBox()
        for label, bits in (("FP16 / BF16", 16), ("FP8 / INT8", 8), ("INT4", 4), ("INT2", 2)):
            self.kv_cache_bits_combo.addItem(label, bits)
        self.kv_cache_bits_combo.setToolTip("KV-cache precision; changing it updates the live VRAM/RAM projection.")
        projection_form.addRow("KV-cache bits", self.kv_cache_bits_combo)

        self._projection_values: dict[str, QLabel] = {}
        result_grid = QGridLayout()
        result_grid.setHorizontalSpacing(14)
        result_grid.setVerticalSpacing(6)
        for index, (key, title) in enumerate((("weight", "Weights"), ("kv_cache", "KV cache"), ("vram", "Estimated VRAM"), ("ram", "Estimated RAM"))):
            label = QLabel(title)
            label.setStyleSheet("color: #a6adc8; font-size: 11px;")
            value = QLabel(_UNKNOWN)
            value.setStyleSheet("color: #f5c2e7; font-size: 13px; font-weight: bold;")
            value.setToolTip(f"Estimator result for {title.lower()}.")
            row, column = divmod(index, 2)
            result_grid.addWidget(label, row, column * 2)
            result_grid.addWidget(value, row, column * 2 + 1)
            self._projection_values[key] = value
        projection_form.addRow(result_grid)

        self.assumptions_label = QLabel()
        self.assumptions_label.setWordWrap(True)
        self.assumptions_label.setStyleSheet("color: #f9e2af; font-size: 11px;")
        self.assumptions_label.setToolTip("Estimator assumptions used when inspected metadata is incomplete.")
        projection_form.addRow("Assumptions", self.assumptions_label)
        content_layout.addWidget(projection)
        content_layout.addStretch()

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(self.reject)
        self.copy_configuration_button = QPushButton("Copy Configuration")
        self.copy_configuration_button.setToolTip("Copy the current plain-text runtime configuration to the clipboard.")
        self.copy_configuration_button.clicked.connect(self.copy_configuration)
        buttons.addButton(self.copy_configuration_button, QDialogButtonBox.ButtonRole.ActionRole)
        root.addWidget(buttons)

        self.context_spin.valueChanged.connect(self._recalculate)
        self.quantization_combo.currentIndexChanged.connect(self._quantization_changed)
        self.weight_bits_spin.valueChanged.connect(self._recalculate)
        self.batch_spin.valueChanged.connect(self._recalculate)
        self.kv_cache_bits_combo.currentIndexChanged.connect(self._recalculate)

    def set_inspection(self, inspection: Mapping[str, Any] | None) -> None:
        """Replace inspected metadata and refresh facts, badges, and projection."""
        self._inspection = dict(inspection) if isinstance(inspection, Mapping) else {}
        self._facts = facts_from_inspection(self._inspection)
        self._update_summary()
        self._replace_badges(self._capability_row, self._capability_badges, self._facts.capabilities, "capability")
        self._replace_badges(self._domain_row, self._domain_badges, self._facts.domains, "domain")

        context = self._facts.max_context or 4096
        self.context_spin.blockSignals(True)
        self.context_spin.setValue(max(1, min(int(context), self.context_spin.maximum())))
        self.context_spin.blockSignals(False)
        self.batch_spin.blockSignals(True)
        self.batch_spin.setValue(1)
        self.batch_spin.blockSignals(False)
        self._set_initial_quantization()
        self._recalculate()

    def _update_summary(self) -> None:
        facts = self._facts
        values = {
            "architecture": facts.architecture,
            "layer_count": self._number_text(facts.layer_count),
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
        text = runtime_configuration(self._projection, self._facts)
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
        foreground, background = _BADGE_COLORS.get(kind, _BADGE_COLORS["missing"])
        badge = QLabel(text)
        badge.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        badge.setStyleSheet(
            f"background-color: {foreground}; color: {background}; padding: 3px 9px; "
            "border-radius: 5px; font-size: 11px; font-weight: bold;"
        )
        badge.setToolTip(f"Detected {kind}: {text}.")
        return badge

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


AdvancedViewerPopup = AdvancedViewerDialog
AdvancedViewer = AdvancedViewerDialog
