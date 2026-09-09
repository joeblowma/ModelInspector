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
    is_checkpoint_model_path,
    model_format_for_path,
    read_model_header,
)

from .adapter_detection import detect_adapter_type
from .architecture_metadata import detect_architecture
from .capability_facts import build_capability_facts
from .checkpoint_reader import (
    CHECKPOINT_SAFETY_REJECT,
    UnsafeCheckpointError,
    normalize_checkpoint_safety,
)
from .sidecar_discovery import (
    SidecarRecord,
    discover_sidecars,
    sidecar_identity_snapshot,
)
from .shard_discovery import discover_shard_set
from .companion_discovery import (
    build_architecture_facts,
    companion_identities,
    discover_companion_metadata,
)
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


from back.model_classification import has_vision_component


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
    if str(refreshed.get("model_type") or "Unknown").strip().casefold() == "unknown":
        cached_components = refreshed.get("components")
        refreshed_type = classify_model_type(
            cached_components if isinstance(cached_components, dict) else {},
            str(refreshed.get("architecture") or ""),
            filepath=filepath,
            file_format=refreshed.get("format"),
        )
        if refreshed_type != "Unknown":
            refreshed["model_type"] = refreshed_type
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


def _dynamic_identity_matches(
    cached: dict,
    shard_set,
    sidecars: tuple[SidecarRecord, ...],
    include_sidecars: bool,
) -> bool:
    """Keep companion-file changes from being hidden by the primary cache key."""
    if shard_set and cached.get("shard_identity") != shard_set.identity():
        return False
    if not include_sidecars:
        return True
    cached_sidecars = cached.get("sidecar_identities")
    return cached_sidecars == sidecar_identity_snapshot(sidecars)


def _companion_identity_matches(cached: dict, current: dict) -> bool:
    """Invalidate old results when a nearby config or template changes."""
    if not isinstance(cached.get("architecture_facts"), dict) or not isinstance(
        cached.get("capability_facts"), dict
    ):
        return False
    current_identities = companion_identities(current)
    cached_identities = cached.get("companion_identities")
    if not isinstance(cached_identities, list):
        return not any(item.get("exists") for item in current_identities)
    return cached_identities == current_identities


def _attach_sidecars(
    result: dict,
    filepath: str,
    options: dict,
    sidecars: tuple[SidecarRecord, ...],
) -> None:
    """Attach compact identities and separate full records without recursion."""
    result["sidecar_identities"] = sidecar_identity_snapshot(sidecars)
    result["sidecar_roles"] = [record.role for record in sidecars]
    result["sidecar_paths"] = [record.path for record in sidecars]
    records = []
    child_options = dict(options)
    child_options["include_sidecars"] = False
    child_options["_sidecar_inspection"] = True
    for record in sidecars:
        try:
            child = inspect_file(record.path, options=child_options)
        except Exception as exc:
            child = {
                "filepath": record.path,
                "filename": Path(record.path).name,
                "format": model_format_for_path(record.path),
                "warnings": [f"Sidecar inspection failed: {exc}"],
            }
        child["sidecar_role"] = record.role
        child["sidecar_path"] = record.path
        records.append(child)
    result["sidecars"] = records
    result["sidecar_inspections"] = records


def inspect_file(
    filepath: str,
    options: dict | None = None,
    *,
    checkpoint_safety: str | None = None,
) -> dict:
    """Analyze one model header and return the structured inspection result."""
    options = dict(options or {})
    if checkpoint_safety is not None:
        options["checkpoint_safety"] = checkpoint_safety
    checkpoint_safety = normalize_checkpoint_safety(
        options.get("checkpoint_safety", CHECKPOINT_SAFETY_REJECT)
    )
    if is_checkpoint_model_path(filepath) and checkpoint_safety == CHECKPOINT_SAFETY_REJECT:
        raise UnsafeCheckpointError(
            f"Refusing checkpoint inspection for {filepath!r}; pass "
            "checkpoint_safety='metadata' to enable safe metadata-only inspection"
        )
    options["checkpoint_safety"] = checkpoint_safety
    include_sidecars = not options.get("_sidecar_inspection") and options.get(
        "include_sidecars", True
    )
    shard_set = discover_shard_set(filepath)
    sidecar_base = shard_set.primary_path if shard_set else filepath
    sidecars = discover_sidecars(sidecar_base) if include_sidecars else ()
    companion = discover_companion_metadata(filepath)
    cached = get_cached_inspection(filepath, options)
    if cached is not None and _dynamic_identity_matches(
        cached, shard_set, sidecars, include_sidecars
    ) and _companion_identity_matches(cached, companion):
        refreshed = _refresh_cached_result(filepath, cached)
        if refreshed.get("model_type") != cached.get("model_type"):
            store_cached_inspection(filepath, refreshed, options)
        return refreshed

    allow_aliases = bool(options.get("allow_filename_alias_detection", False))
    metadata, tensor_info, file_size = read_model_header(filepath, options)
    if options.get("cache_full_data", False):
        store_model_data(filepath, metadata, tensor_info, file_size, options)

    resolved_filepath = _resolve_display_path(filepath)
    file_format = metadata.get("smi.format") or model_format_for_path(filepath)
    quantization = metadata.get("smi.quantization")
    original_keys = list(tensor_info.keys())
    keys = sorted(original_keys, key=_numeric_sort_key)
    dtypes, total_params, shapes = analyze_tensors(tensor_info)
    components = detect_components(keys)
    components["vision"] = has_vision_component(keys)
    architecture, arch_details = detect_architecture(
        keys, shapes, total_params, components, metadata, companion
    )
    if allow_aliases:
        architecture = _apply_filename_alias_detection(architecture, filepath)
    architecture_facts = build_architecture_facts(keys, companion, arch_details)
    capability_facts = build_capability_facts(
        keys, metadata, companion, architecture, components
    )
    if capability_facts["domain"] in {"VLM", "MMLM"}:
        components["vision"] = True
    model_type = classify_model_type(
        components,
        architecture,
        filepath=filepath,
        file_format=file_format,
    )
    moe_info = detect_moe(keys, metadata, architecture)
    adapter_type = detect_adapter_type(keys, metadata)
    training_meta = _extract_training_meta(metadata)
    warnings = list(metadata.get("smi.warnings") or [])
    warnings.extend(str(item) for item in companion.get("warnings", []))

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
        "tensor_order": original_keys,
        "original_tensor_order": original_keys,
        "original_order": original_keys,
        "sorted_tensor_order": keys,
        "sorted_order": keys,
        "total_params": total_params,
        "total_params_friendly": format_params(total_params),
        "architecture": architecture,
        "architecture_facts": architecture_facts,
        "capability_facts": capability_facts,
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
        "companion_metadata": companion,
        "companion_identities": companion_identities(companion),
        "extra": extra,
        "warnings": warnings,
    }
    shard_manifest = metadata.get("smi.shard_manifest")
    if isinstance(shard_manifest, dict):
        result["shard_manifest"] = shard_manifest
        result["shard_identity"] = metadata.get("smi.shard_identity")
    if include_sidecars:
        _attach_sidecars(result, filepath, options, sidecars)
    store_cached_inspection(filepath, result, options)
    return result
