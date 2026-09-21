"""Read-only embedded-metadata and raw-source regression checks."""

import json
import struct

import pytest
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
    assert raw_metadata_bytes(inspection, candidate) == template_bytes
    available, message = raw_metadata_status(inspection, candidate)
    assert available
    assert message == "Extract exact GGUF metadata value bytes; tensor payloads are never read."


def test_metadata_actions_stop_at_gguf_metadata_boundary(monkeypatch, tmp_path):
    template = "{{ user }}"
    template_bytes = template.encode("utf-8")
    key = b"tokenizer.chat_template"
    raw_value = struct.pack("<Q", len(template_bytes)) + template_bytes
    header = (
        b"GGUF"
        + struct.pack("<IQQ", 3, 1, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 8)
        + raw_value
    )
    source = tmp_path / "bounded.gguf"
    source.write_bytes(header + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ")
    inspection = {"filepath": str(source), "metadata": {key.decode(): template}}
    candidate = detect_embedded_content(inspection)[0]
    saved: list[bytes] = []
    monkeypatch.setattr(explorer_metadata, "_save", lambda *args: saved.append(args[3]) or "saved")

    real_open = explorer_metadata.Path.open

    class HeaderBoundedFile:
        def __init__(self, wrapped):
            self._wrapped = wrapped

        def read(self, size=-1):
            position = self._wrapped.tell()
            if size < 0 or position + size > len(header):
                raise AssertionError("metadata action read into tensor payload")
            return self._wrapped.read(size)

        def seek(self, offset, whence=0):
            position = self._wrapped.seek(offset, whence)
            if position > len(header):
                raise AssertionError("metadata action sought into tensor payload")
            return position

        def tell(self):
            return self._wrapped.tell()

        def __enter__(self):
            return self

        def __exit__(self, *args):
            self._wrapped.close()

        def __getattr__(self, name):
            return getattr(self._wrapped, name)

    def guarded_open(path, *args, **kwargs):
        opened = real_open(path, *args, **kwargs)
        return HeaderBoundedFile(opened) if path == source else opened

    monkeypatch.setattr(explorer_metadata.Path, "open", guarded_open)

    assert perform_metadata_action(None, inspection, candidate, "save") == "saved"
    assert perform_metadata_action(None, inspection, candidate, "extract") == "saved"
    assert saved == [template_bytes, template_bytes]


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


def test_inspect_labels_cached_preview_when_source_is_unavailable(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    inspection = {
        "filepath": str(tmp_path / "missing.safetensors"),
        "metadata": {"tokenizer.chat_template": "cached preview"},
    }
    candidate = detect_embedded_content(inspection)[0]
    titles: list[str] = []
    monkeypatch.setattr(explorer_metadata.QDialog, "exec", lambda dialog: titles.append(dialog.windowTitle()) or 0)

    assert perform_metadata_action(None, inspection, candidate, "inspect") == ""
    assert titles == ["tokenizer.chat_template"]


def test_actions_reload_full_safetensors_metadata_instead_of_reader_preview(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    values = [f"token-{index}" for index in range(60)]
    metadata = {"tokenizer": {"tokens": values}}
    header = json.dumps({"__metadata__": metadata, "weight": {"dtype": "F16", "shape": [1], "data_offsets": [0, 2]}}).encode()
    source = tmp_path / "preview.safetensors"
    source.write_bytes(struct.pack("<Q", len(header)) + header + b"\0\0")
    preview = {"count": len(values), "preview": values[:50], "truncated": True}
    inspection = {"filepath": str(source), "metadata": {"tokenizer": {"tokens": preview}}}
    candidate = detect_embedded_content(inspection)[0]
    displayed: list[str] = []
    saved: list[bytes] = []

    monkeypatch.setattr(explorer_metadata.QDialog, "exec", lambda dialog: displayed.append(dialog.findChild(QTextEdit).toPlainText()))
    monkeypatch.setattr(explorer_metadata, "_save", lambda *args: saved.append(args[3]) or "saved")

    assert perform_metadata_action(None, inspection, candidate, "inspect") == ""
    assert perform_metadata_action(None, inspection, candidate, "save") == "saved"
    assert "token-49" in displayed[0]
    assert "token-59" not in displayed[0]
    assert displayed[0].endswith(explorer_metadata.TRIMMED_OUTPUT_MARKER)
    assert b"token-59" in saved[0] and b'"preview"' not in saved[0]


def test_actions_decode_full_gguf_array_metadata_instead_of_preview(monkeypatch, tmp_path):
    QApplication.instance() or QApplication([])
    values = [f"token-{index}" for index in range(60)]
    key = b"tokenizer.tokens"
    encoded = struct.pack("<IQ", 8, len(values)) + b"".join(
        struct.pack("<Q", len(value.encode())) + value.encode() for value in values
    )
    source = tmp_path / "preview.gguf"
    source.write_bytes(
        b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<Q", len(key)) + key
        + struct.pack("<I", 9) + encoded
    )
    preview = {"count": len(values), "preview": values[:50], "truncated": True}
    inspection = {"filepath": str(source), "metadata": {"tokenizer.tokens": preview}}
    candidate = detect_embedded_content(inspection)[0]
    saved: list[bytes] = []
    monkeypatch.setattr(explorer_metadata, "_save", lambda *args: saved.append(args[3]) or "saved")

    assert perform_metadata_action(None, inspection, candidate, "save") == "saved"
    assert b"token-59" in saved[0] and b'"preview"' not in saved[0]


@pytest.mark.parametrize("suffix", (".safetensors", ".gguf"))
def test_cached_preview_exports_from_requested_live_source(monkeypatch, tmp_path, suffix):
    values = [f"token-{index}" for index in range(60)]
    preview = {"count": len(values), "preview": values[:50], "truncated": True}
    source = tmp_path / f"live{suffix}"
    if suffix == ".safetensors":
        header = json.dumps({"__metadata__": {"tokenizer": {"tokens": values}}}).encode()
        source.write_bytes(struct.pack("<Q", len(header)) + header + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ")
        metadata = {"tokenizer": {"tokens": preview}}
    else:
        key = b"tokenizer.tokens"
        encoded = struct.pack("<IQ", 8, len(values)) + b"".join(
            struct.pack("<Q", len(value)) + value.encode() for value in values
        )
        source.write_bytes(b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<Q", len(key)) + key + struct.pack("<I", 9) + encoded + b"TENSOR_PAYLOAD_MUST_NOT_BE_READ")
        metadata = {key.decode(): preview}
    inspection = {
        "filepath": str(tmp_path / f"stale{suffix}"),
        "resolved_filepath": str(source),
        "requested_filepath": str(source),
        "metadata": metadata,
    }
    candidate = detect_embedded_content(inspection)[0]
    saved: list[bytes] = []
    monkeypatch.setattr(explorer_metadata, "_save", lambda *args: saved.append(args[3]) or "saved")

    assert b"token-59" in raw_metadata_bytes(inspection, candidate)
    assert perform_metadata_action(None, inspection, candidate, "save") == "saved"
    assert b"token-59" in saved[0] and b'"preview"' not in saved[0]


def test_gguf_raw_array_drops_type_count_and_string_length_framing(tmp_path):
    values = [b"alpha", b"{\"role\":\"user\"}"]
    key = b"tokenizer.tokens"
    encoded = struct.pack("<IQ", 8, len(values)) + b"".join(
        struct.pack("<Q", len(value)) + value for value in values
    )
    source = tmp_path / "framed.gguf"
    source.write_bytes(
        b"GGUF" + struct.pack("<IQQ", 3, 0, 1) + struct.pack("<Q", len(key)) + key
        + struct.pack("<I", 9) + encoded
    )
    inspection = {"filepath": str(source), "metadata": {key.decode(): values}}
    candidate = detect_embedded_content(inspection)[0]

    assert raw_metadata_bytes(inspection, candidate) == b"".join(values)


@pytest.mark.parametrize(
    ("name", "value", "suffix"),
    (
        ("tokenizer.chat_template", "{{ messages }}", ".jinja"),
        ("metadata", '{"role":"user"}', ".json"),
        ("metadata", "<root><item /></root>", ".xml"),
        ("metadata", "plain text", ".txt"),
    ),
)
def test_readable_artifact_suffixes_are_content_aware(name, value, suffix):
    candidate = {"name": name, "value": value}
    assert explorer_metadata._readable_suffix(candidate, readable_metadata(candidate)) == suffix


def test_json_metadata_sidecar_is_opt_in_and_not_duplicated_for_json_main_file(
    monkeypatch, tmp_path
):
    template = "{{ user }}"
    header = json.dumps({"__metadata__": {"tokenizer.chat_template": template}}).encode()
    source = tmp_path / "sidecar.safetensors"
    source.write_bytes(struct.pack("<Q", len(header)) + header)
    inspection = {"filepath": str(source), "metadata": {"tokenizer.chat_template": template}}
    candidate = detect_embedded_content(inspection)[0]
    readable_path = tmp_path / "template.jinja"
    monkeypatch.setattr(
        explorer_metadata.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(readable_path), ""),
    )

    perform_metadata_action(None, inspection, candidate, "save")
    assert not readable_path.with_suffix(".json").exists()

    perform_metadata_action(
        None, inspection, candidate, "save", dump_json_modelinfo=True
    )
    assert readable_path.with_suffix(".json").read_text(encoding="utf-8") == (
        json.dumps(template, ensure_ascii=False, indent=2, default=str) + "\n"
    )

    json_main = tmp_path / "natural.json"
    monkeypatch.setattr(
        explorer_metadata.QFileDialog,
        "getSaveFileName",
        lambda *_args: (str(json_main), ""),
    )
    perform_metadata_action(
        None, inspection, candidate, "save", dump_json_modelinfo=True
    )
    assert not json_main.with_suffix(".json.json").exists()


def test_actions_decode_full_gguf_scalar_metadata(monkeypatch, tmp_path):
    key = b"tokenizer.count"
    source = tmp_path / "scalar.gguf"
    source.write_bytes(
        b"GGUF"
        + struct.pack("<IQQ", 3, 0, 1)
        + struct.pack("<Q", len(key))
        + key
        + struct.pack("<I", 10)
        + struct.pack("<Q", 60)
    )
    inspection = {"filepath": str(source), "metadata": {key.decode(): 0}}
    candidate = detect_embedded_content(inspection)[0]
    saved: list[bytes] = []
    monkeypatch.setattr(explorer_metadata, "_save", lambda *args: saved.append(args[3]) or "saved")

    assert perform_metadata_action(None, inspection, candidate, "save") == "saved"
    assert saved == [b"60"]


def test_save_refuses_truncated_preview_when_source_is_unavailable(monkeypatch, tmp_path):
    preview = {"count": 60, "preview": ["token-0"], "truncated": True}
    inspection = {"filepath": str(tmp_path / "missing.safetensors"), "metadata": {"tokenizer": {"tokens": preview}}}
    candidate = detect_embedded_content(inspection)[0]
    monkeypatch.setattr(explorer_metadata, "_save", lambda *_args: pytest.fail("preview must not be saved"))

    assert perform_metadata_action(None, inspection, candidate, "save") == "Readable metadata source unavailable; nothing was saved."
