"""Read-only verification of persisted inspection-cache entries.

The verifier intentionally does not import the cache writer or mutate files.
It accepts entries in the current ``model_cache`` schema as well as older
entries with identity fields at the root.  Callers can apply the returned
action plan after presenting it to the user.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping


TOTAL = "total"
ACTIVE = "active"
HISTORIC = "historic"


@dataclass(frozen=True)
class FileStat:
    path: str
    size: int | None
    mtime_ns: int | None


@dataclass(frozen=True)
class CacheEntryVerification:
    path: str
    canonical_path: str
    path_aliases: tuple[str, ...]
    classification: str
    action: str
    candidate: bool
    reason: str
    cached_size: int | None = None
    cached_mtime_ns: int | None = None
    current_size: int | None = None
    current_mtime_ns: int | None = None

    @property
    def is_active(self) -> bool:
        return self.classification == "active"

    @property
    def is_historic(self) -> bool:
        return self.classification == "historic"


@dataclass(frozen=True)
class CacheAvailability:
    """Counts and conditional menu availability for cache actions."""

    total: int
    active: int
    historic: int
    refresh_candidates: int
    sync_candidates: int

    @property
    def total_count(self) -> int:
        return self.total

    @property
    def active_count(self) -> int:
        return self.active

    @property
    def historic_count(self) -> int:
        return self.historic

    @property
    def load_cache(self) -> bool:
        return self.total > 0

    @property
    def load_cache_all(self) -> bool:
        return self.active > 0

    @property
    def load_cache_archived(self) -> bool:
        return self.historic > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "active": self.active,
            "historic": self.historic,
            "refresh_candidates": self.refresh_candidates,
            "sync_candidates": self.sync_candidates,
            "Load Cache": {"available": self.load_cache, "count": self.total},
            "Load Cache All": {"available": self.load_cache_all, "count": self.active},
            "Load Cache Archived": {"available": self.load_cache_archived, "count": self.historic},
        }


@dataclass(frozen=True)
class CacheVerificationReport:
    entries: tuple[CacheEntryVerification, ...] = ()
    availability: CacheAvailability = field(default_factory=lambda: CacheAvailability(0, 0, 0, 0, 0))

    @property
    def action_plan(self) -> tuple[CacheEntryVerification, ...]:
        return tuple(entry for entry in self.entries if entry.candidate)

    def as_dict(self) -> dict[str, Any]:
        return {
            "entries": [entry.__dict__.copy() for entry in self.entries],
            "availability": self.availability.as_dict(),
            "action_plan": [entry.__dict__.copy() for entry in self.action_plan],
        }


StatProvider = Callable[[str], FileStat | None]


def _text_path(value: Any) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(value)
    except Exception:
        return None


def _aliases(entry: Mapping[str, Any], requested: str | None) -> tuple[str, ...]:
    paths: list[str] = []
    if requested:
        paths.append(requested)
    identity_raw = entry.get("identity")
    data_raw = entry.get("data")
    identity: Mapping[str, Any] = identity_raw if isinstance(identity_raw, Mapping) else {}
    data: Mapping[str, Any] = data_raw if isinstance(data_raw, Mapping) else {}
    for source in (entry, identity, data):
        for key in ("filepath", "resolved_filepath", "path", "original_path", "alias"):
            path = _text_path(source.get(key))
            if path and path.lower() not in {item.lower() for item in paths}:
                paths.append(path)
    return tuple(paths)


def _cached_stat(entry: Mapping[str, Any]) -> tuple[int | None, int | None]:
    sources = [entry]
    for key in ("identity", "data"):
        if isinstance(entry.get(key), Mapping):
            sources.append(entry[key])
    size: int | None = None
    mtime: int | None = None
    for source in sources:
        if size is None:
            raw = source.get("file_size", source.get("size"))
            try:
                size = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                pass
        if mtime is None:
            raw = source.get("mtime_ns", source.get("modified_ns"))
            if raw is None and source.get("mtime") is not None:
                raw = float(source["mtime"]) * 1_000_000_000
            try:
                mtime = int(raw) if raw is not None else None
            except (TypeError, ValueError):
                pass
    return size, mtime


def _default_stat(path: str) -> FileStat | None:
    try:
        stat = Path(path).stat()
    except (OSError, ValueError):
        return None
    return FileStat(path, int(stat.st_size), int(stat.st_mtime_ns))


def _provider_from_mapping(filesystem: Mapping[str, Any] | None) -> StatProvider:
    if filesystem is None:
        return _default_stat

    def provider(path: str) -> FileStat | None:
        wanted = path.lower()
        for key, raw in filesystem.items():
            if str(key).lower() != wanted:
                continue
            if isinstance(raw, FileStat):
                return raw
            if isinstance(raw, Mapping):
                size = raw.get("size", raw.get("file_size", raw.get("st_size")))
                mtime = raw.get("mtime_ns", raw.get("modified_ns", raw.get("st_mtime_ns")))
                if mtime is None and raw.get("mtime") is not None:
                    mtime = float(raw["mtime"]) * 1_000_000_000
                try:
                    return FileStat(path, int(size) if size is not None else None, int(mtime) if mtime is not None else None)
                except (TypeError, ValueError):
                    return None
            return None
        return None

    return provider


def verify_cache_entry(
    entry: Mapping[str, Any],
    *,
    path: str | None = None,
    filesystem: Mapping[str, Any] | None = None,
    stat_provider: StatProvider | None = None,
) -> CacheEntryVerification:
    """Verify one entry using size/mtime only; no model bytes are read."""
    if not isinstance(entry, Mapping):
        entry = {}
    aliases = _aliases(entry, path)
    display_path = path or (aliases[0] if aliases else "")
    provider = stat_provider or _provider_from_mapping(filesystem)
    current: FileStat | None = None
    for alias in aliases:
        current = provider(alias)
        if current is not None:
            break
    cached_size, cached_mtime = _cached_stat(entry)
    if current is None:
        return CacheEntryVerification(
            display_path,
            aliases[0] if aliases else display_path,
            aliases,
            "historic",
            "archive",
            True,
            "model file is missing; archive candidate",
            cached_size,
            cached_mtime,
        )
    missing_identity = cached_size is None or cached_mtime is None
    changed_size = cached_size is not None and current.size is not None and cached_size != current.size
    changed_mtime = cached_mtime is not None and current.mtime_ns is not None and cached_mtime != current.mtime_ns
    if missing_identity:
        return CacheEntryVerification(
            display_path,
            current.path,
            aliases,
            "active",
            "refresh",
            True,
            "legacy entry lacks size or mtime; refresh/sync candidate",
            cached_size,
            cached_mtime,
            current.size,
            current.mtime_ns,
        )
    if changed_size or changed_mtime:
        reason = "file size changed" if changed_size else "file mtime changed"
        if changed_size and changed_mtime:
            reason = "file size and mtime changed"
        return CacheEntryVerification(
            display_path,
            current.path,
            aliases,
            "active",
            "refresh",
            True,
            reason + "; refresh/sync candidate",
            cached_size,
            cached_mtime,
            current.size,
            current.mtime_ns,
        )
    return CacheEntryVerification(
        display_path,
        current.path,
        aliases,
        "active",
        "none",
        False,
        "file exists and size/mtime are unchanged",
        cached_size,
        cached_mtime,
        current.size,
        current.mtime_ns,
    )


def verify_cache_entries(
    entries: Iterable[Mapping[str, Any]],
    *,
    filesystem: Mapping[str, Any] | None = None,
    stat_provider: StatProvider | None = None,
) -> CacheVerificationReport:
    """Verify a batch and return counts plus a non-mutating action plan."""
    verified = tuple(verify_cache_entry(entry, filesystem=filesystem, stat_provider=stat_provider) for entry in (entries or ()))
    active = sum(item.classification == "active" for item in verified)
    historic = sum(item.classification == "historic" for item in verified)
    refresh = sum(item.action == "refresh" for item in verified)
    sync = sum(item.action == "refresh" and "sync" in item.reason for item in verified)
    return CacheVerificationReport(verified, CacheAvailability(len(verified), active, historic, refresh, sync))


def summarize_cache_verification(report: CacheVerificationReport) -> dict[str, Any]:
    """Return menu-ready conditional counts without exposing implementation types."""
    return report.availability.as_dict()


verify_cache = verify_cache_entries


__all__ = [
    "FileStat",
    "TOTAL",
    "ACTIVE",
    "HISTORIC",
    "CacheEntryVerification",
    "CacheAvailability",
    "CacheVerificationReport",
    "verify_cache_entry",
    "verify_cache_entries",
    "verify_cache",
    "summarize_cache_verification",
]
