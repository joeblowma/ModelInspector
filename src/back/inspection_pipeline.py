"""Cache-aware model inspection orchestration.

This module contains the structured inspection operation used by both the
command-line application and the desktop application.  It deliberately works
from model headers: tensor payloads are never loaded while producing the
summary returned by :func:`inspect_file`.

The result schema is kept compatible with the historical ``inspect_model``
entry point.  In particular, cached results are refreshed with the caller's
path spelling and the current display path, while newly parsed results retain
all metadata, precision, adapter, and mixture-of-experts fields.
"""

from pathlib import Path

from model_cache import (
    get_cached_inspection,
    store_cached_inspection,
    store_model_data,
)
from model_readers import (
    LLAMA_FILE_TYPE_NAMES,
    analyze_tensors,
    model_format_for_path,
    read_model_header,
)

from .adapter_detection import detect_adapter_type
from .architecture_metadata import detect_architecture
from .model_classification import (
    _apply_filename_alias_detection,
    _extract_training_meta,
    _friendly_encoder_name,
    detect_moe,
    format_params,
    format_size,
    classify_model_type,
)
from .tensor_summary import (
    DTYPE_BITS,
    DTYPE_FRIENDLY,
    _numeric_sort_key,
    _summarize_dtype_mix,
    analyze_component_precisions,
    build_component_precision_map,
    build_component_precision_summary,
    detect_components,
)


__all__ = [
    "inspect_file",
    "_resolve_display_path",
]


def _resolve_display_path(filepath: str) -> str:
    """Return a canonical display path, falling back for missing files."""
    try:
        return str(Path(filepath).resolve(strict=True))
    except OSError:
        return str(Path(filepath).absolute())


def _refresh_cached_result(filepath: str, cached: dict) -> dict:
    """Apply current path and format details to a cached inspection result."""
    refreshed = dict(cached)
    refreshed["filepath"] = filepath
    refreshed["resolved_filepath"] = _resolve_display_path(filepath)
    refreshed["filename"] = Path(filepath).name

    architecture = str(refreshed.get("architecture") or "")
    if architecture.startswith("GGUF "):
        refreshed["architecture"] = architecture[5:]
    if not refreshed.get("format"):
        refreshed["format"] = model_format_for_path(filepath)

    metadata = refreshed.get("metadata") or {}
    file_type = metadata.get("general.file_type")
    quantization = str(refreshed.get("quantization") or "")
    if (not quantization or quantization.startswith("FILE_TYPE_")) and isinstance(
        file_type, int
    ):
        refreshed["quantization"] = LLAMA_FILE_TYPE_NAMES.get(
            file_type, f"FILE_TYPE_{file_type}"
        )
    if "is_moe" not in refreshed:
        refreshed.update(
            detect_moe([], metadata, str(refreshed.get("architecture") or ""))
        )
    return refreshed


def _build_dtype_list(dtypes, tensor_count: int) -> list[dict]:
    """Build the public dtype list in counter order."""
    return [
        {
            "dtype": dtype,
            "friendly": DTYPE_FRIENDLY.get(dtype, dtype),
            "bits": DTYPE_BITS.get(dtype, 0),
            "count": count,
            "pct": round(count / tensor_count * 100, 1),
        }
        for dtype, count in dtypes.most_common()
    ]


def _build_extra_metadata(metadata: dict, training_meta: dict, adapter_type, moe_info):
    """Collect the concise metadata fields surfaced in inspection cards."""
    extra = {}
    direct_fields = (
        ("ss_network_dim", "training_rank"),
        ("ss_network_alpha", "training_alpha"),
        ("ss_lr", "learning_rate"),
        ("ss_optimizer", "optimizer"),
        ("ss_training_comment", "training_comment"),
        ("ss_output_name", "output_name"),
        ("modelspec.title", "model_title"),
        ("modelspec.description", "model_description"),
        ("modelspec.author", "author"),
    )
    for source_key, output_key in direct_fields:
        if metadata.get(source_key):
            extra[output_key] = metadata[source_key]

    if adapter_type:
        extra["adapter_type"] = adapter_type
    if moe_info["is_moe"]:
        extra["moe"] = "Yes"
        if moe_info["expert_count"] is not None:
            extra["expert_count"] = moe_info["expert_count"]
        if moe_info["expert_used_count"] is not None:
            extra["expert_used_count"] = moe_info["expert_used_count"]
    for metadata_key, metadata_value in training_meta.items():
        if metadata_key not in extra:
            extra[metadata_key] = metadata_value
    return extra


