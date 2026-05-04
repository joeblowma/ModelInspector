#!/usr/bin/env python3
"""Read-only model file readers and discovery helpers."""

import json
import os
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable


SUPPORTED_MODEL_EXTENSIONS = (".safetensors", ".gguf")
MAX_METADATA_ARRAY_ITEMS = 50


def is_supported_model_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_MODEL_EXTENSIONS


def read_safetensors_header(filepath: str):
    """Read safetensors header without loading tensor data."""
    file_size = os.path.getsize(filepath)

    with open(filepath, "rb") as f:
        raw = f.read(8)
        if len(raw) < 8:
            raise ValueError("File too small to be a valid safetensors file")
        header_size = struct.unpack("<Q", raw)[0]
        if header_size > 200_000_000:
            raise ValueError(f"Header size ({header_size}) seems unreasonably large")
        header = json.loads(f.read(header_size))

    metadata = header.pop("__metadata__", {})
    tensor_info = header
    return metadata, tensor_info, file_size


def read_model_header(filepath: str):
    suffix = Path(filepath).suffix.lower()
    if suffix == ".safetensors":
        return read_safetensors_header(filepath)
    if suffix == ".gguf":
        return read_gguf_header(filepath)
    raise ValueError(f"Unsupported model format: {suffix or '(none)'}")


def _to_jsonable(value):
    if hasattr(value, "item"):
        return value.item()
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, tuple):
        value = list(value)
    if isinstance(value, list):
        if len(value) > MAX_METADATA_ARRAY_ITEMS:
            return {
                "count": len(value),
                "preview": [_to_jsonable(v) for v in value[:MAX_METADATA_ARRAY_ITEMS]],
                "truncated": True,
            }
        return [_to_jsonable(v) for v in value]
    return value


def read_gguf_header(filepath: str):
    """Read GGUF metadata and tensor descriptors without touching tensor payloads."""
    try:
        return _read_gguf_header_fast(filepath)
    except Exception:
        return _read_gguf_header_with_library(filepath)


def _read_gguf_header_with_library(filepath: str):
    try:
        from gguf import GGUFReader
    except ImportError as exc:
        raise ValueError("GGUF support requires the gguf package") from exc

    reader = GGUFReader(filepath, "r")
    metadata = {}
    for key, field in reader.fields.items():
        if key.startswith("GGUF."):
            continue
        metadata[key] = _to_jsonable(field.contents())

    tensor_info = {}
    for tensor in reader.tensors:
        tensor_info[tensor.name] = {
            "dtype": tensor.tensor_type.name,
            "shape": [int(dim) for dim in tensor.shape.tolist()],
            "n_bytes": int(tensor.n_bytes),
            "data_offsets": [int(tensor.data_offset), int(tensor.data_offset + tensor.n_bytes)],
        }

    return metadata, tensor_info, os.path.getsize(filepath)


def _read_exact(f, size: int) -> bytes:
    data = f.read(size)
    if len(data) != size:
        raise ValueError("Unexpected end of GGUF header")
    return data


def _read_u32(f) -> int:
    return struct.unpack("<I", _read_exact(f, 4))[0]


def _read_u64(f) -> int:
    return struct.unpack("<Q", _read_exact(f, 8))[0]


def _read_scalar(f, value_type: int):
    scalar_formats = {
        0: ("<B", 1),   # UINT8
        1: ("<b", 1),   # INT8
        2: ("<H", 2),   # UINT16
        3: ("<h", 2),   # INT16
        4: ("<I", 4),   # UINT32
        5: ("<i", 4),   # INT32
        6: ("<f", 4),   # FLOAT32
        7: ("<?", 1),   # BOOL
        10: ("<Q", 8),  # UINT64
        11: ("<q", 8),  # INT64
        12: ("<d", 8),  # FLOAT64
    }
    fmt_size = scalar_formats.get(value_type)
    if not fmt_size:
        raise ValueError(f"Unsupported GGUF scalar value type: {value_type}")
    fmt, size = fmt_size
    return struct.unpack(fmt, _read_exact(f, size))[0]


def _read_string(f) -> str:
    length = _read_u64(f)
    return _read_exact(f, length).decode("utf-8", errors="replace")


