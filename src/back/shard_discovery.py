"""Discovery, identity, and header aggregation for model shard sets."""

from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from typing import Callable


SUPPORTED_SHARD_SUFFIXES = (".gguf", ".safetensors")
_SHARD_RE = re.compile(
    r"^(?P<prefix>.*?)(?P<index>\d+)-of-(?P<count>\d+)(?P<suffix>\.gguf|\.safetensors)$",
    re.IGNORECASE,
)
_ALT_SHARD_RE = re.compile(
    r"^(?P<prefix>.*?)(?P<suffix>\.gguf|\.safetensors)-(?P<index>\d+)-of-(?P<count>\d+)$",
    re.IGNORECASE,
)
MAX_INDEX_BYTES = 8_000_000


@dataclass(frozen=True)
class ShardMember:
    """One on-disk member and its stable public shard number."""

    path: str
    shard_id: int
    source_index: int | None = None

    def identity(self) -> dict:
        item = {"path": self.path, "shard_id": self.shard_id}
        try:
            stat = os.stat(self.path)
        except OSError:
            item["exists"] = False
        else:
            item.update(
                {"exists": True, "file_size": stat.st_size, "mtime_ns": stat.st_mtime_ns}
            )
        if self.source_index is not None:
            item["source_index"] = self.source_index
        return item


@dataclass(frozen=True)
class ShardSet:
    """The members and manifest information for one logical model."""

    format: str
    members: tuple[ShardMember, ...]
    primary_path: str
    expected_count: int
    manifest_path: str | None = None

    def manifest(self) -> dict:
        return {
            "format": self.format,
            "expected_count": self.expected_count,
            "member_count": len(self.members),
            "manifest_path": self.manifest_path,
            "members": [member.identity() for member in self.members],
        }

    def identity(self) -> dict:
        return {
            "format": self.format,
            "expected_count": self.expected_count,
            "manifest_path": self.manifest_path,
            "members": [member.identity() for member in self.members],
        }


def _parse_shard_name(path: Path) -> tuple[str, int, int, str] | None:
    match = _SHARD_RE.match(path.name) or _ALT_SHARD_RE.match(path.name)
    if not match:
        return None
    groups = match.groupdict()
    count = int(groups["count"])
    index = int(groups["index"])
    suffix = groups["suffix"].lower()
    if count < 2 or index < 1 or index > count or suffix not in SUPPORTED_SHARD_SUFFIXES:
        return None
    prefix = groups["prefix"].lower()
    if match.re is _ALT_SHARD_RE:
        prefix = prefix.rstrip("-_.")
    return prefix, index, count, suffix


def _index_json(path: Path) -> dict | None:
    try:
        if path.stat().st_size > MAX_INDEX_BYTES:
            return None
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
    except (OSError, ValueError, UnicodeError):
        return None
    return value if isinstance(value, dict) else None


def _safe_member_path(base: Path, raw: str) -> Path | None:
    candidate = (base / raw).resolve()
    try:
        candidate.relative_to(base.resolve())
    except ValueError:
        return None
    if candidate.suffix.lower() != ".safetensors":
        return None
    return candidate


def _set_from_index(index_path: Path) -> ShardSet | None:
    payload = _index_json(index_path)
    if not payload:
        return None
    raw_map = payload.get("weight_map")
    if not isinstance(raw_map, dict):
        return None
    raw_members: list[Path] = []
    for raw in raw_map.values():
        if not isinstance(raw, str):
            continue
        member = _safe_member_path(index_path.parent, raw)
        if member and member not in raw_members:
            raw_members.append(member)
    if len(raw_members) < 2:
        return None
    def descriptor(member: Path, manifest_index: int) -> tuple[int, int, Path]:
        parsed = _parse_shard_name(member)
        shard_id = parsed[1] if parsed else manifest_index
        return shard_id, manifest_index, member

    members = tuple(
        ShardMember(str(member), shard_id=shard_id, source_index=manifest_index)
        for shard_id, manifest_index, member in sorted(
            (descriptor(member, index) for index, member in enumerate(raw_members, 1)),
            key=lambda item: (item[0], item[2].name.lower()),
        )
    )
    existing_members = tuple(member for member in members if Path(member.path).is_file())
    if not existing_members:
        return None
    return ShardSet(
        format="SAFETENSORS",
        members=members,
        primary_path=existing_members[0].path,
        expected_count=len(members),
        manifest_path=str(index_path),
    )


