# pyright: reportOptionalMemberAccess=false
"""Headless checks for the reusable Explorer widget and its data contract."""

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest

pytest.importorskip("PyQt6")

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication

from front.explorer_tab import ExplorerTab, normalize_tensor_descriptors


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
    assert widget.tensor_model.item(0, 4).text() == "6"
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
