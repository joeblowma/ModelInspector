#!/usr/bin/env python3
"""Model-info dump helpers for Model Inspector."""

import json
from pathlib import Path

from back.adapter_detection import _collect_lora_up_dims
from back.architecture_keys import FINGERPRINTS
from back.inspection_pipeline import _resolve_display_path, inspect_file
from back.tensor_summary import _numeric_sort_key
from model_cache import get_cached_inspection_snapshot, get_cached_model_data
from model_readers import analyze_tensors, read_model_header


def _modelinfo_base_path(filepath: str, resolve_output_path: bool = False) -> str:
    if resolve_output_path:
        return _resolve_display_path(filepath)
    return filepath


def modelinfo_text_path(filepath: str, resolve_output_path: bool = False) -> str:
    return _modelinfo_base_path(filepath, resolve_output_path) + ".modelinfo"


def modelinfo_json_path(filepath: str, resolve_output_path: bool = False) -> str:
    return _modelinfo_base_path(filepath, resolve_output_path) + ".modelinfo.json"


def _read_header_or_cached(filepath: str, options: dict | None = None):
    try:
        return read_model_header(filepath, options=options)
    except Exception:
        cached = get_cached_model_data(filepath, options=options)
        if not cached:
            raise
        tensor_info = cached["tensor_info"]
        original_order = cached.get("original_tensor_order")
        if isinstance(original_order, list):
            ordered = {
                name: tensor_info[name]
                for name in original_order
                if name in tensor_info
            }
            ordered.update({name: value for name, value in tensor_info.items() if name not in ordered})
            tensor_info = ordered
        return cached["metadata"], tensor_info, int(cached["file_size"])


