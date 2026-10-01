"""Regression coverage for compact metadata presentation and lazy headers."""

from __future__ import annotations

import json
import os
from pathlib import Path
import struct
import sys
import time

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication, QLabel

from back.inspection_summary import compact_inspection_summary
from front.advanced_viewer import AdvancedViewerDialog
import front.metadata_ui as metadata_ui
from front.metadata_ui import domain_badge_values, inspection_domain
from front.model_card import ModelCard


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _write_safetensors(path: Path) -> None:
    header = {
        "model.embed_tokens.weight": {
            "dtype": "F16", "shape": [2, 3], "data_offsets": [0, 12]
        },
        "model.layers.0.self_attn.q_proj.weight": {
            "dtype": "F16", "shape": [3, 4], "data_offsets": [12, 36]
        },
        "model.layers.1.self_attn.q_proj.weight": {
            "dtype": "F16", "shape": [4, 5], "data_offsets": [36, 76]
        },
    }
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"header-only-test")


def test_live_header_load_skips_full_data_cache_scan(monkeypatch, tmp_path: Path) -> None:
    model = tmp_path / "live.safetensors"
    _write_safetensors(model)

    def unexpected_cache_scan(*_args, **_kwargs):
        raise AssertionError("live header load must not scan full-data cache")

    monkeypatch.setattr(metadata_ui, "get_cached_model_data", unexpected_cache_scan)

    payload = metadata_ui.load_header_only(str(model))

    assert set(payload["tensor_info"]) == {
        "model.embed_tokens.weight",
        "model.layers.0.self_attn.q_proj.weight",
        "model.layers.1.self_attn.q_proj.weight",
    }


def _labels(widget) -> set[str]:
    return {label.text() for label in widget.findChildren(QLabel)}


def test_domain_tags_preserve_raw_type_and_adapter_labels() -> None:
    _app()
    for domain, model_type, description in (
        ("LLM", "LLM", "language model"),
        ("VLM", "VLM", "vision"),
        ("MLM", "MLM", "other modalities"),
    ):
        card = ModelCard(
            {
                "filename": "vl-adapter.safetensors",
                "filepath": f"{domain}.safetensors",
                "architecture": "Qwen2VLForConditionalGeneration",
                "model_type": model_type,
                "adapter_type": "LoRA",
                "capability_facts": {
                    "domain": domain,
                    "capabilities": [],
                    "evidence": {"domain": ["config.json:domain"]},
                },
            },
            simple_view=True,
        )
        labels = _labels(card)
        assert {domain, model_type, "LoRA"} <= labels
        domain_tags = [label for label in card.findChildren(QLabel) if label.property("metadata_domain")]
        assert [tag.text() for tag in domain_tags] == [domain]
        assert description in domain_tags[0].toolTip().lower()


def test_known_domain_hides_unknown_legacy_type_but_keeps_genuine_unknown() -> None:
    _app()
    known_domain = ModelCard(
        {
            "filename": "language-model.gguf",
            "filepath": "language-model.gguf",
            "architecture": "llama",
            "model_type": "Unknown",
            "components": {"text_encoder": True},
            "capability_facts": {
                "domain": "LLM",
                "capabilities": [],
                "evidence": {"domain": ["header metadata"]},
            },
        },
        simple_view=True,
    )
    assert "LLM" in _labels(known_domain)
    assert "Unknown" not in _labels(known_domain)
    assert "Text Enc" in _labels(known_domain)

    unknown = ModelCard(
        {
            "filename": "unknown.gguf",
            "filepath": "unknown.gguf",
            "architecture": "Unknown",
            "model_type": "Unknown",
        },
        simple_view=True,
    )
    assert "Unknown" in _labels(unknown)


def test_structured_capability_badges_require_nonempty_evidence() -> None:
    _app()
    dialog = AdvancedViewerDialog(
        {
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking", "tools"],
                "evidence": {"thinking": [], "tools": []},
            }
        }
    )
    assert [badge.text() for badge in dialog._capability_badges] == ["Unknown"]
    dialog.close()


def test_weak_evidence_strength_suppresses_a_capability_badge() -> None:
    _app()
    from front.metadata_ui import capability_badge_values

    values = capability_badge_values(
        {
            "capability_facts": {
                "domain": "LLM",
                "capabilities": ["thinking", "tools"],
                "evidence": {
                    "thinking": ["chat_template.jinja:thinking marker (weak)"],
                    "tools": ["config.json:supports_tools"],
                },
                "evidence_strength": {"thinking": "weak", "tools": "strong"},
            }
        }
    )

    assert values == ("Tool Use",)


