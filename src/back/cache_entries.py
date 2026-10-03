"""Stable selection of persisted inspection-cache entries."""

from __future__ import annotations

import json
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any


def iter_cache_records(
    legacy_path: Path | None,
    load_legacy_cache: Callable[[Path], dict],
    cache_dir: Path,
    load_index: Callable[[], dict],
    read_entry: Callable[[str], dict | None],
    should_cancel: Callable[[], bool] | None = None,
) -> Iterable[tuple[str, dict]]:
    """Yield cache identity and payload in the established deterministic order."""
    if legacy_path:
        for key, entry in load_legacy_cache(legacy_path)["entries"].items():
            if should_cancel is not None and should_cancel():
                return
            if isinstance(entry, dict):
                yield str(key), entry
        return

    seen = set()
    try:
        paths = sorted((cache_dir / "entries").glob("*.json"))
    except Exception:
        paths = []
    for path in paths:
        if should_cancel is not None and should_cancel():
            return
        entry_id = path.stem
        entry = read_entry(entry_id)
        if isinstance(entry, dict):
            seen.add(entry_id)
            yield str(entry.get("cache_key") or entry_id), entry

    for entry_id in load_index()["entries"]:
        if should_cancel is not None and should_cancel():
            return
        if entry_id in seen:
            continue
        entry = read_entry(entry_id)
        if isinstance(entry, dict):
            yield str(entry.get("cache_key") or entry_id), entry


def _entry_options(cache_key: str, entry: Mapping[str, Any]) -> dict[str, Any] | None:
    options = entry.get("cache_options")
    if isinstance(options, Mapping):
        return dict(options)
    try:
        decoded = json.loads(cache_key)
    except (TypeError, ValueError):
        return None
    if isinstance(decoded, list) and len(decoded) == 2 and isinstance(decoded[1], dict):
        return dict(decoded[1])
    return None


def select_cache_entries(
    records: Iterable[tuple[str, dict]], should_cancel: Callable[[], bool] | None = None
) -> list[dict[str, Any]]:
    """Choose the first summary for each path, retaining its key and options."""
    selected = []
    seen = set()
    for cache_key, entry in records:
        if should_cancel is not None and should_cancel():
            break
        identity = entry.get("identity")
        identity = identity if isinstance(identity, Mapping) else {}
        data = entry.get("data")
        if not isinstance(data, Mapping) or not data:
            continue
        candidates = (
            data.get("filepath"),
            data.get("resolved_filepath"),
            identity.get("resolved_filepath"),
        )
        for candidate in candidates:
            if not candidate or str(candidate).lower() in seen:
                continue
            filepath = str(candidate)
            seen.add(filepath.lower())
            selected.append(
                {
                    "filepath": filepath,
                    "cache_key": cache_key,
                    "cache_options": _entry_options(cache_key, entry),
                    "entry": entry,
                }
            )
            break
    return selected


def list_cache_paths(records: Iterable[tuple[str, dict]]) -> list[str]:
    """Preserve the path-facing listing behavior for legacy cache records."""
    paths = []
    seen = set()
    for _, entry in records:
        identity = entry.get("identity")
        identity = identity if isinstance(identity, dict) else {}
        raw_data = entry.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        for candidate in (
            data.get("filepath"), data.get("resolved_filepath"),
            identity.get("resolved_filepath"),
        ):
            if not candidate:
                continue
            path = str(candidate)
            if path.lower() in seen:
                continue
            seen.add(path.lower())
            paths.append(path)
            break
    return paths
