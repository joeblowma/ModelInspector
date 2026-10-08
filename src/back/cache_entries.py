"""Stable selection of persisted inspection-cache entries."""

from __future__ import annotations

import json
import ntpath
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
    """Choose the first summary per canonical path, retaining its key and options."""
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
        filepath = next(
            (
                str(candidate)
                for candidate in (
                    data.get("filepath"),
                    data.get("resolved_filepath"),
                    identity.get("resolved_filepath"),
                )
                if candidate
            ),
            None,
        )
        if filepath is None:
            continue

        try:
            decoded_key = json.loads(cache_key)
        except (TypeError, ValueError):
            decoded_key = None
        key_path = (
            decoded_key[0]
            if isinstance(decoded_key, list)
            and len(decoded_key) == 2
            and isinstance(decoded_key[0], str)
            else None
        )
        canonical_path = (
            identity.get("resolved_filepath")
            or key_path
            or data.get("resolved_filepath")
            or filepath
        )
        canonical_identity = ntpath.normcase(ntpath.normpath(str(canonical_path)))
        if canonical_identity in seen:
            continue
        seen.add(canonical_identity)
        selected.append(
            {
                "filepath": filepath,
                "cache_key": cache_key,
                "cache_options": _entry_options(cache_key, entry),
                "entry": entry,
            }
        )
    return selected


def list_cache_paths(records: Iterable[tuple[str, dict]]) -> list[str]:
    """List normalized display aliases; entry selection retains distinct identities."""
    paths = []
    seen = set()
    for entry in select_cache_entries(records):
        path = entry["filepath"]
        normalized = ntpath.normcase(ntpath.normpath(path))
        if normalized not in seen:
            seen.add(normalized)
            paths.append(path)
    return paths
