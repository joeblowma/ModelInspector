"""Nestable batching for repeated Cards layout visibility changes."""

from __future__ import annotations

import weakref
from dataclasses import dataclass
from weakref import WeakKeyDictionary


@dataclass
class _LayoutState:
    was_enabled: bool
    leases: int = 0


_LAYOUT_STATES: WeakKeyDictionary = WeakKeyDictionary()


class _LayoutBatchLease:
    def __init__(self, owner) -> None:
        self._owner = weakref.ref(owner)
        self._layout = None
        self._state: _LayoutState | None = None
        self._active = False

    def __enter__(self):
        if self._active:
            return self
        owner = self._owner()
        layout = getattr(owner, "cards_layout", None) if owner is not None else None
        if layout is None:
            return self

        state = _LAYOUT_STATES.get(layout)
        if state is None:
            try:
                was_enabled = bool(layout.isEnabled())
                if was_enabled:
                    layout.setEnabled(False)
            except RuntimeError:
                return self
            state = _LayoutState(was_enabled)
            _LAYOUT_STATES[layout] = state
        state.leases += 1
        self._layout = layout
        self._state = state
        self._active = True
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> bool:
        self.release()
        return False

    def release(self, *, activate: bool = True) -> None:
        if not self._active:
            return
        self._active = False
        layout, state = self._layout, self._state
        self._layout = None
        self._state = None
        if layout is None or state is None:
            return

        state.leases -= 1
        if state.leases:
            return
        if _LAYOUT_STATES.get(layout) is state:
            del _LAYOUT_STATES[layout]
        if not state.was_enabled:
            return
        try:
            layout.setEnabled(True)
            if activate:
                layout.activate()
        except RuntimeError:
            # The window can be destroyed while an asynchronous lease is held.
            pass


def cards_layout_batch(owner) -> _LayoutBatchLease:
    """Return an idempotent lease for one owner’s Cards layout."""
    return _LayoutBatchLease(owner)