def inspect_file(filepath: str, options: dict | None = None) -> dict:
    """Analyze one model header and return the structured inspection result."""
    options = options or {}
    cached = get_cached_inspection(filepath, options)
    if cached is not None:
        return _refresh_cached_result(filepath, cached)

    allow_aliases = bool(options.get("allow_filename_alias_detection", False))
    metadata, tensor_info, file_size = read_model_header(filepath)
    if options.get("cache_full_data", False):
        store_model_data(filepath, metadata, tensor_info, file_size, options)

    resolved_filepath = _resolve_display_path(filepath)
    file_format = metadata.get("smi.format") or model_format_for_path(filepath)
    quantization = metadata.get("smi.quantization")
    keys = sorted(tensor_info.keys(), key=_numeric_sort_key)
    dtypes, total_params, shapes = analyze_tensors(tensor_info)
    components = detect_components(keys)
    architecture, arch_details = detect_architecture(
        keys, shapes, total_params, components, metadata
    )
    if allow_aliases:
        architecture = _apply_filename_alias_detection(architecture, filepath)
    model_type = classify_model_type(components, architecture)
    moe_info = detect_moe(keys, metadata, architecture)
    adapter_type = detect_adapter_type(keys, metadata)
    training_meta = _extract_training_meta(metadata)
    warnings = list(metadata.get("smi.warnings") or [])

    dtype_list = _build_dtype_list(dtypes, len(tensor_info))
    precision_summary = _summarize_dtype_mix(dtypes, len(tensor_info))
    component_dtypes = analyze_component_precisions(tensor_info)
    component_precision_summary = build_component_precision_summary(component_dtypes)
    component_precisions = build_component_precision_map(component_dtypes)
    if precision_summary.startswith("Mixed (") and component_precision_summary:
        precision_display = component_precision_summary
    else:
        precision_display = precision_summary

    comp_flags = {key: value for key, value in components.items() if key != "text_encoders"}
    named_enc = {
        _friendly_encoder_name(name): count
        for name, count in components.get("text_encoders", {}).items()
    }

    lora_rank = arch_details.pop("lora_rank", None)
    detected_adapter = arch_details.pop("adapter_type", None) or adapter_type
    extra = _build_extra_metadata(metadata, training_meta, detected_adapter, moe_info)

    result = {
        "filepath": filepath,
        "resolved_filepath": resolved_filepath,
        "format": file_format,
        "filename": Path(filepath).name,
        "file_size": file_size,
        "file_size_friendly": format_size(file_size),
        "tensor_count": len(tensor_info),
        "total_params": total_params,
        "total_params_friendly": format_params(total_params),
        "architecture": architecture,
        "arch_details": arch_details,
        "model_type": model_type,
        "components": comp_flags,
        "named_text_encoders": named_enc,
        "lora_rank": lora_rank,
        "adapter_type": detected_adapter,
        "quantization": quantization,
        "is_moe": moe_info["is_moe"],
        "expert_count": moe_info["expert_count"],
        "expert_used_count": moe_info["expert_used_count"],
        "training_meta": training_meta,
        "dtypes": dtype_list,
        "precision_summary": precision_summary,
        "component_precision_summary": component_precision_summary,
        "component_precisions": component_precisions,
        "precision_display": precision_display,
        "metadata": metadata,
        "extra": extra,
        "warnings": warnings,
    }
    store_cached_inspection(filepath, result, options)
    return result
