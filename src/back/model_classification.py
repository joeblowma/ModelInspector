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
    "has_language_component",
    "has_vision_component",
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


_VISION_PREFIXES = (
    "vision_tower.",
    "model.vision_tower.",
    "vision_model.",
    "model.vision_model.",
    "visual.",
    "model.visual.",
    "vision_encoder.",
    "model.vision_encoder.",
    "image_encoder.",
    "model.image_encoder.",
    "clip_vision_model.",
    "model.clip_vision_model.",
)

_VISION_EVIDENCE_PATTERNS = (
    re.compile(r"(?:^|\.)(?:encoder|layers?|blocks|resblocks|transformer_blocks)\.\d+(?:\.|$)"),
    re.compile(
        r"(?:^|\.)(?:patch_embed|patch_embedding|embeddings|position_embeddings?|"
        r"class_embedding|conv1|stem)(?:\.|$)"
    ),
    re.compile(
        r"(?:^|\.)(?:self_attn|attn|attention|q_proj|k_proj|v_proj|qkv|"
        r"to_[qkv])(?:\.|$)"
    ),
    re.compile(r"(?:^|\.)(?:mlp|fc[12]|resampler|merger)(?:\.|$)"),
)


def has_vision_component(keys: list[str]) -> bool:
    """Return whether keys provide credible evidence of a vision tower.

    A single tensor with a suggestive container name is not enough: partial
    exports and unrelated tensors can use the same roots.  Require multiple
    tensors from a known vision root plus two distinct structural signals,
    such as indexed encoder blocks and attention/projection weights.  This
    covers the existing CLIP/LLaVA-style ``vision_tower`` and ``vision_model``
    layouts as well as Qwen-VL-style ``visual.blocks`` layouts.
    """
    candidates = [
        str(key).lower()
        for key in keys
        if str(key).lower().startswith(_VISION_PREFIXES)
    ]
    if len(candidates) < 2:
        return False

    evidence = {
        index
        for index, pattern in enumerate(_VISION_EVIDENCE_PATTERNS)
        if any(pattern.search(key) for key in candidates)
    }
    return len(evidence) >= 2


_LANGUAGE_SIGNATURES = re.compile(
    r"(?:causallm|conditionalgeneration|seq2seqlm|llama|mistral|mixtral|qwen|"
    r"gemma|gpt|phi|bert|t5|deepseek|internlm|starcoder|command|olmo|"
    r"mamba|rwkv|nemotron|falcon|glm|baichuan|chatglm|llava|internvl|"
    r"paligemma|smollm|language|llm)",
    re.IGNORECASE,
)
_NON_LANGUAGE_SIGNATURES = re.compile(
    r"(?:diffusion|stable[-_ ]diffusion|flux|sdxl|sd3|unet|vae|mmproj|"
    r"multimodalprojector|multi_modal_projector|vision|clip|vit|siglip|swin)",
    re.IGNORECASE,
)


def has_language_component(
    keys: list[str],
    architecture: str | None = None,
    config: dict | None = None,
    metadata: dict | None = None,
) -> bool:
    """Return language evidence without treating a vision tower as an LLM."""
    config = config if isinstance(config, dict) else {}
    metadata = metadata if isinstance(metadata, dict) else {}
    text_config = config.get("text_config")
    if isinstance(text_config, dict) and any(
        key in text_config for key in ("num_hidden_layers", "hidden_size", "vocab_size")
    ):
        return True
    candidates = [architecture or "", metadata.get("general.architecture", ""), config.get("model_type", "")]
    candidates.extend(config.get("architectures", []) if isinstance(config.get("architectures"), list) else [])
    candidate_text = " ".join(str(value) for value in candidates)
    if _LANGUAGE_SIGNATURES.search(candidate_text) and not _NON_LANGUAGE_SIGNATURES.search(candidate_text):
        return True
    lowered = [str(key).lower() for key in keys]
    if any(
        ("embed_tokens" in key or "gpt_neox.layers." in key or "transformer.h." in key)
        and not any(
            marker in key
            for marker in (
                "vision",
                "visual",
                "image_encoder",
                "mmproj",
                "projector",
                "diffusion",
                "unet",
                "clip",
                "vit",
                "siglip",
            )
        )
        for key in lowered
    ):
        return True
    return False


def _is_mmproj_gguf(arch: str, filepath: str | None, file_format: str | None) -> bool:
    """Recognize only the explicit, standalone GGUF CLIP projector form."""
    normalized_arch = str(arch or "").strip().casefold()
    if normalized_arch.startswith("gguf "):
        normalized_arch = normalized_arch[5:].strip()
    if normalized_arch != "clip":
        return False

    format_name = str(file_format or "").strip().casefold().lstrip(".")
    if not format_name:
        format_name = Path(str(filepath or "")).suffix.casefold().lstrip(".")
    if format_name != "gguf":
        return False
    return "mmproj" in Path(str(filepath or "")).name.casefold()


def classify_model_type(
    components: dict,
    arch: str,
    filepath: str | None = None,
    file_format: str | None = None,
):
    """Classify: multimodal, checkpoint, single component, or LoRA."""
    if _is_mmproj_gguf(arch, filepath, file_format):
        return "mmproj"
    if components.get("lora"):
        return "LoRA"
    if components.get("vision"):
        return "MLLM"

    has_backbone = components.get("unet") or components.get("transformer")
    has_aux = (
        components.get("vae")
        or components.get("text_encoder")
        or components.get("text_encoder_2")
    )

    if has_backbone and has_aux:
        return "Checkpoint"
    if has_backbone:
        return "Backbone"
    if components.get("vae") and not has_backbone:
        return "VAE"
    if (
        components.get("text_encoder") or components.get("text_encoder_2")
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
