import json
from pathlib import Path
import struct
import sys
import zipfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back import checkpoint_reader
from back.checkpoint_reader import UnsafeCheckpointError
from back.reader_registry import ReaderCapabilities, get_reader_registry
from model_readers import read_model_header


def test_registry_exposes_lazy_safe_capabilities():
    registry = get_reader_registry()
    names = {item.name for item in registry.capabilities()}
    assert {"safetensors", "gguf", "onnx", "checkpoint"} <= names
    checkpoint = registry.capabilities("sample.pt")
    assert isinstance(checkpoint, ReaderCapabilities)
    assert not checkpoint.safe_by_default
    assert not checkpoint.loads_tensor_payloads


def test_checkpoint_default_rejects_without_pickle_or_torch(tmp_path):
    path = tmp_path / "model.pt"
    path.write_bytes(b"\x80\x04not a payload")

    try:
        read_model_header(str(path))
    except UnsafeCheckpointError as exc:
        assert "checkpoint_safety='metadata'" in str(exc)
    else:
        raise AssertionError("checkpoint default must reject")


def test_checkpoint_metadata_mode_reads_only_safe_zip_entries(tmp_path):
    path = tmp_path / "model.pt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("version", "1")
        archive.writestr("metadata.json", json.dumps({"architecture": "safe"}))
        archive.writestr("data.pkl", b"this is never opened")

    metadata, tensor_info, file_size = read_model_header(
        str(path), options={"checkpoint_safety": "metadata"}
    )

    assert metadata["checkpoint.version"] == "1"
    assert metadata["checkpoint.metadata"] == {"architecture": "safe"}
    assert metadata["checkpoint.tensor_payloads_read"] is False
    assert tensor_info == {}
    assert file_size == path.stat().st_size


def test_checkpoint_zip_scan_bounds_entries_and_total_metadata_bytes(monkeypatch, tmp_path):
    path = tmp_path / "adversarial.pt"
    with zipfile.ZipFile(path, "w") as archive:
        for index in range(checkpoint_reader.MAX_ARCHIVE_ENTRIES):
            archive.writestr(f"data/{index}", b"x")
        archive.writestr("metadata.json", '{"after": "entry limit"}')
    metadata, _, _ = read_model_header(str(path), checkpoint_safety="metadata")
    assert len(metadata["checkpoint.entries"]) == checkpoint_reader.MAX_ARCHIVE_ENTRIES
    assert metadata["checkpoint.entries_truncated"] is True
    assert "checkpoint.metadata" not in metadata

    monkeypatch.setattr(checkpoint_reader, "MAX_METADATA_BYTES", 16)
    monkeypatch.setattr(checkpoint_reader, "MAX_SAFE_JSON_BYTES", 16)
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("metadata.json", '{"small": 1}')
        archive.writestr("config.json", '{"also_small": 2}')
    metadata, _, _ = read_model_header(str(path), checkpoint_safety="metadata")
    assert metadata["checkpoint.metadata_bytes_examined"] <= 16
    assert "checkpoint.config" not in metadata


def test_checkpoint_rejects_oversized_directory_before_constructing_zipfile(monkeypatch, tmp_path):
    path = tmp_path / "forged-count.pt"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("metadata.json", '{"safe": true}')
    raw = bytearray(path.read_bytes())
    end_record = raw.rfind(b"PK\x05\x06")
    struct.pack_into("<HH", raw, end_record + 8, 0, 0)
    path.write_bytes(raw)

    monkeypatch.setattr(checkpoint_reader, "MAX_ARCHIVE_DIRECTORY_BYTES", 1)
    monkeypatch.setattr(
        checkpoint_reader.zipfile,
        "ZipFile",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("ZipFile constructed")),
    )
    metadata, _, _ = read_model_header(str(path), checkpoint_safety="metadata")

    assert "central directory exceeds" in metadata["checkpoint.archive_error"]


def test_checkpoint_zip64_directory_preflight_when_supported(tmp_path):
    if not hasattr(zipfile, "_EndRecData"):
        return
    path = tmp_path / "empty-zip64.pt"
    zip64_end = struct.pack(
        "<4sQ2H2L4Q", b"PK\x06\x06", 44, 45, 45, 0, 0, 0, 0, 0, 0
    )
    locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1)
    end = struct.pack(
        "<4s4H2LH", b"PK\x05\x06", 0, 0, 0xFFFF, 0xFFFF, 0xFFFFFFFF, 0xFFFFFFFF, 0
    )
    path.write_bytes(zip64_end + locator + end)

    metadata, tensors, _ = read_model_header(str(path), checkpoint_safety="metadata")

    assert metadata["checkpoint.entry_count"] == 0
    assert tensors == {}