def test_legacy_language_domain_aliases_display_canonically() -> None:
    assert inspection_domain({"capability_facts": {"domain": "MMLM"}}) == "MLM"
    assert domain_badge_values({}, ("MLLM", "MMLLLM")) == ("VLM", "VLM")


def test_compact_facts_render_counts_and_evidence_backed_badges() -> None:
    _app()
    full = {
        "filepath": "qwen.safetensors",
        "filename": "qwen.safetensors",
        "architecture": "Qwen3ForCausalLM",
        "model_type": "LLM",
        "total_params": 7_000_000_000,
        "total_params_friendly": "7.00B",
        "architecture_facts": {"layer_count": 32, "block_counts": {"text": 32}},
        "capability_facts": {
            "domain": "LLM",
            "capabilities": ["thinking", "tools"],
            "evidence": {"thinking": ["config.json:thinking"], "tools": ["chat_template.jinja:tool marker"]},
        },
    }
    summary = compact_inspection_summary(full)
    dialog = AdvancedViewerDialog(summary)
    assert dialog._summary_values["layer_count"].text() == "32"
    assert dialog._summary_values["block_counts"].text() == "text=32"
    assert [badge.text() for badge in dialog._capability_badges] == ["Tool Use", "Thinking"]
    assert [badge.text() for badge in dialog._domain_badges] == ["LLM"]
    dialog.close()


def test_tensor_tab_loads_header_only_descriptors_from_compact_summary(tmp_path: Path) -> None:
    _app()
    model = tmp_path / "compact.safetensors"
    _write_safetensors(model)
    summary = compact_inspection_summary(
        {
            "filepath": str(model),
            "filename": model.name,
            "format": "SAFETENSORS",
            "architecture": "Transformer (language)",
            "model_type": "LLM",
            "tensor_count": 3,
            "architecture_facts": {"layer_count": 2, "block_counts": {"text": 2}},
            "capability_facts": {"domain": "LLM", "capabilities": [], "evidence": {"domain": ["tensor header:language signature"]}},
        }
    )
    dialog = AdvancedViewerDialog(summary)
    assert dialog.explorer_tab.tensor_model.rowCount() == 0
    dialog.work_area.setCurrentIndex(3)
    deadline = time.monotonic() + 4
    while dialog.explorer_tab.tensor_model.rowCount() != 3 and time.monotonic() < deadline:
        _app().processEvents()
        time.sleep(0.01)
    assert dialog.explorer_tab.tensor_model.rowCount() == 3
    assert dialog.explorer_tab.tensor_model.item(0, 0).text() == "model.embed_tokens.weight"
    assert "payload is not loaded" in dialog.explorer_tab.tensor_model.item(0, 0).toolTip()
    dialog.close()