def _descriptor_bytes(descriptor: object) -> int | None:
    if not isinstance(descriptor, dict):
        return None
    value = descriptor.get("n_bytes")
    if value is None:
        offsets = descriptor.get("data_offsets")
        if isinstance(offsets, (list, tuple)) and len(offsets) == 2:
            try:
                value = int(offsets[1]) - int(offsets[0])
            except (TypeError, ValueError, OverflowError):
                value = None
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _descriptor_shard_id(descriptor: object) -> int:
    if not isinstance(descriptor, dict):
        return 0
    try:
        return int(descriptor.get("shard_id", 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def generate_modelinfo_dump(filepath: str, options: dict | None = None) -> str:
    """Generate detailed .modelinfo text dump using the requested header policy."""
    if options is None:
        metadata, tensor_info, file_size = _read_header_or_cached(filepath)
    else:
        metadata, tensor_info, file_size = _read_header_or_cached(filepath, options=options)
    original_keys = list(tensor_info)
    keys = sorted(tensor_info.keys(), key=_numeric_sort_key)
    _, total_params, shapes = analyze_tensors(tensor_info)

    lines = []
    sep = "=" * 70
    lines.append(sep)
    lines.append(f"  FILE: {Path(filepath).name}")
    lines.append(f"  Path: {filepath}")
    resolved_filepath = _resolve_display_path(filepath)
    if resolved_filepath != filepath:
        lines.append(f"  Resolved path: {resolved_filepath}")
    lines.append(
        f"  Keys: {len(keys)}    Params: {total_params:,}    Size: {file_size:,} bytes"
    )
    lines.append(sep)

    if metadata:
        lines.append("\n  __metadata__:")
        for mk in sorted(metadata.keys()):
            val = str(metadata[mk])
            if len(val) > 200:
                val = val[:197] + "..."
            lines.append(f"    {mk}: {val}")

    lines.append("\n  Fingerprint substring scan:")
    blob = "\n".join(keys)
    for fp in FINGERPRINTS:
        if fp in blob:
            count = sum(1 for k in keys if fp in k)
            lines.append(f"    [HIT]  {fp:<40} ({count} keys)")

    up_dims = _collect_lora_up_dims(keys, shapes)
    if up_dims:
        lines.append(f"\n  LoRA up dims (target layer sizes): {sorted(up_dims)}")

    lines.append("\n  Original tensor/block order:")
    for order, name in enumerate(original_keys, 1):
        lines.append(f"    {order:>6}. {name}")

    lines.append(f"\n  All tensor keys ({len(keys)}):")
    for k in keys:
        s = shapes.get(k, [])
        descriptor = tensor_info[k]
        d = descriptor.get("dtype", "?")
        n_bytes = _descriptor_bytes(descriptor)
        shard_id = _descriptor_shard_id(descriptor)
        lines.append(
            f"    {k}  {s}  [{d}]  n_bytes={n_bytes if n_bytes is not None else '?'}"
            f"  shard_id={shard_id}"
        )

    lines.append("")
    return "\n".join(lines)


def build_modelinfo_json_data(filepath: str, options: dict | None = None) -> dict:
    """Build the structured .modelinfo JSON payload for a model file."""
    metadata, tensor_info, file_size = _read_header_or_cached(filepath, options=options)
    dtype_counts, total_params, shapes = analyze_tensors(tensor_info)
    try:
        summary = inspect_file(filepath, options=options)
    except Exception:
        summary = get_cached_inspection_snapshot(filepath) or {}

    original_keys = list(tensor_info)
    summary_order = summary.get("original_tensor_order")
    if isinstance(summary_order, list):
        original_keys = [name for name in summary_order if name in tensor_info]
        original_keys.extend(name for name in tensor_info if name not in original_keys)
    sorted_keys = sorted(tensor_info.keys(), key=_numeric_sort_key)
    summary_sorted = summary.get("sorted_tensor_order")
    if isinstance(summary_sorted, list):
        sorted_keys = [name for name in summary_sorted if name in tensor_info]
        sorted_keys.extend(name for name in tensor_info if name not in sorted_keys)
    original_positions = {name: index for index, name in enumerate(original_keys)}
    tensors = []
    for name in sorted_keys:
        shape = shapes.get(name, [])
        params = 1
        for dim in shape:
            params *= dim
        descriptor = tensor_info[name]
        tensors.append(
            {
                "name": name,
                "shape": shape,
                "dtype": descriptor.get("dtype"),
                "parameters": params,
                "n_bytes": _descriptor_bytes(descriptor),
                "shard_id": _descriptor_shard_id(descriptor),
                "original_index": original_positions[name],
            }
        )

    warnings = list(summary.get("warnings") or [])
    result = {
        "format": f"{Path(filepath).suffix.lower().lstrip('.')}-modelinfo-json",
        "format_version": 1,
        "filepath": filepath,
        "resolved_filepath": _resolve_display_path(filepath),
        "filename": Path(filepath).name,
        "file_size": file_size,
        "inspection": summary,
        "metadata": metadata,
        "tensor_summary": {
            "tensor_count": len(tensor_info),
            "total_params": total_params,
            "dtype_counts": dict(sorted(dtype_counts.items())),
        },
        "tensors": tensors,
        "tensor_order": original_keys,
        "original_tensor_order": original_keys,
        "sorted_tensor_order": sorted_keys,
        "warnings": warnings,
    }
    for key in ("shard_manifest", "shard_identity"):
        value = summary.get(key) or metadata.get(f"smi.{key}")
        if value is not None:
            result[key] = value
    return result


def generate_modelinfo_json(filepath: str, options: dict | None = None) -> str:
    data = build_modelinfo_json_data(filepath, options=options)
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_modelinfo_dump(
    filepath: str,
    resolve_output_path: bool = False,
    options: dict | None = None,
) -> str:
    out_path = modelinfo_text_path(filepath, resolve_output_path=resolve_output_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(generate_modelinfo_dump(filepath, options=options))
    return out_path


def write_modelinfo_json(
    filepath: str,
    options: dict | None = None,
    resolve_output_path: bool = False,
) -> str:
    out_path = modelinfo_json_path(filepath, resolve_output_path=resolve_output_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(generate_modelinfo_json(filepath, options=options))
    return out_path
