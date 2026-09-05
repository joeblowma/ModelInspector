"""Raw report, modelinfo, and runtime-path integration coverage."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.estimator import project_resources, runtime_configuration
from back.reporting import print_report
import modelinfo


def _tensor_info() -> dict:
    return {
        "block.10.weight": {
            "dtype": "F16",
            "shape": [2, 2],
            "n_bytes": 16,
            "shard_id": 2,
        },
        "block.2.weight": {
            "dtype": "F16",
            "shape": [2],
            "n_bytes": 4,
            "shard_id": 1,
        },
    }


def test_modelinfo_exposes_original_order_bytes_and_shard_ids(monkeypatch) -> None:
    tensor_info = _tensor_info()
    monkeypatch.setattr(
        modelinfo,
        "_read_header_or_cached",
        lambda _filepath, options=None: ({}, tensor_info, 20),
    )
    monkeypatch.setattr(
        modelinfo,
        "inspect_file",
        lambda _filepath, options=None: {
            "original_tensor_order": list(tensor_info),
            "sorted_tensor_order": ["block.2.weight", "block.10.weight"],
        },
    )

    text = modelinfo.generate_modelinfo_dump("model.safetensors")
    data = modelinfo.build_modelinfo_json_data("model.safetensors")

    assert "Original tensor/block order:" in text
    assert text.index("block.10.weight") < text.index("block.2.weight")
    assert "n_bytes=16" in text
    assert "shard_id=2" in text
    assert data["original_tensor_order"] == ["block.10.weight", "block.2.weight"]
    assert data["sorted_tensor_order"] == ["block.2.weight", "block.10.weight"]
    assert data["tensors"][0]["n_bytes"] == 4
    assert data["tensors"][0]["shard_id"] == 1
    assert data["tensors"][0]["original_index"] == 1


def test_terminal_report_exposes_tensor_details_and_original_order(capsys) -> None:
    print_report("model.safetensors", {}, _tensor_info(), 20)
    output = capsys.readouterr().out

    assert "Original tensor/block order:" in output
    assert "Tensor/block details (sorted presentation):" in output
    assert "n_bytes=16" in output
    assert "shard_id=2" in output


def test_runtime_configuration_includes_associated_sidecar_role_and_path() -> None:
    projection = project_resources({"total_params": 1_000_000})
    path = str(Path("models") / "vision-mmproj.safetensors")
    configuration = runtime_configuration(
        projection,
        inspection={"sidecar_roles": ["mmproj"], "sidecar_paths": [path]},
    )

    assert "Associated sidecars:" in configuration
    assert f"Sidecar mmproj: {path}" in configuration
