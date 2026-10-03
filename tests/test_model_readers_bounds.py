import json
import struct

import pytest

import back.gguf_reader as gguf_reader
import model_readers


def _gguf_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _gguf_header(tensor_count: int = 0, kv_count: int = 0, body: bytes = b"") -> bytes:
    return b"GGUF" + struct.pack("<IQQ", 3, tensor_count, kv_count) + body


def _reject_library_fallback(monkeypatch):
    monkeypatch.setattr(
        model_readers,
        "_read_gguf_header_with_library",
        lambda _path: pytest.fail("unsafe header reached library fallback"),
    )


@pytest.mark.parametrize("count_kind", ("tensor", "metadata"))
def test_gguf_hostile_counts_fail_before_fallback(tmp_path, monkeypatch, count_kind):
    _reject_library_fallback(monkeypatch)
    if count_kind == "tensor":
        raw = _gguf_header(tensor_count=gguf_reader.MAX_GGUF_TENSORS + 1)
    else:
        raw = _gguf_header(kv_count=gguf_reader.MAX_GGUF_METADATA_ENTRIES + 1)
    path = tmp_path / "hostile-count.gguf"
    path.write_bytes(raw)

    with pytest.raises(gguf_reader.GGUFHeaderError):
        model_readers.read_gguf_header(str(path))


def test_gguf_hostile_string_length_fails_before_fallback(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    raw = _gguf_header(
        kv_count=1,
        body=struct.pack("<Q", gguf_reader.MAX_GGUF_STRING_BYTES + 1) + b"\0" * 13,
    )
    path = tmp_path / "hostile-string.gguf"
    path.write_bytes(raw)

    with pytest.raises(gguf_reader.GGUFHeaderError, match="string exceeds"):
        model_readers.read_gguf_header(str(path))


def test_gguf_aggregate_header_budget_is_checked_before_read(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    monkeypatch.setattr(gguf_reader, "MAX_GGUF_HEADER_BYTES", 37)
    body = _gguf_string("k") + struct.pack("<I", 0) + b"\x01"
    path = tmp_path / "header-budget.gguf"
    path.write_bytes(_gguf_header(kv_count=1, body=body))

    with pytest.raises(gguf_reader.GGUFHeaderError, match="byte limit"):
        model_readers.read_gguf_header(str(path))


def test_gguf_numeric_array_over_limit_is_rejected_before_seek(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    array = struct.pack(
        "<IQ", 4, gguf_reader.MAX_GGUF_ARRAY_ITEMS + 1
    )
    body = _gguf_string("values") + struct.pack("<I", 9) + array
    path = tmp_path / "hostile-array.gguf"
    path.write_bytes(_gguf_header(kv_count=1, body=body))

    with pytest.raises(gguf_reader.GGUFHeaderError, match="array exceeds"):
        model_readers.read_gguf_header(str(path))


def test_gguf_tensor_dimension_count_is_bounded(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    body = _gguf_string("tensor") + struct.pack(
        "<I", gguf_reader.MAX_GGUF_DIMS + 1
    ) + b"\0" * 12
    path = tmp_path / "hostile-dims.gguf"
    path.write_bytes(_gguf_header(tensor_count=1, body=body))

    with pytest.raises(gguf_reader.GGUFHeaderError, match="rank exceeds"):
        model_readers.read_gguf_header(str(path))


def test_truncated_gguf_never_reaches_library_fallback(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    path = tmp_path / "truncated.gguf"
    path.write_bytes(_gguf_header(kv_count=1))

    with pytest.raises(gguf_reader.GGUFHeaderError):
        model_readers.read_gguf_header(str(path))


@pytest.mark.parametrize("error_type", (OSError, RuntimeError))
def test_native_gguf_parser_errors_never_reach_library_fallback(
    monkeypatch, error_type
):
    _reject_library_fallback(monkeypatch)

    def raise_parser_error(_path):
        raise error_type("native parser failed")

    monkeypatch.setattr(model_readers, "_read_gguf_header_fast", raise_parser_error)

    with pytest.raises(error_type, match="native parser failed"):
        model_readers.read_gguf_header("model.gguf")


def test_unsupported_gguf_version_raises_without_library_fallback(tmp_path, monkeypatch):
    _reject_library_fallback(monkeypatch)
    path = tmp_path / "unsupported-version.gguf"
    path.write_bytes(b"GGUF" + struct.pack("<IQQ", 4, 0, 0))

    with pytest.raises(gguf_reader.GGUFHeaderError, match="Unsupported GGUF version"):
        model_readers.read_gguf_header(str(path))


def test_valid_gguf_reads_header_only_and_keeps_array_preview(tmp_path, monkeypatch):
    body = _gguf_string("numbers") + struct.pack("<I", 9)
    body += struct.pack("<IQ", 4, 51) + struct.pack("<I", 4) * 51
    body += _gguf_string("tensor") + struct.pack("<I", 1)
    body += struct.pack("<QIQ", 32, 142, 0)
    header = _gguf_header(tensor_count=1, kv_count=1, body=body)
    path = tmp_path / "valid.gguf"
    path.write_bytes(header + b"\0" * (-len(header) % 32) + b"payload bytes")

    real_open = open
    read_ranges = []

    class TrackingFile:
        def __init__(self, file_path, mode):
            self.file = real_open(file_path, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.file.__exit__(*args)

        def read(self, size=-1):
            start = self.file.tell()
            data = self.file.read(size)
            read_ranges.append((start, start + len(data)))
            return data

        def __getattr__(self, name):
            return getattr(self.file, name)

    monkeypatch.setattr(
        gguf_reader, "open", lambda file_path, mode: TrackingFile(file_path, mode), raising=False
    )
    metadata, tensors, file_size = model_readers.read_gguf_header(str(path))

    assert metadata["numbers"] == {"count": 51, "preview": [4] * 50, "truncated": True}
    assert tensors["tensor"]["dtype"] == "PTQ2_0"
    assert tensors["tensor"]["shape"] == [32]
    assert file_size == path.stat().st_size
    assert read_ranges and max(end for _, end in read_ranges) == len(header)


def test_valid_safetensors_header_is_read_exactly(tmp_path):
    encoded = json.dumps(
        {
            "__metadata__": {"owner": "test"},
            "weight": {"dtype": "F16", "shape": [2], "data_offsets": [0, 4]},
        }
    ).encode()
    path = tmp_path / "valid.safetensors"
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded + b"data")

    metadata, tensors, file_size = model_readers.read_safetensors_header(str(path))

    assert metadata["owner"] == "test"
    assert metadata["smi.format"] == "SAFETENSORS"
    assert tensors["weight"]["n_bytes"] == 4
    assert file_size == path.stat().st_size


def test_safetensors_declared_header_past_eof_is_rejected(tmp_path):
    path = tmp_path / "past-eof.safetensors"
    path.write_bytes(struct.pack("<Q", 3) + b"{}")

    with pytest.raises(ValueError, match="past end of file"):
        model_readers.read_safetensors_header(str(path))


def test_safetensors_short_header_read_is_rejected(tmp_path, monkeypatch):
    path = tmp_path / "short-read.safetensors"
    path.write_bytes(struct.pack("<Q", 2) + b"{}")

    class ShortReader:
        def __init__(self):
            self.calls = 0

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def read(self, size):
            self.calls += 1
            return struct.pack("<Q", 2) if self.calls == 1 else b"{"

    monkeypatch.setattr(model_readers, "open", lambda *_args, **_kwargs: ShortReader(), raising=False)

    with pytest.raises(ValueError, match="Unexpected end of safetensors header"):
        model_readers.read_safetensors_header(str(path))
