"""Bounded, read-only metadata discovery for model companions.

Hugging Face exports frequently keep the useful model identity outside the
weight header.  This module reads only small JSON/Jinja companion files next
to the *resolved* model file.  It never opens a model payload and never
executes a chat template; templates are inspected as plain text for a few
explicit capability markers.
"""

from __future__ import annotations

import json
import re
from hashlib import sha256
from pathlib import Path
from typing import Any, Mapping


MAX_COMPANION_BYTES = 1_048_576
MAX_CHAT_TEMPLATE_BYTES = 262_144
MAX_JSON_DEPTH = 8
MAX_JSON_ITEMS = 256
MAX_JSON_STRING_CHARS = 32_768
COMPANION_NAMES = (
    "config.json",
    "chat_template.jinja",
    "tokenizer_config.json",
    "processor_config.json",
)

_LAYER_KEYS = (
    "num_hidden_layers",
    "num_layers",
    "n_layer",
    "n_layers",
    "layer_count",
    "num_transformer_layers",
)
_VISION_ROOTS = (
    "vision_tower",
    "vision_model",
    "visual",
    "vision_encoder",
    "image_encoder",
    "clip_vision_model",
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
_VISION_ONLY_NAMES = re.compile(
    r"(?:^|[_ .-])(clip|vit|siglip|vision|image|siglip2|swin)(?:$|[_ .-])",
    re.IGNORECASE,
)
_LANGUAGE_HINTS = re.compile(
    r"(?:causallm|forconditionalgeneration|forseq2seqlm|language|llm|llama|"
    r"mistral|mixtral|qwen|gemma|gpt|phi|bert|t5|deepseek|internlm|"
    r"starcoder|command|olmo|mamba|rwkv|nemotron|falcon|glm|baichuan|"
    r"chatglm|llava|idefics|internvl|minicpm|paligemma|smollm)",
    re.IGNORECASE,
)
_NON_LANGUAGE_HINTS = re.compile(
    r"(?:diffusion|stable[-_ ]diffusion|flux|sdxl|sd3|unet|vae|mmproj|"
    r"multimodalprojector|multi_modal_projector|vision(?:encoder|model)?|"
    r"clip(?:vision)?|vit|siglip|swin)",
    re.IGNORECASE,
)
_TEXT_INDEX_PATTERNS = (
    re.compile(r"(?:^|\.)model\.layers\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)model\.decoder\.layers\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)transformer\.h\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)transformer\.blocks\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)gpt_neox\.layers\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)blk\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)encoder\.layer\.(\d+)(?:\.|$)"),
    re.compile(r"(?:^|\.)decoder\.block\.(\d+)(?:\.|$)"),
)
_VISION_INDEX_PATTERNS = (
    re.compile(
        r"(?:^|\.)(?:vision_tower|vision_model|visual|vision_encoder|"
        r"image_encoder|clip_vision_model)(?:\.[^.]+)*\."
        r"(?:layers|blocks|encoder\.layers|transformer_blocks)\.(\d+)(?:\.|$)"
    ),
)
_AUDIO_INDEX_PATTERNS = (
    re.compile(r"(?:^|\.)(?:audio|speech)[^.]*\.(?:layers|blocks)\.(\d+)(?:\.|$)"),
)
_VIDEO_INDEX_PATTERNS = (
    re.compile(r"(?:^|\.)(?:video|temporal)[^.]*\.(?:layers|blocks)\.(\d+)(?:\.|$)"),
)
_THINKING_TEMPLATE_RE = re.compile(
    r"(?:<\s*/?\s*think\b|reasoning_content|enable[_ -]?thinking|"
    r"thinking_mode|\b(?:thinking|reasoning)\s*(?:[:=]|\b))",
    re.IGNORECASE,
)
_TOOLS_TEMPLATE_RE = re.compile(
    r"(?:\btool(?:s|_calls?)?\b|\bfunction[_ -]?calls?\b|"
    r"<\|[^|]*(?:tool|function)[^|]*\|>)",
    re.IGNORECASE,
)


def _bounded_digest(path: Path, expected_size: int) -> str | None:
    """Hash a small companion without ever reading an unbounded file."""
    if expected_size < 0 or expected_size > MAX_COMPANION_BYTES:
        return None
    try:
        with path.open("rb") as stream:
            content = stream.read(MAX_COMPANION_BYTES + 1)
    except OSError:
        return None
    if len(content) != expected_size:
        return None
    return sha256(content).hexdigest()


def _resolved_parent(filepath: str | Path) -> Path | None:
    """Return the real model directory, not the directory containing a link."""
    try:
        return Path(filepath).resolve(strict=True).parent
    except (OSError, RuntimeError):
        return None


def _bounded_json_value(value: Any, depth: int = 0) -> Any:
    """Keep parsed companion data finite while retaining useful config paths."""
    if depth >= MAX_JSON_DEPTH:
        return "[truncated: companion metadata depth]"
    if isinstance(value, str):
        if len(value) <= MAX_JSON_STRING_CHARS:
            return value
        return value[: MAX_JSON_STRING_CHARS - 20] + "... [truncated]"
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        items = list(value.items())
        for key, child in items[:MAX_JSON_ITEMS]:
            result[str(key)[:512]] = _bounded_json_value(child, depth + 1)
        if len(items) > MAX_JSON_ITEMS:
            result["_smi_truncated_items"] = len(items) - MAX_JSON_ITEMS
        return result
    if isinstance(value, (list, tuple)):
        result_list = [_bounded_json_value(child, depth + 1) for child in value[:MAX_JSON_ITEMS]]
        if len(value) > MAX_JSON_ITEMS:
            result_list.append(f"[truncated: {len(value) - MAX_JSON_ITEMS} more items]")
        return result_list
    return str(value)[:MAX_JSON_STRING_CHARS]


def _file_identity(path: Path, name: str) -> dict[str, Any]:
    try:
        stat = path.stat()
    except OSError:
        return {
            "name": name,
            "path": str(path),
            "resolved_path": str(path.absolute()),
            "exists": False,
            "file_size": 0,
            "mtime_ns": None,
            "content_digest": None,
        }
    try:
        resolved_path = str(path.resolve(strict=True))
    except (OSError, RuntimeError):
        resolved_path = str(path.absolute())
    return {
        "name": name,
        "path": str(path),
        "resolved_path": resolved_path,
        "exists": path.is_file(),
        "file_size": int(stat.st_size),
        "mtime_ns": int(stat.st_mtime_ns),
        "content_digest": _bounded_digest(path, int(stat.st_size)),
    }


def _read_json(path: Path, name: str, warnings: list[str]) -> Any:
    try:
        size = path.stat().st_size
    except OSError as exc:
        warnings.append(f"{name}: unavailable ({exc})")
        return None
    if size > MAX_COMPANION_BYTES:
        warnings.append(f"{name}: metadata exceeds {MAX_COMPANION_BYTES} bytes")
        return None
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_COMPANION_BYTES + 1)
    except OSError as exc:
        warnings.append(f"{name}: read failed ({exc})")
        return None
    if len(raw) > MAX_COMPANION_BYTES:
        warnings.append(f"{name}: metadata changed beyond the size limit while reading")
        return None
    try:
        parsed = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError) as exc:
        warnings.append(f"{name}: malformed JSON ({exc})")
        return None
    if not isinstance(parsed, (dict, list)):
        warnings.append(f"{name}: JSON root is not an object or array")
        return None
    return _bounded_json_value(parsed)


