# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportReturnType=false
"""Focused checks for the standalone advanced viewer dialog."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication, QSizePolicy, QVBoxLayout

from front.advanced_viewer import AdvancedViewerDialog, Qt, QWidget


_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    application = QApplication.instance()
    _APPLICATION = application if isinstance(application, QApplication) else QApplication([])
    return _APPLICATION


def test_viewer_populates_facts_and_recalculates_projection():
    _app()
    dialog = AdvancedViewerDialog(
        inspection={
            "architecture": "LlamaForCausalLM",
            "model_type": "llm",
            "total_params": "7B",
            "num_hidden_layers": 32,
            "hidden_size": 4096,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
            "max_position_embeddings": 8192,
            "trained_context": 4096,
            "rope_theta": 10000,
            "num_mtp_layers": 2,
            "tool_use": True,
            "thinking": True,
            "quantization": "q4",
        }
    )
    assert dialog._summary_values["architecture"].text() == "LlamaForCausalLM"
    assert dialog._summary_values["layer_count"].text() == "32"
    assert dialog._summary_values["max_context"].text() == "8,192 tokens"
    assert [badge.text() for badge in dialog._capability_badges] == ["Tool Use", "Thinking"]
    assert [badge.text() for badge in dialog._domain_badges] == ["LLM"]
    initial_vram = dialog._projection.vram_bytes

    dialog.context_spin.setValue(16384)
    assert dialog._projection.context_length == 16384
    assert dialog._projection.vram_bytes > initial_vram

    dialog.kv_cache_bits_combo.setCurrentIndex(2)
    assert dialog._projection.kv_cache_bits == 4

    configuration = dialog.copy_configuration()
    assert "Estimated VRAM:" in configuration
    assert QApplication.instance().clipboard().text() == configuration
    dialog.close()


def test_missing_values_are_visible_and_filename_is_not_inference_source():
    _app()
    dialog = AdvancedViewerDialog({"filepath": "vision_model.safetensors"})
    assert dialog._summary_values["architecture"].text() == "Unknown"
    assert dialog._summary_values["layer_count"].text() == "Unknown"
    assert [badge.text() for badge in dialog._capability_badges] == ["Unknown"]
    assert [badge.text() for badge in dialog._domain_badges] == ["Unknown"]
    assert dialog._projection.assumptions
    dialog.close()


def test_viewer_is_parent_owned_window_modal_and_hosts_explorer():
    _app()
    parent = QWidget()
    dialog = AdvancedViewerDialog(
        parent,
        {
            "architecture": "TestArchitecture",
            "tensor_info": {"model.layer.weight": {"shape": [2], "dtype": "F16"}},
        },
    )

    assert dialog.parentWidget() is parent
    assert dialog.windowModality() == Qt.WindowModality.WindowModal
    assert not dialog.windowFlags() & Qt.WindowType.WindowStaysOnTopHint
    assert [dialog.work_area.tabText(index) for index in range(dialog.work_area.count())] == [
        "Overview",
        "Card Details",
        "Metadata",
        "Tensors",
        "Embedded Content",
    ]
    assert dialog.explorer_tab.tensor_model.rowCount() == 1
    dialog.close()
    parent.close()


def test_card_details_honor_detailed_preferences_and_metadata_stays_spacious():
    app = _app()
    dialog = AdvancedViewerDialog(
        {"filepath": "R:/model.safetensors", "total_params": 100, "metadata": {"long": "value\n" * 20}},
        card_fields={"parameters": True, "file_size": False, "tensors": False},
    )
    dialog.show()
    app.processEvents()
    assert dialog._card_details_card is not None
    assert dialog._card_details_card.select_cb.isHidden()
    assert dialog._card_details_card.stats_layout.columnCount() == 2
    assert dialog._card_details_card.stats_layout.rowCount() >= 2
    assert dialog.explorer_tab.metadata_table.wordWrap()
    assert dialog.explorer_tab.metadata_table.columnWidth(1) > 300
    assert dialog.width() >= 840
    assert not dialog.work_area.tabBar().usesScrollButtons()
    dialog.close()


def test_overview_cards_reserve_padding_and_usable_minimum_geometry():
    _app()
    dialog = AdvancedViewerDialog()

    margins = dialog._overview_layout.contentsMargins()
    content_policy = dialog._overview_content.sizePolicy()
    assert dialog._overview_scroll.widgetResizable()
    assert margins.bottom() >= 16
    assert content_policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
    assert content_policy.verticalPolicy() == QSizePolicy.Policy.Minimum
    assert dialog._overview_layout.sizeConstraint() == QVBoxLayout.SizeConstraint.SetMinimumSize
    for card in dialog._overview_cards:
        policy = card.sizePolicy()
        assert policy.horizontalPolicy() == QSizePolicy.Policy.Expanding
        assert policy.verticalPolicy() == QSizePolicy.Policy.Minimum
        assert card.minimumHeight() >= 72
    dialog.close()


def test_overview_long_values_wrap_within_resizable_viewport():
    app = _app()
    dialog = AdvancedViewerDialog(
        {
            "architecture": "LongArchitecture" * 20,
            "rope": {"long_metadata_key": "long metadata value " * 20},
        }
    )
    dialog.resize(640, 700)
    dialog.show()
    app.processEvents()

    assert dialog._summary_values["architecture"].wordWrap()
    assert dialog._summary_values["rope"].wordWrap()
    assert dialog.assumptions_label.wordWrap()
    assert dialog._overview_content.width() <= dialog._overview_scroll.viewport().width()
    dialog.close()
