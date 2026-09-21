# pyright: reportOptionalMemberAccess=false
"""Headless checks for the reusable Explorer widget and its data contract."""

import os
import json
import struct

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QAbstractItemView, QApplication

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
    assert widget.embedded_table.rowCount() == 1
    assert "payloads are not loaded" in widget.status_label.text()


def test_metadata_detail_recovers_full_long_and_deep_header_values(app, tmp_path):
    long_value = "header-start-" + "x" * 1400 + "-long-tail-marker"
    metadata = {
        "tokenizer.chat_template": long_value,
        "structured": {"level1": {"level2": {"level3": {"deep-tail-marker": True}}}},
    }
    header = json.dumps(
        {"__metadata__": metadata, "weight": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]}}
    ).encode()
    source = tmp_path / "full-metadata.safetensors"
    source.write_bytes(struct.pack("<Q", len(header)) + header + b"\0\0TENSOR_PAYLOAD_MUST_NOT_BE_READ")

    widget = ExplorerTab()
    widget.set_inspection({"filepath": str(source), "metadata": metadata})
    assert widget.metadata_table.rowCount() == 2
    assert all("long-tail-marker" not in widget.metadata_table.item(row, 1).text() for row in range(widget.metadata_table.rowCount()))

    long_row = next(row for row in range(widget.metadata_table.rowCount()) if widget.metadata_table.item(row, 0).text() == "tokenizer.chat_template")
    widget.metadata_table.selectRow(long_row)
    assert "long-tail-marker" in widget.metadata_detail.toPlainText()

    deep_row = next(row for row in range(widget.metadata_table.rowCount()) if widget.metadata_table.item(row, 0).text().startswith("structured."))
    widget.metadata_table.selectRow(deep_row)
    assert "deep-tail-marker" in widget.metadata_detail.toPlainText()


def test_metadata_detail_does_not_recover_full_gguf_array_preview_tail(app, tmp_path):
    values = [f"token-{index}" for index in range(60)]
    key = b"tokenizer.tokens"
    encoded = struct.pack("<IQ", 8, len(values)) + b"".join(
        struct.pack("<Q", len(value.encode())) + value.encode() for value in values
    )
    source = tmp_path / "full-array.gguf"
    source.write_bytes(
        b"GGUF" + struct.pack("<IQQ", 3, 1, 1) + struct.pack("<Q", len(key)) + key
        + struct.pack("<I", 9) + encoded + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ"
    )

    widget = ExplorerTab()
    widget.set_inspection({
        "filepath": str(source),
        "metadata": {"tokenizer.tokens": {"count": len(values), "preview": values[:50], "truncated": True}},
    })
    row = next(row for row in range(widget.metadata_table.rowCount()) if widget.metadata_table.item(row, 0).text() == "tokenizer.tokens")
    widget.metadata_table.selectRow(row)
    detail = widget.metadata_detail.toPlainText()
    assert "token-49" in detail
    assert "token-59" not in detail
    assert detail.endswith("\n\n---- output trimmed - extract for full data ----")


def test_metadata_detail_uses_only_stored_preview_and_marks_trimmed_output(app):
    values = [f"token-{index}" for index in range(60)]
    widget = ExplorerTab()
    widget.set_inspection(
        {"metadata": {"tokenizer.tokens": {"count": 60, "preview": values[:50], "truncated": True}}}
    )
    row = next(
        row
        for row in range(widget.metadata_table.rowCount())
        if widget.metadata_table.item(row, 0).text() == "tokenizer.tokens"
    )

    widget.metadata_table.selectRow(row)

    assert "token-49" in widget.metadata_detail.toPlainText()
    assert "token-59" not in widget.metadata_detail.toPlainText()
    assert widget.metadata_detail.toPlainText().endswith(
        "\n\n---- output trimmed - extract for full data ----"
    )


