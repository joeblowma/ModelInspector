from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from model_readers import read_model_header
from back import onnx_reader


def _varint(value: int) -> bytes:
    output = bytearray()
    while value > 127:
        output.append((value & 127) | 128)
        value >>= 7
    output.append(value)
    return bytes(output)


def _field(number: int, wire: int, value: bytes | int) -> bytes:
    encoded = _varint(value) if wire == 0 else bytes(value)
    if wire == 2:
        return _varint(number << 3 | wire) + _varint(len(encoded)) + encoded
    return _varint(number << 3 | wire) + encoded


def _tensor(name: str, shape: list[int], raw: bytes) -> bytes:
    message = b"".join(_field(1, 0, dim) for dim in shape)
    message += _field(2, 0, 1)  # FLOAT
    message += _field(8, 2, name.encode())
    message += _field(9, 2, raw)
    return message


def _onnx_fixture() -> bytes:
    entry = _field(1, 2, b"author") + _field(2, 2, b"portable-test")
    graph = _field(2, 2, b"main") + _field(5, 2, _tensor("first", [2, 3], b"123456"))
    graph += _field(5, 2, _tensor("second", [1], b"abcd"))
    return _field(1, 0, 9) + _field(2, 2, b"fixture") + _field(5, 0, 7) + _field(7, 2, graph) + _field(14, 2, entry)


def _read_budget_fixture(tmp_path, payload: bytes):
    path = tmp_path / "budget.onnx"
    path.write_bytes(payload)
    return read_model_header(str(path))


def _value_info(name: str, dimensions: list[int]) -> bytes:
    shape = b"".join(
        _field(1, 2, _field(1, 0, dimension)) for dimension in dimensions
    )
    tensor_type = _field(1, 0, 1) + _field(2, 2, shape)
    type_proto = _field(1, 2, tensor_type)
    return _field(1, 2, name.encode()) + _field(2, 2, type_proto)


def test_dependency_free_onnx_metadata_preserves_initializer_order(tmp_path):
    path = tmp_path / "fixture.onnx"
    path.write_bytes(_onnx_fixture())

    metadata, tensors, file_size = read_model_header(str(path))

    assert metadata["smi.format"] == "ONNX"
    assert metadata["author"] == "portable-test"
    assert metadata["onnx.model_version"] == 7
    assert list(tensors) == ["first", "second"]
    assert tensors["first"]["shape"] == [2, 3]
    assert tensors["first"]["n_bytes"] == 6
    assert all(item["shard_id"] == 0 for item in tensors.values())
    assert file_size == path.stat().st_size


def test_normal_large_initializer_header_remains_within_budget(tmp_path):
    graph = b"".join(
        _field(5, 2, _tensor(f"initializer-{index}", [1], b""))
        for index in range(593)
    )

    _, tensors, _ = _read_budget_fixture(tmp_path, _field(7, 2, graph))

    assert len(tensors) == 593


def test_malformed_onnx_lengths_are_rejected(tmp_path):
    for name, payload in {
        "truncated-length.onnx": b"\x3a\x80",  # graph field with truncated varint
        "oversized-length.onnx": b"\x3a\x7f",  # graph length exceeds file
    }.items():
        path = tmp_path / name
        path.write_bytes(payload)
        try:
            read_model_header(str(path))
        except ValueError:
            pass
        else:
            raise AssertionError(f"{name} must be rejected without over-reading")


@pytest.mark.parametrize(
    ("name", "field"),
    (
        ("truncated-fixed64.onnx", b"\x09\x00"),  # fixed64 lacks seven bytes
        ("truncated-fixed32.onnx", b"\x15\x00"),  # fixed32 lacks three bytes
    ),
)
def test_malformed_onnx_fixed_width_field_is_rejected(tmp_path, name, field):
    path = tmp_path / name
    path.write_bytes(field)

    with pytest.raises(ValueError, match="fixed-width"):
        read_model_header(str(path))


@pytest.mark.parametrize(
    "field",
    (
        b"\x09" + b"\x00" * 7,  # fixed64 is one byte short inside the graph.
        b"\x15" + b"\x00" * 3,  # fixed32 is one byte short inside the graph.
    ),
)
def test_nested_fixed_width_fields_cannot_escape_message_bounds(tmp_path, field):
    path = tmp_path / "truncated-nested-fixed.onnx"
    path.write_bytes(_field(7, 2, field) + b"\x08\x09")

    with pytest.raises(ValueError, match="fixed-width"):
        read_model_header(str(path))