def _skip_scalar(f, value_type: int, count: int):
    scalar_sizes = {
        0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1,
        10: 8, 11: 8, 12: 8,
    }
    size = scalar_sizes.get(value_type)
    if not size:
        raise ValueError(f"Unsupported GGUF scalar value type: {value_type}")
    f.seek(size * count, os.SEEK_CUR)


def _read_gguf_value(f, value_type: int):
    if value_type == 8:  # STRING
        return _read_string(f)
    if value_type == 9:  # ARRAY
        item_type = _read_u32(f)
        count = _read_u64(f)
        preview_count = min(count, MAX_METADATA_ARRAY_ITEMS)
        values = []
        if item_type == 8:
            for idx in range(count):
                value = _read_string(f)
                if idx < preview_count:
                    values.append(value)
        else:
            for _ in range(preview_count):
                values.append(_read_scalar(f, item_type))
            _skip_scalar(f, item_type, count - preview_count)
        if count > MAX_METADATA_ARRAY_ITEMS:
            return {
                "count": count,
                "preview": values,
                "truncated": True,
            }
        return values
    return _read_scalar(f, value_type)


def _read_gguf_header_fast(filepath: str):
    try:
        from gguf import GGMLQuantizationType
        from gguf.constants import GGML_QUANT_SIZES, GGUF_DEFAULT_ALIGNMENT, GGUF_MAGIC
    except ImportError as exc:
        raise ValueError("GGUF support requires the gguf package") from exc

    metadata = {}
    tensor_records = []

    with open(filepath, "rb") as f:
        magic = _read_u32(f)
        if magic != GGUF_MAGIC:
            raise ValueError("GGUF magic invalid")
        version = _read_u32(f)
        if version not in (2, 3):
            raise ValueError(f"Unsupported GGUF version: {version}")
        tensor_count = _read_u64(f)
        kv_count = _read_u64(f)

        for _ in range(kv_count):
            key = _read_string(f)
            value_type = _read_u32(f)
            metadata[key] = _read_gguf_value(f, value_type)

        for _ in range(tensor_count):
            name = _read_string(f)
            dims_count = _read_u32(f)
            dims = [_read_u64(f) for _ in range(dims_count)]
            raw_dtype = _read_u32(f)
            relative_offset = _read_u64(f)
            tensor_records.append((name, dims, raw_dtype, relative_offset))

        alignment = int(metadata.get("general.alignment") or GGUF_DEFAULT_ALIGNMENT)
        data_offset = f.tell()
        padding = data_offset % alignment
        if padding:
            data_offset += alignment - padding

    tensor_info = {}
    for name, dims, raw_dtype, relative_offset in tensor_records:
        tensor_type = GGMLQuantizationType(raw_dtype)
        n_elements = 1
        for dim in dims:
            n_elements *= dim
        block_size, type_size = GGML_QUANT_SIZES[tensor_type]
        n_bytes = n_elements * type_size // block_size
        start = data_offset + relative_offset
        tensor_info[name] = {
            "dtype": tensor_type.name,
            "shape": [int(dim) for dim in dims],
            "n_bytes": int(n_bytes),
            "data_offsets": [int(start), int(start + n_bytes)],
        }

    return metadata, tensor_info, os.path.getsize(filepath)


def analyze_tensors(tensor_info: dict):
    """Return dtype counts, total parameter count, and per-tensor shapes."""
    dtypes = Counter()
    total_params = 0
    shapes = {}

    for name, info in tensor_info.items():
        dtype = info.get("dtype", "unknown")
        tensor_shape = info.get("shape", [])
        dtypes[dtype] += 1
        shapes[name] = tensor_shape
        params = 1
        for dim in tensor_shape:
            params *= dim
        total_params += params

    return dtypes, total_params, shapes


def iter_model_paths(
    targets: Iterable[str],
    recursive: bool,
    extensions: tuple[str, ...] = SUPPORTED_MODEL_EXTENSIONS,
) -> list[str]:
    found = []
    seen = set()
    normalized_extensions = tuple(ext.lower() for ext in extensions)

    for raw in targets:
        p = Path(raw)
        if p.is_file():
            if p.suffix.lower() in normalized_extensions:
                resolved = str(p.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(str(p))
            continue

        if p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            for fp in iterator:
                if not fp.is_file() or fp.suffix.lower() not in normalized_extensions:
                    continue
                resolved = str(fp.resolve())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(str(fp))

    return found