def _find_index_for_member(path: Path) -> ShardSet | None:
    try:
        candidates = sorted(path.parent.glob("*.safetensors.index.json"))
    except OSError:
        return None
    for candidate in candidates[:64]:
        shard_set = _set_from_index(candidate)
        if shard_set and any(Path(member.path).name == path.name for member in shard_set.members):
            return shard_set
    return None


def _set_from_filename(path: Path) -> ShardSet | None:
    parsed = _parse_shard_name(path)
    if not parsed:
        return None
    prefix, _, expected_count, suffix = parsed
    members_with_index = []
    try:
        candidates = list(path.parent.iterdir())
    except OSError:
        return None
    for candidate in candidates:
        if not candidate.is_file() and not candidate.is_symlink():
            continue
        other = _parse_shard_name(candidate)
        if not other or other[0] != prefix or other[2] != expected_count or other[3] != suffix:
            continue
        members_with_index.append((other[1], candidate))
    if len(members_with_index) < 2:
        return None
    members_with_index.sort(key=lambda item: (item[0], item[1].name.lower()))
    members = tuple(
        ShardMember(str(candidate), shard_id=source_index, source_index=ordinal)
        for ordinal, (source_index, candidate) in enumerate(members_with_index, 1)
    )
    return ShardSet(
        format=suffix.lstrip(".").upper(),
        members=members,
        primary_path=members[0].path,
        expected_count=expected_count,
    )


def discover_shard_set(filepath: str | Path) -> ShardSet | None:
    """Return a logical shard set for a shard or safetensors index path."""
    path = Path(filepath)
    lower = str(path).lower()
    if lower.endswith(".safetensors.index.json"):
        return _set_from_index(path)
    indexed = _find_index_for_member(path)
    if indexed:
        return indexed
    return _set_from_filename(path)


def canonical_primary_path(filepath: str | Path) -> str:
    """Return the first stable member path, or the original path."""
    shard_set = discover_shard_set(filepath)
    return shard_set.primary_path if shard_set else str(filepath)


def discoverable_primary_path(filepath: str | Path) -> str | None:
    """Return a model path suitable for discovery, excluding invalid indexes."""
    shard_set = discover_shard_set(filepath)
    if shard_set:
        return shard_set.primary_path
    if is_safetensors_index_path(filepath):
        return None
    return str(filepath)


def is_safetensors_index_path(filepath: str | Path) -> bool:
    return str(filepath).lower().endswith(".safetensors.index.json")


def aggregate_shard_headers(
    requested_path: str,
    shard_set: ShardSet,
    read_one: Callable[[str], tuple[dict, dict, int]],
) -> tuple[dict, dict, int]:
    """Merge member header triples while preserving member and tensor order."""
    metadata: dict = {}
    tensor_info: dict = {}
    total_size = 0
    warnings = []
    for member in shard_set.members:
        try:
            member_metadata, member_tensors, member_size = read_one(member.path)
        except (OSError, ValueError) as exc:
            warnings.append(f"Shard {member.shard_id} could not be read: {exc}")
            continue
        if not metadata:
            metadata.update(member_metadata)
        else:
            for key, value in member_metadata.items():
                metadata.setdefault(key, value)
        total_size += int(member_size)
        for name, descriptor in member_tensors.items():
            output_name = str(name)
            if output_name in tensor_info:
                output_name = f"{output_name}@shard{member.shard_id}"
                warnings.append(f"Duplicate tensor name {name!r} was disambiguated")
            normalized = dict(descriptor)
            normalized["shard_id"] = member.shard_id
            normalized["shard_path"] = member.path
            tensor_info[output_name] = normalized

    metadata["smi.format"] = shard_set.format
    metadata["smi.sharded"] = True
    metadata["smi.shard_manifest"] = shard_set.manifest()
    metadata["smi.shard_identity"] = shard_set.identity()
    if warnings:
        existing = list(metadata.get("smi.warnings") or [])
        metadata["smi.warnings"] = existing + warnings
    return metadata, tensor_info, total_size


__all__ = [
    "ShardMember",
    "ShardSet",
    "SUPPORTED_SHARD_SUFFIXES",
    "aggregate_shard_headers",
    "canonical_primary_path",
    "discoverable_primary_path",
    "discover_shard_set",
    "is_safetensors_index_path",
]
