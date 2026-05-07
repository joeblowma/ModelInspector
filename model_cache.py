#!/usr/bin/env python3
"""Persistent inspection-result cache."""

import json
import os
import hashlib
import shutil
from pathlib import Path
from typing import Any

from app_paths import cache_dir


CACHE_VERSION = 1


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


def _cache_key(filepath: str, options: dict | None) -> str:
    try:
        resolved = str(Path(filepath).resolve(strict=True)).lower()
    except OSError:
        resolved = str(Path(filepath).absolute()).lower()
    relevant_options = {
        "allow_filename_alias_detection": bool((options or {}).get("allow_filename_alias_detection", False)),
    }
    return json.dumps([resolved, relevant_options], sort_keys=True, separators=(",", ":"))


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
    if cache.get("version") != CACHE_VERSION or not isinstance(cache.get("entries"), dict):
        return {"version": CACHE_VERSION, "entries": {}}
    return cache


def _load_index() -> dict:
    try:
        with open(_index_path(), "r", encoding="utf-8") as f:
            index = json.load(f)
    except Exception:
        return {"version": CACHE_VERSION, "entries": {}}
    if index.get("version") != CACHE_VERSION or not isinstance(index.get("entries"), dict):
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
    if index.get("version") != CACHE_VERSION or not isinstance(index.get("directories"), dict):
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
            json.dump(entry, f, ensure_ascii=False, sort_keys=True)
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

    index = _load_index()
    for entry_id in index["entries"].keys():
        entry = _read_entry(entry_id)
        if isinstance(entry, dict):
            yield entry


def _entry_matches_path(entry: dict, filepath: str) -> bool:
    wanted = _path_match_values(filepath)
    identity = entry.get("identity") if isinstance(entry.get("identity"), dict) else {}
    data = entry.get("data") if isinstance(entry.get("data"), dict) else {}
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
        index_entry = index["entries"].get(entry_id)
        entry = _read_entry(entry_id) if index_entry else None
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

    _write_entry(entry_id, entry)
    index = _load_index()
    index["entries"][entry_id] = {
        "identity": entry["identity"],
        "data_file": f"entries/{entry_id}.json",
    }
    _save_index(index)


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
    if index.get("version") != CACHE_VERSION or not isinstance(index.get("entries"), list):
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
