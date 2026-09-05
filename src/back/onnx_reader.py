"""Dependency-free ONNX protobuf header reader.

The parser walks only protobuf structure and skips ``raw_data`` and unknown
length-delimited fields with seeks.  It therefore reports graph metadata and
initializer descriptors without materializing ONNX tensor payloads.  The
public return value matches the historical reader triple.
"""

import os
from pathlib import Path
from typing import Any, Sequence


# These limits are intentionally about the protobuf envelope and metadata, not
# tensor storage.  Opaque ``raw_data`` fields are skipped with seek(), so a
# large model can still be inspected without allocating its weights.  The file
# and message limits remain finite so malformed sparse files cannot be treated
# as an unbounded input stream.
MAX_PROTO_FILE_BYTES = 16 * 1024**3
MAX_PROTO_MESSAGE_BYTES = 4 * 1024**3
MAX_PROTO_FIELDS = 1_000_000
MAX_PROTO_WORK_UNITS = 128 * 1024**2
MAX_GRAPH_NODES = 250_000
MAX_INITIALIZERS = 10_000
MAX_TENSOR_DIMS = 4_096
MAX_VALUE_DIMS = 4_096
MAX_METADATA_RECORDS = 100_000
MAX_METADATA_STRING_BYTES = 64 * 1024**2
MAX_PROTO_TEXT_BYTES = 2_000_000
ONNX_DTYPE_NAMES: dict[int, tuple[str, int]] = {
    1: ("F32", 4),
    2: ("U8", 1),
    3: ("I8", 1),
    4: ("U16", 2),
    5: ("I16", 2),
    6: ("I32", 4),
    7: ("I64", 8),
    9: ("U8", 1),
    10: ("F16", 2),
    11: ("F64", 8),
    12: ("U32", 4),
    13: ("U64", 8),
    14: ("F32", 8),
    15: ("F64", 16),
    16: ("BF16", 2),
    17: ("F8_E4M3", 1),
    18: ("F8_E4M3", 1),
    19: ("F8_E5M2", 1),
    20: ("F8_E4M3", 1),
    21: ("F8_E4M3", 1),
    22: ("F8_E5M2", 1),
}


class _ParseBudget:
    """Shared limits for all nested parsers in one ONNX file."""

    def __init__(self) -> None:
        self.fields = 0
        self.work_units = 0
        self.graph_nodes = 0
        self.initializers = 0
        self.metadata_records = 0
        self.metadata_string_bytes = 0

    def work(self, units: int, description: str) -> None:
        if self.work_units + units > MAX_PROTO_WORK_UNITS:
            raise ValueError(f"ONNX protobuf work budget exceeded while {description}")
        self.work_units += units

    def field(self) -> None:
        self.fields += 1
        if self.fields > MAX_PROTO_FIELDS:
            raise ValueError("ONNX protobuf field budget exceeded")
        self.work(1, "parsing fields")

    def metadata_record(self, description: str) -> None:
        self.metadata_records += 1
        if self.metadata_records > MAX_METADATA_RECORDS:
            raise ValueError(f"ONNX metadata record budget exceeded while {description}")

    def metadata_text(self, size: int) -> None:
        if size > MAX_PROTO_TEXT_BYTES:
            raise ValueError(
                f"ONNX protobuf text field exceeds {MAX_PROTO_TEXT_BYTES} bytes"
            )
        if self.metadata_string_bytes + size > MAX_METADATA_STRING_BYTES:
            raise ValueError("ONNX metadata string budget exceeded")
        self.work(size, "reading metadata strings")
        self.metadata_string_bytes += size

    def dimension(self, kind: str, count: int) -> int:
        limit = MAX_TENSOR_DIMS if kind == "tensor" else MAX_VALUE_DIMS
        count += 1
        if count > limit:
            raise ValueError(f"ONNX {kind} dimension budget exceeded")
        return count

    def graph_node(self) -> None:
        self.graph_nodes += 1
        if self.graph_nodes > MAX_GRAPH_NODES:
            raise ValueError("ONNX graph node budget exceeded")

    def initializer(self) -> None:
        self.initializers += 1
        if self.initializers > MAX_INITIALIZERS:
            raise ValueError("ONNX initializer budget exceeded")
        self.metadata_record("initializers")


