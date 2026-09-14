"""Architecture-family variant detection helpers.

This module contains the family-specific refinement logic used by the ordered
key dispatcher in :mod:`architecture_keys`.  It intentionally has no imports
from the dispatcher, keeping the dependency direction one-way.
"""

import json
import re


__all__ = [
    "_build_metadata_blob",
    "_collect_lora_up_dims",
    "_detect_flux_variant",
    "_detect_from_dims",
    "_detect_sd_variant",
    "_detect_sdxl_pony_ilxl",
    "_detect_wan_variant",
    "_detect_zimage_variant",
    "_max_block_index",
    "_zimage_label",
]


def _max_block_index(keys: list[str], block_name: str) -> int:
    mx = -1
    for k in keys:
        if block_name in k:
            try:
                idx = int(k.split(block_name)[1].split(".")[0])
                mx = max(mx, idx)
            except (ValueError, IndexError):
                pass
    return mx


def _collect_lora_up_dims(keys, shapes):
    """Collect the output dimensions of lora_up / lora_B weights."""
    dims = set()
    for k in keys:
        if ("lora_up" in k or "lora_B" in k) and k.endswith(".weight"):
            s = shapes.get(k, [])
            if len(s) >= 2:
                dims.add(s[0])
    return dims


def _build_metadata_blob(metadata: dict):
    """Build normalized metadata text plus key fields for variant detection."""
    spec = metadata.get("modelspec.architecture", "").lower()
    gguf_arch = metadata.get("general.architecture", "").lower()
    gguf_name = metadata.get("general.name", "").lower()
    ss = metadata.get("ss_base_model_version", "").lower()
    title = metadata.get("modelspec.title", "").lower()
    desc = metadata.get("modelspec.description", "").lower()
    output_name = metadata.get("ss_output_name", "").lower()
    sd_model = metadata.get("ss_sd_model_name", "").lower()

    all_meta = (
        f"{spec} {gguf_arch} {gguf_name} {ss} {title} {desc} {output_name} {sd_model}"
    )
    for _, mv in metadata.items():
        v = str(mv).lower()
        if len(v) < 200:
            all_meta += " " + v

    sshs_meta = ""
    for cpk in ("sshs_cp0", "sshs_cp1"):
        cpv = metadata.get(cpk, "")
        if cpv and len(cpv) > 200:
            extracted = []
            decoded = cpv
            for _ in range(2):
                try:
                    parsed = json.loads(decoded)
                except Exception:
                    break
                if isinstance(parsed, str):
                    decoded = parsed
                    continue
                if isinstance(parsed, dict):
                    for field in (
                        "ss_sd_model_name",
                        "ss_output_name",
                        "modelspec.title",
                        "modelspec.description",
                        "ss_base_model_version",
                    ):
                        fv = parsed.get(field)
                        if fv:
                            extracted.append(str(fv).lower())
                    break

            if not extracted:
                cpv_l = str(cpv).lower()
                for field in (
                    "ss_sd_model_name",
                    "ss_output_name",
                    "modelspec.title",
                    "modelspec.description",
                    "ss_base_model_version",
                ):
                    pat = rf'(?:\\?"{re.escape(field)}\\?"\s*:\s*\\?"([^"\\]+))'
                    m = re.search(pat, cpv_l)
                    if m:
                        extracted.append(m.group(1).lower())

            if extracted:
                sshs_meta += " " + " ".join(extracted)
    all_meta += " " + sshs_meta
    # Declared model-version fields only (no free text such as descriptions
    # or sd_merge_* recipe blobs).  Used for generic family-name checks where
    # unrelated merge-recipe mentions must not decide the architecture.
    declared = f"{spec} {gguf_arch} {ss} {title} {sd_model}"
    return {
        "all_meta": all_meta,
        "sshs_meta": sshs_meta,
        "declared": declared,
        "spec": spec,
        "gguf_arch": gguf_arch,
        "ss": ss,
        "output_name": output_name,
        "sd_model": sd_model,
    }