@pytest.mark.parametrize("suffix", (".safetensors", ".gguf"))
def test_metadata_tab_prefers_full_live_header_over_compact_summary(
    tmp_path: Path, monkeypatch, suffix: str
) -> None:
    _app()
    raw_value = "live-header-value-" + "x" * 1400 + "full-value-tail"
    live_metadata = {
        "header.only": f"raw-{suffix}-key",
        "shared": f"live-{suffix}-value",
        "long": raw_value,
    }
    tokens = [f"token-{index}" for index in range(60)]
    model = tmp_path / f"live{suffix}"
    header_size = None
    if suffix == ".safetensors":
        header = json.dumps(
            {
                "__metadata__": live_metadata,
                "live.tensor": {
                    "dtype": "F16",
                    "shape": [2],
                    "data_offsets": [0, 4],
                },
            }
        ).encode("utf-8")
        header_size = len(header)
        model.write_bytes(struct.pack("<Q", header_size) + header + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ")

        import model_readers

        real_open = open
        payload_reads: list[int] = []

        class TrackedFile:
            def __init__(self, stream):
                self.stream = stream

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return self.stream.__exit__(*args)

            def read(self, size: int = -1):
                offset = self.stream.tell()
                value = self.stream.read(size)
                if offset + len(value) > 8 + header_size:
                    payload_reads.append(offset)
                return value

        def tracked_open(path, *args, **kwargs):
            stream = real_open(path, *args, **kwargs)
            return TrackedFile(stream) if Path(path) == model else stream

        real_path_open = Path.open

        def tracked_path_open(path, *args, **kwargs):
            stream = real_path_open(path, *args, **kwargs)
            return TrackedFile(stream) if path == model else stream

        monkeypatch.setattr(model_readers, "open", tracked_open, raising=False)
        monkeypatch.setattr(Path, "open", tracked_path_open)
    else:
        def gguf_string(value: str) -> bytes:
            encoded = value.encode("utf-8")
            return struct.pack("<Q", len(encoded)) + encoded

        gguf_metadata = live_metadata | {"tokenizer.tokens": tokens}
        header = bytearray(b"GGUF" + struct.pack("<IQQ", 3, 0, len(gguf_metadata)))
        for key, value in gguf_metadata.items():
            header.extend(gguf_string(key))
            if isinstance(value, list):
                header.extend(struct.pack("<I", 9))
                header.extend(struct.pack("<IQ", 8, len(value)))
                for token in value:
                    header.extend(gguf_string(token))
            else:
                header.extend(struct.pack("<I", 8))
                header.extend(gguf_string(value))
        model.write_bytes(header)

    summary = {
        "filepath": str(model),
        "metadata": {
            "header.only": "compact-summary-preview",
            "shared": "compact-summary-value",
            "summary.only": "not raw header data",
        },
        "tensor_info": {"cached.tensor": {"dtype": "F32", "shape": [9]}},
    }
    dialog = AdvancedViewerDialog(summary)
    try:
        metadata_index = dialog.work_area.indexOf(dialog.explorer_tab.metadata_page)
        dialog.work_area.setCurrentIndex(metadata_index)
        deadline = time.monotonic() + 4
        while (
            dialog._inspection.get("header_metadata_complete") is not True
            and time.monotonic() < deadline
        ):
            _app().processEvents()
            time.sleep(0.01)

        assert dialog._inspection["metadata"]["header.only"] == f"raw-{suffix}-key"
        assert dialog._inspection["metadata"]["shared"] == f"live-{suffix}-value"
        assert "summary.only" not in dialog._inspection["metadata"]
        assert list(dialog._inspection["tensor_info"]) == (["live.tensor"] if suffix == ".safetensors" else [])
        assert dialog.work_area.tabText(metadata_index) == "Metadata"
        displayed_keys = {
            dialog.explorer_tab.metadata_table.item(index, 0).text()
            for index in range(dialog.explorer_tab.metadata_table.rowCount())
        }
        assert {"header.only", "shared", "long"} <= displayed_keys
        if suffix == ".safetensors":
            assert payload_reads == []

        row = next(
            index
            for index in range(dialog.explorer_tab.metadata_table.rowCount())
            if dialog.explorer_tab.metadata_table.item(index, 0).text() == "long"
        )
        assert "full-value-tail" not in dialog.explorer_tab.metadata_table.item(row, 1).text()
        dialog.explorer_tab.metadata_table.selectRow(row)
        assert "full-value-tail" in dialog.explorer_tab.metadata_detail.toPlainText()
        if suffix == ".safetensors":
            assert payload_reads == []
        else:
            token_row = next(
                index
                for index in range(dialog.explorer_tab.metadata_table.rowCount())
                if dialog.explorer_tab.metadata_table.item(index, 0).text() == "tokenizer.tokens"
            )
            assert "token-59" not in dialog.explorer_tab.metadata_table.item(token_row, 1).text()
            dialog.explorer_tab.metadata_table.selectRow(token_row)
            assert "token-59" in dialog.explorer_tab.metadata_detail.toPlainText()
    finally:
        dialog.close()


def test_missing_model_cached_metadata_is_labeled_incomplete(tmp_path: Path, monkeypatch) -> None:
    _app()
    missing = tmp_path / "missing.safetensors"
    cached = {
        "metadata": {"cached.only": "cached summary"},
        "tensor_info": {"cached.tensor": {"dtype": "F16", "shape": [1]}},
    }
    monkeypatch.setattr(metadata_ui, "get_cached_model_data", lambda *_args, **_kwargs: cached)

    def unexpected_live_read(*_args, **_kwargs):
        raise AssertionError("a missing model must not be read")

    monkeypatch.setattr(metadata_ui, "read_model_header", unexpected_live_read)
    payload = metadata_ui.load_header_only(str(missing))
    assert payload["metadata"] == cached["metadata"]
    assert payload["header_metadata_complete"] is False

    dialog = AdvancedViewerDialog(
        {"filepath": str(missing), "metadata": cached["metadata"], "tensor_info": cached["tensor_info"]}
    )
    try:
        metadata_index = dialog.work_area.indexOf(dialog.explorer_tab.metadata_page)
        assert "Incomplete data" in dialog.work_area.tabText(metadata_index)
        dialog.work_area.setCurrentIndex(metadata_index)
        deadline = time.monotonic() + 4
        while (
            dialog._inspection.get("header_metadata_path") != str(missing)
            and time.monotonic() < deadline
        ):
            _app().processEvents()
            time.sleep(0.01)
        assert dialog._inspection["header_metadata_complete"] is False
        assert "Incomplete data" in dialog.work_area.tabText(metadata_index)
        assert "cached inspection metadata only" in dialog.explorer_tab.metadata_table.toolTip()
    finally:
        dialog.close()