class _ProtoReader:
    def __init__(self, stream, end: int, budget: _ParseBudget):
        self.stream = stream
        self.end = end
        self.budget = budget

    @property
    def position(self) -> int:
        return int(self.stream.tell())

    def varint(self) -> int:
        value = 0
        shift = 0
        while shift < 70:
            if self.position >= self.end:
                raise ValueError("Truncated ONNX protobuf varint")
            raw = self.stream.read(1)
            if len(raw) != 1:
                raise ValueError("Truncated ONNX protobuf varint")
            byte = raw[0]
            self.budget.work(1, "reading varints")
            value |= (byte & 0x7F) << shift
            if not byte & 0x80:
                return value
            shift += 7
        raise ValueError("Invalid ONNX protobuf varint")

    def key(self) -> tuple[int, int]:
        self.budget.field()
        raw = self.varint()
        field, wire = raw >> 3, raw & 7
        if field == 0:
            raise ValueError("Invalid ONNX protobuf field number 0")
        return field, wire

    def length(self) -> int:
        size = self.varint()
        if size > self.end - self.position:
            raise ValueError("ONNX protobuf field exceeds its containing message")
        if size > MAX_PROTO_MESSAGE_BYTES:
            raise ValueError(
                "ONNX protobuf length-delimited field exceeds "
                f"{MAX_PROTO_MESSAGE_BYTES} byte message budget"
            )
        target = self.position + size
        return target

    def text(self, target: int) -> str:
        size = target - self.position
        if size < 0 or target > self.end:
            raise ValueError("ONNX protobuf text field exceeds its containing message")
        self.budget.metadata_text(size)
        raw = self.stream.read(size)
        if len(raw) != size:
            raise ValueError("Truncated ONNX protobuf text field")
        return raw.decode("utf-8", errors="replace")

    def skip(self, wire_type: int) -> None:
        if wire_type == 0:
            self.varint()
        elif wire_type == 1:
            self._skip_fixed_width(8)
        elif wire_type == 2:
            self.stream.seek(self.length())
        elif wire_type == 5:
            self._skip_fixed_width(4)
        else:
            raise ValueError(f"Unsupported ONNX protobuf wire type: {wire_type}")
        if self.position > self.end:
            raise ValueError("ONNX protobuf field exceeds its containing message")

    def _skip_fixed_width(self, width: int) -> None:
        """Advance over a fixed-width field only when it fits this message."""
        if self.position + width > self.end:
            raise ValueError("Truncated ONNX protobuf fixed-width field")
        self.budget.work(width, "skipping fixed-width fields")
        self.stream.seek(width, 1)


def _read_nested(stream, target: int, parser, budget: _ParseBudget) -> Any:
    if target - stream.tell() > MAX_PROTO_MESSAGE_BYTES:
        raise ValueError(
            "ONNX protobuf nested message exceeds "
            f"{MAX_PROTO_MESSAGE_BYTES} byte message budget"
        )
    return parser(_ProtoReader(stream, target, budget))


def _parse_string_entry(reader: _ProtoReader) -> tuple[str, str]:
    reader.budget.metadata_record("string metadata")
    key = ""
    value = ""
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 2 and field in (1, 2):
            target = reader.length()
            text = reader.text(target)
            if field == 1:
                key = text
            else:
                value = text
        else:
            reader.skip(wire)
    return key, value


def _parse_dimension(reader: _ProtoReader) -> int | str | None:
    value: int | str | None = None
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 0 and field == 1:
            value = reader.varint()
        elif wire == 2 and field == 2:
            value = reader.text(reader.length())
        else:
            reader.skip(wire)
    return value


def _parse_tensor_shape(reader: _ProtoReader) -> list[int | str | None]:
    shape: list[int | str | None] = []
    dimension_count = 0
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 2 and field == 1:
            dimension_count = reader.budget.dimension("value", dimension_count)
            shape.append(
                _read_nested(reader.stream, reader.length(), _parse_dimension, reader.budget)
            )
        else:
            reader.skip(wire)
    return shape


def _parse_tensor_type(reader: _ProtoReader) -> tuple[int | None, list[int | str | None]]:
    dtype = None
    shape: list[int | str | None] = []
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 0 and field == 1:
            dtype = reader.varint()
        elif wire == 2 and field == 2:
            shape = _read_nested(
                reader.stream, reader.length(), _parse_tensor_shape, reader.budget
            )
        else:
            reader.skip(wire)
    return dtype, shape


def _parse_value_info(reader: _ProtoReader) -> dict[str, Any]:
    reader.budget.metadata_record("value-info metadata")
    name = ""
    dtype = None
    shape: list[int | str | None] = []
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 2 and field == 1:
            name = reader.text(reader.length())
        elif wire == 2 and field == 2:
            dtype, shape = _read_nested(
                reader.stream, reader.length(), _parse_type_proto, reader.budget
            )
        else:
            reader.skip(wire)
    return {"name": name, "dtype_id": dtype, "shape": shape}


def _parse_type_proto(reader: _ProtoReader) -> tuple[int | None, list[int | str | None]]:
    dtype = None
    shape: list[int | str | None] = []
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 2 and field == 1:
            dtype, shape = _read_nested(
                reader.stream, reader.length(), _parse_tensor_type, reader.budget
            )
        else:
            reader.skip(wire)
    return dtype, shape


def _parse_external_entry(reader: _ProtoReader) -> tuple[str, str]:
    return _parse_string_entry(reader)


def _element_count(shape: Sequence[int | str | None]) -> int | None:
    count = 1
    for dimension in shape:
        if not isinstance(dimension, int) or dimension < 0:
            return None
        count *= dimension
    return count


