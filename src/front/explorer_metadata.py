"""Read-only embedded-metadata actions for :mod:`front.explorer_tab`."""

from __future__ import annotations

import json
import struct
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

from PyQt6.QtWidgets import QDialog, QDialogButtonBox, QFileDialog, QTextEdit, QVBoxLayout, QWidget

_MAX_HEADER_BYTES = 200_000_000
_MAX_INSPECT_TEXT = 8_000
_MAX_GGUF_METADATA_BYTES = _MAX_HEADER_BYTES
_MAX_GGUF_METADATA_DEPTH = 32
_GGUF_SCALAR_FORMATS = {
    0: "<B",
    1: "<b",
    2: "<H",
    3: "<h",
    4: "<I",
    5: "<i",
    6: "<f",
    7: "<?",
    10: "<Q",
    11: "<q",
    12: "<d",
}
_GGUF_SCALAR_SIZES = {
    value_type: struct.calcsize(format_string)
    for value_type, format_string in _GGUF_SCALAR_FORMATS.items()
}
_MAX_GGUF_METADATA_ITEMS = 200_000


class RawMetadataUnavailable(ValueError):
    """The exact metadata value has no safe, locatable source bytes."""


def readable_metadata(candidate: Mapping[str, Any]) -> str:
    """Format one metadata candidate without flattening template newlines."""
    value = candidate.get("value")
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False, indent=2, default=str)
    except (TypeError, ValueError, RecursionError):
        return repr(value)


def _inspect_text(candidate: Mapping[str, Any]) -> str:
    text = readable_metadata(candidate)
    if len(text) <= _MAX_INSPECT_TEXT:
        return text
    return f"{text[:_MAX_INSPECT_TEXT - 32]}… [truncated; {len(text):,} chars]"


def _candidate_path(inspection: Mapping[str, Any], candidate: Mapping[str, Any]) -> Path:
    raw_path = inspection.get("filepath") or inspection.get("path")
    path = Path(str(raw_path or ""))
    if not path.is_file():
        raise RawMetadataUnavailable("source model file is unavailable")
    return path


def _header_bytes(path: Path) -> bytes:
    with path.open("rb") as source:
        prefix = source.read(8)
        if len(prefix) != 8:
            raise RawMetadataUnavailable("source is too small for a safetensors header")
        size = struct.unpack("<Q", prefix)[0]
        if size > _MAX_HEADER_BYTES:
            raise RawMetadataUnavailable("safetensors header is too large to inspect safely")
        header = source.read(size)
    if len(header) != size:
        raise RawMetadataUnavailable("safetensors header is truncated")
    try:
        json.loads(header)
    except (TypeError, ValueError, UnicodeDecodeError) as error:
        raise RawMetadataUnavailable(f"invalid safetensors header: {error}") from error
    return header


def _skip_space(data: bytes, index: int) -> int:
    while index < len(data) and data[index] in b" \t\r\n":
        index += 1
    return index


def _string_end(data: bytes, index: int) -> int:
    if index >= len(data) or data[index] != ord('"'):
        raise RawMetadataUnavailable("invalid JSON string in safetensors header")
    index += 1
    while index < len(data):
        if data[index] == ord("\\"):
            index += 2
        elif data[index] == ord('"'):
            return index + 1
        else:
            index += 1
    raise RawMetadataUnavailable("unterminated JSON string in safetensors header")


def _value_end(data: bytes, index: int) -> int:
    if index >= len(data):
        raise RawMetadataUnavailable("missing JSON value in safetensors header")
    if data[index] == ord('"'):
        return _string_end(data, index)
    if data[index] not in (ord("{"), ord("[")):
        while index < len(data) and data[index] not in b",}] \t\r\n":
            index += 1
        return index
    depth = 0
    while index < len(data):
        char = data[index]
        if char == ord('"'):
            index = _string_end(data, index)
            continue
        if char in (ord("{"), ord("[")):
            depth += 1
        elif char in (ord("}"), ord("]")):
            depth -= 1
            if depth == 0:
                return index + 1
        index += 1
    raise RawMetadataUnavailable("unterminated JSON value in safetensors header")