def _read_template(path: Path, name: str, warnings: list[str]) -> str | None:
    try:
        size = path.stat().st_size
    except OSError as exc:
        warnings.append(f"{name}: unavailable ({exc})")
        return None
    if size > MAX_CHAT_TEMPLATE_BYTES:
        warnings.append(f"{name}: template exceeds {MAX_CHAT_TEMPLATE_BYTES} bytes")
        return None
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CHAT_TEMPLATE_BYTES + 1)
    except OSError as exc:
        warnings.append(f"{name}: read failed ({exc})")
        return None
    if len(raw) > MAX_CHAT_TEMPLATE_BYTES:
        warnings.append(f"{name}: template changed beyond the size limit while reading")
        return None
    return raw.decode("utf-8", errors="replace")


def _template_strings(value: Any, source: str) -> list[tuple[str, str]]:
    """Extract chat-template strings without interpreting Jinja syntax."""
    if isinstance(value, str):
        return [(source, value)]
    if isinstance(value, Mapping):
        found: list[tuple[str, str]] = []
        for key, child in value.items():
            if str(key).lower() in {"template", "chat_template", "default"}:
                found.extend(_template_strings(child, f"{source}:{key}"))
        return found
    if isinstance(value, list):
        found = []
        for index, child in enumerate(value[:16]):
            found.extend(_template_strings(child, f"{source}[{index}]"))
        return found
    return []


