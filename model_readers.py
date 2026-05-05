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
LLAMA_FILE_TYPE_NAMES = {
    0: "F32",
    1: "F16",
    2: "Q4_0",
    3: "Q4_1",
    7: "Q8_0",
    8: "Q5_0",
    9: "Q5_1",
    10: "Q2_K",
    11: "Q3_K_S",
    12: "Q3_K_M",
    13: "Q3_K_L",
    14: "Q4_K_S",
    15: "Q4_K_M",
    16: "Q5_K_S",
    17: "Q5_K_M",
    18: "Q6_K",
    19: "IQ2_XXS",
    20: "IQ2_XS",
    21: "Q2_K_S",
    22: "IQ3_XS",
    23: "IQ3_XXS",
    24: "IQ1_S",
    25: "IQ4_NL",
    26: "IQ3_S",
    27: "IQ3_M",
    28: "IQ2_S",
    29: "IQ2_M",
    30: "IQ4_XS",
    31: "IQ1_M",
    32: "BF16",
    36: "TQ1_0",
    37: "TQ2_0",
    38: "MXFP4_MOE",
    39: "NVFP4",
    40: "Q1_0",
    41: "Q2_0",
    1024: "GUESSED",
}
GGML_QUANT_NAMES = {
    4: "Q4_2",
    5: "Q4_3",
    31: "Q4_0_4_4",
    32: "Q4_0_4_8",
    33: "Q4_0_8_8",
    36: "IQ4_NL_4_4",
    37: "IQ4_NL_4_8",
    38: "IQ4_NL_8_8",
    40: "NVFP4",
    41: "Q1_0",
    42: "Q2_0",
}
OBSOLETE_GGML_QUANT_IDS = {4, 5, 31, 32, 33, 36, 37, 38}


def is_supported_model_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in SUPPORTED_MODEL_EXTENSIONS


def model_format_for_path(path: str | Path) -> str:
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix.upper() if suffix else "UNKNOWN"


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
    _add_common_metadata(metadata, filepath)
    tensor_info = header
    return metadata, tensor_info, file_size


def read_model_header(filepath: str):
    suffix = Path(filepath).suffix.lower()
    if suffix == ".safetensors":
        return read_safetensors_header(filepath)
    if suffix == ".gguf":
        return read_gguf_header(filepath)
    raise ValueError(f"Unsupported model format: {suffix or '(none)'}")


def _add_common_metadata(metadata: dict, filepath: str):
    metadata.setdefault("smi.format", model_format_for_path(filepath))
    file_type = metadata.get("general.file_type")
    if isinstance(file_type, int):
        metadata["smi.quantization"] = LLAMA_FILE_TYPE_NAMES.get(file_type, f"FILE_TYPE_{file_type}")


def _infer_quantization_from_tensor_dtypes(tensor_info: dict) -> str | None:
    dtype_counts = Counter(
        info.get("dtype")
        for info in tensor_info.values()
        if info.get("dtype") and info.get("dtype") not in {"F32", "F16", "BF16"}
    )
    if not dtype_counts:
        return None
    return dtype_counts.most_common(1)[0][0]


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
    _add_common_metadata(metadata, filepath)

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
        from gguf.constants import GGUF_DEFAULT_ALIGNMENT, GGUF_MAGIC
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
    file_size = os.path.getsize(filepath)
    sorted_records = sorted(
        tensor_records,
        key=lambda record: record[3],
    )
    relative_sizes = {}
    for idx, (name, _, _, relative_offset) in enumerate(sorted_records):
        if idx + 1 < len(sorted_records):
            relative_sizes[name] = max(0, sorted_records[idx + 1][3] - relative_offset)
        else:
            relative_sizes[name] = max(0, file_size - (data_offset + relative_offset))

    for name, dims, raw_dtype, relative_offset in tensor_records:
        try:
            dtype_name = GGMLQuantizationType(raw_dtype).name
        except ValueError:
            dtype_name = GGML_QUANT_NAMES.get(raw_dtype, f"GGML_TYPE_{raw_dtype}")
        n_elements = 1
        for dim in dims:
            n_elements *= dim
        n_bytes = relative_sizes.get(name, 0)
        start = data_offset + relative_offset
        tensor_info[name] = {
            "dtype": dtype_name,
            "shape": [int(dim) for dim in dims],
            "n_bytes": int(n_bytes),
            "data_offsets": [int(start), int(start + n_bytes)],
        }

    obsolete_dtype_names = sorted({
        GGML_QUANT_NAMES[raw_dtype]
        for _, _, raw_dtype, _ in tensor_records
        if raw_dtype in OBSOLETE_GGML_QUANT_IDS
    })
    if obsolete_dtype_names:
        metadata["smi.warnings"] = [
            "File contains obsolete or removed GGML quantization type(s): "
            + ", ".join(obsolete_dtype_names)
        ]
    _add_common_metadata(metadata, filepath)
    quantization = str(metadata.get("smi.quantization") or "")
    if quantization.startswith("FILE_TYPE_"):
        inferred = _infer_quantization_from_tensor_dtypes(tensor_info)
        if inferred:
            metadata["smi.quantization"] = inferred

    return metadata, tensor_info, file_size


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
        if p.is_file() or p.is_symlink():
            if p.suffix.lower() in normalized_extensions:
                try:
                    resolved = str(p.resolve(strict=True))
                except OSError:
                    resolved = str(p.absolute())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(str(p))
            continue

        if p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            for fp in iterator:
                if fp.suffix.lower() not in normalized_extensions:
                    continue
                if not fp.is_file() and not fp.is_symlink():
                    continue
                try:
                    resolved = str(fp.resolve(strict=True))
                except OSError:
                    resolved = str(fp.absolute())
                if resolved not in seen:
                    seen.add(resolved)
                    found.append(str(fp))

    return found
