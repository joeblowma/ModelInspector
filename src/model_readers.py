#!/usr/bin/env python3
"""Read-only model file readers and discovery helpers."""

import json
import os
import struct
from collections import Counter
from pathlib import Path
from typing import Iterable

from back.checkpoint_reader import normalize_checkpoint_safety
from back.gguf_reader import (
    _read_exact,
    _read_gguf_header_fast as _read_gguf_header_fast_impl,
    _read_gguf_value,
    _read_scalar,
    _read_string,
    _read_u32,
    _read_u64,
    _skip_scalar,
)
from back.reader_registry import get_reader_registry
from back.shard_discovery import (
    discover_shard_set,
    discoverable_primary_path,
    is_safetensors_index_path,
)
from back.sidecar_discovery import is_probable_sidecar_path


SUPPORTED_MODEL_EXTENSIONS = (".safetensors", ".gguf", ".onnx")
CHECKPOINT_MODEL_EXTENSIONS = (".ckpt", ".pt", ".pth")
CHECKPOINT_FORMAT_WARNING = (
    "PyTorch checkpoint formats (.ckpt, .pt, .pth) can require pickle "
    "deserialization. They are not inspected until an explicit safe-loading "
    "mode is implemented."
)
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
    141: "PTQ2_0",
    143: "PTQ1_0",
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
    142: "PTQ2_0",
    143: "PTQ1_0",
}
OBSOLETE_GGML_QUANT_IDS = {4, 5, 31, 32, 33, 36, 37, 38}


def is_supported_model_path(path: str | Path) -> bool:
    lower = str(path).lower()
    return lower.endswith(SUPPORTED_MODEL_EXTENSIONS) or lower.endswith(
        ".safetensors.index.json"
    )


def is_checkpoint_model_path(path: str | Path) -> bool:
    return Path(path).suffix.lower() in CHECKPOINT_MODEL_EXTENSIONS


def model_format_for_path(path: str | Path) -> str:
    if str(path).lower().endswith(".safetensors.index.json"):
        return "SAFETENSORS"
    suffix = Path(path).suffix.lower().lstrip(".")
    return suffix.upper() if suffix else "UNKNOWN"


def read_safetensors_header(filepath: str, *, options: dict | None = None):
    """Read safetensors header without loading tensor data."""
    del options
    file_size = os.path.getsize(filepath)

    with open(filepath, "rb") as f:
        raw = f.read(8)
        if len(raw) < 8:
            raise ValueError("File too small to be a valid safetensors file")
        header_size = struct.unpack("<Q", raw)[0]
        if header_size > 200_000_000:
            raise ValueError(f"Header size ({header_size}) seems unreasonably large")
        if header_size > file_size - 8:
            raise ValueError("Safetensors header extends past end of file")
        header_bytes = f.read(header_size)
        if len(header_bytes) != header_size:
            raise ValueError("Unexpected end of safetensors header")
        header = json.loads(header_bytes)

    metadata = header.pop("__metadata__", {})
    _add_common_metadata(metadata, filepath)
    tensor_info = {}
    for name, descriptor in header.items():
        if not isinstance(descriptor, dict):
            continue
        normalized = dict(descriptor)
        offsets = normalized.get("data_offsets")
        if "n_bytes" not in normalized and isinstance(offsets, (list, tuple)):
            if len(offsets) == 2:
                try:
                    normalized["n_bytes"] = max(0, int(offsets[1]) - int(offsets[0]))
                except (TypeError, ValueError):
                    pass
        normalized.setdefault("shard_id", 0)
        tensor_info[str(name)] = normalized
    return metadata, tensor_info, file_size


def read_model_header(
    filepath: str,
    options: dict | str | None = None,
    *,
    checkpoint_safety: str | None = None,
    safety: str | None = None,
):
    """Read a format header through the shared lazy reader registry.

    ``checkpoint_safety`` is intentionally explicit.  It defaults to reject;
    ``metadata`` is the only supported opt-in and never deserializes pickle.
    The historical one-argument call remains unchanged.
    """
    if isinstance(options, str):
        if checkpoint_safety is None:
            checkpoint_safety = options
        options = None
    if checkpoint_safety is None:
        checkpoint_safety = safety or (options or {}).get("checkpoint_safety", "reject")
    if is_safetensors_index_path(filepath) and not discover_shard_set(filepath):
        raise ValueError(
            "Safetensors shard manifest is invalid or has no available in-directory shards"
        )
    checkpoint_safety = normalize_checkpoint_safety(checkpoint_safety)
    return get_reader_registry().read(
        filepath,
        options=options,
        checkpoint_safety=checkpoint_safety,
    )


def _add_common_metadata(metadata: dict, filepath: str):
    metadata.setdefault("smi.format", model_format_for_path(filepath))
    file_type = metadata.get("general.file_type")
    if isinstance(file_type, int):
        metadata["smi.quantization"] = LLAMA_FILE_TYPE_NAMES.get(
            file_type, f"FILE_TYPE_{file_type}"
        )


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


def read_gguf_header(filepath: str, *, options: dict | None = None):
    """Read GGUF metadata and tensor descriptors without touching tensor payloads."""
    del options
    return _read_gguf_header_fast(filepath)


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
            "shard_id": 0,
            "data_offsets": [
                int(tensor.data_offset),
                int(tensor.data_offset + tensor.n_bytes),
            ],
        }

    return metadata, tensor_info, os.path.getsize(filepath)


def _read_gguf_header_fast(filepath: str):
    return _read_gguf_header_fast_impl(
        filepath,
        add_common_metadata=_add_common_metadata,
        infer_quantization=_infer_quantization_from_tensor_dtypes,
        quant_names=GGML_QUANT_NAMES,
        obsolete_quant_ids=OBSOLETE_GGML_QUANT_IDS,
    )


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

    def matches(path: Path) -> bool:
        if is_safetensors_index_path(path):
            return ".safetensors" in normalized_extensions
        return path.suffix.lower() in normalized_extensions

    def add(path: Path) -> None:
        if not matches(path) or is_probable_sidecar_path(path):
            return
        canonical: str = str(path)
        try:
            if not path.is_file() and not path.is_symlink():
                return
            discovered = discoverable_primary_path(path)
            if discovered is None:
                return
            canonical = discovered
            resolved = str(Path(canonical).resolve(strict=True))
        except OSError:
            resolved = str(Path(canonical).absolute())
        if resolved in seen:
            return
        seen.add(resolved)
        found.append(str(canonical if canonical != str(path) else path))

    for raw in targets:
        p = Path(raw)
        if p.is_file() or p.is_symlink():
            add(p)
            continue

        if p.is_dir():
            iterator = p.rglob("*") if recursive else p.glob("*")
            for fp in iterator:
                add(fp)

    return found


def iter_checkpoint_paths(targets: Iterable[str], recursive: bool) -> list[str]:
    return iter_model_paths(targets, recursive, extensions=CHECKPOINT_MODEL_EXTENSIONS)
