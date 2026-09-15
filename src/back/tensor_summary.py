"""Tensor-key component and precision summaries.

The inspection pipeline keeps tensor-header parsing deliberately separate from
the presentation layer.  This module contains the small, deterministic helpers
used to classify tensor keys, count named components, and render dtype details.
The functions operate on already-read header dictionaries; they never load
tensor payloads.
"""

from collections import Counter


DTYPE_BITS = {
    "F64": 64,
    "F32": 32,
    "F16": 16,
    "BF16": 16,
    "I64": 64,
    "I32": 32,
    "I16": 16,
    "I8": 8,
    "U8": 8,
    "F8_E4M3": 8,
    "F8_E5M2": 8,
}

DTYPE_FRIENDLY = {
    "F64": "float64",
    "F32": "float32",
    "F16": "float16",
    "BF16": "bfloat16",
    "I64": "int64",
    "I32": "int32",
    "I16": "int16",
    "I8": "int8",
    "U8": "uint8",
    "F8_E4M3": "float8 (E4M3)",
    "F8_E5M2": "float8 (E5M2)",
}


__all__ = [
    "DTYPE_BITS",
    "DTYPE_FRIENDLY",
    "_numeric_sort_key",
    "detect_components",
    "_tensor_component_bucket",
    "_summarize_dtype_mix",
    "analyze_component_precisions",
    "build_component_precision_summary",
    "build_component_precision_map",
]


def _numeric_sort_key(key: str) -> tuple:
    """Extract numeric parts for natural sorting of tensor keys.

    Splits the key into numeric and non-numeric segments, then sorts
    numerically where applicable. For example:
    - ``"blk.1.*"`` -> ``("blk.", 1, ".*")``
    - ``"blk.10.*"`` -> ``("blk.", 10, ".*")``
    - ``"model.layers.0.*"`` -> ``("model.layers.", 0, ".*")``

    The tuple shape intentionally matches the original inspection helper:
    each character is retained as a text segment and each contiguous number is
    represented as an integer segment tagged with its kind.
    """
    parts = []
    current_num = ""
    for char in key:
        if char.isdigit():
            current_num += char
        else:
            if current_num:
                parts.append((0, int(current_num)))
                current_num = ""
            parts.append((1, char))
    if current_num:
        parts.append((0, int(current_num)))
    return tuple(parts)


def detect_components(keys: list[str]):
    """Detect high-level components represented by tensor keys.

    The returned dictionary is intentionally the same schema used by the
    inspection result: standard boolean component flags plus ``text_encoders``,
    a mapping of named generic text encoders to tensor counts.  Adapter keys
    set ``lora`` for both conventional LoRA and LyCORIS-family formats.
    """
    components = {
        "unet": False,
        "transformer": False,
        "vae": False,
        "text_encoder": False,
        "text_encoder_2": False,
        "text_encoders": {},  # name -> tensor count for named text encoders
        "lora": False,
    }

    for k in keys:
        if k.startswith("model.diffusion_model."):
            components["unet"] = True
        if (
            "double_blocks." in k
            or "single_blocks." in k
            or "single_transformer_blocks." in k
            or k.startswith("transformer.")
            or k.startswith("model.double_layers.")
            or k.startswith("model.single_layers.")
        ):
            components["transformer"] = True
        if k.startswith("first_stage_model."):
            components["vae"] = True
        if (
            k.startswith("vae.")
            or (k.startswith("encoder.") and "text" not in k)
            or (k.startswith("decoder.") and "text" not in k)
        ):
            components["vae"] = True
        # Standard text encoder prefixes
        if (
            k.startswith("cond_stage_model.")
            or k.startswith("text_encoder.")
            or k.startswith("conditioner.embedders.")
        ):
            components["text_encoder"] = True
        if k.startswith("text_encoder_2."):
            components["text_encoder_2"] = True
        # Generic text_encoders.{name}.* pattern (e.g. text_encoders.clip_l,
        # text_encoders.clip_g, text_encoders.t5xxl, text_encoders.qwen3_4b)
        if k.startswith("text_encoders."):
            parts = k.split(".")
            if len(parts) >= 2:
                enc_name = parts[1]
                components["text_encoders"][enc_name] = (
                    components["text_encoders"].get(enc_name, 0) + 1
                )
                components["text_encoder"] = True
        if (
            "lora_up" in k
            or "lora_down" in k
            or "lora_A" in k
            or "lora_B" in k
            or ".lora." in k
            or k.startswith("lora_")
        ):
            components["lora"] = True
        # LyCORIS family adapters may not use lora_up/lora_down keys.
        if (
            k.startswith("lycoris_")
            or "lokr_" in k
            or "loha_" in k
            or "hada_" in k
            or "dora_" in k
            or "glora" in k
        ):
            components["lora"] = True

    return components


