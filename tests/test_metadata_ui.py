"""Regression coverage for compact metadata presentation and lazy headers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication, QLabel

from back.inspection_summary import compact_inspection_summary
from front.advanced_viewer import AdvancedViewerDialog
from front.model_card import ModelCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_safetensors(path: Path) -> None:
    header = {
        "model.embed_tokens.weight": {
            "dtype": "F16", "shape": [2, 3], "data_offsets": [0, 12]
        },
        "model.layers.0.self_attn.q_proj.weight": {
            "dtype": "F16", "shape": [3, 4], "data_offsets": [12, 36]
        },
        "model.layers.1.self_attn.q_proj.weight": {
            "dtype": "F16", "shape": [4, 5], "data_offsets": [36, 76]
        },
    }
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"header-only-test")


def _labels(widget) -> set[str]:
    return {label.text() for label in widget.findChildren(QLabel)}


def test_domain_tags_preserve_raw_type_and_adapter_labels() -> None:
    _app()
    for domain, model_type, description in (
        ("LLM", "LLM", "language model"),
        ("VLM", "MLLM", "vision"),
        ("MMLM", "MLLM", "other modalities"),
    ):
        card = ModelCard(
            {
                "filename": "vl-adapter.safetensors",
                "filepath": f"{domain}.safetensors",
                "architecture": "Qwen2VLForConditionalGeneration",
                "model_type": model_type,
                "adapter_type": "LoRA",
                "capability_facts": {
                    "domain": domain,
                    "capabilities": [],
                    "evidence": {"domain": ["config.json:domain"]},
                },
            },
            simple_view=True,
        )
        labels = _labels(card)
        assert {domain, model_type, "LoRA"} <= labels
        domain_tags = [label for label in card.findChildren(QLabel) if label.property("metadata_domain")]
        assert [tag.text() for tag in domain_tags] == [domain]
        assert description in domain_tags[0].toolTip().lower()


def test_known_domain_hides_unknown_legacy_type_but_keeps_genuine_unknown() -> None:
    _app()
    known_domain = ModelCard(
        {
            "filename": "language-model.gguf",
            "filepath": "language-model.gguf",
            "architecture": "llama",
            "model_type": "Unknown",
            "components": {"text_encoder": True},
            "capability_facts": {
                "domain": "LLM",
                "capabilities": [],
                "evidence": {"domain": ["header metadata"]},
            },
        },
        simple_view=True,
    )
    assert "LLM" in _labels(known_domain)
    assert "Unknown" not in _labels(known_domain)
    assert "Text Enc" in _labels(known_domain)

    unknown = ModelCard(
        {
            "filename": "unknown.gguf",
            "filepath": "unknown.gguf",
            "architecture": "Unknown",
            "model_type": "Unknown",
        },
        simple_view=True,
    )
    assert "Unknown" in _labels(unknown)


def test_structured_capability_badges_require_nonempty_evidence() -> None:
    _app()
    dialog = AdvancedViewerDialog(
        {
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking", "tools"],
                "evidence": {"thinking": [], "tools": []},
            }
        }
    )
    assert [badge.text() for badge in dialog._capability_badges] == ["Unknown"]
    dialog.close()


def test_weak_evidence_strength_suppresses_a_capability_badge() -> None:
    _app()
    from front.metadata_ui import capability_badge_values

    values = capability_badge_values(
        {
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking", "tools"],
                "evidence": {
                    "thinking": ["chat_template.jinja:thinking marker (weak)"],
                    "tools": ["config.json:supports_tools"],
                },
                "evidence_strength": {"thinking": "weak", "tools": "strong"},
            }
        }
    )

    assert values == ("Tool Use",)


def test_compact_facts_render_counts_and_evidence_backed_badges() -> None:
    _app()
    full = {
        "filepath": "qwen.safetensors",
        "filename": "qwen.safetensors",
        "architecture": "Qwen3ForCausalLM",
        "model_type": "LLM",
        "total_params": 7_000_000_000,
        "total_params_friendly": "7.00B",
        "architecture_facts": {"layer_count": 32, "block_counts": {"text": 32}},
        "capability_facts": {
            "domain": "LLM",
            "capabilities": ["thinking", "tools"],
            "evidence": {"thinking": ["config.json:thinking"], "tools": ["chat_template.jinja:tool marker"]},
        },
    }
    summary = compact_inspection_summary(full)
    dialog = AdvancedViewerDialog(summary)
    assert dialog._summary_values["layer_count"].text() == "32"
    assert dialog._summary_values["block_counts"].text() == "text=32"
    assert [badge.text() for badge in dialog._capability_badges] == ["Tool Use", "Thinking"]
    assert [badge.text() for badge in dialog._domain_badges] == ["LLM"]
    dialog.close()


def test_tensor_tab_loads_header_only_descriptors_from_compact_summary(tmp_path: Path) -> None:
    _app()
    model = tmp_path / "compact.safetensors"
    _write_safetensors(model)
    summary = compact_inspection_summary(
        {
            "filepath": str(model),
            "filename": model.name,
            "format": "SAFETENSORS",
            "architecture": "Transformer (language)",
            "model_type": "LLM",
            "tensor_count": 3,
            "architecture_facts": {"layer_count": 2, "block_counts": {"text": 2}},
            "capability_facts": {"domain": "LLM", "capabilities": [], "evidence": {"domain": ["tensor header:language signature"]}},
        }
    )
    dialog = AdvancedViewerDialog(summary)
    assert dialog.explorer_tab.tensor_model.rowCount() == 0
    dialog.work_area.setCurrentIndex(3)
    deadline = time.monotonic() + 4
    while dialog.explorer_tab.tensor_model.rowCount() != 3 and time.monotonic() < deadline:
        _app().processEvents()
        time.sleep(0.01)
    assert dialog.explorer_tab.tensor_model.rowCount() == 3
    assert dialog.explorer_tab.tensor_model.item(0, 0).text() == "model.embed_tokens.weight"
    assert "payload is not loaded" in dialog.explorer_tab.tensor_model.item(0, 0).toolTip()
    dialog.close()