def _object_members(data: bytes, start: int, end: int) -> dict[str, tuple[int, int]]:
    if start >= end or data[start] != ord("{"):
        raise RawMetadataUnavailable("metadata source is not a JSON object")
    index = _skip_space(data, start + 1)
    members: dict[str, tuple[int, int]] = {}
    while index < end and data[index] != ord("}"):
        key_end = _string_end(data, index)
        try:
            key = json.loads(data[index:key_end])
        except (TypeError, ValueError, UnicodeDecodeError) as error:
            raise RawMetadataUnavailable(f"invalid metadata key: {error}") from error
        index = _skip_space(data, key_end)
        if index >= end or data[index] != ord(":"):
            raise RawMetadataUnavailable("invalid metadata object separator")
        value_start = _skip_space(data, index + 1)
        value_end = _value_end(data, value_start)
        members[str(key)] = (value_start, value_end)
        index = _skip_space(data, value_end)
        if index < end and data[index] == ord(","):
            index = _skip_space(data, index + 1)
        elif index < end and data[index] != ord("}"):
            raise RawMetadataUnavailable("invalid metadata object delimiter")
    return members


def _gguf_exact(source, size: int, file_size: int) -> bytes:
    if (
        size < 0
        or source.tell() + size > file_size
        or source.tell() + size > _MAX_GGUF_METADATA_BYTES
    ):
        raise RawMetadataUnavailable("truncated GGUF metadata")
    value = source.read(size)
    if len(value) != size:
        raise RawMetadataUnavailable("truncated GGUF metadata")
    return value


def _gguf_string(source, file_size: int) -> str:
    length = struct.unpack("<Q", _gguf_exact(source, 8, file_size))[0]
    try:
        return _gguf_exact(source, length, file_size).decode("utf-8")
    except UnicodeDecodeError as error:
        raise RawMetadataUnavailable(f"invalid GGUF metadata text: {error}") from error


def _gguf_value_end(source, value_type: int, file_size: int, depth: int = 0) -> int:
    if depth > _MAX_GGUF_METADATA_DEPTH:
        raise RawMetadataUnavailable("GGUF metadata array nesting exceeds the safe scan limit")
    if value_type == 8:
        _gguf_string(source, file_size)
    elif value_type == 9:
        item_type = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
        count = struct.unpack("<Q", _gguf_exact(source, 8, file_size))[0]
        if count > _MAX_GGUF_METADATA_ITEMS:
            raise RawMetadataUnavailable("GGUF metadata array exceeds the safe scan limit")
        for _ in range(count):
            _gguf_value_end(source, item_type, file_size, depth + 1)
    elif value_type in _GGUF_SCALAR_SIZES:
        _gguf_exact(source, _GGUF_SCALAR_SIZES[value_type], file_size)
    else:
        raise RawMetadataUnavailable(f"unsupported GGUF metadata type {value_type}")
    return source.tell()


def _gguf_read_value(source, value_type: int, file_size: int, depth: int = 0) -> Any:
    """Decode one bounded GGUF metadata value; tensor payloads are never reached."""
    if depth > _MAX_GGUF_METADATA_DEPTH:
        raise RawMetadataUnavailable("GGUF metadata array nesting exceeds the safe read limit")
    if value_type == 8:
        return _gguf_string(source, file_size)
    if value_type == 9:
        item_type = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
        count = struct.unpack("<Q", _gguf_exact(source, 8, file_size))[0]
        if count > _MAX_GGUF_METADATA_ITEMS:
            raise RawMetadataUnavailable("GGUF metadata array exceeds the safe read limit")
        return [
            _gguf_read_value(source, item_type, file_size, depth + 1)
            for _ in range(count)
        ]
    format_string = _GGUF_SCALAR_FORMATS.get(value_type)
    if format_string is None:
        raise RawMetadataUnavailable(f"unsupported GGUF metadata type {value_type}")
    size = struct.calcsize(format_string)
    try:
        return struct.unpack(format_string, _gguf_exact(source, size, file_size))[0]
    except struct.error as error:
        raise RawMetadataUnavailable(f"invalid GGUF metadata value: {error}") from error


