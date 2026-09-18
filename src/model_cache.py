#!/usr/bin/env python3
"""Persistent inspection-result cache."""

import json
import os
import hashlib
import shutil
import threading
from pathlib import Path
from typing import Any, Callable

from app_paths import cache_dir, model_cache_dir
from back.cache_storage import (
    get_cached_directory_scan as _get_cached_directory_scan,
    get_cached_raw_dump as _get_cached_raw_dump,
    ensure_sidecar_metadata,
    list_cached_directories as _list_cached_directories,
    load_index as _load_storage_index,
    load_legacy_cache as _load_storage_legacy_cache,
    primary_identity_matches as _primary_identity_matches,
    read_entry as _read_storage_entry,
    restore_sidecar_inspections,
    save_index as _save_storage_index,
    split_sidecar_inspections,
    store_directory_scan as _store_directory_scan,
    store_raw_dump as _store_raw_dump,
    store_sidecar_records,
    write_entry as _write_storage_entry,
)
from back.inspection_summary import compact_inspection_summary
from back.companion_discovery import companion_identities_match
from back.shard_discovery import discover_shard_set
from back.sidecar_discovery import discover_sidecars, sidecar_identity_snapshot
from back.cache_invalidation import invalidate_raw_dump as _invalidate_raw_dump


CACHE_VERSION = 2
_CACHE_LOCK = threading.Lock()
def _load_legacy_cache(path: Path) -> dict:
    return _load_storage_legacy_cache(path, CACHE_VERSION)
def _legacy_cache_path() -> Path | None:
    override = os.environ.get("SMI_CACHE_PATH")
    if override:
        return Path(override)
    return None
def _index_path() -> Path:
    return model_cache_dir() / "index.json"
def _entry_path(entry_id: str) -> Path:
    return model_cache_dir() / "entries" / f"{entry_id}.json"
def _data_path(entry_id: str) -> Path:
    return model_cache_dir() / "data" / f"{entry_id}.json"
def _cache_key(filepath: str, options: dict | None) -> str:
    try:
        resolved = str(Path(filepath).resolve(strict=True)).lower()
    except OSError:
        resolved = str(Path(filepath).absolute()).lower()
    relevant_options = {
        "allow_filename_alias_detection": bool(
            (options or {}).get("allow_filename_alias_detection", False)
        ),
    }
    return json.dumps(
        [resolved, relevant_options], sort_keys=True, separators=(",", ":")
    )