def _zimage_label(metadata=None, key_blob=""):
    """Return canonical Z-Image label from behavior hints (CFG vs no-CFG)."""
    all_hints = key_blob.lower()
    if metadata:
        meta = _build_metadata_blob(metadata)
        all_hints = f"{all_hints} {meta['all_meta']}"

    has_cfg_true = bool(
        re.search(
            r'(?:use_cfg|do_cfg|classifier[_ ]?free[_ ]?guidance)\s*["=: ]+\s*true',
            all_hints,
        )
    )
    has_cfg_false = bool(
        re.search(
            r'(?:use_cfg|do_cfg|classifier[_ ]?free[_ ]?guidance)\s*["=: ]+\s*false',
            all_hints,
        )
    )

    if has_cfg_false:
        return "Z-Image Turbo"
    if has_cfg_true:
        return "Z-Image Base"
    return "Z-Image Turbo"


def _detect_flux_variant(keys, key_blob, shapes, total_params, details):
    """Distinguish Flux.1 Dev / Schnell / Kontext and count blocks."""
    db = _max_block_index(keys, "double_blocks.") + 1
    sb = _max_block_index(keys, "single_blocks.") + 1

    if db <= 0:
        db = _max_block_index(keys, "transformer_blocks.") + 1
    if sb <= 0:
        sb = _max_block_index(keys, "single_transformer_blocks.") + 1

    if db > 0:
        details["double_blocks"] = db
    if sb > 0:
        details["single_blocks"] = sb

    has_guidance = "guidance_in" in key_blob
    is_lora = "lora_A" in key_blob or "lora_B" in key_blob or "lora_down" in key_blob

    if db == 19 and sb == 38:
        details["guidance_input"] = has_guidance
        if has_guidance:
            return "Flux.1 Dev", details
        return "Flux.1 Schnell", details

    if is_lora:
        details["guidance_input"] = has_guidance
        return "Flux.1 Dev", details

    if 0 < db < 19 or 0 < sb < 38:
        details["guidance_input"] = has_guidance
        return "Flux (compact variant)", details

    details["guidance_input"] = has_guidance
    return "Flux.1 Dev", details


def _detect_sd_variant(
    keys, key_blob, shapes, total_params, components, metadata, details
):
    """Distinguish SD 1.5 vs SDXL (full checkpoints and LoRAs)."""
    is_sdxl = (
        "label_emb" in key_blob
        or "conditioner" in key_blob
        or "lora_te2_" in key_blob
        or "lora_te1_" in key_blob
    )

    if not is_sdxl:
        up_dims = _collect_lora_up_dims(keys, shapes)
        if any(d == 2048 or d == 2816 for d in up_dims):
            is_sdxl = True

    if is_sdxl:
        arch = _detect_sdxl_pony_ilxl(keys, metadata, details)
    else:
        arch = "SD 1.5"

    if not components.get("lora"):
        if components.get("vae") and components.get("text_encoder"):
            details["model_type"] = "Checkpoint"
        elif components.get("vae"):
            details["model_type"] = "Checkpoint (UNet + VAE)"
        elif components.get("text_encoder"):
            details["model_type"] = "Checkpoint (UNet + Text Enc)"
        else:
            details["model_type"] = "UNet only"

    return arch, details


def _detect_sdxl_pony_ilxl(keys, metadata, details):
    """Distinguish PDXL / ILXL / NAI from generic SDXL where metadata permits."""
    meta_blob = _build_metadata_blob(metadata)["all_meta"]
    if (
        ("pony" in meta_blob and "v7" in meta_blob)
        or "ponyv7" in meta_blob
        or "pony v7" in meta_blob
    ):
        return "Pony7"
    if "pony" in meta_blob or "pdxl" in meta_blob:
        return "PDXL"
    if "illustrious" in meta_blob or "ilxl" in meta_blob or "noobai" in meta_blob:
        return "ILXL"
    if "noob" in meta_blob or " nai " in f" {meta_blob} ":
        return "NAI"
    return "SDXL"


