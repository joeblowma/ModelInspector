"""Model classification, report formatting, and training metadata helpers.

This module contains the classification domain extracted from ``inspect_model``.
The helpers intentionally remain dependency-light so callers can use them from
both command-line and GUI-facing code without importing the inspection engine.
"""

import json
import re
from pathlib import Path


__all__ = [
    "classify_model_type",
    "detect_moe",
    "format_size",
    "format_params",
    "_friendly_encoder_name",
    "_safe_json_loads",
    "_extract_training_meta",
    "_apply_filename_alias_detection",
]


# ---------------------------------------------------------------------------
# Model type classification
# ---------------------------------------------------------------------------


def classify_model_type(components: dict, arch: str):
    """Classify: checkpoint, single component, or LoRA."""
    if components["lora"]:
        return "LoRA"

    has_backbone = components["unet"] or components["transformer"]
    has_aux = (
        components["vae"] or components["text_encoder"] or components["text_encoder_2"]
    )

    if has_backbone and has_aux:
        return "Checkpoint"
    if has_backbone:
        return "Backbone"
    if components["vae"] and not has_backbone:
        return "VAE"
    if (
        components["text_encoder"] or components["text_encoder_2"]
    ) and not has_backbone:
        return "Text Encoder"

    return "Unknown"


def detect_moe(keys: list[str], metadata: dict, arch: str) -> dict:
    """Detect mixture-of-experts structure from metadata first, tensor keys second."""
    lower_arch = str(arch or metadata.get("general.architecture", "")).lower()
    moe = "moe" in lower_arch
    expert_count = None
    expert_used_count = None

    def intish(value):
        if value in (None, "", "None"):
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None

    for key, value in metadata.items():
        lk = str(key).lower()
        if (
            lk.endswith(".expert_count")
            or lk.endswith(".num_experts")
            or lk.endswith(".n_experts")
        ):
            expert_count = intish(value) or expert_count
        elif (
            lk.endswith(".expert_used_count")
            or lk.endswith(".num_experts_per_tok")
            or lk.endswith(".experts_per_token")
        ):
            expert_used_count = intish(value) or expert_used_count
        if "expert" in lk or "moe" in lk:
            moe = True

    if not moe:
        expert_markers = (
            ".experts.",
            ".feed_forward.experts.",
            ".ffn.experts.",
            ".block_sparse_moe.",
            ".gate.experts.",
            ".router.",
        )
        moe = any(marker in key.lower() for key in keys for marker in expert_markers)

    return {
        "is_moe": bool(moe),
        "expert_count": expert_count,
        "expert_used_count": expert_used_count,
    }


# ---------------------------------------------------------------------------
# Report formatting
# ---------------------------------------------------------------------------


def format_size(size_bytes: int) -> str:
    size = float(size_bytes)
    units = ("B", "KB", "MB", "GB", "TB", "PB")
    for unit in units[:-1]:
        if size < 1024.0:
            return f"{size:.2f} {unit}"
        size /= 1024.0
    return f"{size:.2f} {units[-1]}"


def format_params(count: int) -> str:
    if count >= 1_000_000_000:
        return f"{count / 1_000_000_000:.2f}B"
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)


def _friendly_encoder_name(raw_name: str) -> str:
    """Map raw text encoder key names to friendly display names."""
    mapping = {
        "clip_l": "CLIP-L (OpenAI ViT-L/14)",
        "clip_g": "CLIP-G (OpenCLIP ViT-bigG)",
        "clip": "CLIP",
        "t5xxl": "T5-XXL",
        "t5": "T5",
        "qwen3_4b": "Qwen3 4B",
        "qwen2_vl": "Qwen2-VL",
        "qwen": "Qwen",
    }
    return mapping.get(raw_name.lower(), raw_name)


def _safe_json_loads(raw):
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    s = str(raw).strip()
    if not s:
        return None
    try:
        return json.loads(s)
    except Exception:
        return None


