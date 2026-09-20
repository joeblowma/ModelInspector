"""Widget construction for :mod:`front.advanced_viewer`.

Keeping the sizeable Qt layout separate leaves the dialog module focused on
state transitions, calculations, and theme refresh behavior.  The builder
uses the project's PyQt6 binding, matching the Explorer widget it hosts.
"""

from __future__ import annotations

from typing import Any, cast

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QDialogButtonBox,
    QComboBox,
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

from back.theme_loader import get_global_theme_colors
from front.explorer_tab import ExplorerTab
from front.metadata_ui import HeaderInspectionController
from front.model_path_label import ModelPathLabel

__all__ = ["build_advanced_viewer_ui"]


def _muted_style(colors: dict[str, str]) -> str:
    return "color: %(muted)s; font-size: 11px;" % colors


def _value_style(colors: dict[str, str]) -> str:
    return "color: %(text)s; font-size: 13px; font-weight: bold;" % colors


def _disable_tab_scroll_buttons(work_area: Any) -> None:
    tab_bar = work_area.tabBar()
    if tab_bar is not None:
        tab_bar.setUsesScrollButtons(False)


def build_advanced_viewer_ui(dialog: Any) -> None:
    """Build and connect all widgets owned by an advanced viewer dialog."""
    root = QVBoxLayout(dialog)
    root.setContentsMargins(14, 14, 14, 14)
    root.setSpacing(10)
    colors = get_global_theme_colors()

    model_row = QHBoxLayout()
    model_title = QLabel("Model:")
    model_title.setStyleSheet(_muted_style(colors))
    model_row.addWidget(model_title)
    dialog.model_path_label = ModelPathLabel()
    dialog.model_path_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    dialog.model_path_label.setStyleSheet(_value_style(colors))
    model_row.addWidget(dialog.model_path_label, 1)
    root.addLayout(model_row)

    dialog.work_area = QTabWidget()
    dialog.work_area.setToolTip(
        "Browse Overview, Card Details, Metadata, Tensors, and Embedded Content pages."
    )
    _disable_tab_scroll_buttons(dialog.work_area)

    facts_page = QWidget()
    facts_layout = QVBoxLayout(facts_page)
    facts_layout.setContentsMargins(0, 0, 0, 0)
    overview_scroll = QScrollArea()
    overview_scroll.setWidgetResizable(True)
    overview_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    overview_scroll.setToolTip("Scroll through model facts, capabilities, and resource estimates.")
    overview_content = QWidget()
    overview_content.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
    overview_layout = QVBoxLayout(overview_content)
    overview_layout.setContentsMargins(8, 8, 8, 16)
    overview_layout.setSpacing(10)
    overview_layout.setSizeConstraint(QVBoxLayout.SizeConstraint.SetMinimumSize)
    overview_scroll.setWidget(overview_content)
    facts_layout.addWidget(overview_scroll, 1)
    dialog._overview_scroll = overview_scroll
    dialog._overview_content = overview_content
    dialog._overview_layout = overview_layout

    summary = QGroupBox("At a glance")
    summary.setToolTip("Facts are extracted from inspected metadata; unavailable facts are hidden.")
    summary_grid = QGridLayout(summary)
    summary_grid.setHorizontalSpacing(16)
    summary_grid.setVerticalSpacing(8)
    dialog._summary_values = {}
    dialog._summary_labels = []
    dialog._summary_rows = {}
    summary_fields = (
        ("architecture", "Architecture"),
        ("layer_count", "Layer Count"),
        ("block_counts", "Block Counts"),
        ("experts_total", "Experts Total"),
        ("experts_active", "Experts Active"),
        ("trained_context", "Trained Context"),
        ("max_context", "Max Context"),
        ("rope", "RoPE"),
        ("mtp", "MTP"),
    )
    for index, (key, title) in enumerate(summary_fields):
        label = QLabel(title)
        label.setStyleSheet(_muted_style(colors))
        value = QLabel("Unknown")
        value.setWordWrap(True)
        value.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        value.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        value.setStyleSheet(_value_style(colors))
        label.setToolTip(f"Inspected model {title.lower()}.")
        value.setToolTip(f"Inspected model {title.lower()}; unavailable values are hidden.")
        row, column = divmod(index, 2)
        summary_grid.addWidget(label, row, column * 2)
        summary_grid.addWidget(value, row, column * 2 + 1)
        dialog._summary_labels.append(label)
        dialog._summary_values[key] = value
        dialog._summary_rows[key] = (label, value)
    summary_grid.setColumnStretch(1, 1)
    summary_grid.setColumnStretch(3, 1)
    overview_layout.addWidget(summary)

    badges = QGroupBox("Capabilities and domains")
    badges.setToolTip("Badges are derived by the backend from inspection metadata, never from filenames.")
    badges_layout = QVBoxLayout(badges)
    capability_title = QLabel("Capabilities")
    capability_title.setStyleSheet(_muted_style(colors))
    capability_title.setToolTip("Model capabilities detected in inspected metadata.")
    badges_layout.addWidget(capability_title)
    dialog._capability_row = QHBoxLayout()
    dialog._capability_row.setSpacing(6)
    dialog._capability_row.addStretch()
    badges_layout.addLayout(dialog._capability_row)
    domain_title = QLabel("Domains")
    domain_title.setStyleSheet(_muted_style(colors))
    domain_title.setToolTip("Model domains detected in inspected metadata.")
    badges_layout.addWidget(domain_title)
    dialog._domain_row = QHBoxLayout()
    dialog._domain_row.setSpacing(6)
    dialog._domain_row.addStretch()
    badges_layout.addLayout(dialog._domain_row)
    dialog._badge_labels = [capability_title, domain_title]
    overview_layout.addWidget(badges)

    projection = QGroupBox("Runtime resource projection")
    projection.setToolTip("Adjust controls to recalculate the estimator projection immediately.")
    projection_form = QFormLayout(projection)
    projection_form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.ExpandingFieldsGrow)
    projection_form.setHorizontalSpacing(14)
    projection_form.setVerticalSpacing(8)

    dialog.context_spin = QSpinBox()
    dialog.context_spin.setRange(1, 1_048_576)
    dialog.context_spin.setSingleStep(256)
    dialog.context_spin.setSuffix(" tokens")
    dialog.context_spin.setToolTip("Runtime context length in tokens; changing it updates KV cache and VRAM/RAM.")
    projection_form.addRow("Context", dialog.context_spin)

    dialog.quantization_combo = QComboBox()
    dialog.quantization_combo.addItem("Auto / inspected", None)
    for label, bits in (("FP32", 32), ("FP16 / BF16", 16), ("Q8", 8), ("Q6", 6), ("Q5", 5), ("Q4", 4), ("Q3", 3), ("Q2", 2)):
        dialog.quantization_combo.addItem(label, bits)
    dialog.quantization_combo.setToolTip("Select a weight quantization; this sets the weight-bits control and recalculates estimates.")
    projection_form.addRow("Quantization", dialog.quantization_combo)

    dialog.weight_bits_spin = QDoubleSpinBox()
    dialog.weight_bits_spin.setRange(1.0, 64.0)
    dialog.weight_bits_spin.setDecimals(2)
    dialog.weight_bits_spin.setSingleStep(0.10)
    dialog.weight_bits_spin.setSuffix(" bits")
    dialog.weight_bits_spin.setToolTip("Effective resident weight precision. Auto uses inspected tensor bytes when complete; presets or edits override it.")
    projection_form.addRow("Weight bits", dialog.weight_bits_spin)

    dialog.batch_spin = QSpinBox()
    dialog.batch_spin.setRange(1, 4096)
    dialog.batch_spin.setToolTip("Number of concurrent sequences; larger batches increase activation and KV-cache estimates.")
    projection_form.addRow("Batch", dialog.batch_spin)

    dialog.kv_cache_bits_combo = QComboBox()
    for label, bits in (("FP16 / BF16", 16), ("FP8 / INT8", 8), ("INT4", 4), ("INT2", 2)):
        dialog.kv_cache_bits_combo.addItem(label, bits)
    dialog.kv_cache_bits_combo.setToolTip("KV-cache precision; changing it updates the live VRAM/RAM projection.")
    projection_form.addRow("KV-cache bits", dialog.kv_cache_bits_combo)

    dialog._projection_values = {}
    dialog._projection_labels = []
    result_grid = QGridLayout()
    result_grid.setHorizontalSpacing(14)
    result_grid.setVerticalSpacing(6)
    for index, (key, title) in enumerate((("weight", "Weights"), ("kv_cache", "KV cache"), ("vram", "Estimated VRAM"), ("ram", "Estimated RAM"))):
        label = QLabel(title)
        label.setStyleSheet(_muted_style(colors))
        value = QLabel("Unknown")
        value.setStyleSheet("color: %(accent_display)s; font-size: 13px; font-weight: bold;" % colors)
        value.setToolTip(f"Estimator result for {title.lower()}.")
        row, column = divmod(index, 2)
        result_grid.addWidget(label, row, column * 2)
        result_grid.addWidget(value, row, column * 2 + 1)
        dialog._projection_labels.append(label)
        dialog._projection_values[key] = value
    result_grid.setColumnStretch(1, 1)
    result_grid.setColumnStretch(3, 1)
    projection_form.addRow(result_grid)

    dialog.assumptions_label = QLabel()
    dialog.assumptions_label.setWordWrap(True)
    dialog.assumptions_label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
    dialog.assumptions_label.setStyleSheet("color: %(warning)s; font-size: 11px;" % colors)
    dialog.assumptions_label.setToolTip("Estimator assumptions used when inspected metadata is incomplete.")
    projection_form.addRow("Assumptions", dialog.assumptions_label)
    overview_layout.addWidget(projection)
    overview_layout.addStretch()
    dialog._overview_cards = (summary, badges, projection)
    for card in dialog._overview_cards:
        card.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Minimum)
        card.setMinimumHeight(max(72, card.minimumSizeHint().height()))
    dialog._overview_muted_labels = [*dialog._summary_labels, *dialog._badge_labels, *dialog._projection_labels]

    dialog.card_details_page = QWidget()
    card_details_layout = QVBoxLayout(dialog.card_details_page)
    card_details_layout.setContentsMargins(0, 0, 0, 0)
    dialog._card_details_layout = card_details_layout
    card_details_scroll = QScrollArea()
    card_details_scroll.setWidgetResizable(True)
    card_details_scroll.setFrameShape(QScrollArea.Shape.NoFrame)
    card_details_scroll.setToolTip("Scroll through the card details view of the inspected model.")
    dialog._card_details_content = QWidget()
    dialog._card_details_content_layout = QVBoxLayout(dialog._card_details_content)
    dialog._card_details_content_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
    card_details_scroll.setWidget(dialog._card_details_content)
    card_details_layout.addWidget(card_details_scroll)

    dialog.explorer_tab = ExplorerTab()
    dialog.work_area.addTab(facts_page, "Overview")
    dialog.work_area.addTab(dialog.card_details_page, "Card Details")
    for title, page in dialog.explorer_tab.detach_pages():
        dialog.work_area.addTab(cast(Any, page), title)
    root.addWidget(dialog.work_area, 1)

    dialog._header_controller = HeaderInspectionController(
        cast(Any, dialog),
        dialog.work_area,
        dialog.explorer_tab.tensors_page,
        dialog.explorer_tab,
        lambda: dialog._inspection,
        dialog.set_inspection,
    )
    dialog.finished.connect(lambda *_args: dialog._header_controller.cancel())

    buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
    buttons.rejected.connect(dialog.reject)
    dialog.copy_configuration_button = QPushButton("Copy Configuration")
    dialog.copy_configuration_button.setToolTip("Copy the current plain-text runtime configuration to the clipboard.")
    dialog.copy_configuration_button.clicked.connect(dialog.copy_configuration)
    buttons.addButton(dialog.copy_configuration_button, QDialogButtonBox.ButtonRole.ActionRole)
    root.addWidget(buttons)

    dialog.context_spin.valueChanged.connect(dialog._recalculate)
    dialog.quantization_combo.currentIndexChanged.connect(dialog._quantization_changed)
    dialog.weight_bits_spin.valueChanged.connect(dialog._weight_bits_changed)
    dialog.batch_spin.valueChanged.connect(dialog._recalculate)
    dialog.kv_cache_bits_combo.currentIndexChanged.connect(dialog._recalculate)