def _detect_zimage_variant(keys, shapes, metadata, details):
    """Distinguish Z-Image from Lumina 2, including Z-Image LoRAs."""
    key_blob = "\n".join(keys)
    has_lumina_marker = "lumina" in key_blob
    has_cap_embedder = any("cap_embedder" in k for k in keys)

    has_wrapped_diffusion = any(k.startswith("model.diffusion_model.") for k in keys)
    has_flat_layers = any(re.match(r"^layers\.\d+\.", k) for k in keys)
    if has_wrapped_diffusion:
        details["zimage_layout"] = "wrapped_diffusion_model"
        return "Z-Image Turbo", details
    if has_flat_layers and not has_wrapped_diffusion:
        details["zimage_layout"] = "flat_layers"
        return "Z-Image Base", details

    for k in keys:
        if "cap_embedder" in k and k.endswith(".weight"):
            s = shapes.get(k, [])
            if s:
                max_dim = max(s)
                if max_dim >= 3840:
                    return _zimage_label(metadata, key_blob), details
                if 2280 <= max_dim <= 2320:
                    return "Lumina 2", details
                if max_dim >= 2304 and max_dim < 3840 and has_lumina_marker:
                    return "Lumina 2", details

    up_dims = _collect_lora_up_dims(keys, shapes)
    if any(3800 <= d <= 3900 for d in up_dims):
        return _zimage_label(metadata, key_blob), details
    if any(2280 <= d <= 2320 for d in up_dims):
        return "Lumina 2", details

    if "lumina" in key_blob:
        return "Lumina 2", details
    if has_cap_embedder:
        return _zimage_label(metadata, key_blob), details
    # No Z-Image/Lumina evidence beyond the generic layers.N adapter layout:
    # other trainers (e.g. Ideogram 4 LoRAs) reuse the same key names, so
    # leave unconfirmed files Unknown instead of guessing Z-Image.
    details["zimage_layout"] = "unconfirmed"
    return "Unknown", details


def _detect_wan_variant(keys, shapes, total_params, metadata, details):
    """Detect Wan variant (2.1 vs 2.2), modality, and model size."""
    has_3d = any(len(shapes.get(k, [])) == 5 for k in keys)
    if has_3d:
        details["has_3d_conv"] = True

    key_blob = "\n".join(keys)
    if "vace_patch_embedding" in key_blob:
        details["wan_variant"] = "VACE"
    elif "control_adapter" in key_blob:
        details["wan_variant"] = "Camera"
    elif "img_emb" in key_blob:
        details["wan_variant"] = "I2V"

    if total_params > 0:
        if total_params < 2_000_000_000:
            details["variant_note"] = "1.3B"
        elif total_params < 10_000_000_000:
            details["variant_note"] = "Large"
        else:
            details["variant_note"] = "14B"

    block_indices = set()
    for k in keys:
        if "blocks" in k:
            try:
                for sep in ["blocks.", "blocks_"]:
                    if sep in k:
                        idx_str = k.split(sep)[1].split(".")[0].split("_")[0]
                        block_indices.add(int(idx_str))
            except (ValueError, IndexError):
                pass

    if block_indices:
        max_idx = max(block_indices)
        min_idx = min(block_indices)
        details["block_range"] = f"{min_idx}-{max_idx}"
    meta = _build_metadata_blob(metadata)
    all_meta = meta["all_meta"]
    sd_model = meta["sd_model"]
    spec = meta["spec"]

    wan_ver = "Wan"
    ver_source = f"{sd_model} {spec}"
    if "wan2.2" in ver_source or "wan 2.2" in ver_source or "2.2" in ver_source:
        wan_ver = "Wan 2.2"
    elif "wan2.1" in ver_source or "wan 2.1" in ver_source or "2.1" in ver_source:
        wan_ver = "Wan 2.1"

    has_i2v = (
        "img_emb" in key_blob or " i2v " in f" {all_meta} " or "image2video" in all_meta
    )
    has_t2v = " t2v " in f" {all_meta} " or "text2video" in all_meta
    is_lora = any(("lora_" in k or ".lora." in k or "lycoris_" in k) for k in keys)
    if has_i2v:
        return f"{wan_ver} I2V", details
    if has_t2v or not is_lora:
        return f"{wan_ver} T2V", details
    return wan_ver, details


def _detect_from_dims(keys, shapes, total_params, metadata, details):
    """Last-resort dimension detection for ambiguous ``blocks.N`` models."""
    up_dims = _collect_lora_up_dims(keys, shapes)
    if not up_dims:
        for k in keys:
            if k.endswith(".weight") and "blocks" in k:
                s = shapes.get(k, [])
                if len(s) >= 2:
                    up_dims.add(max(s))

    if any(3800 <= d <= 3900 for d in up_dims):
        return _zimage_label(metadata, "\n".join(keys)), details
    if any(1400 <= d <= 1420 for d in up_dims):
        return "Hunyuan", details
    if any(1520 <= d <= 1550 for d in up_dims):
        return "Wan", details
    if any(5100 <= d <= 5150 for d in up_dims):
        return "Wan", details

    return "Unknown", details
