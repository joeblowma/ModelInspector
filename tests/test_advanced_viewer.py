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
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking", "tools"],
                "evidence": {
                    "thinking": ["config.json:enable_thinking"],
                    "tools": ["config.json:supports_tools"],
                },
                "evidence_strength": {"thinking": "strong", "tools": "strong"},
            },
            "quantization": "Q4_K_M",
        }
    )
    assert dialog._summary_values["architecture"].text() == "LlamaForCausalLM"
    assert dialog._summary_values["layer_count"].text() == "32"
    assert dialog._summary_values["max_context"].text() == "8,192 tokens"
    assert [badge.text() for badge in dialog._capability_badges] == ["Tool Use", "Thinking"]
    assert [badge.text() for badge in dialog._domain_badges] == ["LLM"]
    assert dialog.quantization_combo.currentIndex() == 0
    assert dialog.weight_bits_spin.value() == 4.5
    assert dialog.weight_bits_spin.decimals() == 2
    assert dialog.weight_bits_spin.singleStep() == 0.10
    initial_vram = dialog._projection.vram_bytes

    dialog.weight_bits_spin.setValue(5.4)
    assert dialog._projection.weight_bits == 5.4

    dialog.context_spin.setValue(16384)
    assert dialog._projection.context_length == 16384
    assert dialog._projection.vram_bytes > initial_vram

    dialog.kv_cache_bits_combo.setCurrentIndex(2)
    assert dialog._projection.kv_cache_bits == 4

    configuration = dialog.copy_configuration()
    assert "Estimated VRAM:" in configuration
    assert QApplication.instance().clipboard().text() == configuration
    dialog.close()


def test_unknown_summary_rows_are_hidden_and_filename_is_not_inference_source():
    _app()
    dialog = AdvancedViewerDialog({"filepath": "vision_model.safetensors"})
    for key, value_label in dialog._summary_values.items():
        assert value_label.text() == "Unknown"
        label, _ = dialog._summary_rows[key]
        assert label.isHidden() and value_label.isHidden()
    assert [badge.text() for badge in dialog._capability_badges] == ["Unknown"]
    assert [badge.text() for badge in dialog._domain_badges] == ["Unknown"]
    assert dialog._projection.assumptions
    dialog.close()


def test_known_zero_false_rows_stay_visible_and_unknown_rows_return():
    _app()
    dialog = AdvancedViewerDialog(
        {
            "architecture": "LlamaForCausalLM",
            "num_hidden_layers": 0,
            "rope_theta": 0,
            "num_mtp_layers": False,
        }
    )
    # Known values — including explicit 0/False — must stay visible.
    assert dialog._summary_values["architecture"].text() == "LlamaForCausalLM"
    assert dialog._summary_values["layer_count"].text() == "0"
    assert dialog._summary_values["rope"].text() == "rope_theta=0"
    assert dialog._summary_values["mtp"].text() == "num_mtp_layers=False"
    for key in ("architecture", "layer_count", "rope", "mtp"):
        label, value = dialog._summary_rows[key]
        assert not label.isHidden() and not value.isHidden()
    # Still-unknown rows stay hidden.
    assert dialog._summary_rows["experts_total"][1].isHidden()

    # A later inspection with known facts re-shows the hidden rows.
    dialog.set_inspection({"expert_count": 8, "expert_used_count": 2})
    for key in ("experts_total", "experts_active"):
        label, value = dialog._summary_rows[key]
        assert not label.isHidden() and not value.isHidden()
    assert dialog._summary_values["experts_total"].text() == "8"
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


def test_viewer_exposes_sidecars_and_copies_their_paths_in_configuration():
    _app()
    dialog = AdvancedViewerDialog(
        {
            "sidecar_roles": ["mmproj"],
            "sidecar_paths": ["R:/models/model-mmproj.gguf"],
            "tensor_info": {"layer.weight": {"shape": [2], "dtype": "F16", "shard_id": 0}},
        }
    )

    metadata = {
        dialog.explorer_tab.metadata_table.item(row, 0).text(): dialog.explorer_tab.metadata_table.item(row, 1).text()
        for row in range(dialog.explorer_tab.metadata_table.rowCount())
    }
    assert metadata["associated_sidecars.sidecar_roles"] == '["mmproj"]'
    assert "model-mmproj.gguf" in dialog.copy_configuration()
    assert dialog.explorer_tab.tensor_order_combo.count() == 2
    dialog.close()


