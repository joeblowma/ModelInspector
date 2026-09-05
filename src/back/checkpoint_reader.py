"""Safe metadata-only handling for PyTorch checkpoint extensions.

This module intentionally never imports torch, pickle, or a pickle-compatible
loader.  The explicit ``metadata`` safety mode reads only ZIP central-directory
information plus small JSON/version entries.  The default ``reject`` mode
fails before opening the file so a caller cannot accidentally deserialize an
untrusted checkpoint.
"""

import json
import os
import zipfile
from pathlib import Path
from typing import Any, Literal


CHECKPOINT_SAFETY_REJECT = "reject"
CHECKPOINT_SAFETY_METADATA = "metadata"
CHECKPOINT_SAFETY_CHOICES = (
    CHECKPOINT_SAFETY_REJECT,
    CHECKPOINT_SAFETY_METADATA,
)
CheckpointSafety = Literal["reject", "metadata"]
MAX_SAFE_JSON_BYTES = 2_000_000
MAX_ARCHIVE_ENTRIES = 256
MAX_METADATA_BYTES = 2_000_000


class UnsafeCheckpointError(ValueError):
    """Raised when checkpoint inspection was not explicitly opted into."""


def normalize_checkpoint_safety(value: str | None) -> str:
    """Normalize the small public safety vocabulary and reject unsafe modes."""
    normalized = str(value or CHECKPOINT_SAFETY_REJECT).strip().lower()
    aliases = {
        "metadata-only": CHECKPOINT_SAFETY_METADATA,
        "safe": CHECKPOINT_SAFETY_METADATA,
        "disabled": CHECKPOINT_SAFETY_REJECT,
        "none": CHECKPOINT_SAFETY_REJECT,
    }
    normalized = aliases.get(normalized, normalized)
    if normalized not in CHECKPOINT_SAFETY_CHOICES:
        raise ValueError(
            "checkpoint_safety must be 'reject' or 'metadata'; "
            "unsafe deserialization is not supported"
        )
    return normalized


def _safe_json_name(name: str) -> bool:
    lower = name.replace("\\", "/").lower()
    base = lower.rsplit("/", 1)[-1]
    return base in {
        "metadata.json",
        "config.json",
        "model_config.json",
        "params.json",
        "version.json",
    } or lower.endswith("/metadata.json")


def _jsonable(value: Any, depth: int = 0) -> Any:
    if depth > 4:
        return "[truncated]"
    if isinstance(value, dict):
        return {str(k): _jsonable(v, depth + 1) for k, v in list(value.items())[:128]}
    if isinstance(value, list):
        return [_jsonable(v, depth + 1) for v in value[:128]]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def _read_small_json(
    archive: zipfile.ZipFile, info: zipfile.ZipInfo, remaining: int
) -> tuple[dict | list | None, int]:
    limit = min(MAX_SAFE_JSON_BYTES, max(0, remaining))
    if not limit or info.file_size < 0 or info.file_size > limit:
        return None, 0
    try:
        with archive.open(info, "r") as stream:
            raw = stream.read(limit)
        value = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError, UnicodeError, zipfile.BadZipFile):
        return None, 0
    return _jsonable(value), len(raw)


def _zip_metadata(filepath: str, file_size: int) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "checkpoint.archive_type": "zip",
        "checkpoint.safety": CHECKPOINT_SAFETY_METADATA,
    }
    with zipfile.ZipFile(filepath, "r") as archive:
        infos = archive.infolist()
        examined = infos[:MAX_ARCHIVE_ENTRIES]
        names = [info.filename for info in examined]
        metadata["checkpoint.entries"] = names
        metadata["checkpoint.entry_count"] = len(infos)
        metadata["checkpoint.entries_truncated"] = len(infos) > len(examined)
        remaining = MAX_METADATA_BYTES

        version_candidates = (
            info
            for info in examined
            if info.filename.replace("\\", "/").lower().rsplit("/", 1)[-1]
            in {"version", "version.txt", "version.json"}
        )
        for info in version_candidates:
            limit = min(4096, remaining)
            if 0 <= info.file_size <= limit:
                try:
                    with archive.open(info, "r") as stream:
                        raw = stream.read(limit)
                    remaining -= len(raw)
                    metadata["checkpoint.version"] = raw.decode(
                        "utf-8", errors="replace"
                    )[:limit].strip()
                except OSError:
                    pass
                break

        for info in examined:
            if not _safe_json_name(info.filename):
                continue
            value, consumed = _read_small_json(archive, info, remaining)
            remaining -= consumed
            if value is not None:
                key = Path(info.filename).stem.lower().replace(" ", "_")
                metadata[f"checkpoint.{key}"] = value
        metadata["checkpoint.metadata_bytes_examined"] = MAX_METADATA_BYTES - remaining
    return metadata


def read_checkpoint_header(
    filepath: str,
    *,
    options: dict[str, Any] | None = None,
    checkpoint_safety: str = CHECKPOINT_SAFETY_REJECT,
) -> tuple[dict, dict, int]:
    """Read safe checkpoint metadata without deserializing tensor data."""
    del options
    safety = normalize_checkpoint_safety(checkpoint_safety)
    if safety == CHECKPOINT_SAFETY_REJECT:
        raise UnsafeCheckpointError(
            f"Refusing checkpoint inspection for {filepath!r}; pass "
            "checkpoint_safety='metadata' to enable safe metadata-only inspection"
        )

    file_size = os.path.getsize(filepath)
    metadata: dict[str, Any] = {
        "smi.format": Path(filepath).suffix.lower().lstrip(".").upper(),
        "checkpoint.safety": CHECKPOINT_SAFETY_METADATA,
        "checkpoint.tensor_payloads_read": False,
    }
    with open(filepath, "rb") as stream:
        signature = stream.read(16)
    if signature[:4] == b"PK\x03\x04" or zipfile.is_zipfile(filepath):
        try:
            metadata.update(_zip_metadata(filepath, file_size))
        except (OSError, zipfile.BadZipFile) as exc:
            metadata["checkpoint.archive_error"] = str(exc)
    elif signature[:2] == b"\x80\x04" or signature[:2] == b"\x80\x05":
        metadata["checkpoint.signature"] = "pickle"
        metadata["smi.warnings"] = [
            "Checkpoint has a pickle signature; only the file signature was read."
        ]
    else:
        metadata["checkpoint.signature"] = signature[:8].hex()
        metadata["smi.warnings"] = [
            "Checkpoint was inspected without deserialization; no tensor metadata was found."
        ]
    return metadata, {}, file_size


__all__ = [
    "CHECKPOINT_SAFETY_CHOICES",
    "CHECKPOINT_SAFETY_METADATA",
    "CHECKPOINT_SAFETY_REJECT",
    "CheckpointSafety",
    "MAX_ARCHIVE_ENTRIES",
    "MAX_METADATA_BYTES",
    "UnsafeCheckpointError",
    "normalize_checkpoint_safety",
    "read_checkpoint_header",
]
