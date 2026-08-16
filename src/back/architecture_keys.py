"""Ordered key-pattern architecture detection.

The metadata detector delegates here only after metadata is inconclusive.  The
family-specific variant refinements live in :mod:`architecture_variants`, so
this module remains the single ordered dispatch point.
"""

import re
from collections import Counter

from .architecture_variants import (
    _build_metadata_blob,
    _collect_lora_up_dims,
    _detect_flux_variant,
    _detect_from_dims,
    _detect_sd_variant,
    _detect_sdxl_pony_ilxl,
    _detect_wan_variant,
    _detect_zimage_variant,
    _max_block_index,
    _zimage_label,
)


__all__ = [
    "FINGERPRINTS",
    "detect_adapter_type",
    "_build_metadata_blob",
    "_collect_lora_up_dims",
    "_detect_flux_variant",
    "_detect_from_dims",
    "_detect_from_keys",
    "_detect_lora_rank",
    "_detect_sd_variant",
    "_detect_sdxl_pony_ilxl",
    "_detect_wan_variant",
    "_detect_zimage_variant",
    "_max_block_index",
    "_zimage_label",
]


# Kept as a shared public compatibility value: the detailed ``.modelinfo``
# report scans these ordered substrings to give users a compact key overview.
FINGERPRINTS = [
    "distilled_guidance_layer",
    "individual_token_refiner",
    "double_stream_modulation",
    "joint_blocks",
    "context_block",
    "x_block",
    "caption_projection",
    "txt_norm",
    "mlp_t5",
    "cap_embedder",
    "head.modulation",
    "head_modulation",
    "adaln_single",
    "patchify_proj",
    "double_blocks",
    "single_blocks",
    "img_attn",
    "txt_attn",
    "input_blocks",
    "output_blocks",
    "middle_block",
    "label_emb",
    "conditioner",
    "diffusion_model",
    "lora_te_",
    "lora_te1_",
    "lora_te2_",
    "lora_unet_",
    "cross_attn",
    "self_attn",
    "blocks",
    "model.layers",
    "embed_tokens",
    "guidance_in",
    "attn2",
    "noise_refiner",
    "transformer_blocks",
]


def _detect_lora_rank(keys, shapes):
    """Detect the LoRA rank from the weight shapes."""
    ranks = []
    for k in keys:
        if ("lora_down" in k or "lora_A" in k) and k.endswith(".weight"):
            s = shapes.get(k, [])
            if len(s) >= 2:
                ranks.append(s[0])
    if not ranks:
        return None
    return Counter(ranks).most_common(1)[0][0]


def detect_adapter_type(keys: list[str], metadata: dict) -> str | None:
    """Detect adapter family/type when file contains adapter weights."""
    if not keys:
        return None

    key_blob = "\n".join(keys).lower()
    lyco_cfg = str(metadata.get("lycoris_config", "")).lower()
    ss_network_module = str(metadata.get("ss_network_module", "")).lower()
    ss_network_args = str(metadata.get("ss_network_args", "")).lower()
    algo_lokr = bool(
        re.search(r'"algo"\s*:\s*"lokr"', lyco_cfg + " " + ss_network_args)
    )
    algo_loha = bool(
        re.search(r'"algo"\s*:\s*"loha"', lyco_cfg + " " + ss_network_args)
    )
    algo_dora = bool(
        re.search(r'"algo"\s*:\s*"dora"', lyco_cfg + " " + ss_network_args)
    )
    algo_glora = bool(
        re.search(r'"algo"\s*:\s*"glora"', lyco_cfg + " " + ss_network_args)
    )

    if "lokr_w1" in key_blob or "lokr_w2" in key_blob or algo_lokr:
        return "LoKr"
    if (
        "hada_w1_a" in key_blob
        or "hada_w1_b" in key_blob
        or "hada_w2_a" in key_blob
        or "hada_w2_b" in key_blob
        or algo_loha
    ):
        return "LoHa"
    if "dora_scale" in key_blob or algo_dora:
        return "DoRA"
    has_glora_factorized = all(tok in key_blob for tok in (".a1", ".a2", ".b1", ".b2"))
    if "glora" in key_blob or algo_glora or has_glora_factorized:
        return "GLoRA"

    if (
        "lycoris_" in key_blob
        or "lycoris" in lyco_cfg
        or "lycoris" in ss_network_module
    ):
        return "LyCORIS"

    if (
        "lora_up" in key_blob
        or "lora_down" in key_blob
        or "lora_a" in key_blob
        or "lora_b" in key_blob
        or ".lora." in key_blob
    ):
        return "LoRA"

    return None