def test_file_and_nested_message_budgets_reject_before_parsing(tmp_path, monkeypatch):
    payload = _onnx_fixture()
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_FILE_BYTES", len(payload) - 1)
    with pytest.raises(ValueError, match="file-size budget"):
        _read_budget_fixture(tmp_path, payload)

    monkeypatch.setattr(onnx_reader, "MAX_PROTO_FILE_BYTES", 1_000)
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_MESSAGE_BYTES", 4)
    with pytest.raises(ValueError, match="message budget"):
        _read_budget_fixture(tmp_path, _field(7, 2, b"\x08\x01" * 3))


def test_field_and_varint_work_budgets_are_shared_across_the_message(tmp_path, monkeypatch):
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_FIELDS", 2)
    with pytest.raises(ValueError, match="field budget"):
        _read_budget_fixture(tmp_path, b"\x08\x01\x28\x02\x08\x03")

    monkeypatch.setattr(onnx_reader, "MAX_PROTO_FIELDS", 1_000_000)
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_WORK_UNITS", 2)
    with pytest.raises(ValueError, match="work budget"):
        _read_budget_fixture(tmp_path, b"\x08\x01")


def test_fixed_width_work_is_budgeted(tmp_path, monkeypatch):
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_WORK_UNITS", 4)
    with pytest.raises(ValueError, match="work budget"):
        _read_budget_fixture(tmp_path, b"\x09" + b"\x00" * 8)


def test_graph_node_and_initializer_budgets_bound_lists_and_counts(tmp_path, monkeypatch):
    monkeypatch.setattr(onnx_reader, "MAX_GRAPH_NODES", 1)
    graph = _field(1, 2, b"") + _field(1, 2, b"")
    with pytest.raises(ValueError, match="graph node budget"):
        _read_budget_fixture(tmp_path, _field(7, 2, graph))

    monkeypatch.setattr(onnx_reader, "MAX_GRAPH_NODES", 250_000)
    monkeypatch.setattr(onnx_reader, "MAX_INITIALIZERS", 2)
    graph = b"".join(
        _field(5, 2, _tensor(f"tensor-{index}", [1], b""))
        for index in range(3)
    )
    with pytest.raises(ValueError, match="initializer budget"):
        _read_budget_fixture(tmp_path, _field(7, 2, graph))


def test_tensor_and_value_dimension_budgets_apply_to_nested_shapes(tmp_path, monkeypatch):
    monkeypatch.setattr(onnx_reader, "MAX_TENSOR_DIMS", 2)
    with pytest.raises(ValueError, match="tensor dimension budget"):
        _read_budget_fixture(tmp_path, _field(7, 2, _field(5, 2, _tensor("x", [1, 2, 3], b""))))

    monkeypatch.setattr(onnx_reader, "MAX_TENSOR_DIMS", 4_096)
    monkeypatch.setattr(onnx_reader, "MAX_VALUE_DIMS", 2)
    value = _value_info("input", [1, 2, 3])
    with pytest.raises(ValueError, match="value dimension budget"):
        _read_budget_fixture(tmp_path, _field(7, 2, _field(11, 2, value)))


def test_metadata_record_and_string_budgets_reject_without_truncation(tmp_path, monkeypatch):
    entry = _field(1, 2, b"key") + _field(2, 2, b"value")
    monkeypatch.setattr(onnx_reader, "MAX_METADATA_RECORDS", 2)
    with pytest.raises(ValueError, match="metadata record budget"):
        _read_budget_fixture(tmp_path, _field(14, 2, entry) * 3)

    monkeypatch.setattr(onnx_reader, "MAX_METADATA_RECORDS", 100_000)
    monkeypatch.setattr(onnx_reader, "MAX_METADATA_STRING_BYTES", 5)
    with pytest.raises(ValueError, match="metadata string budget"):
        _read_budget_fixture(tmp_path, _field(14, 2, _field(1, 2, b"abcdef")))

    monkeypatch.setattr(onnx_reader, "MAX_METADATA_STRING_BYTES", 64 * 1024**2)
    monkeypatch.setattr(onnx_reader, "MAX_PROTO_TEXT_BYTES", 3)
    with pytest.raises(ValueError, match="text field"):
        _read_budget_fixture(tmp_path, _field(14, 2, _field(1, 2, b"long")))
