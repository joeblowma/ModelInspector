"""Compact, safe header-diagnostic projection for ``.modelinfo`` outputs."""

from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from .capability_evidence import evidence_backed_capabilities
from .reader_registry import reader_capabilities


_SENSITIVE_KEY = re.compile(
    r"(?:"
    r"api[-_]?key|authorization|credential|private[-_]?key|secret|"
    r"\bpass(?:word|phrase|wd)?\b|"
    r"(?:access|auth|refresh)[-_]?token\b|\btoken\b"
    r")",
    re.IGNORECASE,
)


def safe_metadata(value: Any) -> Any:
    """Copy header metadata while redacting values labelled as credentials."""
    if isinstance(value, Mapping):
        return {
            str(key): "[redacted]" if _SENSITIVE_KEY.search(str(key)) else safe_metadata(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [safe_metadata(item) for item in value]
    if isinstance(value, tuple):
        return [safe_metadata(item) for item in value]
    return value


def _reader_name(filepath: str) -> str:
    try:
        name = getattr(reader_capabilities(filepath), "name", None)
        return str(name or "unknown")
    except (KeyError, TypeError, ValueError):
        return "unknown"


def _companion_files(inspection: Mapping[str, Any]) -> list[dict[str, Any]]:
    values = inspection.get("companion_identities")
    if not isinstance(values, list):
        companion = inspection.get("companion_metadata")
        values = companion.get("identities") if isinstance(companion, Mapping) else []
    if not isinstance(values, list):
        return []
    return [
        {
            key: item[key]
            for key in ("path", "exists", "file_size")
            if key in item
        }
        for item in values
        if isinstance(item, Mapping)
    ]


def build_header_diagnostics(
    filepath: str,
    inspection: Mapping[str, Any] | None,
    metadata: Mapping[str, Any] | None,
    dtype_counts: Mapping[str, int],
) -> dict[str, Any]:
    """Project one pipeline result into stable, header-only diagnostics."""
    inspection = inspection if isinstance(inspection, Mapping) else {}
    metadata = metadata if isinstance(metadata, Mapping) else {}
    facts = inspection.get("capability_facts")
    facts = facts if isinstance(facts, Mapping) else {}
    capabilities = evidence_backed_capabilities(facts)
    evidence = facts.get("evidence")
    evidence = evidence if isinstance(evidence, Mapping) else {}
    visible_evidence = {
        key: list(value)
        for key, value in evidence.items()
        if key == "domain" or key in capabilities
        if isinstance(value, (list, tuple))
    }
    diagnostics: dict[str, Any] = {
        "reader": _reader_name(filepath),
        "format": inspection.get("format") or metadata.get("smi.format") or "UNKNOWN",
        "architecture": inspection.get("architecture") or "Unknown",
        "model_type": inspection.get("model_type") or "Unknown",
        "domain": facts.get("domain") or "Unknown",
        "capabilities": list(capabilities),
        "evidence": visible_evidence,
        "dtype_counts": dict(sorted(dtype_counts.items())),
    }
    for key in ("shard_manifest", "shard_identity"):
        value = inspection.get(key) or metadata.get(f"smi.{key}")
        if value is not None:
            diagnostics[key] = safe_metadata(value)
    companion_files = _companion_files(inspection)
    if companion_files:
        diagnostics["companion_files"] = companion_files
    return diagnostics


__all__ = ["build_header_diagnostics", "safe_metadata"]
