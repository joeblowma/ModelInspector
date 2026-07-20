"""Generation-safe, time-sliced delivery of scan events to Qt widgets."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from time import perf_counter
from typing import Callable

from PyQt6.QtCore import QObject, QTimer


@dataclass(slots=True)
class ProjectionEvent:
    generation: int
    kind: str
    payload: object
    acknowledge: Callable[[], None] | None = None


class ScanProjectionBuffer(QObject):
    """FIFO scan event buffer with a strict per-tick item/time budget."""

    def __init__(
        self,
        project: Callable[[str, object], None],
        reconcile: Callable[[bool], None],
        completed: Callable[[object], None],
        *,
        max_items: int = 8,
        max_milliseconds: float = 12.0,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent)
        self._project = project
        self._reconcile = reconcile
        self._completed = completed
        self.max_items = max(1, int(max_items))
        self.max_milliseconds = max(0.1, float(max_milliseconds))
        self._events: deque[ProjectionEvent] = deque()
        self._generation = 0
        self._terminal: object | None = None
        self._scheduled = False

    @property
    def generation(self) -> int:
        return self._generation

    @property
    def pending_count(self) -> int:
        return len(self._events)

    def begin(self) -> int:
        self.invalidate()
        return self._generation

    def enqueue(self, event: ProjectionEvent) -> None:
        if event.generation != self._generation:
            self._acknowledge(event)
            return
        self._events.append(event)
        self._schedule()

    def mark_terminal(self, generation: int, terminal: object) -> None:
        if generation != self._generation:
            return
        self._terminal = terminal
        self._schedule()

    def invalidate(self) -> None:
        self._generation += 1
        self._terminal = None
        while self._events:
            self._acknowledge(self._events.popleft())

    def drain_now(self) -> None:
        """Drain one bounded tick; public for deterministic tests."""
        self._scheduled = False
        started = perf_counter()
        projected = 0
        while self._events and projected < self.max_items:
            event = self._events.popleft()
            if event.generation == self._generation:
                self._project(event.kind, event.payload)
            self._acknowledge(event)
            projected += 1
            if (perf_counter() - started) * 1000.0 >= self.max_milliseconds:
                break

        if projected:
            self._reconcile(False)
        if self._events:
            self._schedule()
            return
        if self._terminal is not None:
            terminal = self._terminal
            self._terminal = None
            self._reconcile(True)
            self._completed(terminal)

    def _schedule(self) -> None:
        if self._scheduled:
            return
        self._scheduled = True
        QTimer.singleShot(0, self.drain_now)

    @staticmethod
    def _acknowledge(event: ProjectionEvent) -> None:
        if event.acknowledge is not None:
            event.acknowledge()

