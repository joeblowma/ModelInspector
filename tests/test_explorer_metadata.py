"""Read-only embedded-metadata and raw-source regression checks."""

import struct

from PyQt6.QtWidgets import QApplication, QTextEdit

from front.explorer_data import detect_embedded_content
from front import explorer_metadata
from front.explorer_metadata import perform_metadata_action, raw_metadata_bytes, raw_metadata_status, readable_metadata


def test_embedded_metadata_includes_tokenizer_sections_and_exact_raw_values(tmp_path):
    metadata_bytes = (
        b'{"tokenizer.chat_template":"{{ user }}\\n{{ assistant }}",'
        b'"tokenizer":{"token_types":["bos"],"merges":["a b"]},'
        b'"tags":["example"]}'
    )
    header = b'{"__metadata__":' + metadata_bytes + b',"weight":{"dtype":"F16","shape":[1],"data_offsets":[0,2]}}'
    source = tmp_path / "metadata.safetensors"
    source.write_bytes(struct.pack("<Q", len(header)) + header + b"\0\0")
    inspection = {
        "filepath": str(source),
        "metadata": {
            "tokenizer.chat_template": "{{ user }}\n{{ assistant }}",
            "tokenizer": {"token_types": ["bos"], "merges": ["a b"]},
            "tags": ["example"],
        },
        "components": {"vae": True},
    }

    candidates = detect_embedded_content(inspection, [{"component_bucket": "vae"}])
    by_name = {candidate["name"]: candidate for candidate in candidates}

    assert set(by_name) == {"tokenizer.chat_template", "tokenizer.token_types", "tokenizer.merges", "tags"}
    assert "\n" in readable_metadata(by_name["tokenizer.chat_template"])
    assert raw_metadata_bytes(inspection, by_name["tokenizer.chat_template"]) == b'"{{ user }}\\n{{ assistant }}"'
    assert raw_metadata_bytes(inspection, by_name["tokenizer.merges"]) == b'["a b"]'
    available, message = raw_metadata_status({"filepath": str(tmp_path / "missing.safetensors")}, by_name["tags"])
    assert not available
    assert message.startswith("Raw original bytes unavailable:")


def test_gguf_embedded_metadata_extracts_header_bytes_without_tensor_reads(tmp_path):
    template = "{{ user }}\n{{ '\\n' }}"
    template_bytes = template.encode("utf-8")
    key = b"tokenizer.chat_template"
    raw_value = struct.pack("<Q", len(template_bytes)) + template_bytes
    source = tmp_path / "metadata.gguf"
    source.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + raw_value
    )
    inspection = {"filepath": str(source), "metadata": {key.decode(): template}}
    candidate = detect_embedded_content(inspection)[0]

    assert readable_metadata(candidate) == template
    assert raw_metadata_bytes(inspection, candidate) == raw_value


def test_inspect_opens_readable_popup_without_transforming_template_text(monkeypatch):
    QApplication.instance() or QApplication([])
    template = "{{ user }}\n{{ '\\n' }}"
    displayed: list[str] = []

    def capture(dialog):
        detail = dialog.findChild(QTextEdit)
        assert detail is not None
        displayed.append(detail.toPlainText())
        return 0

    monkeypatch.setattr(explorer_metadata.QDialog, "exec", capture)
    assert perform_metadata_action(None, {}, {"name": "tokenizer.chat_template", "value": template}, "inspect") == ""
    assert displayed == [template]
