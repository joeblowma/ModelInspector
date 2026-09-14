"""Conservative language, modality, and chat-capability evidence helpers."""

from __future__ import annotations

import re
from typing import Any, Mapping

from .companion_discovery import (
    _LAYER_KEYS,
    _LANGUAGE_HINTS,
    _NON_LANGUAGE_HINTS,
    _first_positive,
    _mapping,
    _template_strings,
)


_OTHER_MODALITY_KEYS = {
    "audio_config",
    "speech_config",
    "video_config",
    "depth_config",
    "point_cloud_config",
    "lidar_config",
    "audio_token_index",
    "video_token_index",
    "speech_token_index",
}
_THINKING_STRONG_RE = re.compile(
    r"<\s*/?\s*think\b|reasoning_content|enable[_ -]?thinking|thinking_mode|"
    r"reasoning_effort|<\|[^|]*(?:think|reasoning)[^|]*\|>",
    re.IGNORECASE,
)
_THINKING_WEAK_RE = re.compile(
    r"\b(?:thinking|reasoning|chain[_ -]?of[_ -]?thought)\b", re.IGNORECASE
)
_TOOLS_STRONG_RE = re.compile(
    r"\btool_calls?\b|\bfunction_calls?\b|\btool_call_id\b|parallel_tool_calls|"
    r"<\|[^|]*(?:tool|function)[^|]*\|>",
    re.IGNORECASE,
)
_TOOLS_WEAK_RE = re.compile(r"\b(?:tools|tool|functions?)\b", re.IGNORECASE)
_JINJA_COMMENT_RE = re.compile(r"\{#.*?#\}", re.DOTALL)
_HTML_COMMENT_RE = re.compile(r"<!--.*?-->", re.DOTALL)
_NEGATION_RE = re.compile(
    r"\b(?:no|not|never|without|disable[sd]?|unsupported)\b", re.IGNORECASE
)
_POST_NEGATION_RE = re.compile(
    r"^\s*(?:are|is|am|was|were|:|=)?\s*"
    r"(?:not|never|no|disabled|unsupported|off|false)\b",
    re.IGNORECASE,
)
_QWEN_VL_ARCHITECTURE_RE = re.compile(
    r"\bqwen(?:[._ -]?(?:2(?:[._ -]?5)?|3))?[._ -]?vl\b", re.IGNORECASE
)
_PROJECTOR_KEY_RE = re.compile(
    r"(?:^|[._])(?:mmproj|projector|multi[_-]?modal[_-]?projector)(?:[._]|$)",
    re.IGNORECASE,
)


def _walk_values(value: Any, prefix: str = ""):
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield path.lower(), child
            yield from _walk_values(child, path)
    elif isinstance(value, list):
        for index, child in enumerate(value[:32]):
            yield from _walk_values(child, f"{prefix}[{index}]")


_POSITIVE_SCHEMA_KEYS = frozenset(
    {
        "enabled",
        "enable",
        "supported",
        "support",
        "active",
        "available",
        "is_enabled",
        "is_supported",
    }
)
_POSITIVE_TOKENS = frozenset(
    {
        "true",
        "yes",
        "on",
        "enabled",
        "enable",
        "supported",
        "support",
        "1",
        "active",
        "available",
    }
)


def _positive_scalar(value: Any) -> bool:
    """Accept only an explicit true/positive scalar, never arbitrary data."""
    if value is True:
        return True
    if value is False or value is None or isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return value > 0
    if isinstance(value, str):
        lowered = value.strip().lower()
        if _NEGATION_RE.search(lowered):
            return False
        return lowered in _POSITIVE_TOKENS
    return False


def _truthy_capability(value: Any) -> bool:
    """Conservative capability flag check.

    A bare arbitrary string, nested mapping, or list of prose is not evidence.
    Only a positive scalar, a recognized ``enabled``/``supported`` schema leaf,
    or a container holding such a leaf counts.
    """
    if value is None or value is False:
        return False
    if isinstance(value, Mapping):
        for key, child in value.items():
            if str(key).strip().lower() in _POSITIVE_SCHEMA_KEYS:
                return _positive_scalar(child)
        return False
    if isinstance(value, (list, tuple, set, frozenset)):
        return any(_positive_scalar(item) for item in value)
    return _positive_scalar(value)


