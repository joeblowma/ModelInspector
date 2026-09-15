"""Read-only metadata projections and asynchronous header loading for the UI.

The Cards view receives compact inspection summaries by design.  This module
keeps the presentation rules for the structured facts in one place and owns
the optional, header-only follow-up read used by the Advanced Viewer's tensor
page.  No worker here opens tensor payloads or writes to the model/cache.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
import re
from pathlib import Path
from typing import Any

from PyQt6.QtCore import QObject, QRunnable, QThreadPool, pyqtSignal

from back.capability_evidence import evidence_backed_capabilities
from model_cache import get_cached_model_data
from model_readers import read_model_header

from .explorer_data import normalize_tensor_descriptors

__all__ = [
    "HeaderInspectionController",
    "HeaderInspectionLoader",
    "capability_badge_values",
    "domain_badge_values",
    "domain_tag_description",
    "inspection_domain",
]

_DOMAINS = frozenset(("LLM", "VLM", "MLM"))
_DOMAIN_ALIASES = {"MMLM": "MLM", "MLLM": "VLM", "MMLLLM": "VLM"}
_CAPABILITY_LABELS = (("tools", "Tool Use"), ("thinking", "Thinking"))
_DOMAIN_DESCRIPTIONS = {
    "LLM": "Language model",
    "VLM": "Language model with vision",
    "MLM": "Language model with other modalities",
}
_NATURAL_PARTS = re.compile(r"(\d+)")


def _capability_facts(inspection: Mapping[str, Any]) -> Mapping[str, Any] | None:
    value = inspection.get("capability_facts")
    return value if isinstance(value, Mapping) else None


def inspection_domain(inspection: Mapping[str, Any] | None) -> str | None:
    """Return only the backend's canonical language-domain fact."""
    source = inspection if isinstance(inspection, Mapping) else {}
    facts = _capability_facts(source)
    raw = facts.get("domain") if facts is not None else None
    domain = _DOMAIN_ALIASES.get(str(raw or "").strip().upper(), str(raw or "").strip().upper())
    return domain if domain in _DOMAINS else None


def domain_tag_description(domain: str) -> str:
    """Describe the evidence-backed domain shown on a model card."""
    return _DOMAIN_DESCRIPTIONS.get(str(domain).upper(), "Detected language domain")


def capability_badge_values(
    inspection: Mapping[str, Any] | None,
    fallback: Iterable[str] = (),
) -> tuple[str, ...]:
    """Return conservative chat-capability labels for the Advanced Viewer.

    A structured ``capability_facts`` value is authoritative and is projected
    through the shared backend helper, so a capability needs non-empty evidence
    and an explicit ``weak``/``low``/``uncertain`` strength suppresses it.  The
    legacy fallback is retained for older in-memory results and accepts only the
    two explicit chat labels; filename-derived Vision heuristics never become a
    chat-capability badge.
    """
    source = inspection if isinstance(inspection, Mapping) else {}
    facts = _capability_facts(source)
    if facts is not None:
        certain = set(evidence_backed_capabilities(facts))
        return tuple(
            label for key, label in _CAPABILITY_LABELS if key in certain
        ) or ("Unknown",)

    accepted = {label for _, label in _CAPABILITY_LABELS}
    values = tuple(str(value) for value in fallback if str(value) in accepted)
    return values or ("Unknown",)


def domain_badge_values(
    inspection: Mapping[str, Any] | None,
    fallback: Iterable[str] = (),
) -> tuple[str, ...]:
    """Prefer the compact canonical domain while retaining legacy domains."""
    domain = inspection_domain(inspection)
    if domain:
        return (domain,)
    values = tuple(
        _DOMAIN_ALIASES.get(str(value).upper(), str(value).upper())
        for value in fallback
        if str(value) != "Unknown"
    )
    return values or ("Unknown",)


def _natural_key(value: str) -> tuple[str | int, ...]:
    return tuple(
        int(part) if part.isdigit() else part.casefold()
        for part in _NATURAL_PARTS.split(str(value))
    )


