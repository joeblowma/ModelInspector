"""Bounded, Qt-free data normalization for :mod:`front.explorer_tab`."""

from __future__ import annotations

import ast
import json
import re
from collections.abc import Mapping, Sequence
from math import prod
from typing import Any

__all__ = ["normalize_tensor_descriptors", "detect_embedded_content", "flatten_metadata"]

_MAX_TEXT = 1200
_MAX_METADATA_ROWS = 2000
_MAX_INTEGER = 10**30
_DESCRIPTOR_KEYS = frozenset(
    {
        "name", "shape", "dims", "dimensions", "dtype", "data_type", "tensor_type", "type",
        "parameter_count", "num_parameters", "numel", "n_elements", "n_params", "n_bytes", "component",
        "component_bucket", "shard_id", "original_index", "data_offsets", "offsets", "byte_offsets",
    }
)


def _safe_int(value: Any) -> int | None:
    """Return a bounded integer, avoiding hostile or malformed descriptors."""
    if isinstance(value, bool):
        return int(value)
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if abs(result) <= _MAX_INTEGER else None


def _safe_text(value: Any, limit: int = _MAX_TEXT) -> str:
    """Render arbitrary metadata without allowing giant values into a widget."""
    if value is None:
        return ""
    if isinstance(value, str):
        text = value
    else:
        try:
            text = json.dumps(value, ensure_ascii=False, default=str)
        except (TypeError, ValueError, RecursionError):
            text = repr(value)
    if len(text) <= limit:
        return text
    return f"{text[: max(0, limit - 32)]}… [truncated; {len(text):,} chars]"


def _bounded_value(value: Any, depth: int = 0) -> Any:
    """Copy a small, display-safe portion of a descriptor for detail previews."""
    if depth > 2:
        return _safe_text(value, 160)
    if isinstance(value, Mapping):
        items = list(value.items())[:40]
        result = {str(key): _bounded_value(item, depth + 1) for key, item in items}
        if len(value) > len(items):
            result["…"] = f"{len(value) - len(items):,} more fields"
        return result
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        items = [_bounded_value(item, depth + 1) for item in list(value)[:40]]
        if len(value) > len(items):
            items.append(f"… {len(value) - len(items):,} more items")
        return items
    return _safe_text(value, 320) if not isinstance(value, (int, float, bool)) else value