def _gguf_metadata_bytes(path: Path, raw_path: Sequence[Any]) -> bytes:
    if len(raw_path) != 1:
        raise RawMetadataUnavailable("GGUF metadata keys are not nested source locations")
    target_key = str(raw_path[0])
    file_size = path.stat().st_size
    with path.open("rb") as source:
        if _gguf_exact(source, 4, file_size) != b"GGUF":
            raise RawMetadataUnavailable("invalid GGUF magic")
        version = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
        if version not in (2, 3):
            raise RawMetadataUnavailable(f"unsupported GGUF version {version}")
        _gguf_exact(source, 8, file_size)  # tensor count; tensor descriptors are never read.
        key_count = struct.unpack("<Q", _gguf_exact(source, 8, file_size))[0]
        if key_count > _MAX_GGUF_METADATA_ITEMS:
            raise RawMetadataUnavailable("GGUF metadata count exceeds the safe scan limit")
        for _ in range(key_count):
            key = _gguf_string(source, file_size)
            value_type = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
            value_start = source.tell()
            value_end = _gguf_value_end(source, value_type, file_size)
            if key == target_key:
                source.seek(value_start)
                return _gguf_exact(source, value_end - value_start, file_size)
    raise RawMetadataUnavailable("metadata value is not present in the GGUF header")


def _gguf_metadata_value(path: Path, raw_path: Sequence[Any]) -> Any:
    """Read the complete source value for display without touching tensor data."""
    if len(raw_path) != 1:
        raise RawMetadataUnavailable("GGUF metadata keys are not nested source locations")
    target_key = str(raw_path[0])
    file_size = path.stat().st_size
    with path.open("rb") as source:
        if _gguf_exact(source, 4, file_size) != b"GGUF":
            raise RawMetadataUnavailable("invalid GGUF magic")
        version = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
        if version not in (2, 3):
            raise RawMetadataUnavailable(f"unsupported GGUF version {version}")
        _gguf_exact(source, 8, file_size)
        key_count = struct.unpack("<Q", _gguf_exact(source, 8, file_size))[0]
        if key_count > _MAX_GGUF_METADATA_ITEMS:
            raise RawMetadataUnavailable("GGUF metadata count exceeds the safe scan limit")
        for _ in range(key_count):
            key = _gguf_string(source, file_size)
            value_type = struct.unpack("<I", _gguf_exact(source, 4, file_size))[0]
            if key == target_key:
                return _gguf_read_value(source, value_type, file_size)
            _gguf_value_end(source, value_type, file_size)
    raise RawMetadataUnavailable("metadata value is not present in the GGUF header")


def raw_metadata_bytes(inspection: Mapping[str, Any], candidate: Mapping[str, Any]) -> bytes:
    """Return exact metadata source bytes without reading tensor payloads."""
    raw_path = candidate.get("raw_path")
    if not isinstance(raw_path, Sequence) or isinstance(raw_path, (str, bytes, bytearray)):
        raise RawMetadataUnavailable("metadata source location is unknown")
    path = _candidate_path(inspection, candidate)
    if path.suffix.lower() == ".gguf":
        return _gguf_metadata_bytes(path, raw_path)
    if path.suffix.lower() != ".safetensors":
        raise RawMetadataUnavailable("raw metadata extraction is unsupported for this format")
    header = _header_bytes(path)
    root = _object_members(header, _skip_space(header, 0), len(header))
    location = root.get("__metadata__")
    if location is None:
        raise RawMetadataUnavailable("source header has no embedded metadata")
    start, end = location
    for key in raw_path:
        members = _object_members(header, start, end)
        location = members.get(str(key))
        if location is None:
            raise RawMetadataUnavailable("metadata value is not present in the source header")
        start, end = location
    return header[start:end]


def raw_metadata_status(inspection: Mapping[str, Any], candidate: Mapping[str, Any]) -> tuple[bool, str]:
    try:
        path = _candidate_path(inspection, candidate)
        raw_metadata_bytes(inspection, candidate)
    except (OSError, RawMetadataUnavailable) as error:
        return False, f"Raw original bytes unavailable: {error}"
    if path.suffix.lower() == ".gguf":
        return True, "Extract exact GGUF-encoded metadata value bytes; tensor payloads are never read."
    return True, "Extract exact JSON source bytes; tensor payloads are never read."