def test_metadata_and_embedded_selection_use_sorted_row_payloads(app):
    widget = ExplorerTab()
    widget.set_inspection(
        {"metadata": {"z": "Z", "a": "A", "m": "M", "tokenizer": {"z": "Z", "a": "A"}}}
    )
    widget.metadata_table.sortItems(0, Qt.SortOrder.AscendingOrder)
    a_row = next(row for row in range(widget.metadata_table.rowCount()) if widget.metadata_table.item(row, 0).text() == "a")
    widget.metadata_table.selectRow(a_row)
    assert widget.metadata_detail.toPlainText() == "A"

    widget.metadata_search.setText("m")
    m_row = next(row for row in range(widget.metadata_table.rowCount()) if not widget.metadata_table.isRowHidden(row))
    widget.metadata_table.selectRow(m_row)
    assert widget.metadata_detail.toPlainText() == "M"

    widget.metadata_search.clear()
    widget.embedded_table.setSortingEnabled(True)
    widget.embedded_table.sortItems(1, Qt.SortOrder.AscendingOrder)
    embedded_a = next(row for row in range(widget.embedded_table.rowCount()) if widget.embedded_table.item(row, 1).text() == "tokenizer.a")
    widget.embedded_table.selectRow(embedded_a)
    assert "A" in widget.embedded_detail.toPlainText()

    widget.set_inspection({"metadata": {"z": "Z2", "a": "A2", "m": "M2"}})
    a_row = next(row for row in range(widget.metadata_table.rowCount()) if widget.metadata_table.item(row, 0).text() == "a")
    widget.metadata_table.selectRow(a_row)
    assert widget.metadata_detail.toPlainText() == "A2"


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
        {"metadata": {"tokenizer.chat_template": "{{ messages }}"}},
        {"vae.weight": {"shape": [2], "dtype": "F16"}},
    )

    widget._emit_candidate(widget.extraction_requested, "extract")

    assert emitted
    assert emitted[0]["read_only"] is True
    assert emitted[0]["payload_available"] is False
    assert emitted[0]["candidate"]["kind"] == "Embedded metadata"


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
    assert widget.tensor_model.item(2, 4).text() == "None"
    assert widget.tensor_model.item(2, 4).data(Qt.ItemDataRole.UserRole + 1) == 0

    widget.tensor_order_combo.setCurrentIndex(1)
    assert not widget.tensor_table.isSortingEnabled()
    assert [widget.tensor_model.item(row, 0).text() for row in range(3)] == ["first", "second", "single"]
    assert widget.tensor_model.item(1, 5).text() == "16 B"
    assert widget.tensor_model.item(1, 0).background().color().isValid()


def test_tensor_sorting_is_natural_and_original_order_keeps_discovery_shards(app):
    widget = ExplorerTab()
    widget.set_tensor_data(
        {
            "model.layers.10.weight": {"shape": [1], "dtype": "F16"},
            "model.layers.9.weight": {"shape": [1], "dtype": "F16"},
        }
    )
    assert [widget.tensor_proxy.index(row, 0).data() for row in range(2)] == [
        "model.layers.9.weight",
        "model.layers.10.weight",
    ]

    widget.set_tensor_data(
        {
            "two.second": {"shape": [1], "dtype": "F16", "shard_id": 2, "original_index": 1},
            "two.first": {"shape": [1], "dtype": "F16", "shard_id": 2, "original_index": 0},
            "one.first": {"shape": [1], "dtype": "F16", "shard_id": 1, "original_index": 0},
        }
    )
    widget.tensor_order_combo.setCurrentIndex(1)
    assert [widget.tensor_model.item(row, 0).text() for row in range(3)] == [
        "two.first",
        "two.second",
        "one.first",
    ]


def test_bucket_ids_remain_canonical_and_metadata_scrolls_per_pixel(app):
    rows = normalize_tensor_descriptors(
        {
            "vae.decoder": {},
            "lora_up.weight": {},
            "mtp.block": {},
            "text_model.layer": {},
            "blk.0.weight": {},
        }
    )
    assert [row["component_bucket"] for row in rows] == ["vae", "lora", "draft", "text", "weights"]

    widget = ExplorerTab()
    assert widget.metadata_table.horizontalScrollMode() == QAbstractItemView.ScrollMode.ScrollPerPixel


def test_model_file_dialog_filter_includes_onnx_and_explicit_checkpoint_warning_group():
    file_filter = _model_file_filter()
    assert "*.onnx" in file_filter
    assert "*.safetensors.index.json" in file_filter
    assert "Checkpoint Files - metadata-only inspection" in file_filter