def _tensor_component_bucket(key: str) -> str | None:
    """Map a tensor key to a high-level model bucket."""
    if key.startswith("model.diffusion_model."):
        return "unet"
    if (
        "double_blocks." in key
        or "single_blocks." in key
        or "single_transformer_blocks." in key
        or key.startswith("transformer.")
        or key.startswith("model.double_layers.")
        or key.startswith("model.single_layers.")
    ):
        return "transformer"
    if key.startswith("first_stage_model."):
        return "vae"
    if (
        key.startswith("vae.")
        or (key.startswith("encoder.") and "text" not in key)
        or (key.startswith("decoder.") and "text" not in key)
    ):
        return "vae"
    if key.startswith("text_encoder_2."):
        return "text_encoder_2"
    if (
        key.startswith("cond_stage_model.")
        or key.startswith("text_encoder.")
        or key.startswith("conditioner.embedders.")
        or key.startswith("text_encoders.")
    ):
        return "text_encoder"
    return None


def _summarize_dtype_mix(dtype_counts: Counter[str], total_tensors: int) -> str:
    """Summarize a dtype counter using the global precision tolerance."""
    if not dtype_counts or total_tensors <= 0:
        return "-"
    if len(dtype_counts) == 1:
        only = next(iter(dtype_counts.keys()))
        return DTYPE_FRIENDLY.get(only, only)

    dominant_dtype, dominant_count = dtype_counts.most_common(1)[0]
    dominant_pct = dominant_count / total_tensors * 100
    if dominant_pct >= 99.0:
        return DTYPE_FRIENDLY.get(dominant_dtype, dominant_dtype)
    return (
        "Mixed ("
        + ", ".join(DTYPE_FRIENDLY.get(d, d) for d, _ in dtype_counts.most_common())
        + ")"
    )


def analyze_component_precisions(tensor_info: dict) -> dict[str, Counter[str]]:
    """Build per-component dtype counters from tensor keys."""
    component_dtypes: dict[str, Counter[str]] = {}
    for name, info in tensor_info.items():
        bucket = _tensor_component_bucket(name)
        if not bucket:
            continue
        dtype = info.get("dtype", "unknown")
        if bucket not in component_dtypes:
            component_dtypes[bucket] = Counter()
        component_dtypes[bucket][dtype] += 1
    return component_dtypes


def build_component_precision_summary(component_dtypes: dict[str, Counter]) -> str:
    """Render per-component precision summary for mixed checkpoints."""
    ordered_labels = [
        ("unet", "UNet"),
        ("transformer", "Transformer"),
        ("vae", "VAE"),
        ("text_encoder", "Text Encoder"),
        ("text_encoder_2", "Text Encoder 2"),
    ]
    parts = []
    for key, label in ordered_labels:
        dtype_counts = component_dtypes.get(key)
        if not dtype_counts:
            continue
        summary = _summarize_dtype_mix(dtype_counts, sum(dtype_counts.values()))
        parts.append(f"{label}: {summary}")
    return " | ".join(parts)


def build_component_precision_map(
    component_dtypes: dict[str, Counter],
) -> dict[str, str]:
    """Return per-component precision summaries keyed by component id."""
    ordered_keys = [
        "unet",
        "transformer",
        "vae",
        "text_encoder",
        "text_encoder_2",
    ]
    out: dict[str, str] = {}
    for key in ordered_keys:
        dtype_counts = component_dtypes.get(key)
        if not dtype_counts:
            continue
        out[key] = _summarize_dtype_mix(dtype_counts, sum(dtype_counts.values()))
    return out
