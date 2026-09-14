"""Contract tests for bounded companion metadata and normalized model facts."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.companion_discovery import (
    COMPANION_NAMES,
    MAX_COMPANION_BYTES,
    build_architecture_facts,
    discover_companion_metadata,
)
from back.capability_facts import build_capability_facts
from back.inspection_pipeline import inspect_file
from back.inspection_summary import compact_inspection_summary


def _write_safetensors(path: Path, tensor_names: list[str]) -> None:
    header = {
        name: {
            "dtype": "F16",
            "shape": [16, 16],
            "data_offsets": [0, 512],
        }
        for name in tensor_names
    }
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"payload")


def _language_tensors() -> list[str]:
    return [
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.27.self_attn.q_proj.weight",
    ]


def test_companions_follow_resolved_model_parent_for_symlink(tmp_path: Path) -> None:
    real_dir = tmp_path / "real-model"
    link_dir = tmp_path / "link-view"
    real_dir.mkdir()
    link_dir.mkdir()
    model = real_dir / "model.safetensors"
    _write_safetensors(model, _language_tensors())
    (real_dir / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen2_vl",
                "architectures": ["Qwen2VLForConditionalGeneration"],
                "text_config": {"num_hidden_layers": 28},
                "vision_config": {"num_hidden_layers": 24},
            }
        ),
        encoding="utf-8",
    )
    link = link_dir / model.name
    try:
        link.symlink_to(model)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    companion = discover_companion_metadata(link)
    assert companion["root"] == str(real_dir.resolve())
    assert companion["config"]["model_type"] == "qwen2_vl"
    assert companion["identities"][0]["path"] == str(real_dir / "config.json")


def test_bad_and_oversized_companions_are_bounded_and_nonfatal(tmp_path: Path) -> None:
    model = tmp_path / "broken.safetensors"
    _write_safetensors(model, _language_tensors())
    (tmp_path / "config.json").write_text("{not json", encoding="utf-8")
    (tmp_path / "tokenizer_config.json").write_bytes(b"{" + b"x" * MAX_COMPANION_BYTES)
    (tmp_path / "processor_config.json").write_text(
        json.dumps({"image_processor_type": "CLIPImageProcessor"}), encoding="utf-8"
    )

    companion = discover_companion_metadata(model)
    assert "config" not in companion
    assert "tokenizer_config" not in companion
    assert companion["processor_config"]["image_processor_type"] == "CLIPImageProcessor"
    assert any("malformed JSON" in warning for warning in companion["warnings"])
    assert any("exceeds" in warning for warning in companion["warnings"])


def test_nested_multimodal_config_normalizes_text_and_vision_counts(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "vl.safetensors"
    _write_safetensors(
        model,
        _language_tensors()
        + [
            "vision_tower.vision_model.encoder.layers.0.self_attn.q_proj.weight",
            "vision_tower.vision_model.encoder.layers.23.self_attn.q_proj.weight",
        ],
    )
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen2_vl",
                "architectures": ["Qwen2VLForConditionalGeneration"],
                "text_config": {"model_type": "qwen2", "num_hidden_layers": 28},
                "vision_config": {"hidden_size": 1024, "num_hidden_layers": 24},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "processor_config.json").write_text(
        json.dumps({"image_processor_type": "Qwen2VLImageProcessor"}), encoding="utf-8"
    )

    result = inspect_file(str(model))

    assert result["architecture"] == "Qwen2VLForConditionalGeneration"
    assert result["architecture_facts"] == {
        "layer_count": 28,
        "block_counts": {"text": 28, "vision": 24},
    }
    assert result["capability_facts"]["domain"] == "VLM"
    assert result["model_type"] == "MLLM"


def test_chat_templates_are_static_evidence_and_mmlm_is_distinct(tmp_path: Path) -> None:
    model = tmp_path / "omni.safetensors"
    _write_safetensors(model, _language_tensors())
    (tmp_path / "config.json").write_text(
        json.dumps(
            {
                "model_type": "qwen2_5_omni",
                "text_config": {"num_hidden_layers": 28},
                "vision_config": {"num_hidden_layers": 24},
                "audio_config": {"num_hidden_layers": 12},
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "chat_template.jinja").write_text(
        "{% if enable_thinking %}<think>{% endif %}{% if tools %}tool_call{% endif %}",
        encoding="utf-8",
    )

    companion = discover_companion_metadata(model)
    facts = build_capability_facts(
        _language_tensors(), {}, companion, "Qwen2.5-Omni", {"vision": True}
    )

    assert facts["domain"] == "MMLM"
    assert facts["capabilities"] == ["thinking", "tools"]
    assert "chat_template.jinja:thinking marker" in facts["evidence"]["thinking"]
    assert "chat_template.jinja:tool marker" in facts["evidence"]["tools"]


@pytest.mark.parametrize("architecture", ["qwen2vl", "qwen2.5-vl", "qwen3_vl"])
def test_known_qwen_vl_gguf_architectures_are_vision_language_models(
    architecture: str,
) -> None:
    facts = build_capability_facts(
        ["blk.0.attn_q.weight", "token_embd.weight"],
        {"general.architecture": architecture},
        {},
        architecture,
        {},
    )

    assert facts["domain"] == "VLM"
    assert "architecture/header:known Qwen-VL family" in facts["evidence"]["domain"]


def test_standalone_projector_does_not_become_a_qwen_vl_model() -> None:
    facts = build_capability_facts(
        ["mmproj.0.weight", "multi_modal_projector.linear.weight"],
        {"general.architecture": "qwen2vl"},
        {},
        "qwen2vl",
        {},
    )

    assert facts["domain"] is None


def test_companion_digest_invalidates_same_size_preserved_mtime_edit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    config = tmp_path / "config.json"
    _write_safetensors(model, _language_tensors())
    config.write_text('{"model_type":"llama","num_hidden_layers":2}', encoding="utf-8")
    first = inspect_file(str(model))
    original_stat = config.stat()
    config.write_text('{"model_type":"llama","num_hidden_layers":3}', encoding="utf-8")
    os.utime(config, ns=(original_stat.st_atime_ns, original_stat.st_mtime_ns))

    refreshed = inspect_file(str(model))

    assert refreshed["architecture_facts"]["layer_count"] == 3
    assert refreshed["companion_identities"] != first["companion_identities"]


def test_companion_realpath_change_invalidates_cached_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    first_target = tmp_path / "config-one.json"
    second_target = tmp_path / "config-two.json"
    config = tmp_path / "config.json"
    _write_safetensors(model, _language_tensors())
    content = '{"model_type":"llama","num_hidden_layers":2}'
    first_target.write_text(content, encoding="utf-8")
    second_target.write_text(content, encoding="utf-8")
    try:
        config.symlink_to(first_target)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    first = inspect_file(str(model))
    config.unlink()
    config.symlink_to(second_target)

    refreshed = inspect_file(str(model))

    assert first["companion_identities"][0]["resolved_path"] == str(first_target)
    assert refreshed["companion_identities"][0]["resolved_path"] == str(second_target)


def test_invalid_fractional_layer_count_falls_back_to_header_indices() -> None:
    facts = build_architecture_facts(
        _language_tensors(), {"config": {"num_hidden_layers": 2.5}}, {}
    )

    assert facts == {"layer_count": 28, "block_counts": {"text": 28}}


def test_summary_preserves_compact_facts_but_not_raw_metadata() -> None:
    result = {
        "architecture": "Llama",
        "architecture_facts": {"layer_count": 32, "block_counts": {"text": 32}},
        "capability_facts": {
            "domain": "LLM",
            "capabilities": ["thinking"],
            "evidence": {"thinking": ["config.json:thinking"]},
        },
        "metadata": {"huge": "x" * 10000},
        "tensor_info": {"payload": {"shape": [1, 2]}},
    }

    summary = compact_inspection_summary(result)

    assert summary["architecture_facts"] == result["architecture_facts"]
    assert summary["capability_facts"] == result["capability_facts"]
    assert "metadata" not in summary
    assert "tensor_info" not in summary
    assert summary["architecture_facts"] is not result["architecture_facts"]


def test_gguf_sibling_config_is_a_bounded_fallback(tmp_path: Path) -> None:
    model = tmp_path / "model.gguf"
    model.write_bytes(b"GGUF")
    (tmp_path / "config.json").write_text(
        json.dumps({"model_type": "llama", "num_hidden_layers": 4}),
        encoding="utf-8",
    )

    companion = discover_companion_metadata(model)

    assert companion["root"] == str(tmp_path.resolve())
    assert companion["config"]["model_type"] == "llama"
    assert [identity["name"] for identity in companion["identities"]] == list(
        COMPANION_NAMES
    )

    other = tmp_path / "model.onnx"
    other.write_bytes(b"not a model")
    assert discover_companion_metadata(other) == {"identities": [], "warnings": []}


def test_chat_template_json_is_used_only_without_a_jinja_file(tmp_path: Path) -> None:
    model = tmp_path / "model.safetensors"
    _write_safetensors(model, _language_tensors())
    (tmp_path / "chat_template.json").write_text(
        json.dumps({"chat_template": "{% if enable_thinking %}<think>{% endif %}"}),
        encoding="utf-8",
    )

    json_only = discover_companion_metadata(model)

    assert [entry["source"] for entry in json_only["chat_templates"]] == [
        "chat_template.json:chat_template"
    ]

    (tmp_path / "chat_template.jinja").write_text(
        "{% if tools %}<|tool|>{% endif %}", encoding="utf-8"
    )
    preferred = discover_companion_metadata(model)

    assert [entry["source"] for entry in preferred["chat_templates"]] == [
        "chat_template.jinja"
    ]


def test_gguf_tensor_count_wins_over_stale_sibling_config() -> None:
    keys = [
        "blk.0.attn_q.weight",
        "blk.31.attn_q.weight",
        "token_embd.weight",
    ]

    facts = build_architecture_facts(keys, {"config": {"num_hidden_layers": 99}}, {})

    assert facts == {"layer_count": 32, "block_counts": {"text": 32}}


def test_adding_chat_template_json_invalidates_a_cached_result(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    _write_safetensors(model, _language_tensors())
    first = inspect_file(str(model))

    (tmp_path / "chat_template.json").write_text(
        json.dumps({"chat_template": "{% if enable_thinking %} thinking{% endif %}"}),
        encoding="utf-8",
    )
    refreshed = inspect_file(str(model))

    assert refreshed["companion_identities"] != first["companion_identities"]
    assert refreshed["capability_facts"]["capabilities"] == ["thinking"]
    assert refreshed["capability_facts"]["evidence_strength"] == {"thinking": "strong"}
