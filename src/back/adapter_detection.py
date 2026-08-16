"""Detection helpers for LoRA and related adapter weights.

Adapter checkpoints use several naming conventions.  The low-level helpers in
this module inspect header keys and metadata only, so callers can identify the
adapter family without opening or materializing tensor data.  The core
``detect_adapter_type`` function intentionally preserves the precedence and
return values of the original inspection implementation.
"""

from collections import Counter
import re
from typing import Iterable


ADAPTER_FAMILIES = ("LoRA", "LoKr", "LoHa", "DoRA", "GLoRA", "LyCORIS")

_STANDARD_LORA_MARKERS = ("lora_up", "lora_down", "lora_a", "lora_b", ".lora.")
_LYCORIS_MARKERS = ("lycoris_", "lokr_", "loha_", "hada_", "dora_", "glora")


__all__ = [
    "ADAPTER_FAMILIES",
    "_max_block_index",
    "_collect_lora_up_dims",
    "_detect_lora_rank",
    "detect_adapter_type",
    "is_adapter_key",
    "adapter_key_families",
    "adapter_key_counts",
    "summarize_adapter_dimensions",
]


def _max_block_index(keys: list[str], block_name: str) -> int:
    """Return the largest numeric index following ``block_name`` in keys."""
    mx = -1
    for k in keys:
        if block_name in k:
            try:
                idx = int(k.split(block_name)[1].split(".")[0])
                mx = max(mx, idx)
            except (ValueError, IndexError):
                pass
    return mx


def _collect_lora_up_dims(keys, shapes):
    """Collect output dimensions of ``lora_up`` / ``lora_B`` weights.

    These dimensions correspond to the hidden dimension of the target layer
    and are used by architecture detection for otherwise ambiguous LoRAs.
    """
    dims = set()
    for k in keys:
        if ("lora_up" in k or "lora_B" in k) and k.endswith(".weight"):
            s = shapes.get(k, [])
            if len(s) >= 2:
                dims.add(s[0])
    return dims


def _detect_lora_rank(keys, shapes):
    """Detect the most common LoRA rank from ``lora_down`` / ``lora_A``."""
    ranks = []
    for k in keys:
        if ("lora_down" in k or "lora_A" in k) and k.endswith(".weight"):
            s = shapes.get(k, [])
            if len(s) >= 2:
                ranks.append(s[0])
    if not ranks:
        return None
    return Counter(ranks).most_common(1)[0][0]


def _metadata_algorithm_flags(metadata: dict) -> dict[str, bool]:
    """Read LyCORIS algorithm hints from the two supported metadata fields."""
    lyco_cfg = str(metadata.get("lycoris_config", "")).lower()
    ss_network_args = str(metadata.get("ss_network_args", "")).lower()
    algorithm_text = lyco_cfg + " " + ss_network_args
    return {
        "lokr": bool(re.search(r'"algo"\s*:\s*"lokr"', algorithm_text)),
        "loha": bool(re.search(r'"algo"\s*:\s*"loha"', algorithm_text)),
        "dora": bool(re.search(r'"algo"\s*:\s*"dora"', algorithm_text)),
        "glora": bool(re.search(r'"algo"\s*:\s*"glora"', algorithm_text)),
    }


def _has_glora_factors(key_blob: str) -> bool:
    """Return whether a normalized key blob has all four GLoRA factors."""
    return all(token in key_blob for token in (".a1", ".a2", ".b1", ".b2"))


def is_adapter_key(key: str) -> bool:
    """Return whether ``key`` uses a known adapter naming marker.

    This is deliberately broader than standard LoRA: LyCORIS variants often
    contain only ``lokr_``, ``loha_``, ``hada_``, ``dora_``, or ``glora`` keys.
    The same case-sensitive checks used by component detection are retained for
    the prefix markers, while common embedded markers are matched literally.
    """
    return (
        "lora_up" in key
        or "lora_down" in key
        or "lora_A" in key
        or "lora_B" in key
        or ".lora." in key
        or key.startswith("lora_")
        or key.startswith("lycoris_")
        or "lokr_" in key
        or "loha_" in key
        or "hada_" in key
        or "dora_" in key
        or "glora" in key
    )


def _normalized_adapter_blob(keys: Iterable[str]) -> str:
    """Join keys in the same normalized form used by family detection."""
    return "\n".join(keys).lower()


