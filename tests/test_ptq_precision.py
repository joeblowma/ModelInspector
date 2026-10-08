import struct
import sys
from collections import Counter
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.estimator_metadata import quantization_bits
from back.tensor_summary import _summarize_dtype_mix
from model_readers import analyze_tensors, read_gguf_header


def _gguf_string(value: str) -> bytes:
    encoded = value.encode("utf-8")
    return struct.pack("<Q", len(encoded)) + encoded


def _write_ptq_header(path: Path, file_type: int, tensor_type: int) -> None:
    header = b"".join(
        (
            b"GGUF",
            struct.pack("<IQQ", 3, 1, 1),
            _gguf_string("general.file_type"),
            struct.pack("<II", 4, file_type),
            _gguf_string("model.weight"),
            struct.pack("<IQIQ", 1, 32, tensor_type, 0),
        )
    )
    path.write_bytes(header + b"\0" * (-len(header) % 32))


@pytest.mark.parametrize(
    ("file_type", "tensor_type", "expected"),
    ((141, 142, "PTQ2_0"), (143, 143, "PTQ1_0")),
)
def test_ptq_tensor_types_preserve_header_precision(tmp_path, file_type, tensor_type, expected):
    path = tmp_path / f"{expected}.gguf"
    _write_ptq_header(path, file_type, tensor_type)

    metadata, tensor_info, _ = read_gguf_header(str(path))
    dtype_counts, _, _ = analyze_tensors(tensor_info)

    assert metadata["smi.quantization"] == expected
    assert dtype_counts == Counter({expected: 1})
    assert _summarize_dtype_mix(dtype_counts, 1) == expected
    assert quantization_bits(expected) == 16.0