def _cache_identity_matches(filepath: str, cached: Mapping[str, Any]) -> bool:
    identity = cached.get("identity")
    if not isinstance(identity, Mapping):
        return False
    try:
        path = Path(filepath)
        stat = path.stat()
        resolved = str(path.resolve(strict=True)).lower()
    except (OSError, RuntimeError):
        return False
    return (
        str(identity.get("resolved_filepath") or "").lower() == resolved
        and int(identity.get("file_size", -1)) == int(stat.st_size)
        and int(identity.get("mtime_ns", -1)) == int(stat.st_mtime_ns)
    )


def load_header_only(filepath: str) -> dict[str, Any]:
    """Load descriptors from a valid full-data cache or model header only."""
    cached = get_cached_model_data(
        filepath, options={"checkpoint_safety": "metadata"}
    )
    if isinstance(cached, Mapping) and isinstance(cached.get("tensor_info"), Mapping):
        if _cache_identity_matches(filepath, cached) or not Path(filepath).exists():
            tensor_info = dict(cached["tensor_info"])
            original = cached.get("original_tensor_order")
            original_order = (
                [str(name) for name in original]
                if isinstance(original, list)
                else list(tensor_info)
            )
            return {
                "metadata": dict(cached.get("metadata") or {}),
                "tensor_info": tensor_info,
                "file_size": int(cached.get("file_size") or 0),
                "original_tensor_order": original_order,
            }

    metadata, tensor_info, file_size = read_model_header(
        filepath, options={"checkpoint_safety": "metadata"}
    )
    descriptors = dict(tensor_info) if isinstance(tensor_info, Mapping) else {}
    original_order = list(descriptors)
    return {
        "metadata": dict(metadata) if isinstance(metadata, Mapping) else {},
        "tensor_info": descriptors,
        "file_size": int(file_size),
        "original_tensor_order": original_order,
    }


def merge_header_inspection(
    inspection: Mapping[str, Any], payload: Mapping[str, Any]
) -> dict[str, Any]:
    """Attach header descriptors to a compact result without changing facts."""
    result = dict(inspection)
    header_metadata = payload.get("metadata")
    existing_metadata = result.get("metadata")
    if isinstance(header_metadata, Mapping):
        merged_metadata = dict(header_metadata)
        if isinstance(existing_metadata, Mapping):
            merged_metadata.update(existing_metadata)
        result["metadata"] = merged_metadata
    tensor_info = payload.get("tensor_info")
    descriptors = dict(tensor_info) if isinstance(tensor_info, Mapping) else {}
    original = payload.get("original_tensor_order")
    original_order = (
        [str(name) for name in original if str(name) in descriptors]
        if isinstance(original, list)
        else list(descriptors)
    )
    original_order.extend(name for name in descriptors if name not in original_order)
    result["tensor_info"] = descriptors
    result.setdefault("original_tensor_order", original_order)
    result.setdefault("sorted_tensor_order", sorted(descriptors, key=_natural_key))
    if payload.get("file_size") is not None:
        result.setdefault("file_size", payload["file_size"])
    result.setdefault("tensor_count", len(descriptors))
    return result


class _HeaderLoadSignals(QObject):
    result = pyqtSignal(int, object)
    error = pyqtSignal(int, str)
    finished = pyqtSignal(int)


class _HeaderLoadTask(QRunnable):
    def __init__(self, generation: int, filepath: str, signals: _HeaderLoadSignals):
        super().__init__()
        self.generation = generation
        self.filepath = filepath
        self.signals = signals
        self.cancelled = False

    def cancel(self) -> None:
        self.cancelled = True

    def run(self) -> None:
        try:
            payload = load_header_only(self.filepath)
        except Exception as exc:  # worker boundary: surface, never crash Qt
            if not self.cancelled:
                self.signals.error.emit(self.generation, str(exc))
        else:
            if not self.cancelled:
                self.signals.result.emit(self.generation, payload)
        finally:
            self.signals.finished.emit(self.generation)