def adapter_key_families(keys: Iterable[str], metadata: dict | None = None) -> tuple[str, ...]:
    """Return all adapter families suggested by keys and optional metadata.

    Unlike :func:`detect_adapter_type`, this diagnostic helper does not apply
    precedence.  It is useful when a checkpoint contains a generic container
    marker together with a more specific algorithm marker.
    """
    key_blob = _normalized_adapter_blob(keys)
    metadata = metadata or {}
    flags = _metadata_algorithm_flags(metadata)
    families = []

    if "lokr_w1" in key_blob or "lokr_w2" in key_blob or flags["lokr"]:
        families.append("LoKr")
    if (
        "hada_w1_a" in key_blob
        or "hada_w1_b" in key_blob
        or "hada_w2_a" in key_blob
        or "hada_w2_b" in key_blob
        or flags["loha"]
    ):
        families.append("LoHa")
    if "dora_scale" in key_blob or flags["dora"]:
        families.append("DoRA")
    if "glora" in key_blob or flags["glora"] or _has_glora_factors(key_blob):
        families.append("GLoRA")

    lyco_cfg = str(metadata.get("lycoris_config", "")).lower()
    ss_network_module = str(metadata.get("ss_network_module", "")).lower()
    if (
        "lycoris_" in key_blob
        or "lycoris" in lyco_cfg
        or "lycoris" in ss_network_module
    ):
        families.append("LyCORIS")
    if any(marker in key_blob for marker in _STANDARD_LORA_MARKERS):
        families.append("LoRA")

    # Keep declaration order while removing duplicate evidence.
    return tuple(dict.fromkeys(families))


def adapter_key_counts(keys: Iterable[str]) -> dict[str, int]:
    """Count broad adapter marker categories in a sequence of tensor keys."""
    counts = {
        "lora": 0,
        "lycoris": 0,
        "lokr": 0,
        "loha": 0,
        "dora": 0,
        "glora": 0,
    }
    for key in keys:
        lowered = key.lower()
        if any(marker in lowered for marker in _STANDARD_LORA_MARKERS):
            counts["lora"] += 1
        if "lycoris_" in lowered:
            counts["lycoris"] += 1
        if "lokr_" in lowered or "lokr_w" in lowered:
            counts["lokr"] += 1
        if "loha_" in lowered or "hada_" in lowered:
            counts["loha"] += 1
        if "dora_" in lowered:
            counts["dora"] += 1
        if "glora" in lowered or _has_glora_factors(lowered):
            counts["glora"] += 1
    return counts


def summarize_adapter_dimensions(keys, shapes) -> dict[str, object]:
    """Return rank and target-dimension evidence for an adapter checkpoint."""
    up_dims = _collect_lora_up_dims(keys, shapes)
    return {
        "rank": _detect_lora_rank(keys, shapes),
        "up_dims": sorted(up_dims),
        "up_dim_count": len(up_dims),
    }


def detect_adapter_type(keys: list[str], metadata: dict) -> str | None:
    """Detect adapter family/type when file contains adapter weights."""
    if not keys:
        return None

    key_blob = "\n".join(keys).lower()
    lyco_cfg = str(metadata.get("lycoris_config", "")).lower()
    ss_network_module = str(metadata.get("ss_network_module", "")).lower()
    ss_network_args = str(metadata.get("ss_network_args", "")).lower()
    algo_lokr = bool(
        re.search(r'"algo"\s*:\s*"lokr"', lyco_cfg + " " + ss_network_args)
    )
    algo_loha = bool(
        re.search(r'"algo"\s*:\s*"loha"', lyco_cfg + " " + ss_network_args)
    )
    algo_dora = bool(
        re.search(r'"algo"\s*:\s*"dora"', lyco_cfg + " " + ss_network_args)
    )
    algo_glora = bool(
        re.search(r'"algo"\s*:\s*"glora"', lyco_cfg + " " + ss_network_args)
    )

    # Specific algorithms first
    if "lokr_w1" in key_blob or "lokr_w2" in key_blob or algo_lokr:
        return "LoKr"
    if (
        "hada_w1_a" in key_blob
        or "hada_w1_b" in key_blob
        or "hada_w2_a" in key_blob
        or "hada_w2_b" in key_blob
        or algo_loha
    ):
        return "LoHa"
    if "dora_scale" in key_blob or algo_dora:
        return "DoRA"
    # GLoRA commonly stores factorized weights as a1/a2/b1/b2 and algo in
    # ss_network_args.
    has_glora_factorized = all(tok in key_blob for tok in (".a1", ".a2", ".b1", ".b2"))
    if "glora" in key_blob or algo_glora or has_glora_factorized:
        return "GLoRA"

    # Generic LyCORIS container (non-LoRA variants, unknown exact algo)
    if (
        "lycoris_" in key_blob
        or "lycoris" in lyco_cfg
        or "lycoris" in ss_network_module
    ):
        return "LyCORIS"

    # Standard LoRA formats
    if (
        "lora_up" in key_blob
        or "lora_down" in key_blob
        or "lora_a" in key_blob
        or "lora_b" in key_blob
        or ".lora." in key_blob
    ):
        return "LoRA"

    return None
