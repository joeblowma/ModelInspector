"""Persistent auxiliary stores used by the inspection cache.

The primary cache entry contains the compact inspection summary.  Large
companion inspections are kept in a sidecar store keyed by the primary cache
entry so loading a normal model card does not materialize every companion
record.  Directory scans and legacy raw-dump persistence live here as well;
the public compatibility functions remain in :mod:`model_cache`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping

from app_paths import cache_dir


def _empty(version: int, collection: str) -> dict[str, Any]:
    return {"version": version, collection: {}}


def _read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except Exception:
        return fallback
    return value if isinstance(value, dict) else fallback


def _write_json(path: Path, value: Mapping[str, Any], *, compact: bool = False) -> bool:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(path.suffix + ".tmp")
        with temporary.open("w", encoding="utf-8") as stream:
            if compact:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            else:
                json.dump(value, stream, ensure_ascii=False, sort_keys=True)
        os.replace(temporary, path)
        return True
    except Exception:
        return False


def load_legacy_cache(path: Path, version: int) -> dict[str, Any]:
    value = _read_json(path, _empty(version, "entries"))
    if value.get("version") != version or not isinstance(value.get("entries"), dict):
        return _empty(version, "entries")
    return value


def load_index(path: Path, version: int) -> dict[str, Any]:
    return load_legacy_cache(path, version)


def save_index(path: Path, index: dict[str, Any]) -> bool:
    return _write_json(path, index)


def read_entry(path: Path) -> dict[str, Any] | None:
    value = _read_json(path, {})
    return value if value else None


def write_entry(path: Path, entry: dict[str, Any]) -> bool:
    return _write_json(path, entry, compact=True)


def primary_identity_matches(
    cached: Mapping[str, Any] | None, current: Mapping[str, Any]
) -> bool:
    if not isinstance(cached, Mapping):
        return False
    return all(
        cached.get(key) == current.get(key)
        for key in ("resolved_filepath", "file_size", "mtime_ns")
    )


def store_directory_scan(folder: str, paths: Iterable[str], version: int) -> None:
    path = cache_dir() / "directory_scans.json"
    index = _read_json(path, _empty(version, "directories"))
    if index.get("version") != version or not isinstance(index.get("directories"), dict):
        index = _empty(version, "directories")
    try:
        resolved_folder = str(Path(folder).resolve(strict=True))
    except OSError:
        resolved_folder = str(Path(folder).absolute())
    try:
        key = str(Path(folder).resolve(strict=True)).lower()
    except OSError:
        key = str(Path(folder).absolute()).lower()
    index["directories"][key] = {
        "folder": resolved_folder,
        "paths": list(dict.fromkeys(str(item) for item in paths)),
    }
    _write_json(path, index)


def list_cached_directories(version: int) -> list[str]:
    path = cache_dir() / "directory_scans.json"
    index = _read_json(path, _empty(version, "directories"))
    if index.get("version") != version or not isinstance(index.get("directories"), dict):
        return []
    return [str(item["folder"]) for item in index["directories"].values() if isinstance(item, dict) and item.get("folder")]


def get_cached_directory_scan(folder: str, version: int) -> list[str]:
    path = cache_dir() / "directory_scans.json"
    index = _read_json(path, _empty(version, "directories"))
    if index.get("version") != version or not isinstance(index.get("directories"), dict):
        return []
    try:
        key = str(Path(folder).resolve(strict=True)).lower()
    except OSError:
        key = str(Path(folder).absolute()).lower()
    entry = index["directories"].get(key)
    if not isinstance(entry, dict):
        return []
    return [str(item) for item in entry.get("paths", []) if item]


def _raw_index(version: int) -> tuple[Path, dict[str, Any]]:
    path = cache_dir() / "raw_dumps.json"
    index = _read_json(path, {"version": version, "entries": []})
    if index.get("version") != version or not isinstance(index.get("entries"), list):
        index = {"version": version, "entries": []}
    return path, index


def store_raw_dump(
    filepath: str,
    dump: str,
    version: int,
    path_match_values: Callable[[str], set[str]],
) -> None:
    path, index = _raw_index(version)
    try:
        resolved = str(Path(filepath).resolve(strict=True))
    except OSError:
        resolved = str(Path(filepath).absolute())
    replacement = {"filepath": filepath, "resolved_filepath": resolved, "dump": dump}
    wanted = path_match_values(filepath)
    entries: list[Any] = []
    replaced = False
    for existing in index["entries"]:
        if not isinstance(existing, dict):
            continue
        candidates = {
            str(existing.get("filepath") or "").lower(),
            str(existing.get("resolved_filepath") or "").lower(),
        }
        if wanted & candidates:
            entries.append(replacement)
            replaced = True
        else:
            entries.append(existing)
    if not replaced:
        entries.append(replacement)
    index["entries"] = entries
    _write_json(path, index)


def get_cached_raw_dump(
    filepath: str,
    version: int,
    path_match_values: Callable[[str], set[str]],
) -> str | None:
    _, index = _raw_index(version)
    wanted = path_match_values(filepath)
    for entry in index["entries"]:
        if not isinstance(entry, dict):
            continue
        candidates = {
            str(entry.get("filepath") or "").lower(),
            str(entry.get("resolved_filepath") or "").lower(),
        }
        if wanted & candidates and isinstance(entry.get("dump"), str):
            return entry["dump"]
    return None


def _sidecar_path(reference: str, legacy_path: Path | None) -> Path:
    if legacy_path is not None:
        return legacy_path.with_name(legacy_path.stem + ".sidecars") / f"{reference}.json"
    return cache_dir() / "sidecars" / f"{reference}.json"


def sidecar_reference(entry_id: str, legacy_path: Path | None) -> str:
    if legacy_path is not None:
        return str(_sidecar_path(entry_id, legacy_path))
    return f"sidecars/{entry_id}.json"


def store_sidecar_records(
    entry_id: str,
    records: Iterable[Mapping[str, Any]],
    version: int,
    legacy_path: Path | None = None,
) -> str | None:
    values = [dict(record) for record in records if isinstance(record, Mapping)]
    path = _sidecar_path(entry_id, legacy_path)
    if not values:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            pass
        return None
    payload = {"version": version, "sidecar_records": values}
    return sidecar_reference(entry_id, legacy_path) if _write_json(path, payload, compact=True) else None


def load_sidecar_records(
    reference: str | None,
    version: int,
    legacy_path: Path | None = None,
) -> list[dict[str, Any]] | None:
    if not reference:
        return None
    try:
        path = Path(reference)
        if not path.is_absolute():
            path = cache_dir() / reference if reference.startswith("sidecars/") else _sidecar_path(reference, legacy_path)
        root = (cache_dir() / "sidecars") if legacy_path is None else legacy_path.with_name(legacy_path.stem + ".sidecars")
        path = path.resolve()
        path.relative_to(root.resolve())
    except (OSError, RuntimeError, ValueError):
        return None
    value = _read_json(path, {})
    records = value.get("sidecar_records", value.get("records"))
    if value.get("version") != version or not isinstance(records, list):
        return None
    return [dict(record) for record in records if isinstance(record, Mapping)]


def split_sidecar_inspections(data: Mapping[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    primary = dict(data)
    records: list[dict[str, Any]] = []
    for key in ("sidecars", "sidecar_inspections", "sidecar_records"):
        value = primary.pop(key, None)
        if isinstance(value, list) and not records:
            records = [dict(item) for item in value if isinstance(item, Mapping)]
    return primary, records


def _record_identity(record: Mapping[str, Any]) -> dict[str, Any]:
    path = str(record.get("sidecar_path") or record.get("filepath") or record.get("path") or "")
    identity: dict[str, Any] = {
        "filepath": path,
        "path": path,
        "role": str(record.get("sidecar_role") or record.get("role") or ""),
    }
    try:
        stat = os.stat(path)
    except OSError:
        identity["exists"] = False
    else:
        identity.update({"exists": True, "file_size": stat.st_size, "mtime_ns": stat.st_mtime_ns})
    return identity


def ensure_sidecar_metadata(data: Mapping[str, Any]) -> dict[str, Any]:
    result = dict(data)
    records = (
        result.get("sidecars")
        or result.get("sidecar_inspections")
        or result.get("sidecar_records")
    )
    paths = result.get("sidecar_paths")
    roles = result.get("sidecar_roles")
    companion_paths = isinstance(paths, list) and bool(paths)
    companion_records = isinstance(records, list) and bool(records)
    if not isinstance(result.get("sidecar_identities"), list) or (
        not result.get("sidecar_identities") and (companion_paths or companion_records)
    ):
        values = records if isinstance(records, list) else [
            {"path": path, "role": roles[index] if isinstance(roles, list) and index < len(roles) else ""}
            for index, path in enumerate(paths if isinstance(paths, list) else [])
        ]
        result["sidecar_identities"] = [_record_identity(item) for item in values if isinstance(item, Mapping)]
    result.setdefault("sidecar_roles", [str(item.get("role") or item.get("sidecar_role")) for item in result["sidecar_identities"] if isinstance(item, Mapping) and (item.get("role") or item.get("sidecar_role"))])
    result.setdefault("sidecar_paths", [str(item.get("path") or item.get("filepath")) for item in result["sidecar_identities"] if isinstance(item, Mapping) and (item.get("path") or item.get("filepath"))])
    return result


def restore_sidecar_inspections(
    data: Mapping[str, Any],
    reference: str | None,
    version: int,
    *,
    include_sidecars: bool,
    require_records: bool,
    legacy_path: Path | None = None,
) -> dict[str, Any] | None:
    result = ensure_sidecar_metadata(data)
    if not include_sidecars or any(
        key in result for key in ("sidecars", "sidecar_inspections", "sidecar_records")
    ):
        return result
    identities = result.get("sidecar_identities")
    if not isinstance(identities, list) or not identities:
        return result
    records = load_sidecar_records(reference, version, legacy_path)
    if records is None:
        return None if require_records else result
    result["sidecars"] = records
    result["sidecar_inspections"] = records
    result["sidecar_records"] = records
    return result


__all__ = [
    "ensure_sidecar_metadata",
    "get_cached_directory_scan",
    "get_cached_raw_dump",
    "list_cached_directories",
    "load_index",
    "load_legacy_cache",
    "load_sidecar_records",
    "primary_identity_matches",
    "read_entry",
    "restore_sidecar_inspections",
    "save_index",
    "sidecar_reference",
    "split_sidecar_inspections",
    "store_directory_scan",
    "store_raw_dump",
    "store_sidecar_records",
    "write_entry",
]