def _metadata_value_at_path(metadata: Any, raw_path: Sequence[Any]) -> Any:
    value = metadata
    for key in raw_path:
        if not isinstance(value, Mapping) or str(key) not in value:
            raise RawMetadataUnavailable("metadata value is not present in the source header")
        value = value[str(key)]
    return value


def _source_metadata_value(inspection: Mapping[str, Any], candidate: Mapping[str, Any]) -> Any:
    """Recover a complete display value from the original header when possible."""
    raw_path = candidate.get("raw_path")
    if not isinstance(raw_path, Sequence) or isinstance(raw_path, (str, bytes, bytearray)):
        raise RawMetadataUnavailable("metadata source location is unknown")
    path = _candidate_path(inspection, candidate)
    suffix = path.suffix.lower()
    if suffix == ".safetensors":
        return json.loads(raw_metadata_bytes(inspection, candidate))
    if suffix == ".gguf":
        return _gguf_metadata_value(path, raw_path)
    try:
        from model_readers import read_model_header

        metadata, _, _ = read_model_header(
            str(path), options={"checkpoint_safety": "metadata"}
        )
    except ImportError as error:
        raise RawMetadataUnavailable(f"source reader is unavailable: {error}") from error
    return _metadata_value_at_path(metadata, raw_path)


def _source_candidate(inspection: Mapping[str, Any], candidate: Mapping[str, Any]) -> dict[str, Any] | None:
    try:
        value = _source_metadata_value(inspection, candidate)
    except (OSError, RawMetadataUnavailable, TypeError, ValueError, RecursionError):
        return None
    resolved = dict(candidate)
    resolved["value"] = value
    return resolved


def _save(parent: QWidget, title: str, default_name: str, data: bytes, file_filter: str) -> str:
    filename, _ = QFileDialog.getSaveFileName(parent, title, default_name, file_filter)
    if not filename:
        return ""
    try:
        Path(filename).write_bytes(data)
    except OSError as error:
        return f"Could not save metadata: {error}"
    return f"Saved {len(data):,} bytes to {filename}"


def perform_metadata_action(parent: QWidget, inspection: Mapping[str, Any], candidate: Mapping[str, Any], action: str) -> str:
    """Run the approved UI action for metadata only; return feedback when needed."""
    source_candidate = (
        _source_candidate(inspection, candidate)
        if action in {"inspect", "save"}
        else None
    )
    if action == "inspect":
        display_candidate = source_candidate or dict(candidate)
        dialog = QDialog(parent)
        title = str(display_candidate.get("name") or "Embedded metadata")
        if source_candidate is None and candidate.get("raw_path") is not None:
            title += " (cached preview; source unavailable)"
        dialog.setWindowTitle(title)
        layout = QVBoxLayout(dialog)
        detail = QTextEdit()
        detail.setReadOnly(True)
        detail.setPlainText(_inspect_text(display_candidate))
        layout.addWidget(detail)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject)
        buttons.accepted.connect(dialog.accept)
        layout.addWidget(buttons)
        dialog.resize(720, 480)
        dialog.exec()
        return ""
    if action == "save":
        if source_candidate is None:
            return "Readable metadata source unavailable; nothing was saved."
        display_candidate = source_candidate
        text = readable_metadata(display_candidate)
        suffix = ".txt" if isinstance(display_candidate.get("value"), str) else ".json"
        return _save(parent, "Save readable metadata", f"embedded_metadata{suffix}", text.encode("utf-8"), "Text or JSON files (*.txt *.json);;All files (*)")
    try:
        raw = raw_metadata_bytes(inspection, candidate)
    except (OSError, RawMetadataUnavailable) as error:
        return f"Raw original bytes unavailable: {error}"
    return _save(parent, "Extract raw metadata bytes", "embedded_metadata.raw", raw, "Raw files (*.raw);;All files (*)")