def discover_companion_metadata(filepath: str | Path) -> dict[str, Any]:
    """Read bounded companions beside a resolved safetensors model.

    The returned mapping is safe to attach to an inspection result.  Missing,
    malformed, inaccessible, and oversized files are represented by warnings
    rather than exceptions.  ``identities`` includes absent candidates so a
    newly-created config invalidates an old cached result at the pipeline
    boundary.
    """
    path_text = str(filepath).lower()
    if not (path_text.endswith(".safetensors") or path_text.endswith(".safetensors.index.json")):
        return {"identities": [], "warnings": []}
    parent = _resolved_parent(filepath)
    if parent is None:
        return {"identities": [], "warnings": []}

    warnings: list[str] = []
    identities = [_file_identity(parent / name, name) for name in COMPANION_NAMES]
    result: dict[str, Any] = {
        "root": str(parent),
        "identities": identities,
        "warnings": warnings,
    }
    json_values: dict[str, Any] = {}
    for name in ("config.json", "tokenizer_config.json", "processor_config.json"):
        candidate = parent / name
        if not candidate.is_file():
            continue
        parsed = _read_json(candidate, name, warnings)
        if parsed is not None:
            key = name[:-5]
            result[key] = parsed
            json_values[name] = parsed

    templates: list[tuple[str, str]] = []
    template_path = parent / "chat_template.jinja"
    if template_path.is_file():
        template = _read_template(template_path, "chat_template.jinja", warnings)
        if template is not None:
            templates.append(("chat_template.jinja", template))
    for name, parsed in json_values.items():
        if name in {"tokenizer_config.json", "config.json"}:
            templates.extend(_template_strings(parsed.get("chat_template") if isinstance(parsed, Mapping) else None, f"{name}:chat_template"))
    if templates:
        result["chat_templates"] = [
            {"source": source, "text": text} for source, text in templates
        ]
    return result


def _mapping(companion: Mapping[str, Any], key: str) -> Mapping[str, Any]:
    value = companion.get(key)
    return value if isinstance(value, Mapping) else {}


def _first_positive(mapping: Mapping[str, Any], names: tuple[str, ...]) -> int | None:
    for name in names:
        value = mapping.get(name)
        if isinstance(value, bool):
            continue
        if not isinstance(value, (str, int, float)):
            continue
        if isinstance(value, float) and not value.is_integer():
            continue
        try:
            number = int(value)
        except (TypeError, ValueError):
            continue
        if 0 < number <= 100_000:
            return number
    return None


def _indexed_count(keys: list[str], patterns: tuple[re.Pattern[str], ...]) -> int | None:
    indices: set[int] = set()
    for key in keys:
        for pattern in patterns:
            match = pattern.search(str(key).lower())
            if match:
                index_text = match.group(1)
                if index_text is not None:
                    indices.add(int(index_text))
                break
    return max(indices) + 1 if indices else None


