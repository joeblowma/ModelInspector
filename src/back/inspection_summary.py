"""Compact inspection results for long-lived GUI presentation state."""

from typing import Any


MAX_SUMMARY_STRING_CHARS = 512
MAX_DISPLAY_CONTAINER_ITEMS = 32
MAX_DISPLAY_DEPTH = 4
MAX_DISPLAY_METADATA_NODES = 128
TRUNCATED_TEXT_MARKER = "... [truncated]"
TRUNCATED_ITEMS_KEY = "_smi_summary_truncated_items"
TRUNCATED_DEPTH_MARKER = "[truncated: maximum display depth]"
TRUNCATED_BUDGET_MARKER = "[truncated: display budget exhausted]"


GUI_SUMMARY_KEYS = (
    "filepath",
    "resolved_filepath",
    "filename",
    "format",
    "file_size",
    "file_size_friendly",
    "tensor_count",
    "total_params",
    "total_params_friendly",
    "architecture",
    "architecture_facts",
    "capability_facts",
    "model_type",
    "adapter_type",
    "quantization",
    "components",
    "named_text_encoders",
    "lora_rank",
    "is_moe",
    "expert_count",
    "expert_used_count",
    "precision_summary",
    "component_precision_summary",
    "component_precisions",
    "precision_display",
    "training_meta",
    "extra",
    "warnings",
    "cache_status",
    "modelinfo_outputs",
)

_STRUCTURAL_CONTAINER_KEYS = {
    "components",
    "named_text_encoders",
    "component_precisions",
}
_USER_SIZED_CONTAINER_KEYS = {
    "training_meta",
    "extra",
    "warnings",
}
_EXACT_NESTED_COPY_KEYS = {
    "modelinfo_outputs",
    "architecture_facts",
    "capability_facts",
}


def _shallow_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, list):
        return list(value)
    if isinstance(value, tuple):
        return tuple(value)
    if isinstance(value, set):
        return set(value)
    return value


def _exact_nested_copy(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: _exact_nested_copy(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_exact_nested_copy(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_exact_nested_copy(item) for item in value)
    if isinstance(value, set):
        return {_exact_nested_copy(item) for item in value}
    if isinstance(value, frozenset):
        return frozenset(_exact_nested_copy(item) for item in value)
    return value


def _bounded_string(value: str) -> str:
    if len(value) <= MAX_SUMMARY_STRING_CHARS:
        return value
    prefix_length = MAX_SUMMARY_STRING_CHARS - len(TRUNCATED_TEXT_MARKER)
    return value[:prefix_length] + TRUNCATED_TEXT_MARKER


def _bounded_display_value(
    value: Any,
    budget: list[int],
    depth: int = 0,
) -> Any:
    """Copy user-sized display data within deterministic size/depth budgets."""
    if budget[0] <= 0:
        return TRUNCATED_BUDGET_MARKER
    budget[0] -= 1

    if isinstance(value, str):
        return _bounded_string(value)
    if isinstance(value, bytes):
        return _bounded_string(value.decode("utf-8", errors="replace"))
    if isinstance(value, (dict, list, tuple, set, frozenset)):
        if depth >= MAX_DISPLAY_DEPTH:
            return TRUNCATED_DEPTH_MARKER

    if isinstance(value, dict):
        copied = {}
        items = list(value.items())
        for key, item in items[:MAX_DISPLAY_CONTAINER_ITEMS]:
            display_key = _bounded_string(str(key))
            copied[display_key] = _bounded_display_value(item, budget, depth + 1)
        omitted = len(items) - MAX_DISPLAY_CONTAINER_ITEMS
        if omitted > 0:
            copied[TRUNCATED_ITEMS_KEY] = omitted
        return copied

    if isinstance(value, (list, tuple)):
        copied = [
            _bounded_display_value(item, budget, depth + 1)
            for item in value[:MAX_DISPLAY_CONTAINER_ITEMS]
        ]
        omitted = len(value) - MAX_DISPLAY_CONTAINER_ITEMS
        if omitted > 0:
            copied.append(f"[truncated: {omitted} more items]")
        return tuple(copied) if isinstance(value, tuple) else copied

    if isinstance(value, (set, frozenset)):
        ordered = sorted(value, key=lambda item: (type(item).__name__, repr(item)))
        copied = [
            _bounded_display_value(item, budget, depth + 1)
            for item in ordered[:MAX_DISPLAY_CONTAINER_ITEMS]
        ]
        omitted = len(ordered) - MAX_DISPLAY_CONTAINER_ITEMS
        if omitted > 0:
            copied.append(f"[truncated: {omitted} more items]")
        return tuple(copied)

    return value


def compact_inspection_summary(result: dict[str, Any]) -> dict[str, Any]:
    """Return a fresh GUI-safe projection without mutating ``result``."""
    summary = {}
    metadata_budget = [MAX_DISPLAY_METADATA_NODES]
    for key in GUI_SUMMARY_KEYS:
        if key not in result:
            continue
        value = result[key]
        if key in _USER_SIZED_CONTAINER_KEYS:
            summary[key] = _bounded_display_value(value, metadata_budget)
        elif key in _EXACT_NESTED_COPY_KEYS:
            summary[key] = _exact_nested_copy(value)
        elif key in _STRUCTURAL_CONTAINER_KEYS:
            summary[key] = _shallow_copy(value)
        else:
            summary[key] = _shallow_copy(value)
    return summary
