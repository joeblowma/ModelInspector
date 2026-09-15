import sys
from pathlib import Path

import pytest


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from front.view_controller import _data_quantization_display


def test_explicit_quantization_label_takes_precedence_over_dtype_details():
    assert _data_quantization_display({
        "quantization": "Q4_K_M",
        "dtypes": [{"dtype": "F16"}, {"dtype": "BF16"}],
    }) == "Q4_K_M"


@pytest.mark.parametrize("dtype,expected", [
    ("F32", "f32"),
    ("F16", "f16"),
    ("BF16", "bf16"),
])
def test_uniform_standard_tensor_dtype_maps_to_canonical_code(dtype, expected):
    assert _data_quantization_display({"dtypes": [{"dtype": dtype}]}) == expected


@pytest.mark.parametrize("precision,expected", [
    ("float32", "f32"),
    ("float16", "f16"),
    ("bfloat16", "bf16"),
    ("blfloat16", "bf16"),  # historical typo tolerated
])
def test_precision_summary_fallback_infers_canonical_code(precision, expected):
    assert _data_quantization_display({"precision_summary": precision}) == expected


@pytest.mark.parametrize("data", [
    {"dtypes": [{"dtype": "F16"}, {"dtype": "BF16"}]},
    {"precision_summary": "Mixed (float16, float32)"},
    {"precision_summary": "-"},
    {},
])
def test_mixed_or_missing_dtype_information_is_blank(data):
    assert _data_quantization_display(data) == "-"


def test_duplicate_uniform_dtype_entries_still_map_to_canonical_code():
    assert _data_quantization_display({
        "dtypes": [{"dtype": "F16"}, {"dtype": "F16", "count": 9}],
    }) == "f16"


def test_non_dict_dtype_entries_are_ignored():
    assert _data_quantization_display({
        "dtypes": [{"dtype": "F16"}, "garbage", {"no_dtype": True}],
    }) == "f16"
