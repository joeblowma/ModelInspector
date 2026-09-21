"""Metadata-first model architecture detection.

Metadata fields provide the most reliable architecture signal, especially for
adapter files.  When metadata is inconclusive, :func:`detect_architecture`
delegates to the ordered key-pattern detector in :mod:`architecture_keys`.
"""

import re

from .architecture_keys import (
    _build_metadata_blob,
    _detect_from_keys,
    _detect_lora_rank,
    _zimage_label,
    detect_adapter_type,
)
from .companion_discovery import companion_architecture_hint


__all__ = [
    "detect_architecture",
    "_build_metadata_blob",
    "_detect_from_metadata",
    "_zimage_label",
]


def _block_indices(keys: list[str], block_names: tuple[str, ...]) -> set[int]:
    """Collect block indices without confusing single and dual block names."""
    indices: set[int] = set()
    for block_name in block_names:
        pattern = re.compile(rf"(?:^|\.){re.escape(block_name)}\.(\d+)(?:\.|$)")
        for key in keys:
            match = pattern.search(key)
            if match:
                indices.add(int(match.group(1)))
    return indices


def _is_standard_flux_lora_header(
    keys: list[str], shapes: dict, components: dict
) -> bool:
    """Recognize the unambiguous FLUX LoRA header signature.

    Diffusers FLUX adapters can expose ``add_k_proj``/``add_q_proj`` names,
    which the broad Qwen detector also uses.  The complete 19/38 block layout
    and rank-64 adapter evidence are stronger header-only signals, so keep this
    check here, before the general metadata and key-pattern dispatch.
    """
    if not components.get("lora"):
        return False

    key_blob = "\n".join(keys).lower()
    if "add_k_proj" not in key_blob or "add_q_proj" not in key_blob:
        return False
    if _detect_lora_rank(keys, shapes) != 64:
        return False

    dual_blocks = _block_indices(keys, ("double_blocks", "transformer_blocks"))
    single_blocks = _block_indices(
        keys, ("single_blocks", "single_transformer_blocks")
    )
    return dual_blocks == set(range(19)) and single_blocks == set(range(38))


def detect_architecture(
    keys: list[str],
    shapes: dict,
    total_params: int,
    components: dict,
    metadata: dict,
    companion: dict | None = None,
):
    """Detect model architecture. Returns (arch_name, details_dict)."""
    details = {}

    # Surface useful metadata
    spec_arch = metadata.get("modelspec.architecture", "")
    if spec_arch:
        details["metadata_architecture"] = spec_arch
    gguf_arch = metadata.get("general.architecture", "")
    if gguf_arch:
        details["metadata_architecture"] = gguf_arch
    ss_base = metadata.get("ss_base_model_version", "")
    if ss_base:
        details["training_base_model"] = ss_base

    # LoRA rank (compute early, attach to details)
    if components["lora"]:
        details["lora_rank"] = _detect_lora_rank(keys, shapes)
        adapter_type = detect_adapter_type(keys, metadata)
        if adapter_type:
            details["adapter_type"] = adapter_type

    # The exact FLUX adapter header is more specific than the broad Qwen
    # add_* projection heuristic (and remains header-only, with no payload
    # access).  LoRA headers do not reliably retain the guidance input marker,
    # so use the conventional Dev label for this standard layout.
    if _is_standard_flux_lora_header(keys, shapes, components):
        details["double_blocks"] = 19
        details["single_blocks"] = 38
        details["guidance_input"] = any("guidance_in" in k.lower() for k in keys)
        return "Flux.1 Dev", details

    # 1. Try metadata-based detection (most reliable, especially for LoRAs)
    meta_result = _detect_from_metadata(metadata)
    if meta_result:
        return meta_result, details

    # 2. Tensor-key detection remains stronger than a generic config hint.
    key_blob = "\n".join(keys)
    key_result = _detect_from_keys(
        keys, key_blob, shapes, total_params, components, metadata, details
    )
    companion_result = companion_architecture_hint(companion)
    if companion_result and key_result[0] in {
        "Unknown",
        "Qwen (text encoder)",
        "Transformer (language)",
        "GPT-style Transformer",
    }:
        details["companion_architecture"] = companion_result
        return companion_result, details
    return key_result