class HeaderInspectionLoader(QObject):
    """Run one cancellable-at-the-boundary header read on the Qt thread pool."""

    result_ready = pyqtSignal(int, object)
    error_occurred = pyqtSignal(int, str)

    def __init__(self, parent: QObject | None = None):
        super().__init__(parent)
        self._generation = 0
        self._tasks: dict[int, _HeaderLoadTask] = {}

    @property
    def generation(self) -> int:
        return self._generation

    def request(self, filepath: str) -> int:
        self.cancel()
        self._generation += 1
        generation = self._generation
        signals = _HeaderLoadSignals()
        task = _HeaderLoadTask(generation, str(filepath), signals)
        signals.result.connect(self._forward_result)
        signals.error.connect(self._forward_error)
        signals.finished.connect(self._task_finished)
        self._tasks[generation] = task
        pool = QThreadPool.globalInstance()
        assert pool is not None
        pool.start(task)
        return generation

    def cancel(self) -> None:
        for task in self._tasks.values():
            task.cancel()

    def _forward_result(self, generation: int, payload: object) -> None:
        self.result_ready.emit(generation, payload)

    def _forward_error(self, generation: int, message: str) -> None:
        self.error_occurred.emit(generation, message)

    def _task_finished(self, generation: int) -> None:
        self._tasks.pop(generation, None)


class HeaderInspectionController(QObject):
    """Connect a tensor tab to safe, stale-result-checked header loading."""

    def __init__(
        self,
        parent: QObject,
        tabs: Any,
        tensor_page: Any,
        explorer: Any,
        inspection_getter: Callable[[], Mapping[str, Any]],
        apply_inspection: Callable[[Mapping[str, Any]], None],
    ):
        super().__init__(parent)
        self._tabs = tabs
        self._tensor_page = tensor_page
        self._explorer = explorer
        self._inspection_getter = inspection_getter
        self._apply_inspection = apply_inspection
        self._loader = HeaderInspectionLoader(self)
        self._pending_path: str | None = None
        tabs.currentChanged.connect(self._tab_changed)
        self._loader.result_ready.connect(self._loaded)
        self._loader.error_occurred.connect(self._failed)

    def replace_inspection(self) -> None:
        self._pending_path = None
        self._loader.cancel()
        self._explorer.set_loading(False)

    def cancel(self) -> None:
        self.replace_inspection()

    def _tab_changed(self, index: int) -> None:
        if self._tabs.widget(index) is self._tensor_page:
            self._request_if_needed()

    def request_if_needed(self) -> None:
        """Request headers when the tensor page is already the active page.

        ``currentChanged`` only fires when the index changes.  Replacing the
        inspected model while the Tensors page is open therefore needs this
        explicit entry point as well.
        """
        if self._tabs.currentWidget() is self._tensor_page:
            self._request_if_needed()

    def _request_if_needed(self) -> None:
        inspection = self._inspection_getter()
        for key in ("tensor_info", "tensors", "tensor_data", "descriptors", "headers"):
            if normalize_tensor_descriptors(inspection.get(key)):
                return
        filepath = str(inspection.get("filepath") or "")
        if not filepath or filepath == self._pending_path:
            return
        self._pending_path = filepath
        self._explorer.set_loading(True)
        self._loader.request(filepath)

    def _is_current(self, generation: int) -> bool:
        return (
            generation == self._loader.generation
            and self._pending_path
            == str(self._inspection_getter().get("filepath") or "")
        )

    def _loaded(self, generation: int, payload: object) -> None:
        if not self._is_current(generation) or not isinstance(payload, Mapping):
            return
        self._pending_path = None
        self._apply_inspection(merge_header_inspection(self._inspection_getter(), payload))

    def _failed(self, generation: int, message: str) -> None:
        if not self._is_current(generation):
            return
        self._pending_path = None
        self._explorer.set_loading(False)
        self._explorer.status_label.setText(
            f"Read-only header view. Tensor descriptors unavailable: {str(message)[:240]}"
        )
