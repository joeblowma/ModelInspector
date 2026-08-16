# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportReturnType=false
"""Focused checks for the standalone advanced viewer dialog."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # pragma: no cover - fallback for the project's PyQt6 env.
    from PyQt6.QtWidgets import QApplication

from front.advanced_viewer import AdvancedViewerDialog


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


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
