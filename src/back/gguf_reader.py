"""Bounded, header-only GGUF reader."""

import os
import struct
from collections.abc import Callable, Collection, Mapping


MAX_GGUF_HEADER_BYTES = 64 * 1024 * 1024
MAX_GGUF_STRING_BYTES = 16 * 1024 * 1024
MAX_GGUF_METADATA_ENTRIES = 100_000
MAX_GGUF_TENSORS = 500_000
MAX_GGUF_ARRAY_ITEMS = 1_000_000
MAX_GGUF_DIMS = 16
MAX_GGUF_WORK_ITEMS = 2_000_000
_MAX_METADATA_PREVIEW = 50


class GGUFHeaderError(ValueError):
    """A malformed, truncated, or over-limit GGUF header."""


def _read_exact(f, size: int) -> bytes:
    position = f.tell()
    if size < 0 or position > MAX_GGUF_HEADER_BYTES - size:
        raise GGUFHeaderError("GGUF header exceeds the byte limit")
    data = f.read(size)
    if len(data) != size:
        raise GGUFHeaderError("Unexpected end of GGUF header")
    return data


def _read_u32(f) -> int:
    return struct.unpack("<I", _read_exact(f, 4))[0]


def _read_u64(f) -> int:
    return struct.unpack("<Q", _read_exact(f, 8))[0]


def _read_scalar(f, value_type: int):
    scalar_formats = {
        0: "<B", 1: "<b", 2: "<H", 3: "<h", 4: "<I", 5: "<i",
        6: "<f", 7: "<?", 10: "<Q", 11: "<q", 12: "<d",
    }
    fmt = scalar_formats.get(value_type)
    if fmt is None:
        raise GGUFHeaderError(f"Unsupported GGUF scalar value type: {value_type}")
    return struct.unpack(fmt, _read_exact(f, struct.calcsize(fmt)))[0]


def _read_string(f) -> str:
    length = _read_u64(f)
    if length > MAX_GGUF_STRING_BYTES:
        raise GGUFHeaderError(f"GGUF string exceeds byte limit: {length}")
    return _read_exact(f, length).decode("utf-8", errors="replace")


def _skip_scalar(f, value_type: int, count: int):
    scalar_sizes = {0: 1, 1: 1, 2: 2, 3: 2, 4: 4, 5: 4, 6: 4, 7: 1, 10: 8, 11: 8, 12: 8}
    size = scalar_sizes.get(value_type)
    if size is None:
        raise GGUFHeaderError(f"Unsupported GGUF scalar value type: {value_type}")
    skip = size * count
    position = f.tell()
    if count < 0 or position > MAX_GGUF_HEADER_BYTES - skip:
        raise GGUFHeaderError("GGUF header exceeds the byte limit")
    f.seek(0, os.SEEK_END)
    file_size = f.tell()
    f.seek(position)
    if skip > file_size - position:
        raise GGUFHeaderError("Unexpected end of GGUF header")
    f.seek(skip, os.SEEK_CUR)


def _read_gguf_value_bounded(f, value_type: int, remaining_work: int):
    if value_type == 8:
        return _read_string(f), 0
    if value_type != 9:
        return _read_scalar(f, value_type), 0

    item_type = _read_u32(f)
    count = _read_u64(f)
    if count > MAX_GGUF_ARRAY_ITEMS:
        raise GGUFHeaderError(f"GGUF array exceeds item limit: {count}")
    if count > remaining_work:
        raise GGUFHeaderError("GGUF header exceeds the work limit")
    preview_count = min(count, _MAX_METADATA_PREVIEW)
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
    if count > _MAX_METADATA_PREVIEW:
        return {"count": count, "preview": values, "truncated": True}, count
    return values, count


def _read_gguf_value(f, value_type: int):
    return _read_gguf_value_bounded(f, value_type, MAX_GGUF_WORK_ITEMS)[0]


