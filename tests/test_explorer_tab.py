# pyright: reportOptionalMemberAccess=false
"""Headless checks for the reusable Explorer widget and its data contract."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from front.explorer_tab import ExplorerTab, normalize_tensor_descriptors
from front.window_core import _model_file_filter


@pytest.fixture(scope="session")
def app():
    return QApplication.instance() or QApplication([])


def test_normalization_accepts_reader_mapping_and_common_aliases():
    rows = normalize_tensor_descriptors(
        {
            "tensor_info": {
                "vae.decoder.weight": {"shape": [2, 3], "dtype": "F16"},
                "lora_up.weight": {"dims": "(4, 5)", "data_type": "F32", "numel": 20},
            }
        }
    )

    assert [row["name"] for row in rows] == ["vae.decoder.weight", "lora_up.weight"]
    assert rows[0]["shape"] == (2, 3)
    assert rows[0]["parameter_count"] == 6
    assert rows[0]["component_bucket"] == "vae"
    assert rows[1]["dtype"] == "F32"
    assert rows[1]["component_bucket"] == "lora"
    assert rows[0]["shard_id"] == 0


def test_explorer_displays_bounded_metadata_tensors_and_candidates(app):
    widget = ExplorerTab()
    widget.set_inspection(
        {
            "metadata": {
                "tokenizer.chat_template": "{{ messages }}" + "x" * 2000,
                "nested": {"author": "Model Inspector"},
            },
            "extra": {"training_rank": 16},
            "components": {"vae": True, "lora": True},
            "tensor_count": 2,
        },
        {
            "vae.decoder.weight": {"shape": [2, 3], "dtype": "F16"},
            "lora_up.weight": {"shape": [4, 5], "dtype": "F32"},
        },
    )

    assert widget.tensor_model.rowCount() == 2
    assert widget.tensor_model.headerData(0, Qt.Orientation.Horizontal) == "Name"
    assert widget.tensor_model.item(0, 1).text() == "[2, 3]"
    assert widget.tensor_model.item(0, 6).text() == "6"
    assert widget.metadata_table.rowCount() >= 3
    assert all(len(widget.metadata_table.item(row, 1).text()) < 1300 for row in range(widget.metadata_table.rowCount()))
    assert widget.embedded_table.rowCount() >= 3
    assert "payloads are not loaded" in widget.status_label.text()


def test_tensor_search_bucket_filter_and_detail_preview(app):
    widget = ExplorerTab()
    widget.set_tensor_data(
        {
            "unet.block.weight": {"shape": [1, 2], "dtype": "F32"},
            "text_encoder.emb.weight": {"shape": [3, 4], "dtype": "F16"},
        }
    )

    widget.tensor_search.setText("text_encoder")
    assert widget.tensor_proxy.rowCount() == 1
    widget.tensor_search.clear()
    widget.tensor_bucket_filter.setCurrentText("unet")
    assert widget.tensor_proxy.rowCount() == 1
    widget.tensor_table.selectRow(0)
    assert "unet.block.weight" in widget.tensor_detail.toPlainText()


def test_candidate_requests_are_signals_and_mark_header_only(app):
    widget = ExplorerTab()
    emitted = []
    widget.extraction_requested.connect(emitted.append)
    widget.set_inspection(
        {"components": {"vae": True}},
        {"vae.weight": {"shape": [2], "dtype": "F16"}},
    )

    widget.extract_button.click()

    assert emitted
    assert emitted[0]["read_only"] is True
    assert emitted[0]["payload_available"] is False
    assert emitted[0]["candidate"]["kind"] == "VAE"


def test_tensor_order_shards_and_sizes_are_visible_with_safe_fallbacks(app):
    widget = ExplorerTab()
    widget.set_inspection(
        {
            "original_tensor_order": ["second", "first", "single"],
            "sorted_tensor_order": ["first", "second", "single"],
            "tensor_info": {
                "first": {"shape": [2, 4], "dtype": "F16", "shard_id": 2, "original_index": 1, "n_bytes": 16},
                "second": {"shape": [4], "dtype": "F32", "shard_id": 1, "original_index": 0, "data_offsets": [8, 24]},
                "single": {"shape": [1], "dtype": "F16", "shard_id": 0, "original_index": 2},
            },
        }
    )

    assert [widget.tensor_model.item(row, 0).text() for row in range(3)] == ["first", "second", "single"]
    assert widget.tensor_model.item(0, 5).text() == "16 B"
    assert "Raw bytes: 16 bytes; display: 16 B" in widget.tensor_model.item(0, 5).toolTip()
    assert widget.tensor_model.item(2, 4).text() == "Single file (0)"
    assert widget.tensor_model.item(2, 4).data(Qt.ItemDataRole.UserRole + 1) == 0

    widget.tensor_order_combo.setCurrentIndex(1)
    assert not widget.tensor_table.isSortingEnabled()
    assert [widget.tensor_model.item(row, 0).text() for row in range(3)] == ["single", "second", "first"]
    assert widget.tensor_model.item(1, 5).text() == "16 B"
    assert widget.tensor_model.item(1, 0).background().color().isValid()


def test_model_file_dialog_filter_includes_onnx_and_explicit_checkpoint_warning_group():
    file_filter = _model_file_filter()
    assert "*.onnx" in file_filter
    assert "*.safetensors.index.json" in file_filter
    assert "metadata-only after safety confirmation" in file_filter
