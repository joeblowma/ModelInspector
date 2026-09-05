"""Typed, deterministic model facts and runtime memory projections.

The functions in this module consume the dictionary returned by
``back.inspection_pipeline.inspect_file``.  They never inspect a filename and
never load tensor payloads.  Values that cannot be established from inspection
metadata are represented as ``None`` and the projection records the
conservative assumptions used for its estimate.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import math
import re
from typing import Any, Iterable, Mapping, cast


_MISSING = object()
_NUMBER_RE = re.compile(r"^\s*([+-]?(?:\d+(?:\.\d*)?|\.\d+))\s*([kmgtpe]?)\s*(?:b)?\s*$", re.I)
_QUANT_BITS = {"q2": 2, "q3": 3, "q4": 4, "q5": 5, "q6": 6, "q8": 8}
_LAYER_KEYS = ("num_hidden_layers", "n_layer", "n_layers", "num_layers", "layer_count", "block_count", "n_blocks")
_EXPERT_KEYS = ("num_experts", "n_experts", "expert_count", "num_local_experts")
_ACTIVE_EXPERT_KEYS = (
    "num_experts_per_tok",
    "experts_per_token",
    "expert_used_count",
    "active_experts",
)
_CONTEXT_KEYS = (
    "max_position_embeddings",
    "max_seq_len",
    "max_sequence_length",
    "context_length",
    "n_ctx",
    "max_context",
)
_TRAINED_CONTEXT_KEYS = (
    "trained_context",
    "training_context_length",
    "context_length_train",
    "train_context_length",
    "original_max_position_embeddings",
)


@dataclass(frozen=True)
class ModelFacts:
    """Stable at-a-glance facts suitable for a model card or table row."""

    architecture: str | None = None
    model_type: str | None = None
    total_params: int | None = None
    total_params_display: str = "Unknown"
    layer_count: int | None = None
    hidden_size: int | None = None
    attention_heads: int | None = None
    key_value_heads: int | None = None
    head_dim: int | None = None
    expert_count: int | None = None
    active_expert_count: int | None = None
    trained_context: int | None = None
    max_context: int | None = None
    rope: dict[str, Any] = field(default_factory=dict)
    mtp: dict[str, Any] = field(default_factory=dict)
    domains: tuple[str, ...] = ()
    capabilities: tuple[str, ...] = ()
    evidence: Mapping[str, tuple[str, ...]] = field(default_factory=dict)


@dataclass(frozen=True)
class ResourceProjection:
    """Estimated runtime resources, in bytes and preformatted display units."""

    weight_bytes: int
    kv_cache_bytes: int
    activation_bytes: int
    overhead_bytes: int
    vram_bytes: int
    ram_bytes: int
    weight_bits: float
    kv_cache_bits: float
    context_length: int
    batch_size: int
    kv_cache_dtype: str
    weight_display: str
    kv_cache_display: str
    vram_display: str
    ram_display: str
    assumptions: tuple[str, ...] = ()


def _flatten(value: Any, prefix: str = "") -> Iterable[tuple[str, Any]]:
    if isinstance(value, Mapping):
        for key, child in value.items():
            path = f"{prefix}.{key}" if prefix else str(key)
            yield from _flatten(child, path)
    else:
        yield prefix.lower(), value


def _fields(inspection: Mapping[str, Any]) -> dict[str, Any]:
    fields: dict[str, Any] = {}
    for key, value in _flatten(inspection):
        fields.setdefault(key, value)
        short = key.rsplit(".", 1)[-1]
        fields.setdefault(short, value)
    return fields


def _number(value: Any, *, integer: bool = False) -> float | int | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        result = float(value)
    else:
        raw = str(value).replace(",", "").strip()
        # Inspection displays parameter counts as ``7B``; in that context B
        # means billion (while GB/TB retain their normal binary-looking unit).
        billion = re.fullmatch(r"([+-]?(?:\d+(?:\.\d*)?|\.\d+))B", raw)
        if billion:
            result = float(billion.group(1)) * 1e9
            return int(result) if integer else result
        match = _NUMBER_RE.match(raw)
        if not match:
            return None
        result = float(match.group(1))
        result *= {"": 1, "k": 1e3, "m": 1e6, "g": 1e9, "t": 1e12, "p": 1e15, "e": 1e18}[match.group(2).lower()]
    if not math.isfinite(result) or result < 0:
        return None
    return int(result) if integer else result


def _first_number(fields: Mapping[str, Any], keys: Iterable[str]) -> int | None:
    for key in keys:
        for actual, value in fields.items():
            if actual == key or actual.endswith("." + key):
                number = _number(value, integer=True)
                if number is not None:
                    return int(number)
    return None


def _params(fields: Mapping[str, Any]) -> int | None:
    keys = ("total_params", "total_parameters", "parameter_count", "n_params", "params")
    return _first_number(fields, keys)


def _display_params(value: int | None) -> str:
    if value is None:
        return "Unknown"
    for threshold, suffix, divisor in ((1e12, "T", 1e12), (1e9, "B", 1e9), (1e6, "M", 1e6), (1e3, "K", 1e3)):
        if value >= threshold:
            return f"{value / divisor:.2f}{suffix}"
    return str(value)


def _text(fields: Mapping[str, Any]) -> str:
    values: list[str] = []
    for key, value in fields.items():
        if key.endswith(("filepath", "filename")) or key in {"path", "file"}:
            # Domain and capability inference must never rely on a filename.
            continue
        values.append(str(key))
        if isinstance(value, (str, bool, int, float)):
            values.append(str(value))
        elif isinstance(value, (list, tuple, set, frozenset)):
            values.extend(str(item) for item in value if isinstance(item, (str, bool, int, float)))
    return " ".join(values).lower()


def _contains(fields: Mapping[str, Any], words: Iterable[str]) -> bool:
    text = _text(fields)
    return any(word in text for word in words)


def facts_from_inspection(inspection: Mapping[str, Any] | None) -> ModelFacts:
    """Extract facts safely from a possibly incomplete inspection mapping."""
    source = inspection if isinstance(inspection, Mapping) else {}
    fields = _fields(source)
    architecture = source.get("architecture")
    model_type = source.get("model_type")
    architecture_text = str(architecture or "").lower()
    model_type_text = str(model_type or "").lower()
    total_params = _params(fields)
    layer_count = _first_number(fields, _LAYER_KEYS)
    expert_count_value = _number(source.get("expert_count"), integer=True)
    active_expert_value = _number(source.get("expert_used_count"), integer=True)
    expert_count = int(expert_count_value) if expert_count_value is not None else _first_number(fields, _EXPERT_KEYS)
    active_expert_count = int(active_expert_value) if active_expert_value is not None else _first_number(fields, _ACTIVE_EXPERT_KEYS)
    trained_context = _first_number(fields, _TRAINED_CONTEXT_KEYS)
    max_context = _first_number(fields, _CONTEXT_KEYS)
    if max_context is None:
        max_context = trained_context
    hidden_size = _first_number(fields, ("hidden_size", "d_model", "n_embd"))
    attention_heads = _first_number(fields, ("num_attention_heads", "n_head", "attention_heads"))
    key_value_heads = _first_number(fields, ("num_key_value_heads", "n_kv_heads")) or attention_heads
    head_dim = _first_number(fields, ("head_dim", "attention_head_dim"))
    if head_dim is None and hidden_size and attention_heads:
        head_dim = max(1, hidden_size // attention_heads)

    rope: dict[str, Any] = {}
    for key in ("rope_theta", "rope_scaling", "rope_type", "freq_base", "rope_freq_base"):
        for actual, value in fields.items():
            if actual == key or actual.endswith("." + key):
                if value not in (None, ""):
                    rope[key] = value
                    break
    mtp: dict[str, Any] = {}
    for key in ("mtp", "num_mtp_layers", "num_nextn_predict_layers", "nextn_predict_layers"):
        for actual, value in fields.items():
            if actual == key or actual.endswith("." + key):
                if value not in (None, ""):
                    mtp[key] = value
                    break

    components_raw = source.get("components")
    components: Mapping[str, Any] = components_raw if isinstance(components_raw, Mapping) else {}
    component_text = " ".join(str(key).lower() for key, value in components.items() if value)
    combined = f"{architecture_text} {model_type_text} {component_text} {_text(fields)}"
    evidence: dict[str, tuple[str, ...]] = {}
    capabilities: list[str] = []
    if _contains(fields, ("tool_use", "tool-use", "function_call", "function calling", "tool calling", "tools")):
        capabilities.append("Tool Use")
        evidence["Tool Use"] = ("inspection metadata",)
    if _contains(fields, ("thinking", "reasoning", "chain_of_thought", "deepseek-r1")):
        capabilities.append("Thinking")
        evidence["Thinking"] = ("inspection metadata",)
    vision = bool(re.search(r"vision|image|multimodal|vl|clip|vit", combined))
    if vision:
        capabilities.append("Vision")
        evidence["Vision"] = ("architecture/components metadata",)

    lora = "lora" in model_type_text or bool(source.get("adapter_type") or source.get("lora_rank") or components.get("lora"))
    diffusion = bool(components.get("unet") or components.get("vae")) or bool(re.search(r"diffusion|stable.?diffusion|sdxl|flux", combined))
    multimodal = vision and ("multimodal" in combined or "vl" in architecture_text or bool(components.get("vision")))
    llm = not diffusion and ("llm" in model_type_text or bool(re.search(r"llama|qwen|mistral|gemma|gpt|transformer|language|decoder", combined)))
    domains = [name for name, present in (("LLM", llm), ("Multimodal", multimodal), ("Diffusion", diffusion), ("LoRA", lora)) if present]
    return ModelFacts(
        architecture=str(architecture) if architecture not in (None, "") else None,
        model_type=str(model_type) if model_type not in (None, "") else None,
        total_params=total_params,
        total_params_display=_display_params(total_params),
        layer_count=layer_count,
        hidden_size=hidden_size,
        attention_heads=attention_heads,
        key_value_heads=key_value_heads,
        head_dim=head_dim,
        expert_count=expert_count,
        active_expert_count=active_expert_count,
        trained_context=trained_context,
        max_context=max_context,
        rope=rope,
        mtp=mtp,
        domains=tuple(domains),
        capabilities=tuple(capabilities),
        evidence=evidence,
    )


def _bits(value: Any, default: float) -> float:
    parsed = _number(value)
    if parsed is not None and 1 <= parsed <= 64:
        return parsed
    text = str(value or "").lower()
    for token, bits in (("int2", 2), ("int3", 3), ("int4", 4), ("int8", 8), ("uint8", 8), ("float32", 32), ("float16", 16), ("bf16", 16)):
        if token in text:
            return float(bits)
    for token, bits in _QUANT_BITS.items():
        if token in text:
            return float(bits)
    if "float32" in text or "fp32" in text:
        return 32.0
    if "float16" in text or "fp16" in text or "bf16" in text:
        return 16.0
    return default


def _unit(value: int) -> str:
    amount = float(max(value, 0))
    for suffix in ("B", "KiB", "MiB", "GiB", "TiB"):
        if amount < 1024 or suffix == "TiB":
            return f"{amount:.2f} {suffix}"
        amount /= 1024
    return f"{amount:.2f} TiB"


def _runtime_sidecar_lines(
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


def project_resources(
    inspection: Mapping[str, Any] | ModelFacts | None,
    *,
    context_length: int | None = None,
    batch_size: int = 1,
    weight_bits: float | None = None,
    quantization: str | None = None,
    kv_cache_dtype: str = "fp16",
    kv_cache_bits: float | None = None,
) -> ResourceProjection:
    """Estimate VRAM/RAM without reading model weights.

    If layer/head metadata is absent, a deliberately conservative 12% of
    weight bytes per 4K context is used for KV cache.  Weight storage includes
    12% quantization/runtime overhead; activations include 8% per batch item.
    """
    facts = inspection if isinstance(inspection, ModelFacts) else facts_from_inspection(inspection)
    fields = _fields(inspection if isinstance(inspection, Mapping) else {})
    assumptions: list[str] = []
    weights_bits = _bits(weight_bits if weight_bits is not None else quantization or fields.get("quantization"), 16.0)
    if weight_bits is None and not quantization and not fields.get("quantization"):
        assumptions.append("weight precision unavailable; assumed 16-bit")
    kv_bits = _bits(kv_cache_bits if kv_cache_bits is not None else kv_cache_dtype, 16.0)
    context = _number(context_length, integer=True) if context_length is not None else facts.max_context
    if context is None or context < 1:
        context = 4096
        assumptions.append("context length unavailable; assumed 4K tokens")
    batch = _number(batch_size, integer=True) or 1
    batch = max(1, min(batch, 4096))
    parameter_count = facts.total_params or 0
    weight_bytes = int(parameter_count * weights_bits / 8)
    if not parameter_count:
        assumptions.append("parameter count unavailable; weight estimate is zero")

    layers = facts.layer_count
    hidden = _first_number(fields, ("hidden_size", "d_model", "n_embd")) or facts.hidden_size
    heads = _first_number(fields, ("num_attention_heads", "n_head", "attention_heads")) or facts.attention_heads
    kv_heads = _first_number(fields, ("num_key_value_heads", "n_kv_heads")) or facts.key_value_heads or heads
    head_dim = _first_number(fields, ("head_dim", "attention_head_dim")) or facts.head_dim
    if layers and kv_heads and head_dim:
        kv_cache_bytes = int(2 * layers * kv_heads * head_dim * context * batch * kv_bits / 8)
    else:
        kv_cache_bytes = int(
            weight_bytes * 0.12 * (context / 4096) * batch * (kv_bits / 16.0)
        )
        assumptions.append(
            "layer/head metadata unavailable; conservative 16-bit KV-cache fallback scaled by selected precision"
        )
    activation_bytes = int(weight_bytes * 0.08 * batch)
    overhead_bytes = int(weight_bytes * 0.12)
    vram_bytes = weight_bytes + kv_cache_bytes + activation_bytes + overhead_bytes
    ram_bytes = int(weight_bytes * 1.30 + kv_cache_bytes * 0.50 + 256 * 1024**2)
    return ResourceProjection(
        weight_bytes=weight_bytes,
        kv_cache_bytes=kv_cache_bytes,
        activation_bytes=activation_bytes,
        overhead_bytes=overhead_bytes,
        vram_bytes=vram_bytes,
        ram_bytes=ram_bytes,
        weight_bits=float(weights_bits),
        kv_cache_bits=float(kv_bits),
        context_length=int(context),
        batch_size=int(batch),
        kv_cache_dtype=str(kv_cache_dtype),
        weight_display=_unit(weight_bytes),
        kv_cache_display=_unit(kv_cache_bytes),
        vram_display=_unit(vram_bytes),
        ram_display=_unit(ram_bytes),
        assumptions=tuple(assumptions),
    )


def runtime_configuration(
    projection: ResourceProjection,
    facts: ModelFacts | None = None,
    inspection: Mapping[str, Any] | None = None,
    *,
    sidecars: Iterable[Mapping[str, Any]] | Mapping[str, Any] | None = None,
) -> str:
    """Return a plain-text runtime configuration for copy/paste in the GUI."""
    if inspection is None and isinstance(facts, Mapping):
        inspection = facts
        facts = None
    lines = [
        f"Context: {projection.context_length:,} tokens",
        f"Batch size: {projection.batch_size}",
        f"Weights: {projection.weight_bits:g}-bit ({projection.weight_display})",
        f"KV cache: {projection.kv_cache_dtype} / {projection.kv_cache_bits:g}-bit ({projection.kv_cache_display})",
        f"Estimated VRAM: {projection.vram_display}",
        f"Estimated RAM: {projection.ram_display}",
    ]
    if facts and facts.layer_count is not None:
        lines.insert(0, f"Layers: {facts.layer_count}")
    if projection.assumptions:
        lines.append("Assumptions: " + "; ".join(projection.assumptions))
    lines.extend(_runtime_sidecar_lines(inspection, sidecars))
    return "\n".join(lines)


extract_model_facts = facts_from_inspection
estimate_resources = project_resources
format_runtime_configuration = runtime_configuration
infer_model_facts = facts_from_inspection
estimate_model_resources = project_resources
build_runtime_configuration = runtime_configuration


__all__ = [
    "ModelFacts",
    "ResourceProjection",
    "facts_from_inspection",
    "extract_model_facts",
    "infer_model_facts",
    "project_resources",
    "estimate_resources",
    "estimate_model_resources",
    "runtime_configuration",
    "format_runtime_configuration",
    "build_runtime_configuration",
]
