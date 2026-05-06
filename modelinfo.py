#!/usr/bin/env python3
"""Model-info dump helpers for Safetensors Model Inspector."""

import json
from collections import Counter
from pathlib import Path

from inspect_model import FINGERPRINTS, inspect_file, _collect_lora_up_dims
from model_readers import analyze_tensors, read_model_header


def _resolve_display_path(filepath: str) -> str:
    try:
        return str(Path(filepath).resolve(strict=True))
    except OSError:
        return str(Path(filepath).absolute())


def _modelinfo_base_path(filepath: str, resolve_output_path: bool = False) -> str:
    if resolve_output_path:
        return _resolve_display_path(filepath)
    return filepath


def modelinfo_text_path(filepath: str, resolve_output_path: bool = False) -> str:
    return _modelinfo_base_path(filepath, resolve_output_path) + ".modelinfo"


def modelinfo_json_path(filepath: str, resolve_output_path: bool = False) -> str:
    return _modelinfo_base_path(filepath, resolve_output_path) + ".modelinfo.json"


def generate_modelinfo_dump(filepath: str) -> str:
    """Generate detailed .modelinfo text dump for a single safetensors file."""
    metadata, tensor_info, file_size = read_model_header(filepath)
    keys = sorted(tensor_info.keys())
    _, total_params, shapes = analyze_tensors(tensor_info)

    lines = []
    sep = "=" * 70
    lines.append(sep)
    lines.append(f"  FILE: {Path(filepath).name}")
    lines.append(f"  Path: {filepath}")
    resolved_filepath = _resolve_display_path(filepath)
    if resolved_filepath != filepath:
        lines.append(f"  Resolved path: {resolved_filepath}")
    lines.append(f"  Keys: {len(keys)}    Params: {total_params:,}    Size: {file_size:,} bytes")
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

    lines.append("\n  Top key prefixes (depth 2):")
    prefixes = Counter()
    for k in keys:
        parts = k.split(".")
        p = parts[0]
        if len(parts) > 1:
            p += "." + parts[1]
        prefixes[p] += 1
    for p, c in prefixes.most_common(25):
        lines.append(f"    {p:<55} {c:>5}")

    lines.append(f"\n  All tensor keys ({len(keys)}):")
    for k in keys:
        s = shapes.get(k, [])
        d = tensor_info[k].get("dtype", "?")
        lines.append(f"    {k}  {s}  [{d}]")

    lines.append("")
    return "\n".join(lines)


def build_modelinfo_json_data(filepath: str, options: dict | None = None) -> dict:
    """Build the structured .modelinfo JSON payload for a model file."""
    metadata, tensor_info, file_size = read_model_header(filepath)
    dtype_counts, total_params, shapes = analyze_tensors(tensor_info)
    summary = inspect_file(filepath, options=options)

    tensors = []
    for name in sorted(tensor_info.keys()):
        shape = shapes.get(name, [])
        params = 1
        for dim in shape:
            params *= dim
        tensors.append({
            "name": name,
            "shape": shape,
            "dtype": tensor_info[name].get("dtype"),
            "parameters": params,
        })

    warnings = list(summary.get("warnings") or [])
    return {
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
        "warnings": warnings,
    }


def generate_modelinfo_json(filepath: str, options: dict | None = None) -> str:
    data = build_modelinfo_json_data(filepath, options=options)
    return json.dumps(data, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def write_modelinfo_dump(filepath: str, resolve_output_path: bool = False) -> str:
    out_path = modelinfo_text_path(filepath, resolve_output_path=resolve_output_path)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(generate_modelinfo_dump(filepath))
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