def _detect_from_metadata(metadata: dict):
    """Try to identify architecture purely from safetensors __metadata__."""
    meta = _build_metadata_blob(metadata)
    all_meta = meta["all_meta"]
    sshs_meta = meta["sshs_meta"]
    gguf_arch = meta["gguf_arch"]
    ss = meta["ss"]
    spec = meta["spec"]
    output_name = meta["output_name"]
    sd_model = meta["sd_model"]

    if not all_meta.strip():
        return None

    # Order matters: check specific variants before generic families

    normalized_spec = re.sub(r"[-\s]+", "_", spec)
    if normalized_spec in {"qwen_image_2.1_vae", "qwen_image_2_1_vae"}:
        return "Qwen Image 2.1 VAE"
    if normalized_spec in {"qwen_image_2.1", "qwen_image_2_1"}:
        return "Qwen Image 2.1"

    # Chroma
    if "chroma" in all_meta:
        return "Chroma"
    # Aura Flow
    if "auraflow" in all_meta or "aura_flow" in all_meta or "aura flow" in all_meta:
        return "Aura Flow"

    # Krea 2 before the generic "krea" check (which maps to FLUX.1 Krea).
    if "krea2" in all_meta or "krea 2" in all_meta:
        return "Krea 2"
    # Mage Flow: explicit trainer metadata (ss_base_model_version /
    # modelspec.architecture "mageflow").
    if "mageflow" in all_meta:
        return "Mage Flow"
    # Ideogram 4: explicit ss_base_model_version ("ideogram4"); its LoRAs
    # reuse the generic Lumina-style layers.N key layout, so only trust the
    # dedicated base-model field here.
    if "ideogram4" in ss or "ideogram 4" in ss:
        return "Ideogram 4"

    # Flux variants (specific before generic)
    if "kontext" in all_meta:
        return "Flux Kontext"
    # Generic "krea" only trusts declared model-version fields (spec /
    # ss_base_model_version / title / sd_model_name).  Merge-recipe text
    # (sd_merge_recipe / sd_merge_models) mentioning "Krea" is unrelated
    # provenance and must not label a Krea 2 file "Flux Krea".
    if "krea" in meta["declared"]:
        return "Flux Krea"
    # Flux 2 Klein: must have "klein" explicitly
    if "klein" in all_meta:
        return "Flux 2 Klein"
    # Flux 2: "flux2" without "klein"
    if "flux2" in all_meta or "flux.2" in all_meta or "flux 2" in all_meta:
        return "Flux 2"
    if "flux" in all_meta:
        if "schnell" in all_meta:
            return "Flux.1 Schnell"
        return "Flux.1 Dev"

    # LTX / LNX (before HiDream; some LTX variants can contain caption_projection)
    if "lnx" in all_meta:
        return "LNX Video"
    if "ltx" in all_meta:
        if "ltxvideo2" in all_meta or "ltx2" in all_meta or "ltx-2" in all_meta:
            return "LTX 2"
        return "LTX"

    # HiDream
    if "hidream" in all_meta:
        return "HiDream"

    if gguf_arch:
        return gguf_arch

    # SD3 variants (check 3.5 before 3)
    if (
        "sd3.5" in all_meta
        or "sd35" in all_meta
        or "stable-diffusion-3.5" in all_meta
        or "stable_diffusion_3_5" in all_meta
        or "3-5-large" in all_meta
        or "3-5-medium" in all_meta
        or "stable-diffusion-3-3-5" in all_meta
    ):
        return "SD3.5"
    if (
        "sd3" in all_meta
        or "stable-diffusion-v3" in all_meta
        or "stable_diffusion_3" in all_meta
        or "stable-diffusion-3" in all_meta
    ):
        # Make sure we don't false-match on "stable-diffusion-3-3-5" (already caught above)
        return "SD3"

    # SDXL variants (specific forks before generic SDXL)
    # NAI: check sshs_meta for "illustrious" from training checkpoint name
    if "noob" in all_meta or "nai" in all_meta.split():
        return "NAI"
    if (
        ("pony" in all_meta and "v7" in all_meta)
        or "ponyv7" in all_meta
        or "pony v7" in all_meta
    ):
        return "Pony7"
    if "pony" in all_meta or "pdxl" in all_meta:
        return "PDXL"
    if "illustrious" in all_meta or "ilxl" in all_meta or "noobai" in all_meta:
        return "ILXL"
    # Also check sshs_meta specifically for illustrious (NAI trained on illustrious)
    if "illustrious" in sshs_meta:
        return "ILXL"
    if "sdxl" in all_meta or "sd_xl" in all_meta:
        return "SDXL"
    if (
        "v1-5" in all_meta
        or "v1_5" in all_meta
        or "stable-diffusion-v1" in all_meta
        or ss == "sd_1.5"
        or "sd 1.5" in all_meta
        or "sd1.5" in all_meta
    ):
        return "SD 1.5"

    # Wan: check before Hunyuan because Wan metadata can include
    # implementation URLs containing "HunyuanVideo".
    if "wan" in all_meta:
        wan_ver = "Wan"
        # Version detection: check for 2.2 in sd_model_name (more reliable)
        if "wan2.2" in all_meta or "wan 2.2" in all_meta or "2.2" in sd_model:
            wan_ver = "Wan 2.2"
        elif "wan2.1" in all_meta or "wan 2.1" in all_meta or "2.1" in sd_model:
            wan_ver = "Wan 2.1"
        # HIGH/LOW noise pass detection
        if "high_noise" in all_meta or "high noise" in all_meta:
            return f"{wan_ver} HIGH"
        if "low_noise" in all_meta or "low noise" in all_meta:
            return f"{wan_ver} LOW"
        if "i2v" in all_meta or "image2video" in all_meta:
            return f"{wan_ver} I2V"
        if "t2v" in all_meta or "text2video" in all_meta:
            return f"{wan_ver} T2V"
        return wan_ver

    # Hunyuan
    if "hunyuan" in all_meta:
        if "video" in all_meta:
            return "HunyuanVideo"
        return "Hunyuan"

    # Z-Image
    if "z-image" in all_meta or "zimage" in all_meta or "z_image" in all_meta:
        return _zimage_label(metadata, all_meta)

    # Qwen
    if "qwen" in all_meta:
        if (
            "edit" in all_meta
            or "qwen_edit" in all_meta
            or "qwen-edit" in all_meta
            or "image_edit" in all_meta
        ):
            return "Qwen Edit"
        return None

    return None