def _coerce_shape(value: Any) -> tuple[int | str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        text = value.strip()
        try:
            value = json.loads(text)
        except (TypeError, ValueError):
            try:
                value = ast.literal_eval(text)
            except (SyntaxError, ValueError):
                value = re.findall(r"-?\d+", text)
    if isinstance(value, Mapping):
        value = value.get("dims", value.get("shape", ()))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        result: list[int | str] = []
        for dimension in value:
            parsed = _safe_int(dimension)
            result.append(parsed if parsed is not None else _safe_text(dimension, 80))
        return tuple(result)
    parsed = _safe_int(value)
    return (parsed,) if parsed is not None else (_safe_text(value, 80),)


def _dtype_text(value: Any) -> str:
    if isinstance(value, Mapping):
        value = value.get("name", value.get("dtype", value.get("type", "")))
    name = getattr(value, "name", None)
    return _safe_text(name if name is not None else value, 100) or "Unknown"


def _bucket_for_name(name: str) -> str:
    lower = name.lower()
    if any(marker in lower for marker in ("lora", "lycoris", "lokr_", "loha_", "hada_", "dora_")):
        return "LoRA"
    if lower.startswith("first_stage_model.") or lower.startswith(("vae.", "encoder.", "decoder.")):
        return "VAE"
    if lower.startswith("text_encoder_2."):
        return "text_encoder_2"
    if lower.startswith(("text_encoder.", "cond_stage_model.", "conditioner.embedders.", "text_encoders.")):
        return "text_encoder"
    if lower.startswith(("model.visual.")):
        return "Vision"
    if lower.startswith(("mtp.*")):
        return "Draft"
    if lower.startswith(("text_model.*")):
        return "Text"
    if lower.startswith(("blk.*")):
        return "Weights"
    if any(marker in lower for marker in ("double_blocks.", "single_blocks.", "transformer.")):
        return "transformer"
    if lower.startswith(("unet.", "model.diffusion_model.")):
        return "unet"
    return "??"


def _looks_like_descriptor(value: Any) -> bool:
    return isinstance(value, Mapping) and bool(_DESCRIPTOR_KEYS.intersection(value))


def _dtype_byte_width(dtype: str) -> int | None:
    """Return a conservative element width for common header dtype spellings."""
    normalized = dtype.lower().replace("_", "").replace("-", "")
    widths = {
        "f64": 8, "float64": 8, "double": 8, "i64": 8, "int64": 8, "u64": 8,
        "f32": 4, "float32": 4, "float": 4, "i32": 4, "int32": 4, "u32": 4,
        "f16": 2, "float16": 2, "half": 2, "bf16": 2, "bfloat16": 2,
        "i16": 2, "int16": 2, "u16": 2,
        "f8": 1, "float8": 1, "i8": 1, "int8": 1, "u8": 1, "uint8": 1,
        "bool": 1, "boolean": 1,
    }
    return widths.get(normalized)


def _descriptor_bytes(fields: Mapping[str, Any], count: int | None, dtype: str) -> int | None:
    """Use descriptor facts only; never load data to determine a row's size."""
    explicit = _safe_int(fields.get("n_bytes"))
    if explicit is not None and explicit >= 0:
        return explicit
    for key in ("data_offsets", "offsets", "byte_offsets"):
        offsets = fields.get(key)
        if isinstance(offsets, Sequence) and not isinstance(offsets, (str, bytes, bytearray)) and len(offsets) >= 2:
            start, end = _safe_int(offsets[0]), _safe_int(offsets[1])
            if start is not None and end is not None and end >= start:
                return end - start
    width = _dtype_byte_width(dtype)
    if count is not None and count >= 0 and width is not None:
        size = count * width
        return size if size <= _MAX_INTEGER else None
    return None


def _one_tensor(name: Any, descriptor: Any) -> dict[str, Any]:
    fields = descriptor if isinstance(descriptor, Mapping) else {}
    actual_name = fields.get("name", name)
    tensor_name = _safe_text(actual_name, 500) or "(unnamed tensor)"
    shape = _coerce_shape(fields.get("shape", fields.get("dims", fields.get("dimensions", fields.get("tensor_shape")))))
    explicit_count = next(
        (fields.get(key) for key in ("parameter_count", "num_parameters", "numel", "n_elements", "n_params", "elements", "params", "size") if key in fields),
        None,
    )
    parameter_count = _safe_int(explicit_count)
    if parameter_count is None and shape and all(isinstance(dim, int) and dim >= 0 for dim in shape):
        try:
            computed = prod(int(dim) for dim in shape)
            parameter_count = computed if computed <= _MAX_INTEGER else None
        except (OverflowError, ValueError):
            parameter_count = None
    dtype = _dtype_text(fields.get("dtype", fields.get("data_type", fields.get("tensor_type", fields.get("type")))))
    shard_id = _safe_int(fields.get("shard_id", 0))
    original_index = _safe_int(fields.get("original_index"))
    bucket = fields.get("component_bucket", fields.get("component", fields.get("bucket")))
    bucket_text = _safe_text(bucket, 100).strip().lower() if bucket is not None else ""
    return {
        "name": tensor_name,
        "shape": shape,
        "dtype": dtype,
        "component_bucket": bucket_text or _bucket_for_name(tensor_name),
        "parameter_count": parameter_count,
        "n_bytes": _descriptor_bytes(fields, parameter_count, dtype),
        "shard_id": shard_id if shard_id is not None else 0,
        "original_index": original_index,
        "raw": _bounded_value(descriptor),
    }


def normalize_tensor_descriptors(data: Any) -> list[dict[str, Any]]:
    """Normalize common model-reader header shapes into stable row records."""
    if data is None:
        return []
    if isinstance(data, Mapping):
        for nested_key in ("tensor_info", "tensors", "tensor_data", "descriptors", "headers"):
            if nested_key in data:
                return normalize_tensor_descriptors(data[nested_key])
        if _looks_like_descriptor(data):
            return [_one_tensor(data.get("name", ""), data)]
        result = []
        for name, descriptor in data.items():
            if isinstance(descriptor, Mapping) or isinstance(descriptor, Sequence):
                result.append(_one_tensor(name, descriptor))
        return result
    if isinstance(data, Sequence) and not isinstance(data, (str, bytes, bytearray)):
        result = []
        for item in data:
            if isinstance(item, Mapping):
                result.append(_one_tensor(item.get("name", item.get("key", "")), item))
            elif isinstance(item, Sequence) and not isinstance(item, (str, bytes, bytearray)) and len(item) >= 2:
                result.append(_one_tensor(item[0], item[1]))
        return result
    return []


def _flatten_metadata(value: Any, prefix: str = "", depth: int = 0) -> list[dict[str, Any]]:
    if not isinstance(value, Mapping) or depth > 3:
        return [{"key": prefix or "value", "value": _safe_text(value), "raw": value}]
    rows: list[dict[str, Any]] = []
    for key, item in value.items():
        full_key = f"{prefix}.{key}" if prefix else str(key)
        if isinstance(item, Mapping) and depth < 3:
            rows.extend(_flatten_metadata(item, full_key, depth + 1))
        else:
            rows.append({"key": full_key, "value": _safe_text(item), "raw": item})
        if len(rows) >= _MAX_METADATA_ROWS:
            rows.append({"key": "…", "value": "Metadata row limit reached", "raw": None})
            break
    return rows


def flatten_metadata(value: Any) -> list[dict[str, Any]]:
    """Return bounded, searchable rows from a nested metadata mapping."""
    return _flatten_metadata(value)


def detect_embedded_content(inspection: Mapping[str, Any] | None, records: Sequence[Mapping[str, Any]] = ()) -> list[dict[str, Any]]:
    """Identify candidate component groups and text metadata without payload reads."""
    inspection = inspection or {}
    component_value = inspection.get("components")
    components: Mapping[str, Any] = component_value if isinstance(component_value, Mapping) else {}
    buckets = {str(record.get("component_bucket", "")).lower() for record in records}
    candidates: list[dict[str, Any]] = []

    def add(kind: str, name: str, summary: Any, source: str = "tensor headers") -> None:
        candidates.append({"kind": kind, "name": name, "summary": _safe_text(summary, 300), "source": source})

    if components.get("vae") or "vae" in buckets:
        add("VAE", "VAE group", sum(record.get("component_bucket") == "vae" for record in records))
    if components.get("lora") or "lora" in buckets:
        add("LoRA", "LoRA / adapter group", sum(record.get("component_bucket") == "lora" for record in records))
    named = inspection.get("named_text_encoders")
    if isinstance(named, Mapping):
        for name, count in named.items():
            add("Text encoder", str(name), count)
    elif components.get("text_encoder") or "text_encoder" in buckets:
        add("Text encoder", "Text encoder group", sum("text_encoder" in bucket for bucket in buckets))
    metadata = inspection.get("metadata") if isinstance(inspection.get("metadata"), Mapping) else {}
    for row in _flatten_metadata(metadata):
        key = str(row["key"]).lower()
        if any(marker in key for marker in ("jinja", "chat_template", "chat.template", "template")):
            add("Text field", str(row["key"]), row["value"], "metadata")
    return candidates