def _parse_tensor(reader: _ProtoReader) -> dict[str, Any]:
    dims: list[int] = []
    dimension_count = 0
    dtype_id: int | None = None
    name = ""
    raw_bytes = None
    external: dict[str, str] = {}
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 0 and field == 1:
            dimension_count = reader.budget.dimension("tensor", dimension_count)
            dims.append(reader.varint())
        elif wire == 2 and field == 1:
            packed = _ProtoReader(reader.stream, reader.length(), reader.budget)
            while packed.position < packed.end:
                dimension_count = reader.budget.dimension("tensor", dimension_count)
                dims.append(packed.varint())
        elif wire == 0 and field == 2:
            dtype_id = reader.varint()
        elif wire == 2 and field == 8:
            name = reader.text(reader.length())
        elif wire == 2 and field == 9:
            target = reader.length()
            raw_bytes = target - reader.position
            reader.stream.seek(target)
        elif wire == 2 and field == 13:
            entry = _read_nested(
                reader.stream, reader.length(), _parse_external_entry, reader.budget
            )
            if entry[0]:
                external[entry[0]] = entry[1]
        else:
            reader.skip(wire)

    dtype_key = dtype_id if dtype_id is not None else -1
    dtype_name, item_size = ONNX_DTYPE_NAMES.get(dtype_key, (f"ONNX_TYPE_{dtype_id}", 0))
    inferred = None
    if raw_bytes is not None:
        inferred = raw_bytes
    elif external.get("length"):
        try:
            inferred = int(external["length"])
        except ValueError:
            inferred = None
    else:
        elements = _element_count(dims)
        if elements is not None and item_size:
            inferred = elements * item_size
    descriptor: dict[str, Any] = {
        "dtype": dtype_name,
        "shape": dims,
        "shard_id": 0,
    }
    if inferred is not None:
        descriptor["n_bytes"] = int(inferred)
    if external:
        descriptor["external_data"] = external
    if name:
        descriptor["name"] = name
    return descriptor


def _parse_graph(reader: _ProtoReader) -> tuple[str, list[dict[str, Any]], int]:
    graph_name = ""
    tensors: list[dict[str, Any]] = []
    node_count = 0
    while reader.position < reader.end:
        field, wire = reader.key()
        if wire == 2 and field == 1:
            reader.budget.graph_node()
            reader.stream.seek(reader.length())
            node_count += 1
        elif wire == 2 and field == 2:
            graph_name = reader.text(reader.length())
        elif wire == 2 and field == 5:
            reader.budget.initializer()
            tensor = _read_nested(
                reader.stream, reader.length(), _parse_tensor, reader.budget
            )
            tensors.append(tensor)
        elif wire == 2 and field in (11, 12, 13):
            # Parse graph signatures only to validate/consume the nested
            # protobuf; initializers remain the public tensor descriptors.
            _read_nested(reader.stream, reader.length(), _parse_value_info, reader.budget)
        else:
            reader.skip(wire)
    return graph_name, tensors, node_count


def read_onnx_header(
    filepath: str,
    *,
    options: dict[str, Any] | None = None,
) -> tuple[dict, dict, int]:
    """Read ONNX metadata and initializer headers without loading raw data."""
    del options
    file_size = os.path.getsize(filepath)
    if file_size > MAX_PROTO_FILE_BYTES:
        raise ValueError(
            f"ONNX file exceeds {MAX_PROTO_FILE_BYTES} byte file-size budget"
        )
    metadata: dict[str, Any] = {"smi.format": "ONNX"}
    tensors: list[dict[str, Any]] = []
    with open(filepath, "rb") as stream:
        reader = _ProtoReader(stream, file_size, _ParseBudget())
        while reader.position < reader.end:
            field, wire = reader.key()
            if wire == 0 and field == 1:
                metadata["onnx.ir_version"] = reader.varint()
            elif wire == 2 and field in (2, 3, 4, 6):
                target = reader.length()
                text = reader.text(target)
                metadata[
                    {
                        2: "onnx.producer_name",
                        3: "onnx.producer_version",
                        4: "onnx.domain",
                        6: "onnx.doc_string",
                    }[field]
                ] = text
            elif wire == 0 and field == 5:
                metadata["onnx.model_version"] = reader.varint()
            elif wire == 2 and field == 7:
                graph_name, graph_tensors, node_count = _read_nested(
                    stream, reader.length(), _parse_graph, reader.budget
                )
                if graph_name:
                    metadata["onnx.graph_name"] = graph_name
                metadata["onnx.node_count"] = node_count
                tensors.extend(graph_tensors)
            elif wire == 2 and field == 14:
                key, value = _read_nested(
                    stream, reader.length(), _parse_string_entry, reader.budget
                )
                if key:
                    metadata[key] = value
            else:
                reader.skip(wire)

    tensor_info: dict[str, dict[str, Any]] = {}
    for index, descriptor in enumerate(tensors):
        name = str(descriptor.pop("name", "") or f"initializer_{index}")
        if name in tensor_info:
            name = f"{name}@{index}"
        tensor_info[name] = descriptor
    metadata["onnx.initializer_count"] = len(tensor_info)
    return metadata, tensor_info, file_size


__all__ = ["read_onnx_header"]