def _entry_id(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()
def _identity(filepath: str) -> dict[str, Any]:
    p = Path(filepath)
    st = p.stat()
    try:
        resolved = str(p.resolve(strict=True))
    except OSError:
        resolved = str(p.absolute())
    return {
        "resolved_filepath": resolved,
        "file_size": st.st_size,
        "mtime_ns": st.st_mtime_ns,
    }
def _load_index() -> dict:
    return _load_storage_index(_index_path(), CACHE_VERSION)
def _save_index(index: dict):
    _save_storage_index(_index_path(), index)
def _path_match_values(filepath: str) -> set[str]:
    values = {str(Path(filepath).absolute()).lower()}
    try:
        values.add(str(Path(filepath).resolve(strict=True)).lower())
    except OSError:
        pass
    return values
def _read_entry(entry_id: str) -> dict | None:
    return _read_storage_entry(_entry_path(entry_id))
def _write_entry(entry_id: str, entry: dict):
    _write_storage_entry(_entry_path(entry_id), entry)
def _read_data_entry(entry_id: str) -> dict | None:
    return _read_storage_entry(_data_path(entry_id))
def _write_data_entry(entry_id: str, entry: dict):
    _write_storage_entry(_data_path(entry_id), entry)
def _iter_cached_entries():
    legacy_path = _legacy_cache_path()
    if legacy_path:
        cache = _load_legacy_cache(legacy_path)
        for entry in cache["entries"].values():
            if isinstance(entry, dict):
                yield entry
        return

    seen = set()
    try:
        entry_paths = sorted((model_cache_dir() / "entries").glob("*.json"))
    except Exception:
        entry_paths = []
    for path in entry_paths:
        entry_id = path.stem
        entry = _read_entry(entry_id)
        if isinstance(entry, dict):
            seen.add(entry_id)
            yield entry

    index = _load_index()
    for entry_id in index["entries"].keys():
        if entry_id in seen:
            continue
        entry = _read_entry(entry_id)
        if isinstance(entry, dict):
            yield entry
def _entry_matches_path(entry: dict, filepath: str) -> bool:
    wanted = _path_match_values(filepath)
    raw_identity = entry.get("identity")
    identity = raw_identity if isinstance(raw_identity, dict) else {}
    raw_data = entry.get("data")
    data = raw_data if isinstance(raw_data, dict) else {}
    candidates = {
        str(identity.get("resolved_filepath") or "").lower(),
        str(data.get("filepath") or "").lower(),
        str(data.get("resolved_filepath") or "").lower(),
    }
    candidates.discard("")
    return bool(wanted & candidates)
def _include_sidecars(options: dict | None) -> bool:
    options = options or {}
    return not options.get("_sidecar_inspection") and options.get(
        "include_sidecars", True
    )
def _cache_companion_identities_match(
    filepath: str, data: dict, options: dict | None
) -> bool:
    """Validate shard and nearby-sidecar identities without reading payloads."""
    shard_set = discover_shard_set(filepath)
    cached_shard = data.get("shard_identity")
    if shard_set:
        if cached_shard != shard_set.identity():
            return False
    elif cached_shard:
        return False
    if not _include_sidecars(options):
        return companion_identities_match(filepath, data)
    sidecar_base = shard_set.primary_path if shard_set else filepath
    current_sidecars = discover_sidecars(sidecar_base)
    return data.get("sidecar_identities", []) == sidecar_identity_snapshot(
        current_sidecars
    ) and companion_identities_match(filepath, data)
def get_cached_inspection(filepath: str, options: dict | None = None) -> dict | None:
    key = _cache_key(filepath, options)
    entry_id = _entry_id(key)
    ident = _identity(filepath)
    legacy_path = _legacy_cache_path()
    if legacy_path:
        cache = _load_legacy_cache(legacy_path)
        entry = cache["entries"].get(key)
    else:
        index = _load_index()
        entry = _read_entry(entry_id)
    if not entry:
        return None
    if not _primary_identity_matches(entry.get("identity"), ident):
        return None
    raw_data = entry.get("data")
    if not isinstance(raw_data, dict):
        return None
    data = restore_sidecar_inspections(
        raw_data,
        entry.get("sidecar_data_file") or raw_data.get("sidecar_data_file"),
        CACHE_VERSION,
        include_sidecars=_include_sidecars(options),
        require_records=_include_sidecars(options),
        legacy_path=legacy_path,
    )
    if data is None or not _cache_companion_identities_match(filepath, data, options):
        return None
    return data
def get_cached_inspection_snapshot(filepath: str) -> dict | None:
    """Return cached inspection data for a path without requiring the file to exist."""
    if Path(filepath).exists():
        current = get_cached_inspection(filepath)
        if current is None:
            return None
        current.setdefault("cache_status", "snapshot")
        return current
    for entry in _iter_cached_entries():
        if not _entry_matches_path(entry, filepath):
            continue
        raw_data = entry.get("data")
        if isinstance(raw_data, dict):
            snapshot = restore_sidecar_inspections(
                raw_data,
                entry.get("sidecar_data_file") or raw_data.get("sidecar_data_file"),
                CACHE_VERSION,
                include_sidecars=True,
                require_records=False,
                legacy_path=_legacy_cache_path(),
            )
            if snapshot is None:
                snapshot = dict(raw_data)
            snapshot.setdefault("cache_status", "snapshot")
            return snapshot
    return None
def _iter_cached_inspection_matches(filepaths: list[str]):
    """Yield each requested filepath and matching cached data at most once."""
    wanted_by_value = {}
    for filepath in filepaths:
        for value in _path_match_values(filepath):
            wanted_by_value[value] = filepath

    matched = set()
    for entry in _iter_cached_entries():
        raw_identity = entry.get("identity")
        identity = raw_identity if isinstance(raw_identity, dict) else {}
        raw_data = entry.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        if not data:
            continue
        candidates = {
            str(identity.get("resolved_filepath") or "").lower(),
            str(data.get("filepath") or "").lower(),
            str(data.get("resolved_filepath") or "").lower(),
        }
        candidates.discard("")
        for candidate in candidates:
            filepath = wanted_by_value.get(candidate)
            if filepath and filepath not in matched:
                matched.add(filepath)
                yield filepath, data
def get_cached_inspection_snapshots(filepaths: list[str]) -> dict[str, dict]:
    """Return cached inspection snapshots for many paths using one cache scan."""
    snapshots = {}
    for filepath, data in _iter_cached_inspection_matches(filepaths):
        snapshot = restore_sidecar_inspections(
            data,
            data.get("sidecar_data_file"),
            CACHE_VERSION,
            include_sidecars=True,
            require_records=False,
            legacy_path=_legacy_cache_path(),
        ) or dict(data)
        snapshot.setdefault("cache_status", "snapshot")
        snapshots[filepath] = snapshot
    return snapshots


def get_cached_inspection_summary_snapshot(filepath: str) -> dict | None:
    """Return a compact GUI snapshot while preserving the full cache entry."""
    snapshot = get_cached_inspection_snapshot(filepath)
    if snapshot is None:
        return None
    return compact_inspection_summary(snapshot)


def get_cached_inspection_summary_snapshots(
    filepaths: list[str],
) -> dict[str, dict]:
    """Return compact persisted snapshots without recomputing an option-derived key."""
    return dict(iter_cached_inspection_summary_snapshots(filepaths))
def iter_cached_inspection_summary_snapshots(
    filepaths: list[str], should_cancel: Callable[[], bool] | None = None
):
    """Yield compact persisted snapshots, stopping between records when cancelled."""
    for filepath, data in _iter_cached_inspection_matches(filepaths):
        if should_cancel is not None and should_cancel():
            return
        summary_source = dict(data)
        summary_source.setdefault("cache_status", "snapshot")
        yield filepath, compact_inspection_summary(summary_source)
def list_cached_inspection_paths() -> list[str]:
    """Return paths that have cached inspection summaries."""
    paths = []
    seen = set()
    for entry in _iter_cached_entries():
        raw_identity = entry.get("identity")
        identity = raw_identity if isinstance(raw_identity, dict) else {}
        raw_data = entry.get("data")
        data = raw_data if isinstance(raw_data, dict) else {}
        candidates = [
            data.get("filepath"),
            data.get("resolved_filepath"),
            identity.get("resolved_filepath"),
        ]
        for candidate in candidates:
            if not candidate:
                continue
            path = str(candidate)
            key = path.lower()
            if key in seen:
                continue
            seen.add(key)
            paths.append(path)
            break
    return paths
def store_cached_inspection(filepath: str, data: dict, options: dict | None = None):
    key = _cache_key(filepath, options)
    entry_id = _entry_id(key)
    normalized_data = ensure_sidecar_metadata(data)
    primary_data, sidecar_records = split_sidecar_inspections(normalized_data)
    legacy_path = _legacy_cache_path()
    sidecar_data_file = store_sidecar_records(
        entry_id, sidecar_records, CACHE_VERSION, legacy_path
    )
    if sidecar_data_file:
        primary_data["sidecar_data_file"] = sidecar_data_file
    else:
        primary_data.pop("sidecar_data_file", None)
    entry_identity = _identity(filepath)
    entry_identity.update({key: primary_data[key] for key in ("shard_identity", "sidecar_identities") if key in primary_data})
    entry: dict[str, Any] = {
        "identity": entry_identity,
        "data": primary_data,
    }
    if sidecar_data_file:
        entry["sidecar_data_file"] = sidecar_data_file
    if legacy_path:
        cache = _load_legacy_cache(legacy_path)
        cache["entries"][key] = entry
        try:
            legacy_path.parent.mkdir(parents=True, exist_ok=True)
            tmp_path = legacy_path.with_suffix(legacy_path.suffix + ".tmp")
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, sort_keys=True)
            os.replace(tmp_path, legacy_path)
        except Exception:
            pass
        return

    with _CACHE_LOCK:
        _write_entry(entry_id, entry)
        index = _load_index()
        index_entry = dict(index["entries"].get(entry_id) or {})
        index_entry.update(
            {
                "identity": entry["identity"],
                "data_file": f"entries/{entry_id}.json",
                "sidecar_data_file": sidecar_data_file,
            }
        )
        index["entries"][entry_id] = index_entry
        _save_index(index)
