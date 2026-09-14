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


# ---------------------------------------------------------------------------
# Conservative multi-key signatures (observed on real header samples; see
# test/fast_drive_image_models and test/slow_drive_mostly_llm mirrors).
# ---------------------------------------------------------------------------


def _detect(keys, metadata=None, components=None, shapes=None):
    return detect_architecture(
        keys,
        shapes if shapes is not None else {key: [8, 8] for key in keys},
        0,
        components if components is not None else {"lora": False},
        metadata or {},
    )[0]


def test_seedvr2_dual_stream_ada_signature() -> None:
    keys = [
        "blocks.0.ada.txt.attn_gate.weight",
        "blocks.0.ada.vid.attn_gate.weight",
        "blocks.0.attn.norm_q.txt.weight",
        "blocks.0.attn.norm_q.vid.weight",
        "vid_out.proj.weight",
    ]
    assert _detect(keys) == "SeedVR2"

    # Negative: a single ada stream is not discriminative.
    partial = [k for k in keys if "ada.vid" not in k]
    assert _detect(partial) != "SeedVR2"


def test_sana_video_signature_not_wan() -> None:
    keys = [
        "attn_res.attn_proj.weight",
        "attn_res.final_proj.weight",
        "blocks.0.attn.beta_proj.weight",
        "blocks.0.attn.qkv.weight",
        "blocks.0.cross_attn.kv_linear.weight",
        "blocks.0.mlp.gate_proj.weight",
        "final_layer.scale_shift_table",
    ]
    assert _detect(keys) == "SANA Video"

    # Negative: Wan's cross_attn/self_attn layout must stay Wan.
    wan_keys = [
        "head.modulation",
        "blocks.0.cross_attn.k.weight",
        "blocks.0.cross_attn.norm_q.weight",
        "blocks.0.self_attn.q.weight",
        "blocks.0.self_attn.norm_k.weight",
        "blocks.0.ffn.0.weight",
        "blocks.0.modulation",
    ]
    assert _detect(wan_keys) == "Wan T2V"


def test_rcan_upscaler_signature() -> None:
    keys = [
        "body.0.body.0.body.0.weight",
        "body.0.body.0.body.3.conv_du.0.weight",
        "body.0.body.0.body.3.conv_du.2.weight",
        "conv_up1.weight",
    ]
    shapes = {
        "body.0.body.0.body.0.weight": [64, 64, 3, 3],
        "body.0.body.0.body.3.conv_du.0.weight": [4, 64, 1, 1],
        "body.0.body.0.body.3.conv_du.2.weight": [64, 4, 1, 1],
        "conv_up1.weight": [64, 64, 3, 3],
    }
    assert _detect(keys, shapes=shapes) == "RCAN (upscaler)"

    # Negative: generic body.N convs without conv_du stay Unknown.
    plain = ["body.0.body.0.body.0.weight", "conv_up1.weight"]
    assert _detect(plain) == "Unknown"


def test_anima_llm_adapter_signature_not_sd15() -> None:
    keys = [
        "model.diffusion_model.llm_adapter.embed.weight",
        "model.diffusion_model.blocks.0.adaln_modulation_cross_attn.1.weight",
        "model.diffusion_model.blocks.0.adaln_modulation_self_attn.1.weight",
        "model.diffusion_model.blocks.0.self_attn.q_proj.weight",
        "model.diffusion_model.blocks.0.cross_attn.k_proj.weight",
    ]
    assert _detect(keys) == "Anima"

    # Negative: generic SD-style diffusion_model blocks stay SD 1.5.
    sd_keys = [
        "model.diffusion_model.blocks.0.self_attn.q_proj.weight",
        "model.diffusion_model.blocks.0.cross_attn.k_proj.weight",
    ]
    assert _detect(sd_keys) == "SD 1.5"


def test_krea2_weight_scale_quantized_keys() -> None:
    # Key set mirrors the real krea2_turbo-int4_convrot header: wq/wo
    # attention + SwiGLU mlp plus the Krea-unique qknorm per-head scales.
    keys = [
        "blocks.0.attn.wq.weight_scale",
        "blocks.0.attn.wk.weight_scale",
        "blocks.0.attn.wv.weight_scale",
        "blocks.0.attn.wo.weight_scale",
        "blocks.0.attn.gate.weight_scale",
        "blocks.0.attn.qknorm.qnorm.scale",
        "blocks.0.attn.qknorm.knorm.scale",
        "blocks.0.mlp.up.weight_scale",
        "blocks.0.mlp.gate.weight_scale",
        "blocks.0.mlp.down.weight_scale",
    ]
    assert _detect(keys) == "Krea 2"

    # Negative: the same wq/wo/mlp layout WITHOUT a Krea-unique token
    # (txtfusion / qknorm) is generic SwiGLU-transformer naming and must
    # not be claimed as Krea 2.
    generic = [k for k in keys if "qknorm" not in k]
    assert _detect(generic) != "Krea 2"

    # Negative: Flux 2 double/single stream layout stays Flux 2.
    flux2_keys = [
        "double_stream_modulation_img.lin.weight",
        "double_blocks.0.img_attn.qkv.weight",
        "single_blocks.0.linear1.weight",
    ]
    assert _detect(flux2_keys) == "Flux 2 Dev"

    # Negative: established families keep precedence even alongside generic
    # wq/wo/mlp tokens.
    assert _detect(
        [
            "joint_blocks.0.context_block.attn.qkv.weight",
            "joint_blocks.0.x_block.attn.qkv.weight",
            "blocks.0.attn.wq.weight",
            "blocks.0.mlp.gate.weight",
        ]
    ) == "SD3"
    assert _detect(
        [
            "patchify_proj.weight",
            "blocks.0.attn.wq.weight",
            "blocks.0.mlp.down.weight",
        ]
    ) == "LTX"


