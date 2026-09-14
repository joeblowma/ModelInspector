"""Shared, conservative projection of evidence-backed capability facts.

One helper is used by the model-card badges (``front.metadata_ui``), the
terminal report (``back.reporting``), and the typed facts extractor
(``back.estimator``) so the "weak evidence is not a definite capability" rule
cannot drift between surfaces.  Backend-only: this module never imports GUI.
"""

from __future__ import annotations

from typing import Any, Mapping

_WEAK_STRENGTHS = frozenset({"weak", "low", "uncertain"})


def has_evidence(value: Any) -> bool:
    """True when a stored evidence trace is non-empty."""
    if isinstance(value, (list, tuple, set, frozenset)):
        return bool(value)
    return value not in (None, "", False, 0)


def evidence_backed_capabilities(
    facts: Mapping[str, Any] | None,
    *,
    require_evidence: bool = True,
) -> tuple[str, ...]:
    """Return canonical capability keys whose evidence is not explicitly weak.

    ``require_evidence`` (the badge contract) additionally drops keys without a
    non-empty evidence trace.  ``require_evidence=False`` preserves the legacy
    report/estimator behavior for compact facts that only carry a capability
    list, while still suppressing an explicit ``weak``/``low``/``uncertain``
    ``evidence_strength`` entry.
    """
    if not isinstance(facts, Mapping):
        return ()
    raw_values = facts.get("capabilities")
    values = raw_values if isinstance(raw_values, (list, tuple, set, frozenset)) else ()
    raw_evidence = facts.get("evidence")
    evidence = raw_evidence if isinstance(raw_evidence, Mapping) else {}
    raw_strength = facts.get("evidence_strength")
    strength = raw_strength if isinstance(raw_strength, Mapping) else None

    result: list[str] = []
    for value in values:
        key = str(value).strip().lower()
        if not key or key in result:
            continue
        if require_evidence and not has_evidence(evidence.get(key)):
            continue
        if strength is not None:
            level = str(strength.get(key) or "").strip().lower()
            if level in _WEAK_STRENGTHS:
                continue
        result.append(key)
    return tuple(result)


__all__ = ["evidence_backed_capabilities", "has_evidence"]