def store_model_data(
    filepath: str,
    metadata: dict,
    tensor_info: dict,
    file_size: int,
    options: dict | None = None,
):
    key = _cache_key(filepath, options)
    entry_id = _entry_id(key)
    entry = {
        "identity": _identity(filepath),
        "filepath": filepath,
        "resolved_filepath": _identity(filepath)["resolved_filepath"],
        "metadata": metadata,
        "tensor_info": tensor_info,
        "original_tensor_order": list(tensor_info),
        "file_size": file_size,
    }
    with _CACHE_LOCK:
        _write_data_entry(entry_id, entry)
        index = _load_index()
        index["entries"].setdefault(entry_id, {})["data_cache_file"] = (
            f"data/{entry_id}.json"
        )
        _save_index(index)
def get_cached_model_data(filepath: str, options: dict | None = None) -> dict | None:
    try:
        key = _cache_key(filepath, options)
        entry_id = _entry_id(key)
        entry = _read_data_entry(entry_id)
        if isinstance(entry, dict):
            return entry
    except Exception:
        pass

    wanted = _path_match_values(filepath)
    data_dir = model_cache_dir() / "data"
    try:
        candidates = list(data_dir.glob("*.json"))
    except Exception:
        candidates = []
    for path in candidates:
        try:
            with open(path, "r", encoding="utf-8") as f:
                entry = json.load(f)
        except Exception:
            continue
        entry_values = {
            str(entry.get("filepath") or "").lower(),
            str(entry.get("resolved_filepath") or "").lower(),
        }
        if wanted & entry_values:
            return entry
    return None
