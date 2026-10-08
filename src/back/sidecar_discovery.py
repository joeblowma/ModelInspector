"""Conservative adjacent sidecar discovery and compact identities."""

from dataclasses import dataclass
import os
from pathlib import Path
import re


SIDECAR_ROLES = ("mmproj", "dflash", "dspark", "eagle", "draft", "mtp")
SIDECAR_EXTENSIONS = (".gguf", ".safetensors", ".onnx", ".ckpt", ".pt", ".pth")
_ROLE_RE = re.compile(r"(?<![a-z0-9])(mmproj|dflash|dspark|eagle|draft|mtp)(?![a-z0-9])", re.I)
_SHARD_RE = re.compile(r"[-_.]?\d+-of-\d+", re.I)
_VARIANT_RE = re.compile(
    r"(?:^|[-_.])(?:q\d+[a-z0-9_]*|f(?:p)?(?:8|16|32)|bf16|int[248])(?=$|[-_.])",
    re.I,
)


@dataclass(frozen=True)
class SidecarRecord:
    """A sidecar candidate with its stable semantic role."""

    path: str
    role: str

    def identity(self) -> dict:
        identity: dict[str, object] = {"filepath": self.path, "path": self.path, "role": self.role}
        try:
            stat = os.stat(self.path)
        except OSError:
            identity["exists"] = False
        else:
            identity.update(
                {
                    "exists": True,
                    "file_size": stat.st_size,
                    "mtime_ns": stat.st_mtime_ns,
                }
            )
        return identity


def sidecar_role(filepath: str | Path) -> str | None:
    """Return a role only for a standalone conservative filename token."""
    stem = Path(filepath).name.rsplit(".", 1)[0]
    match = _ROLE_RE.search(stem)
    return match.group(1).lower() if match else None


def is_probable_sidecar_path(filepath: str | Path) -> bool:
    """Return true only when a role-tagged file has an associated primary.

    A bare role name (for example ``eagle.safetensors``) is a valid standalone
    model.  Treat role syntax as a sidecar only when an adjacent non-role model
    shares its normalized family.
    """
    candidate = Path(filepath)
    if not sidecar_role(candidate):
        return False
    try:
        siblings = candidate.parent.iterdir()
    except OSError:
        return False
    return any(
        sibling != candidate
        and sibling.suffix.lower() in SIDECAR_EXTENSIONS
        and not sidecar_role(sibling)
        and _same_primary_family(sibling, candidate)
        for sibling in siblings
    )


def _normalized_core(filepath: str | Path) -> str:
    stem = Path(filepath).name.lower()
    for extension in SIDECAR_EXTENSIONS:
        if stem.endswith(extension):
            stem = stem[: -len(extension)]
            break
    stem = _SHARD_RE.sub("", stem)
    role = sidecar_role(filepath)
    if role:
        stem = _ROLE_RE.sub("", stem)
    stem = _VARIANT_RE.sub("-", stem)
    return re.sub(r"[^a-z0-9]+", "", stem)


def _same_primary_family(primary: str | Path, candidate: str | Path) -> bool:
    primary_core = _normalized_core(primary)
    candidate_core = _normalized_core(candidate)
    if not primary_core or not candidate_core:
        return False
    return primary_core == candidate_core


def discover_sidecars(
    primary_path: str | Path,
    candidates: list[str | Path] | None = None,
) -> tuple[SidecarRecord, ...]:
    """Find adjacent role-tagged files belonging to one primary family."""
    primary = Path(primary_path)
    if candidates is None:
        try:
            candidates = list(primary.parent.iterdir())
        except OSError:
            candidates = []
    found: list[SidecarRecord] = []
    for raw_candidate in candidates:
        candidate = Path(raw_candidate)
        if candidate == primary or candidate.suffix.lower() not in SIDECAR_EXTENSIONS:
            continue
        if not candidate.is_file() and not candidate.is_symlink():
            continue
        role = sidecar_role(candidate)
        if not role or not _same_primary_family(primary, candidate):
            continue
        try:
            resolved = str(candidate.resolve(strict=True))
        except OSError:
            resolved = str(candidate.absolute())
        found.append(SidecarRecord(resolved, role))
    role_order = {role: index for index, role in enumerate(SIDECAR_ROLES)}
    return tuple(sorted(found, key=lambda record: (role_order[record.role], record.path.lower())))


def sidecar_identity_snapshot(records: tuple[SidecarRecord, ...] | list[SidecarRecord]) -> list[dict]:
    """Return compact path/role/file identities suitable for cache data."""
    return [record.identity() for record in records]


__all__ = [
    "SIDECAR_EXTENSIONS",
    "SIDECAR_ROLES",
    "SidecarRecord",
    "discover_sidecars",
    "is_probable_sidecar_path",
    "sidecar_identity_snapshot",
    "sidecar_role",
]