def build_architecture_facts(
    keys: list[str],
    companion: Mapping[str, Any] | None = None,
    arch_details: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize text/vision layer counts from config and header signatures."""
    companion = companion if isinstance(companion, Mapping) else {}
    config = _mapping(companion, "config")
    text_config = config.get("text_config")
    text_config = text_config if isinstance(text_config, Mapping) else {}
    vision_config = config.get("vision_config")
    vision_config = vision_config if isinstance(vision_config, Mapping) else {}

    text_count = _first_positive(text_config, _LAYER_KEYS)
    if text_count is None:
        text_count = _first_positive(config, _LAYER_KEYS)
    tensor_text_count = _indexed_count(keys, _TEXT_INDEX_PATTERNS)
    tensor_vision_count = _indexed_count(keys, _VISION_INDEX_PATTERNS)
    if text_count is None and tensor_text_count is not None:
        text_count = tensor_text_count

    block_counts: dict[str, int] = {}
    if text_count is not None:
        block_counts["text"] = text_count
    vision_count = _first_positive(vision_config, _LAYER_KEYS) or tensor_vision_count
    if vision_count is not None:
        block_counts["vision"] = vision_count
    for label, patterns in (("audio", _AUDIO_INDEX_PATTERNS), ("video", _VIDEO_INDEX_PATTERNS)):
        nested = config.get(f"{label}_config")
        count = _first_positive(nested, _LAYER_KEYS) if isinstance(nested, Mapping) else None
        count = count or _indexed_count(keys, patterns)
        if count is not None:
            block_counts[label] = count

    for name, value in (arch_details or {}).items():
        if name in {"double_blocks", "single_blocks", "transformer_blocks"}:
            try:
                number = int(value)
            except (TypeError, ValueError):
                continue
            if number > 0:
                block_counts.setdefault(str(name), number)
    return {"layer_count": text_count, "block_counts": block_counts}


def companion_architecture_hint(companion: Mapping[str, Any] | None) -> str | None:
    """Return a bounded architecture label from config evidence, if present."""
    if not isinstance(companion, Mapping):
        return None
    config = _mapping(companion, "config")
    candidates: list[Any] = []
    architectures = config.get("architectures")
    if isinstance(architectures, list):
        candidates.extend(architectures[:8])
    text_config = config.get("text_config")
    if isinstance(text_config, Mapping):
        nested_architectures = text_config.get("architectures")
        if isinstance(nested_architectures, list):
            candidates.extend(nested_architectures[:8])
    for candidate in candidates:
        text = str(candidate).strip()
        if text and len(text) <= 200 and not text.lower().startswith(("auto", "pretrained")):
            return text

    model_type = str(config.get("model_type") or "").strip().lower()
    if not model_type and isinstance(text_config, Mapping):
        model_type = str(text_config.get("model_type") or "").strip().lower()
    labels = {
        "llama": "Llama",
        "llama3": "Llama 3",
        "mistral": "Mistral",
        "mixtral": "Mixtral",
        "qwen": "Qwen",
        "qwen2": "Qwen2",
        "qwen2_vl": "Qwen2-VL",
        "qwen2_5_vl": "Qwen2.5-VL",
        "qwen3": "Qwen3",
        "qwen3_vl": "Qwen3-VL",
        "qwen2_5_omni": "Qwen2.5-Omni",
        "gemma": "Gemma",
        "gemma2": "Gemma 2",
        "phi": "Phi",
        "phi3": "Phi-3",
        "gpt2": "GPT-2",
        "gpt_neox": "GPT-NeoX",
        "bert": "BERT",
        "t5": "T5",
        "deepseek": "DeepSeek",
        "llava": "LLaVA",
        "internvl": "InternVL",
        "pixtral": "Pixtral",
    }
    if model_type in labels:
        return labels[model_type]
    if model_type and _LANGUAGE_HINTS.search(model_type) and not _NON_LANGUAGE_HINTS.search(model_type):
        return model_type.replace("_", " ").replace("-", " ").title()
    return None


def companion_identities(companion: Mapping[str, Any] | None) -> list[dict[str, Any]]:
    """Return the compact identity list used to invalidate cached companions."""
    if not isinstance(companion, Mapping):
        return []
    identities = companion.get("identities")
    return [dict(item) for item in identities if isinstance(item, Mapping)] if isinstance(identities, list) else []


def companion_identities_match(filepath: str | Path, cached: Mapping[str, Any]) -> bool:
    """Validate bounded metadata companions for cache reads and snapshots."""
    cached_identities = cached.get("companion_identities")
    if not isinstance(cached_identities, list):
        return False
    current = companion_identities(discover_companion_metadata(filepath))
    if any(item.get("exists") and not item.get("content_digest") for item in current):
        return False
    return cached_identities == current


def build_capability_facts(*args, **kwargs):
    """Compatibility export for callers that group all facts by discovery."""
    from .capability_facts import build_capability_facts as _build_capability_facts

    return _build_capability_facts(*args, **kwargs)


__all__ = [
    "COMPANION_NAMES",
    "MAX_CHAT_TEMPLATE_BYTES",
    "MAX_COMPANION_BYTES",
    "build_architecture_facts",
    "build_capability_facts",
    "companion_architecture_hint",
    "companion_identities",
    "companion_identities_match",
    "discover_companion_metadata",
]
