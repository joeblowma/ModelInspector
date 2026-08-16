"""Small read-only cache identity projection for frontend verification."""
# pylint: disable=protected-access

from __future__ import annotations

from typing import Any

import model_cache


_IDENTITY_KEYS = (
    "filepath",
    "resolved_filepath",
    "path",
    "original_path",
    "alias",
    "file_size",
    "size",
    "mtime_ns",
    "modified_ns",
    "mtime",
)


def _identity_snapshot(entry: dict[str, Any], filepath: str) -> dict[str, Any]:
    """Copy only the persisted fields needed for non-mutating verification."""
    snapshot: dict[str, Any] = {"filepath": filepath}
    snapshot.update({key: entry[key] for key in _IDENTITY_KEYS if key in entry})
    identity = entry.get("identity")
    if isinstance(identity, dict):
        snapshot["identity"] = dict(identity)
    data = entry.get("data")
    if isinstance(data, dict):
        data_identity = {key: data[key] for key in _IDENTITY_KEYS if key in data}
        if data_identity:
            snapshot["data"] = data_identity
    return snapshot


def get_cached_inspection_identity_snapshots(
    filepaths: list[str],
) -> dict[str, dict[str, Any]]:
    """Return cache paths and identities without copying inspection payloads."""
    wanted_by_value = {
        value: filepath
        for filepath in filepaths
        for value in model_cache._path_match_values(filepath)
    }
    snapshots: dict[str, dict[str, Any]] = {}
    for entry in model_cache._iter_cached_entries():
        raw_identity = entry.get("identity")
        identity = raw_identity if isinstance(raw_identity, dict) else {}
        raw_data = entry.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        candidates = {
            str(source.get(key) or "").lower()
            for source in (entry, identity, data)
            for key in _IDENTITY_KEYS[:5]
        }
        candidates.discard("")
        for candidate in candidates:
            filepath = wanted_by_value.get(candidate)
            if filepath and filepath not in snapshots:
                snapshots[filepath] = _identity_snapshot(entry, filepath)
                break
    return snapshots