def _read_gguf_header_fast(
    filepath: str,
    *,
    add_common_metadata: Callable[[dict, str], None],
    infer_quantization: Callable[[dict], str | None],
    quant_names: Mapping[int, str],
    obsolete_quant_ids: Collection[int],
):
    try:
        from gguf import GGMLQuantizationType
        from gguf.constants import GGUF_DEFAULT_ALIGNMENT, GGUF_MAGIC
    except ImportError as exc:
        raise ValueError("GGUF support requires the gguf package") from exc

    try:
        metadata = {}
        tensor_records = []
        file_size = os.path.getsize(filepath)

        with open(filepath, "rb") as f:
            magic = _read_u32(f)
            if magic != GGUF_MAGIC:
                raise GGUFHeaderError("GGUF magic invalid")
            version = _read_u32(f)
            if version not in (2, 3):
                raise GGUFHeaderError(f"Unsupported GGUF version: {version}")
            tensor_count = _read_u64(f)
            kv_count = _read_u64(f)
            if tensor_count > MAX_GGUF_TENSORS:
                raise GGUFHeaderError(f"GGUF tensor count exceeds limit: {tensor_count}")
            if kv_count > MAX_GGUF_METADATA_ENTRIES:
                raise GGUFHeaderError(f"GGUF metadata count exceeds limit: {kv_count}")
            work_remaining = MAX_GGUF_WORK_ITEMS - tensor_count - kv_count
            if work_remaining < 0:
                raise GGUFHeaderError("GGUF header exceeds the work limit")
            if kv_count > (file_size - f.tell()) // 13:
                raise GGUFHeaderError("GGUF metadata count exceeds available header bytes")

            for _ in range(kv_count):
                key = _read_string(f)
                value_type = _read_u32(f)
                value, work_used = _read_gguf_value_bounded(
                    f, value_type, work_remaining
                )
                work_remaining -= work_used
                metadata[key] = value

            if tensor_count > (file_size - f.tell()) // 24:
                raise GGUFHeaderError("GGUF tensor count exceeds available header bytes")
            for _ in range(tensor_count):
                name = _read_string(f)
                dims_count = _read_u32(f)
                if dims_count > MAX_GGUF_DIMS:
                    raise GGUFHeaderError(f"GGUF tensor rank exceeds limit: {dims_count}")
                if dims_count > work_remaining:
                    raise GGUFHeaderError("GGUF header exceeds the work limit")
                work_remaining -= dims_count
                dims = [_read_u64(f) for _ in range(dims_count)]
                raw_dtype = _read_u32(f)
                relative_offset = _read_u64(f)
                tensor_records.append((name, dims, raw_dtype, relative_offset))

            alignment = int(metadata.get("general.alignment") or GGUF_DEFAULT_ALIGNMENT)
            if alignment <= 0:
                raise GGUFHeaderError("GGUF alignment must be positive")
            data_offset = f.tell()
            padding = data_offset % alignment
            if padding:
                data_offset += alignment - padding

        sorted_records = sorted(tensor_records, key=lambda record: record[3])
        relative_sizes = {}
        for idx, (name, _, _, relative_offset) in enumerate(sorted_records):
            if idx + 1 < len(sorted_records):
                relative_sizes[name] = max(
                    0, sorted_records[idx + 1][3] - relative_offset
                )
            else:
                relative_sizes[name] = max(
                    0, file_size - (data_offset + relative_offset)
                )

        tensor_info = {}
        for name, dims, raw_dtype, relative_offset in tensor_records:
            try:
                dtype_name = GGMLQuantizationType(raw_dtype).name
            except ValueError:
                dtype_name = quant_names.get(raw_dtype, f"GGML_TYPE_{raw_dtype}")
            n_bytes = relative_sizes.get(name, 0)
            start = data_offset + relative_offset
            tensor_info[name] = {
                "dtype": dtype_name,
                "shape": [int(dim) for dim in dims],
                "n_bytes": int(n_bytes),
                "shard_id": 0,
                "data_offsets": [int(start), int(start + n_bytes)],
            }

        obsolete_dtype_names = sorted(
            {
                quant_names[raw_dtype]
                for _, _, raw_dtype, _ in tensor_records
                if raw_dtype in obsolete_quant_ids
            }
        )
        if obsolete_dtype_names:
            metadata["smi.warnings"] = [
                "File contains obsolete or removed GGML quantization type(s): "
                + ", ".join(obsolete_dtype_names)
            ]
        add_common_metadata(metadata, filepath)
        quantization = str(metadata.get("smi.quantization") or "")
        if quantization.startswith("FILE_TYPE_"):
            inferred = infer_quantization(tensor_info)
            if inferred:
                metadata["smi.quantization"] = inferred
        return metadata, tensor_info, file_size
    except GGUFHeaderError:
        raise
    except Exception as exc:
        raise GGUFHeaderError("Invalid or truncated GGUF header") from exc
