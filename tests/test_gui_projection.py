from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtWidgets import QApplication

from front.scan_projection import ProjectionEvent, ScanProjectionBuffer


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_projection_buffer_enforces_item_budget_and_final_flush():
    _app()
    projected = []
    reconciled = []
    completed = []
    acknowledgements = []
    buffer = ScanProjectionBuffer(
        lambda kind, payload: projected.append((kind, payload)),
        reconciled.append,
        completed.append,
        max_items=8,
        max_milliseconds=1000,
    )
    generation = buffer.begin()
    for value in range(17):
        buffer.enqueue(
            ProjectionEvent(
                generation,
                "result",
                value,
                lambda value=value: acknowledgements.append(value),
            )
        )
    buffer.mark_terminal(generation, "done")

    buffer.drain_now()
    assert len(projected) == 8
    assert buffer.pending_count == 9
    assert completed == []
    buffer.drain_now()
    assert len(projected) == 16
    buffer.drain_now()

    assert len(projected) == 17
    assert sorted(acknowledgements) == list(range(17))
    assert reconciled[-1] is True
    assert completed == ["done"]


def test_projection_buffer_discards_and_acknowledges_stale_events():
    _app()
    projected = []
    acknowledged = []
    buffer = ScanProjectionBuffer(
        lambda kind, payload: projected.append(payload),
        lambda final: None,
        lambda terminal: None,
    )
    stale_generation = buffer.begin()
    buffer.begin()
    buffer.enqueue(
        ProjectionEvent(
            stale_generation,
            "result",
            "stale",
            lambda: acknowledged.append(True),
        )
    )
    assert projected == []
    assert acknowledged == [True]
    assert buffer.pending_count == 0