def _present(value: Any) -> bool:
    """Structural presence for modality configs (not a capability flag)."""
    if value is None or value is False:
        return False
    if isinstance(value, (str, Mapping, list, tuple, set, frozenset)):
        return len(value) > 0
    if isinstance(value, (int, float)):
        return value != 0
    return True


def _explicit_capability(values: list[tuple[str, Any]], names: set[str]) -> list[str]:
    evidence: list[str] = []
    for path, value in values:
        leaf = re.sub(r".*[.]", "", path).split("[")[0].lower()
        if leaf in names and _truthy_capability(value):
            evidence.append(path)
    return evidence


def _strip_template_noise(text: str) -> str:
    """Drop Jinja/HTML comments so prose cannot fake capability evidence."""
    return _HTML_COMMENT_RE.sub(" ", _JINJA_COMMENT_RE.sub(" ", text))


def _negated(text: str, start: int, end: int) -> bool:
    """True when a weak marker is negated before or immediately after it."""
    if _NEGATION_RE.search(text[max(0, start - 32) : start]):
        return True
    return bool(_POST_NEGATION_RE.match(text[end : end + 24]))


def _template_capability_evidence(
    templates: list[tuple[str, str]],
) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    """Classify structural template markers as strong and bare prose as weak."""
    strong: dict[str, list[str]] = {"thinking": [], "tools": []}
    weak: dict[str, list[str]] = {"thinking": [], "tools": []}
    checks = (
        ("thinking", "thinking", _THINKING_STRONG_RE, _THINKING_WEAK_RE),
        ("tools", "tool", _TOOLS_STRONG_RE, _TOOLS_WEAK_RE),
    )
    for source, template in templates:
        cleaned = _strip_template_noise(template)
        for key, label, strong_re, weak_re in checks:
            if strong_re.search(cleaned):
                strong[key].append(f"{source}:{label} marker")
                continue
            for match in weak_re.finditer(cleaned):
                if not _negated(cleaned, match.start(), match.end()):
                    weak[key].append(f"{source}:{label} marker (weak)")
                    break
    return strong, weak


def _vision_evidence(
    config: Mapping[str, Any],
    processor: Mapping[str, Any],
    keys: list[str],
    components: Mapping[str, Any],
    architecture_text: str,
    standalone_projector: bool,
) -> list[str]:
    evidence: list[str] = []
    if isinstance(config.get("vision_config"), Mapping):
        evidence.append("config.json:vision_config")
    if components.get("vision"):
        evidence.append("tensor header:vision component")
    processor_type = str(
        processor.get("image_processor_type") or processor.get("image_processor") or ""
    ).strip().lower()
    if processor_type and re.search(r"image|vision|clip|vl|vit|siglip", processor_type):
        evidence.append("processor_config.json:image_processor_type")
    if not standalone_projector and _QWEN_VL_ARCHITECTURE_RE.search(architecture_text):
        evidence.append("architecture/header:known Qwen-VL family")
    return evidence


def _is_standalone_projector(keys: list[str]) -> bool:
    """Do not promote an isolated mmproj export to a language model."""
    normalized = [str(key) for key in keys if str(key)]
    return bool(normalized) and all(_PROJECTOR_KEY_RE.search(key) for key in normalized)


def _other_modality_evidence(
    config: Mapping[str, Any], processor: Mapping[str, Any], architecture_text: str
) -> list[str]:
    evidence: list[str] = []
    values = list(_walk_values(config)) + list(_walk_values(processor, "processor_config"))
    for path, value in values:
        leaf = re.sub(r".*[.]", "", path).split("[")[0].lower()
        if leaf in _OTHER_MODALITY_KEYS or any(
            token in leaf for token in ("audio", "speech", "video", "depth", "point_cloud")
        ):
            if _present(value):
                evidence.append(path)
        if leaf in {"modalities", "modality"} and isinstance(value, list):
            other = [
                str(item).lower()
                for item in value
                if str(item).lower() not in {"text", "language", "image", "vision"}
            ]
            if other:
                evidence.append(f"{path}:{','.join(other[:4])}")
    if re.search(
        r"(?:audio|speech|video|omni|anytoany)",
        architecture_text,
        re.IGNORECASE,
    ):
        evidence.append("architecture/config modality hint")
    return list(dict.fromkeys(evidence))