def store_directory_scan(folder: str, paths: list[str]):
    """Cache the latest successful recursive scan for a model library folder."""
    _store_directory_scan(folder, paths, CACHE_VERSION)
def list_cached_directories() -> list[str]:
    return _list_cached_directories(CACHE_VERSION)


def get_cached_directory_scan(folder: str) -> list[str]:
    """Return cached scan paths without pruning missing or temporarily unavailable files."""
    return _get_cached_directory_scan(folder, CACHE_VERSION)
def store_raw_dump(filepath: str, dump: str):
    _store_raw_dump(filepath, dump, CACHE_VERSION, _path_match_values)


def get_cached_raw_dump(filepath: str) -> str | None:
    return _get_cached_raw_dump(filepath, CACHE_VERSION, _path_match_values)


def invalidate_cached_inspection(filepath: str, options: dict | None = None) -> bool:
    """Remove the current inspection and full-data cache entries for one model."""
    key = _cache_key(filepath, options)
    entry_id = _entry_id(key)
    legacy_path = _legacy_cache_path()
    with _CACHE_LOCK:
        if legacy_path:
            cache = _load_legacy_cache(legacy_path)
            removed = cache["entries"].pop(key, None) is not None
            try:
                legacy_path.parent.mkdir(parents=True, exist_ok=True)
                tmp_path = legacy_path.with_suffix(legacy_path.suffix + ".tmp")
                tmp_path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
                os.replace(tmp_path, legacy_path)
            except Exception:
                return False
            sidecar_path = legacy_path.with_name(legacy_path.stem + ".sidecars") / f"{entry_id}.json"
            paths = (_data_path(entry_id), sidecar_path)
        else:
            removed = _entry_path(entry_id).exists()
            _entry_path(entry_id).unlink(missing_ok=True)
            index = _load_index()
            removed = index["entries"].pop(entry_id, None) is not None or removed
            _save_index(index)
            paths = (_data_path(entry_id), cache_dir() / "sidecars" / f"{entry_id}.json")
        for path in paths:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        removed = _invalidate_raw_dump(filepath, CACHE_VERSION, _path_match_values) or removed
    return removed


def clear_inspection_cache() -> int:
    """Remove cached inspection entries and return the number of files removed."""
    paths = []
    legacy_path = _legacy_cache_path()
    if legacy_path and legacy_path.exists():
        paths.append(legacy_path)
    if legacy_path:
        legacy_sidecars = legacy_path.with_name(legacy_path.stem + ".sidecars")
        if legacy_sidecars.exists():
            paths.append(legacy_sidecars)
    for cache_path in {cache_dir(), model_cache_dir()}:
        if cache_path.exists():
            paths.append(cache_path)

    removed = 0
    for path in paths:
        try:
            if path.is_dir():
                removed += sum(1 for child in path.rglob("*") if child.is_file())
                shutil.rmtree(path)
            else:
                path.unlink()
                removed += 1
        except Exception:
            pass
    return removed