def _detect_from_keys(
    keys, key_blob, shapes, total_params, components, metadata, details
):
    """Apply architecture key patterns in specificity order."""
    if "distilled_guidance_layer" in key_blob:
        return "Chroma", details

    if "individual_token_refiner" in key_blob:
        return "HunyuanVideo", details

    if "double_stream_modulation" in key_blob:
        db = _max_block_index(keys, "double_blocks.") + 1
        sb = _max_block_index(keys, "single_blocks.") + 1
        if db > 0:
            details["double_blocks"] = db
        if sb > 0:
            details["single_blocks"] = sb
        meta_blob = _build_metadata_blob(metadata)["all_meta"]
        if "klein" in meta_blob:
            return "Flux 2 Klein", details
        return "Flux 2 Dev", details

    if "joint_blocks" in key_blob and (
        "context_block" in key_blob or "x_block" in key_blob
    ):
        if "x_block" in key_blob and "attn2" in key_blob:
            return "SD3.5", details
        return "SD3", details
    if "joint_blocks" in key_blob:
        return "SD3", details

    if "adaln_single" in key_blob or "patchify_proj" in key_blob:
        if "audio_adaln_single" in key_blob:
            return "LTX 2", details
        return "LTX", details

    if (
        "model.single_layers." in key_blob
        and "model.double_layers." in key_blob
        and "model.cond_seq_linear" in key_blob
    ):
        return "Aura Flow", details

    if (
        "caption_projection" in key_blob
        and "adaln_single" not in key_blob
        and "patchify_proj" not in key_blob
    ):
        return "HiDream", details

    if "add_k_proj" in key_blob or "add_q_proj" in key_blob:
        meta_blob = _build_metadata_blob(metadata)["all_meta"]
        if (
            "qwen_edit" in meta_blob
            or "qwen-edit" in meta_blob
            or "image_edit" in meta_blob
            or " edit " in f" {meta_blob} "
        ):
            return "Qwen Edit", details
        if (
            not components.get("lora")
            and "model.diffusion_model." in key_blob
            and "text_encoders.qwen" in key_blob
            and "vae." in key_blob
        ):
            return "Qwen Edit", details
        if "img_mod." not in key_blob and "txt_mod." not in key_blob:
            return "Qwen Edit", details
        if (
            "transformer.transformer_blocks" in key_blob
            and "diffusion_model" not in key_blob
        ):
            return "Qwen Edit", details
        return "Qwen Image", details
    if "txt_norm" in key_blob and "txt_in" not in key_blob:
        if "model.diffusion_model." in key_blob and not components.get("lora"):
            return "Qwen Edit", details
        return "Qwen Image", details
    if any(k.startswith("txt_norm") for k in keys):
        if "model.diffusion_model." in key_blob and not components.get("lora"):
            return "Qwen Edit", details
        return "Qwen Image", details

    if "mlp_t5" in key_blob:
        return "Hunyuan", details

    if "cap_embedder" in key_blob:
        return _detect_zimage_variant(keys, shapes, metadata, details)

    if "diffusion_model.layers." in key_blob and "attention" in key_blob:
        return _detect_zimage_variant(keys, shapes, metadata, details)
    if "auraflow" in key_blob or "aura_flow" in key_blob:
        return "Aura Flow", details

    if "head.modulation" in key_blob or "head_modulation" in key_blob:
        return _detect_wan_variant(keys, shapes, total_params, metadata, details)

    if "diffusion_model.transformer_blocks" in key_blob:
        if "attn1" in key_blob or "attn2" in key_blob:
            return "LTX", details

    if "double_blocks" in key_blob or "single_blocks" in key_blob:
        has_video_dims = any(len(shapes.get(k, [])) == 5 for k in keys)
        has_hunyuanvideo_lora_layout = (
            "transformer.double_blocks." in key_blob
            and ("img_attn_qkv" in key_blob or "txt_attn_qkv" in key_blob)
            and ("img_mod.linear" in key_blob or "txt_mod.linear" in key_blob)
        )
        if has_video_dims or has_hunyuanvideo_lora_layout:
            return "HunyuanVideo", details

    if "single_transformer_blocks" in key_blob:
        return _detect_flux_variant(keys, key_blob, shapes, total_params, details)
    if (
        "transformer.transformer_blocks" in key_blob
        and "double_blocks" not in key_blob
        and "joint_blocks" not in key_blob
        and "add_k_proj" not in key_blob
    ):
        return _detect_flux_variant(keys, key_blob, shapes, total_params, details)

    if "double_blocks" in key_blob or "single_blocks" in key_blob:
        return _detect_flux_variant(keys, key_blob, shapes, total_params, details)

    if "transformer_blocks" in key_blob:
        if (
            "input_blocks" not in key_blob
            and "output_blocks" not in key_blob
            and "diffusion_model" not in key_blob
            and "lora_unet_" not in key_blob
            and "lora_te_" not in key_blob
            and "lora_te1_" not in key_blob
            and "lora_te2_" not in key_blob
            and "down_blocks" not in key_blob
            and "up_blocks" not in key_blob
            and "mid_block" not in key_blob
            and "lycoris" not in key_blob
        ):
            return "LTX", details

    if (
        "input_blocks" in key_blob
        or "output_blocks" in key_blob
        or "middle_block" in key_blob
    ):
        return _detect_sd_variant(
            keys, key_blob, shapes, total_params, components, metadata, details
        )
    if (
        "down_blocks" in key_blob
        and "up_blocks" in key_blob
        and ("mid_block" in key_blob or "conv_in" in key_blob)
    ):
        return _detect_sd_variant(
            keys, key_blob, shapes, total_params, components, metadata, details
        )
    if "diffusion_model" in key_blob:
        if (
            "diffusion_model.transformer_blocks" not in key_blob
            and "diffusion_model.layers." not in key_blob
        ):
            return _detect_sd_variant(
                keys, key_blob, shapes, total_params, components, metadata, details
            )

    if "lora_te2_" in key_blob:
        return _detect_sdxl_pony_ilxl(keys, metadata, details), details
    if "lora_te1_" in key_blob:
        return _detect_sdxl_pony_ilxl(keys, metadata, details), details

    if "lora_te_" in key_blob and "lora_te1_" not in key_blob:
        return "SD 1.5", details

    if "cross_attn" in key_blob and "self_attn" in key_blob and "blocks" in key_blob:
        return _detect_wan_variant(keys, shapes, total_params, metadata, details)

    if "blocks" in key_blob and ("attn" in key_blob or "self_attn" in key_blob):
        return _detect_from_dims(keys, shapes, total_params, metadata, details)

    if (
        "model.layers" in key_blob
        and "self_attn" in key_blob
        and "embed_tokens" in key_blob
    ):
        return "Qwen (text encoder)", details

    if components.get("unet"):
        if (
            "conditioner." in key_blob
            or "conditioner.embedders.1" in key_blob
            or "text_encoder_2" in key_blob
            or "clip_g" in key_blob
        ):
            return _detect_sdxl_pony_ilxl(keys, metadata, details), details
        return "SD 1.5", details

    if (
        components.get("vae")
        and not components.get("unet")
        and not components.get("transformer")
    ):
        vae_prefixes = ("first_stage_model.", "vae.", "encoder.", "decoder.")
        non_vae = [
            k for k in keys if not any(k.startswith(pref) for pref in vae_prefixes)
        ]
        if len(non_vae) <= max(8, len(keys) // 50):
            return "VAE (standalone)", details
    if (
        components.get("text_encoder")
        and not components.get("unet")
        and not components.get("transformer")
    ):
        return "Text Encoder (standalone)", details

    return "Unknown", details