def test_krea2_txtfusion_lora_keys() -> None:
    # ComfyUI-style Krea 2 LoRA (real "krea cowgirl" header): txtfusion
    # blocks carry the unique evidence.
    keys = [
        "diffusion_model.blocks.0.attn.wq.lora_A.weight",
        "diffusion_model.blocks.0.attn.wo.lora_B.weight",
        "diffusion_model.blocks.0.mlp.gate.lora_A.weight",
        "diffusion_model.blocks.0.mlp.down.lora_B.weight",
        "diffusion_model.txtfusion.layerwise_blocks.0.attn.wq.lora_A.weight",
    ]
    assert _detect(keys) == "Krea 2"


def test_krea2_metadata_not_overridden_by_merge_recipe_text() -> None:
    # Real kreamaxEditV10 case: Krea 2 keys with sd_merge_models provenance
    # text mentioning "krea/published/kreamax-edit".  The unrelated merge
    # text must not flip the result to Flux Krea.
    keys = [
        "model.diffusion_model.blocks.0.attn.wq.weight",
        "model.diffusion_model.blocks.0.attn.wo.weight",
        "model.diffusion_model.blocks.0.mlp.gate.weight",
        "model.diffusion_model.blocks.0.mlp.down.weight",
        "model.diffusion_model.txtfusion.layerwise_blocks.0.attn.wq.weight",
    ]
    metadata = {
        "sd_merge_models": (
            '{"d3f818":{"name":"Krea/Published/KreaMAX-Edit-V1.0.safetensors",'
            '"legacy_hash":"a5f176d1","sd_merge_recipe":null}}'
        )
    }
    assert _detect(keys, metadata) == "Krea 2"

    # Declared model-version fields still decide the generic Krea family.
    assert (
        _detect(["model.layers.0.weight"], {"ss_base_model_version": "flux1-krea-dev"})
        == "Flux Krea"
    )
    # A generic Flux layout with only merge-recipe "krea" text stays a Flux
    # label, never "Flux Krea".
    flux_keys = [
        "double_blocks.0.img_attn.qkv.weight",
        "single_blocks.0.linear1.weight",
    ]
    flux_result = _detect(flux_keys, metadata)
    assert flux_result != "Flux Krea"
    assert flux_result.startswith("Flux")


def test_ideogram4_metadata_overrides_generic_layer_layout() -> None:
    keys = [
        "diffusion_model.layers.0.adaln_modulation.lora_A.weight",
        "diffusion_model.layers.0.attention.qkv.lora_A.weight",
        "diffusion_model.layers.0.feed_forward.w1.lora_A.weight",
    ]
    # With explicit trainer metadata the base model is honored.
    assert (
        _detect(keys, {"ss_base_model_version": "ideogram4"}) == "Ideogram 4"
    )

    # Negative: the same key layout without Z-Image evidence (no
    # cap_embedder, no dimension match) is left Unknown instead of being
    # guessed as Z-Image Turbo.
    assert _detect(keys) == "Unknown"


def test_mageflow_metadata_overrides_qwen_layout_guess() -> None:
    keys = [
        "diffusion_model.transformer_blocks.0.attn.add_k_proj.lora_A.weight",
        "diffusion_model.transformer_blocks.0.img_mod.1.lora_A.weight",
        "diffusion_model.transformer_blocks.0.txt_mlp.net.0.proj.lora_A.weight",
    ]
    assert (
        _detect(keys, {"ss_base_model_version": "mageflow"}) == "Mage Flow"
    )
    assert (
        _detect(keys, {"modelspec.architecture": "mageflow/lora"})
        == "Mage Flow"
    )


def test_broad_families_are_not_stolen_by_new_signatures() -> None:
    # Full Z-Image checkpoint (wrapped layout with cap_embedder) stays
    # Z-Image Turbo.
    zimage_keys = [
        "model.diffusion_model.cap_embedder.0.weight",
        "model.diffusion_model.layers.0.attention.qkv.weight",
        "model.diffusion_model.layers.0.adaLN_modulation.0.weight",
        "model.diffusion_model.final_layer.linear.weight",
    ]
    assert _detect(zimage_keys) == "Z-Image Turbo"

    # Qwen-Image diffusers layout (img_in/txt_norm + add_k_proj) stays
    # Qwen Image.  NOTE: Mage Flow full checkpoints reuse this exact layout;
    # without mageflow metadata they are not safely distinguishable
    # header-only and intentionally keep the structural Qwen Image label.
    qwen_keys = [
        "img_in.weight",
        "txt_in.weight",
        "txt_norm.weight",
        "transformer_blocks.0.attn.add_k_proj.weight",
        "transformer_blocks.0.attn.to_q.weight",
        "transformer_blocks.0.img_mod.1.weight",
        "transformer_blocks.0.img_mlp.net.0.proj.weight",
        "transformer_blocks.0.txt_mlp.net.0.proj.weight",
        "time_text_embed.timestep_embedder.linear_1.weight",
    ]
    assert _detect(qwen_keys) == "Qwen Image"

    # Krea 2 metadata (ss_base_model_version "krea2") maps to Krea 2 rather
    # than the FLUX.1 Krea label.
    assert _detect(["model.layers.0.weight"], {"ss_base_model_version": "krea2"}) == "Krea 2"
