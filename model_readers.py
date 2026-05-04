#!/usr/bin/env python3
"""Read-only model file readers and discovery helpers."""

import json
import os
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable


SUPPORTED_MODEL_EXTENSIONS = (".safetensors", ".gguf")


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
        return [_to_jsonable(v) for v in value]
    if isinstance(value, list):
        return [_to_jsonable(v) for v in value]
    return value


def read_gguf_header(filepath: str):
    """Read GGUF metadata and tensor descriptors without exposing edit behavior."""
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
                s = str(p.resolve())
                if s not in seen:
                    seen.add(s)
                    found.append(s)
            continue

        if p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            for fp in iterator:
                if not fp.is_file() or fp.suffix.lower() not in normalized_extensions:
                    continue
                s = str(fp.resolve())
                if s not in seen:
                    seen.add(s)
                    found.append(s)

    return found
