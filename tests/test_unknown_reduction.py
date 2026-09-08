"""Header-only tensor evidence should reduce avoidable Unknown results."""

from __future__ import annotations

import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.architecture_metadata import detect_architecture
from back.capability_facts import build_capability_facts
from back.companion_discovery import build_architecture_facts
from back.inspection_pipeline import inspect_file


def _write_safetensors(path: Path, names: list[str]) -> None:
    header = {
        name: {"dtype": "F16", "shape": [8, 8], "data_offsets": [0, 256]}
        for name in names
    }
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"not a tensor payload")


def _text_header() -> list[str]:
    return [
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.3.self_attn.q_proj.weight",
    ]


def test_generic_decoder_signature_gets_architecture_and_text_count(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "unnamed.safetensors"
    _write_safetensors(model, _text_header())

    result = inspect_file(str(model))

    assert result["architecture"] == "Transformer (language)"
    assert result["architecture_facts"] == {
        "layer_count": 4,
        "block_counts": {"text": 4},
    }
    assert result["capability_facts"]["domain"] == "LLM"


def test_known_tensor_prefixes_and_gguf_metadata_remain_header_only() -> None:
    keys = [
        "blk.0.attn_q.weight",
        "blk.31.attn_q.weight",
        "token_embd.weight",
    ]
    architecture, _ = detect_architecture(
        keys,
        {key: [8, 8] for key in keys},
        512,
        {"lora": False},
        {"general.architecture": "llama"},
    )
    facts = build_architecture_facts(keys, {}, {})
    capabilities = build_capability_facts(
        keys, {"general.architecture": "llama"}, {}, architecture, {}
    )

    assert architecture == "llama"
    assert facts == {"layer_count": 32, "block_counts": {"text": 32}}
    assert capabilities["domain"] == "LLM"


def test_vision_encoder_and_mmproj_do_not_become_language_domains() -> None:
    vision_keys = [
        "visual.patch_embed.proj.weight",
        "visual.blocks.0.attn.q_proj.weight",
        "visual.blocks.23.attn.q_proj.weight",
    ]
    mmproj_keys = ["mmproj.0.weight", "mmproj.1.weight"]

    vision = build_capability_facts(
        vision_keys, {}, {}, "CLIPVisionModel", {"vision": True}
    )
    mmproj = build_capability_facts(mmproj_keys, {}, {}, "mmproj", {})

    assert vision["domain"] is None
    assert mmproj["domain"] is None
    assert vision["capabilities"] == []
    assert mmproj["capabilities"] == []
