"""End-to-end header-only Tensor Data and root-summary checks."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import time

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtWidgets import QApplication

from back.inspection_summary import compact_inspection_summary
from back.reader_registry import reader_capabilities
from front.advanced_viewer import AdvancedViewerDialog
from front.tensor_root_summary import root_name, summarize_tensor_roots
from model_readers import read_model_header


@pytest.fixture(scope="session")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_realistic_safetensors(path: Path) -> None:
    header = {
        "__metadata__": {
            "format": "pt",
            "model_name": "header-only-root-summary",
            "quantization": "F16",
        },
        "model.embed_tokens.weight": {
            "dtype": "F16",
            "shape": [4096, 32000],
            "data_offsets": [0, 262144000],
        },
        "model.layers.0.self_attn.q_proj.weight": {
            "dtype": "F16",
            "shape": [4096, 4096],
            "data_offsets": [262144000, 295698432],
        },
        "text_encoder.embeddings.weight": {
            "dtype": "F32",
            "shape": [768, 49408],
            "data_offsets": [295698432, 447983616],
        },
        "lm_head.weight": {
            "dtype": "BF16",
            "shape": [32000, 4096],
            "data_offsets": [447983616, 710127616],
        },
    }
    raw = json.dumps(header, separators=(",", ":")).encode("utf-8")
    # The payload is deliberately not a valid tensor stream.  A header reader
    # must still succeed without opening or deserializing it.
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"not-a-tensor-payload")


def test_root_name_grouping_is_name_only_and_searchable(app: QApplication):
    assert root_name("model.layers.0.weight") == "model"
    assert root_name("text_encoder/embeddings/weight") == "text_encoder"
    assert root_name("lm_head.weight") == "lm_head"
    assert summarize_tensor_roots(
        ["model.a", "model.b", "text_encoder.weight", "lm_head.weight"]
    ) == (
        {"name": "lm_head", "count": 1},
        {"name": "model", "count": 2},
        {"name": "text_encoder", "count": 1},
    )


def test_advanced_viewer_accepts_all_header_descriptor_aliases(app: QApplication):
    dialog = AdvancedViewerDialog(
        {
            "headers": {
                "model.layers.0.weight": {"shape": [2, 2], "dtype": "F16"},
            }
        }
    )
    try:
        assert dialog.explorer_tab.tensor_model.rowCount() == 1
        assert dialog.explorer_tab.tensor_root_summary.rows == (
            {"name": "model", "count": 1},
        )
    finally:
        dialog.close()


def test_safetensors_tensor_data_loads_header_and_root_names_only(
    app: QApplication, tmp_path: Path
):
    model = tmp_path / "realistic.safetensors"
    _write_realistic_safetensors(model)
    metadata, tensors, file_size = read_model_header(str(model))

    assert metadata["smi.format"] == "SAFETENSORS"
    assert set(tensors) == {
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "text_encoder.embeddings.weight",
        "lm_head.weight",
    }
    assert file_size == model.stat().st_size

    summary = compact_inspection_summary(
        {
            "filepath": str(model),
            "filename": model.name,
            "format": "SAFETENSORS",
            "architecture": "Transformer",
            "model_type": "LLM",
            "tensor_count": len(tensors),
        }
    )
    dialog = AdvancedViewerDialog(summary)
    try:
        tensor_index = dialog.work_area.indexOf(dialog.explorer_tab.tensors_page)
        assert dialog.explorer_tab.tensor_model.rowCount() == 0
        dialog.work_area.setCurrentIndex(tensor_index)
        deadline = time.monotonic() + 4
        while dialog.explorer_tab.tensor_model.rowCount() != len(tensors) and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.01)

        explorer = dialog.explorer_tab
        assert explorer.tensor_model.rowCount() == len(tensors)
        roots = explorer.tensor_root_summary
        assert [roots.table.item(row, 0).text() for row in range(roots.table.rowCount())] == [
            "lm_head",
            "model",
            "text_encoder",
        ]
        assert roots.table.item(1, 1).text() == "2"
        assert all(
            roots.table.item(row, 0).text() not in {"F16", "F32", "BF16"}
            for row in range(roots.table.rowCount())
        )

        roots.search.setText("text")
        assert [roots.table.isRowHidden(row) for row in range(roots.table.rowCount())] == [
            True,
            True,
            False,
        ]
        explorer.tensor_search.setText("text_encoder")
        assert explorer.tensor_proxy.rowCount() == 1
        explorer.tensor_search.clear()
        explorer.tensor_table.selectRow(0)
        assert "dtype" in explorer.tensor_detail.toPlainText()
        assert "payload is not loaded" in explorer.tensor_model.item(0, 0).toolTip()
    finally:
        dialog.close()


def test_safe_registry_capabilities_never_advertise_payload_loading():
    for filename in ("model.safetensors", "model.gguf", "model.onnx"):
        capabilities = reader_capabilities(filename)
        assert capabilities.metadata_only is True
        assert capabilities.loads_tensor_payloads is False
        assert capabilities.safe_by_default is True

    checkpoint = reader_capabilities("model.pt")
    assert checkpoint.metadata_only is True
    assert checkpoint.loads_tensor_payloads is False
    assert checkpoint.safe_by_default is False
