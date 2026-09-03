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


@pytest.mark.parametrize("dtype", ["F32", "F16", "BF16"])
def test_uniform_standard_tensor_dtype_is_shown_without_quantization_claim(dtype):
    assert _data_quantization_display({"dtypes": [{"dtype": dtype}]}) == dtype


@pytest.mark.parametrize("data", [
    {"dtypes": [{"dtype": "F16"}, {"dtype": "BF16"}]},
    {},
])
def test_mixed_or_missing_dtype_information_is_unavailable(data):
    assert _data_quantization_display(data) == "Unavailable"
