#!/usr/bin/env python3
"""Persistent inspection-result cache."""

import json
import os
import hashlib
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
