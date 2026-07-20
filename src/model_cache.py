#!/usr/bin/env python3
"""Persistent inspection-result cache."""

import json
import os
import hashlib
import shutil
import threading
from pathlib import Path
from typing import Any

from app_paths import cache_dir
from back.inspection_summary import compact_inspection_summary


CACHE_VERSION = 1
_CACHE_LOCK = threading.Lock()


def _legacy_cache_path() -> Path | None:
    override = os.environ.get("SMI_CACHE_PATH")
    if override:
        return Path(override)
    return None


def _index_path() -> Path:
    return cache_dir() / "index.json"


def _directory_scan_path() -> Path:
    return cache_dir() / "directory_scans.json"


def _raw_dump_path() -> Path:
    return cache_dir() / "raw_dumps.json"


def _entry_path(entry_id: str) -> Path:
    return cache_dir() / "entries" / f"{entry_id}.json"


def _data_path(entry_id: str) -> Path:
    return cache_dir() / "data" / f"{entry_id}.json"


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


def _load_legacy_cache(path: Path) -> dict:
    try:
        with open(path, "r", encoding="utf-8") as f:
            cache = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "entries": {}}
    if cache.get("version") != CACHE_VERSION or not isinstance(
        cache.get("entries"), dict
    ):
        return {"version": CACHE_VERSION, "entries": {}}
    return cache


def _load_index() -> dict:
    try:
        with open(_index_path(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "entries": {}}
    if index.get("version") != CACHE_VERSION or not isinstance(
        index.get("entries"), dict
    ):
        return {"version": CACHE_VERSION, "entries": {}}
    return index


def _save_index(index: dict):
    try:
        path = _index_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        pass


def _load_directory_scan_index() -> dict:
    try:
        with open(_directory_scan_path(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "directories": {}}
    if index.get("version") != CACHE_VERSION or not isinstance(
        index.get("directories"), dict
    ):
        return {"version": CACHE_VERSION, "directories": {}}
    return index


def _save_directory_scan_index(index: dict):
    try:
        path = _directory_scan_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        pass


def _directory_key(folder: str) -> str:
    try:
        return str(Path(folder).resolve(strict=True)).lower()
    except OSError:
        return str(Path(folder).absolute()).lower()


def _path_match_values(filepath: str) -> set[str]:
    values = {str(Path(filepath).absolute()).lower()}
    try:
        values.add(str(Path(filepath).resolve(strict=True)).lower())
    except OSError:
        pass
    return values


def _read_entry(entry_id: str) -> dict | None:
    try:
        with open(_entry_path(entry_id), "r", encoding="utf-8") as f:
            entry = json.load(f)
    except Exception:
        return None
    return entry if isinstance(entry, dict) else None


def _write_entry(entry_id: str, entry: dict):
    try:
        path = _entry_path(entry_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(
                entry, f, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        os.replace(tmp_path, path)
    except Exception:
        pass


def _read_data_entry(entry_id: str) -> dict | None:
    try:
        with open(_data_path(entry_id), "r", encoding="utf-8") as f:
            entry = json.load(f)
    except Exception:
        return None
    return entry if isinstance(entry, dict) else None


def _write_data_entry(entry_id: str, entry: dict):
    try:
        path = _data_path(entry_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(
                entry, f, ensure_ascii=False, sort_keys=True, separators=(",", ":")
            )
        os.replace(tmp_path, path)
    except Exception:
        pass


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
        entry_paths = sorted((cache_dir() / "entries").glob("*.json"))
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
    if entry.get("identity") != ident:
        return None
    data = entry.get("data")
    return data if isinstance(data, dict) else None


def get_cached_inspection_snapshot(filepath: str) -> dict | None:
    """Return cached inspection data for a path without requiring the file to exist."""
    for entry in _iter_cached_entries():
        if not _entry_matches_path(entry, filepath):
            continue
        data = entry.get("data")
        if isinstance(data, dict):
            snapshot = dict(data)
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
        snapshot = dict(data)
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
    """Stream matching cache entries directly into compact GUI snapshots."""
    snapshots = {}
    for filepath, data in _iter_cached_inspection_matches(filepaths):
        summary_source = dict(data)
        summary_source.setdefault("cache_status", "snapshot")
        snapshots[filepath] = compact_inspection_summary(summary_source)
    return snapshots


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
    entry = {
        "identity": _identity(filepath),
        "data": data,
    }
    legacy_path = _legacy_cache_path()
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
    data_dir = cache_dir() / "data"
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
    index = _load_directory_scan_index()
    try:
        resolved_folder = str(Path(folder).resolve(strict=True))
    except OSError:
        resolved_folder = str(Path(folder).absolute())
    index["directories"][_directory_key(folder)] = {
        "folder": resolved_folder,
        "paths": list(dict.fromkeys(paths)),
    }
    _save_directory_scan_index(index)


def list_cached_directories() -> list[str]:
    index = _load_directory_scan_index()
    directories = []
    for entry in index["directories"].values():
        folder = entry.get("folder")
        if folder:
            directories.append(str(folder))
    return directories


def get_cached_directory_scan(folder: str) -> list[str]:
    """Return cached scan paths without pruning missing or temporarily unavailable files."""
    index = _load_directory_scan_index()
    key = _directory_key(folder)
    entry = index["directories"].get(key)
    if not isinstance(entry, dict):
        return []
    return [str(p) for p in entry.get("paths", []) if p]


def _load_raw_dump_index() -> dict:
    try:
        with open(_raw_dump_path(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "entries": []}
    if index.get("version") != CACHE_VERSION or not isinstance(
        index.get("entries"), list
    ):
        return {"version": CACHE_VERSION, "entries": []}
    return index


def _save_raw_dump_index(index: dict):
    try:
        path = _raw_dump_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = path.with_suffix(path.suffix + ".tmp")
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, sort_keys=True)
        os.replace(tmp_path, path)
    except Exception:
        pass


def store_raw_dump(filepath: str, dump: str):
    index = _load_raw_dump_index()
    try:
        resolved = str(Path(filepath).resolve(strict=True))
    except OSError:
        resolved = str(Path(filepath).absolute())
    entry = {
        "filepath": filepath,
        "resolved_filepath": resolved,
        "dump": dump,
    }
    match_values = _path_match_values(filepath)
    entries = []
    replaced = False
    for existing in index["entries"]:
        existing_values = {
            str(existing.get("filepath") or "").lower(),
            str(existing.get("resolved_filepath") or "").lower(),
        }
        if match_values & existing_values:
            entries.append(entry)
            replaced = True
        else:
            entries.append(existing)
    if not replaced:
        entries.append(entry)
    index["entries"] = entries
    _save_raw_dump_index(index)


def get_cached_raw_dump(filepath: str) -> str | None:
    match_values = _path_match_values(filepath)
    index = _load_raw_dump_index()
    for entry in index["entries"]:
        if not isinstance(entry, dict):
            continue
        entry_values = {
            str(entry.get("filepath") or "").lower(),
            str(entry.get("resolved_filepath") or "").lower(),
        }
        if match_values & entry_values and isinstance(entry.get("dump"), str):
            return entry["dump"]
    return None


def clear_inspection_cache() -> int:
    """Remove cached inspection entries and return the number of files removed."""
    paths = []
    legacy_path = _legacy_cache_path()
    if legacy_path and legacy_path.exists():
        paths.append(legacy_path)
    cache_path = cache_dir()
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