def _extract_training_meta(metadata: dict) -> dict:
    meta = {}

    def first(*keys):
        for k in keys:
            v = metadata.get(k)
            if v not in (None, "", "None"):
                return v
        return None

    train_images = first("ss_num_train_images")
    if train_images is None:
        ds_dirs = _safe_json_loads(metadata.get("ss_dataset_dirs"))
        if isinstance(ds_dirs, dict):
            train_images = (
                sum(
                    int(v.get("img_count", 0))
                    for v in ds_dirs.values()
                    if isinstance(v, dict)
                )
                or None
            )
    if train_images is not None:
        meta["train_images"] = str(train_images)

    epochs = first("ss_epoch", "ss_num_epochs")
    if epochs is not None:
        meta["epochs"] = str(epochs)

    steps = first("ss_steps", "ss_max_train_steps")
    if steps is not None:
        meta["steps"] = str(steps)

    resolution = first("ss_resolution", "modelspec.resolution")
    if resolution is not None:
        meta["resolution"] = str(resolution)

    clip_skip = first("ss_clip_skip")
    if clip_skip is not None:
        meta["clip_skip"] = str(clip_skip)

    lr_scheduler = first("ss_lr_scheduler")
    if lr_scheduler is not None:
        meta["lr_scheduler"] = str(lr_scheduler)

    mixed_precision = first("ss_mixed_precision")
    if mixed_precision is not None:
        meta["mixed_precision"] = str(mixed_precision)

    seed = first("ss_seed")
    if seed is not None:
        meta["seed"] = str(seed)

    network_module = first("ss_network_module")
    if network_module is not None:
        meta["network_module"] = str(network_module)

    started = metadata.get("ss_training_started_at")
    finished = metadata.get("ss_training_finished_at")
    if started not in (None, "", "None") and finished not in (None, "", "None"):
        try:
            duration = float(finished) - float(started)
            if duration >= 0:
                meta["training_duration_sec"] = str(int(duration))
        except Exception:
            pass

    software = _safe_json_loads(metadata.get("software"))
    if isinstance(software, dict):
        name = software.get("name")
        ver = software.get("version")
        if name and ver:
            meta["software"] = f"{name} {ver}"
        elif name:
            meta["software"] = str(name)

    training_info = _safe_json_loads(metadata.get("training_info"))
    if isinstance(training_info, dict):
        if training_info.get("step") is not None:
            meta["ti_step"] = str(training_info.get("step"))
        if training_info.get("epoch") is not None:
            meta["ti_epoch"] = str(training_info.get("epoch"))

    tag_freq = _safe_json_loads(metadata.get("ss_tag_frequency"))
    if isinstance(tag_freq, dict):
        tag_count = 0
        for v in tag_freq.values():
            if isinstance(v, dict):
                tag_count += len(v)
        if tag_count:
            meta["tag_count"] = str(tag_count)

    return meta


def _apply_filename_alias_detection(arch: str, filepath: str) -> str:
    """Optional alias detection from filename for SDXL-family off-model names."""
    stem = Path(filepath).stem.lower()
    # Normalize for robust matching across separators/order.
    # "Qwen-Edit", "qwen_edit", "edit qwen" all become token-compatible.
    collapsed = re.sub(r"[^a-z0-9]+", "", stem)
    tokens = set(re.findall(r"[a-z0-9]+", stem))

    def has_token(value: str) -> bool:
        return value in tokens

    def has_all(*values: str) -> bool:
        return all(v in tokens for v in values)

    # These aliases are opt-in and only used as fallback when enabled.
    if "ilxl" in collapsed or "illustrious" in collapsed or has_token("illu"):
        return "ILXL"
    if "pony7" in collapsed or "ponyv7" in collapsed or has_all("pony", "v7"):
        return "Pony7"
    if "pdxl" in collapsed or has_token("pony"):
        return "PDXL"
    if has_token("nai"):
        return "NAI"
    if "qwenedit" in collapsed or "editqwen" in collapsed or has_all("qwen", "edit"):
        return "Qwen Edit"
    return arch
