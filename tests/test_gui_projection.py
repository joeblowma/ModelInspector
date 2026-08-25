from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtWidgets import QApplication, QLabel

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



def test_mllm_model_type_projects_to_card_and_table():
    import gui

    app = QApplication.instance() or QApplication([])
    window = gui.MainWindow()
    data = {
        "filepath": "mllm.safetensors",
        "filename": "mllm.safetensors",
        "format": "SAFETENSORS",
        "file_size_friendly": "1.0 KB",
        "architecture": "Qwen2VLForConditionalGeneration",
        "model_type": "MLLM",
        "adapter_type": None,
        "quantization": None,
        "precision_summary": "FP16",
        "components": {"transformer": True, "vision": True},
        "named_text_encoders": {},
        "total_params_friendly": "7B",
        "tensor_count": 1,
        "training_meta": {},
    }
    try:
        window._add_card(data)
        window._add_table_row(data)

        card = window._path_to_card[data["filepath"]]
        assert any("MLLM" in label.text() for label in card.findChildren(QLabel))
        assert window.table.item(0, 5).text() == "MLLM"
    finally:
        window.close()
        app.processEvents()
