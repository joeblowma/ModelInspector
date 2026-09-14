"""Focused resource-metadata helpers for :mod:`back.estimator`.

Extracted so ``estimator`` stays under the module-size ceiling.  Read-only:
these helpers only reformat already-inspected facts and never open a file or
tensor payload.
"""

from __future__ import annotations

import re
from typing import Any, Iterable, Mapping, cast

LANGUAGE_DOMAINS = frozenset({"LLM", "VLM", "MMLM"})

_MLA_RE = re.compile(
    r"mla|multihead_latent|kv_lora_rank|qk_nope_head_dim|qk_rope_head_dim",
    re.IGNORECASE,
)
_MISSING_FALLBACK = (
    "layer/head metadata unavailable; conservative 16-bit KV-cache fallback "
    "scaled by selected precision"
)
_NON_TRANSFORMER = (
    "non-transformer or vision-only model; language KV-cache formula not "
    "applicable, conservative fallback used"
)
_MLA_ASSUMPTION = (
    "MLA/compressed-attention metadata; KV-cache is a heuristic estimate, not "
    "an exact projection"
)
_ASYMMETRIC = "asymmetric key/value dimensions; conservative fallback used"


def project_kv_cache(
    *,
    layers: int | None,
    kv_heads: int | None,
    head_dim: int | None,
    key_dim: int | None,
    value_dim: int | None,
    context: int,
    batch: int,
    kv_bits: float,
    weight_bytes: int,
    language_present: bool,
    text_blob: str,
) -> tuple[int, list[str]]:
    """Return a conservative KV-cache byte estimate and its assumptions.

    The symmetric ``2 * kv_heads * head_dim`` formula only holds for standard
    transformer attention.  Vision-only/diffusion models get no language KV
    projection, MLA/compressed attention stays a labeled heuristic, and
    asymmetric key/value dimensions fall back rather than pretending the
    simple formula is exact.
    """
    assumptions: list[str] = []
    fallback = int(weight_bytes * 0.12 * (context / 4096) * batch * (kv_bits / 16.0))
    if not language_present:
        assumptions.append(_NON_TRANSFORMER)
        return fallback, assumptions
    if _MLA_RE.search(text_blob):
        assumptions.append(_MLA_ASSUMPTION)
        return fallback, assumptions
    if key_dim is not None and value_dim is not None:
        if key_dim == value_dim and layers and kv_heads:
            return int(
                layers
                * kv_heads
                * (key_dim + value_dim)
                * context
                * batch
                * kv_bits
                / 8
            ), assumptions
        assumptions.append(_ASYMMETRIC)
        return fallback, assumptions
    if layers and kv_heads and head_dim:
        return int(
            2 * layers * kv_heads * head_dim * context * batch * kv_bits / 8
        ), assumptions
    assumptions.append(_MISSING_FALLBACK)
    return fallback, assumptions


def runtime_sidecar_lines(
    inspection: Mapping[str, Any] | None,
    sidecars: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None,
) -> list[str]:
    """Format associated sidecar role/path pairs without inspecting files."""
    source = inspection if isinstance(inspection, Mapping) else {}
    records: list[Mapping[str, Any]]
    if isinstance(sidecars, Mapping):
        records = [cast(Mapping[str, Any], sidecars)]
    elif sidecars is not None:
        records = []
        for item in sidecars:
            if isinstance(item, Mapping):
                records.append(item)
            else:
                role, path = getattr(item, "role", None), getattr(item, "path", None)
                if role is not None or path is not None:
                    records.append({"role": role, "path": path})
    else:
        records = []
    if not records:
        for key in ("sidecars", "sidecar_inspections", "sidecar_records"):
            value = source.get(key)
            if isinstance(value, list):
                records = [item for item in value if isinstance(item, Mapping)]
                if records:
                    break

    roles = source.get("sidecar_roles")
    paths = source.get("sidecar_paths")
    identities = source.get("sidecar_identities")
    roles = list(roles) if isinstance(roles, (list, tuple)) else []
    paths = list(paths) if isinstance(paths, (list, tuple)) else []
    if not records and isinstance(identities, list):
        records = [item for item in identities if isinstance(item, Mapping)]

    pairs: list[tuple[str, str]] = []
    count = max(len(records), len(roles), len(paths))
    for index in range(count):
        record: Mapping[str, Any] = records[index] if index < len(records) else {}
        role = record.get("sidecar_role", record.get("role")) or (
            roles[index] if index < len(roles) else "unknown"
        )
        path = record.get("sidecar_path", record.get("filepath", record.get("path"))) or (
            paths[index] if index < len(paths) else ""
        )
        role_text, path_text = str(role), str(path)
        if role_text or path_text:
            pairs.append((role_text or "unknown", path_text or "unknown"))
    if not pairs:
        return []
    return ["Associated sidecars:"] + [f"Sidecar {role}: {path}" for role, path in pairs]


__all__ = ["LANGUAGE_DOMAINS", "project_kv_cache", "runtime_sidecar_lines"]