def build_capability_facts(
    keys: list[str],
    metadata: Mapping[str, Any] | None,
    companion: Mapping[str, Any] | None,
    architecture: str | None,
    components: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize conservative domain and chat capability evidence."""
    metadata = metadata if isinstance(metadata, Mapping) else {}
    companion = companion if isinstance(companion, Mapping) else {}
    config = _mapping(companion, "config")
    processor = _mapping(companion, "processor_config")
    architecture_text = " ".join(
        [
            str(architecture or ""),
            str(metadata.get("general.architecture") or ""),
            str(config.get("model_type") or ""),
        ]
    )
    values = list(_walk_values(config, "config.json"))
    values.extend(
        _walk_values(_mapping(companion, "tokenizer_config"), "tokenizer_config.json")
    )
    values.extend(_walk_values(processor, "processor_config.json"))
    values.extend(_walk_values(metadata, "header metadata"))
    standalone_projector = _is_standalone_projector(keys)

    language_evidence: list[str] = []
    text_config = config.get("text_config")
    if not standalone_projector and isinstance(text_config, Mapping) and _first_positive(text_config, _LAYER_KEYS):
        language_evidence.append("config.json:text_config")
    if not standalone_projector and _LANGUAGE_HINTS.search(architecture_text) and not _NON_LANGUAGE_HINTS.search(
        architecture_text
    ):
        language_evidence.append("config/header language architecture")
    lowered_keys = [str(key).lower() for key in keys]
    language_tensor = any(
        (
            re.search(r"(?:^|\.)model\.layers\.\d+\.", key)
            or "embed_tokens" in key
            or "gpt_neox.layers." in key
            or "transformer.h." in key
        )
        and not re.search(
            r"(?:vision|visual|image_encoder|mmproj|projector|diffusion|unet|clip|vit|siglip)",
            key,
        )
        for key in lowered_keys
    )
    if language_tensor:
        language_evidence.append("tensor header:language signature")
    language_evidence = list(dict.fromkeys(language_evidence))

    vision_evidence = _vision_evidence(
        config, processor, keys, components or {}, architecture_text, standalone_projector
    )
    other_evidence = _other_modality_evidence(config, processor, architecture_text)
    if language_evidence:
        if other_evidence:
            domain = "MMLM"
        elif vision_evidence:
            domain = "VLM"
        else:
            domain = "LLM"
    else:
        domain = None

    templates: list[tuple[str, str]] = []
    for entry in companion.get("chat_templates", []):
        if isinstance(entry, Mapping) and isinstance(entry.get("text"), str):
            templates.append((str(entry.get("source") or "chat template"), entry["text"]))
    for key, value in metadata.items():
        if "chat_template" in str(key).lower():
            templates.extend(_template_strings(value, f"header metadata:{key}"))

    thinking_evidence = _explicit_capability(
        values,
        {
            "thinking",
            "enable_thinking",
            "supports_thinking",
            "thinking_mode",
            "reasoning",
            "reasoning_mode",
        },
    )
    tools_evidence = _explicit_capability(
        values,
        {
            "tools",
            "tool_use",
            "tool_call",
            "tool_calls",
            "supports_tools",
            "function_calling",
            "function_calls",
        },
    )
    strong_templates, weak_templates = _template_capability_evidence(templates)
    thinking_evidence.extend(strong_templates["thinking"])
    tools_evidence.extend(strong_templates["tools"])
    thinking_weak = list(dict.fromkeys(weak_templates["thinking"]))
    tools_weak = list(dict.fromkeys(weak_templates["tools"]))
    thinking_evidence = list(dict.fromkeys(thinking_evidence))
    tools_evidence = list(dict.fromkeys(tools_evidence))
    capabilities: list[str] = []
    evidence: dict[str, list[str]] = {}
    evidence_strength: dict[str, str] = {}
    if thinking_evidence or thinking_weak:
        capabilities.append("thinking")
        evidence["thinking"] = thinking_evidence + thinking_weak
        evidence_strength["thinking"] = "strong" if thinking_evidence else "weak"
    if tools_evidence or tools_weak:
        capabilities.append("tools")
        evidence["tools"] = tools_evidence + tools_weak
        evidence_strength["tools"] = "strong" if tools_evidence else "weak"
    domain_evidence = language_evidence + vision_evidence + other_evidence
    if domain_evidence:
        evidence["domain"] = list(dict.fromkeys(domain_evidence))
    return {
        "domain": domain,
        "capabilities": capabilities,
        "evidence": evidence,
        "evidence_strength": evidence_strength,
    }


__all__ = ["build_capability_facts"]