def test_embedded_explorer_switches_order_groups_shards_and_keeps_byte_tooltips():
    _app()
    dialog = AdvancedViewerDialog({
        "sidecar_roles": ["mmproj", "draft"],
        "sidecar_paths": ["R:/models/model-mmproj.gguf", "R:/models/model-draft.gguf"],
        "original_tensor_order": ["second", "first"],
        "sorted_tensor_order": ["first", "second"],
        "tensor_info": {
            "first": {"shape": [2], "dtype": "F16", "shard_id": 2, "n_bytes": 16},
            "second": {"shape": [3], "dtype": "F16", "shard_id": 1, "n_bytes": 24},
        },
    })
    explorer = dialog.explorer_tab
    assert [explorer.tensor_model.item(row, 0).text() for row in range(2)] == ["first", "second"]
    assert explorer.tensor_model.item(0, 4).text() == "Shard 2"
    assert "Raw bytes: 16 bytes; display: 16 B" in explorer.tensor_model.item(0, 5).toolTip()
    explorer.tensor_order_combo.setCurrentIndex(1)
    assert [explorer.tensor_model.item(row, 0).text() for row in range(2)] == ["first", "second"]
    copied = dialog.copy_configuration()
    assert "model-mmproj.gguf" in copied and "model-draft.gguf" in copied
    dialog.close()


def test_card_details_ignore_legacy_preferences_and_metadata_stays_spacious():
    app = _app()
    dialog = AdvancedViewerDialog(
        {"filepath": "R:/model.safetensors", "total_params": 100, "metadata": {"long": "value\n" * 20}},
        card_fields={"parameters": False, "file_size": False, "tensors": False},
    )
    dialog.show()
    app.processEvents()
    assert dialog._card_details_card is not None
    assert dialog._card_details_card.select_cb.isHidden()
    assert dialog._card_details_card.stats_layout.columnCount() == 2
    assert dialog._card_details_card.stats_layout.rowCount() >= 2
    labels = [
        dialog._card_details_card.stats_layout.itemAt(index).widget().text()
        for index in range(dialog._card_details_card.stats_layout.count())
        if dialog._card_details_card.stats_layout.getItemPosition(index)[1] == 0
    ]
    assert {"Parameters", "Precision", "File Size", "Tensors"} <= set(labels)
    assert dialog.explorer_tab.metadata_table.wordWrap()
    assert dialog.explorer_tab.metadata_table.columnWidth(1) > 300
    assert dialog.width() >= 840
    assert not dialog.work_area.tabBar().usesScrollButtons()
    dialog.close()


def test_current_model_location_updates_and_embedded_card_has_no_open_viewer_tooltip():
    _app()
    dialog = AdvancedViewerDialog({"filepath": "R:/models/first.safetensors"})
    assert dialog.filename_label.text() == "first.safetensors"
    assert dialog.filepath_label.text() == "R:/models/first.safetensors"
    assert dialog._card_details_card.toolTip() == ""

    dialog.set_inspection({"filepath": "R:/models/second.gguf"})
    assert dialog.filename_label.text() == "second.gguf"
    assert dialog.filepath_label.text() == "R:/models/second.gguf"
    assert "Click to open the Advanced Viewer" not in dialog._card_details_card.toolTip()
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


def test_refresh_theme_invalidates_badges_and_refreshes_inline_explorer_styles(monkeypatch):
    _app()
    import front.advanced_viewer as advanced_viewer

    colors = {
        "accent": "#123456",
        "accent_text": "#ffffff",
        "success": "#234567",
        "border": "#345678",
        "text": "#456789",
        "muted": "#56789a",
        "accent_display": "#6789ab",
        "warning": "#789abc",
        "background": "#89abcd",
    }
    monkeypatch.setattr(advanced_viewer, "get_global_theme_colors", lambda: colors)
    dialog = AdvancedViewerDialog(
        {
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking"],
                "evidence": {"thinking": ["header"]},
            }
        }
    )
    try:
        dialog.refresh_theme()
        assert advanced_viewer._ADVANCED_VIEWER_COLORS["capability"] == (
            colors["accent"],
            colors["accent_text"],
        )
        assert colors["accent"] in dialog._capability_badges[0].styleSheet()
        assert colors["muted"] in dialog._summary_labels[0].styleSheet()
        assert colors["muted"] in dialog.explorer_tab.status_label.styleSheet()
    finally:
        dialog.close()
