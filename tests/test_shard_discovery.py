import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back import shard_discovery
from back.shard_discovery import _parse_shard_name, discover_shard_set
from model_readers import iter_model_paths, read_model_header
from back.inspection_pipeline import inspect_file


def _write_safetensors(path: Path, name: str, size: int = 4) -> None:
    header = {name: {"dtype": "F16", "shape": [size // 2], "data_offsets": [0, size]}}
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"x" * size)


def test_filename_shards_aggregate_once_with_stable_ids_and_order(tmp_path):
    first = tmp_path / "model-00001-of-00002.safetensors"
    second = tmp_path / "model-00002-of-00002.safetensors"
    _write_safetensors(first, "first")
    _write_safetensors(second, "second", 6)

    metadata, tensors, file_size = read_model_header(str(second))
    paths = iter_model_paths([str(second), str(first)], recursive=False)

    assert paths == [str(first)]
    assert list(tensors) == ["first", "second"]
    assert tensors["first"]["shard_id"] == 1
    assert tensors["second"]["shard_id"] == 2
    assert tensors["second"]["n_bytes"] == 6
    assert metadata["smi.shard_manifest"]["member_count"] == 2
    assert metadata["smi.shard_identity"]["members"][0]["file_size"] == first.stat().st_size
    assert file_size == first.stat().st_size + second.stat().st_size


def test_safetensors_index_shards_are_discovered_and_aggregated(tmp_path):
    first = tmp_path / "model-00001.safetensors"
    second = tmp_path / "model-00002.safetensors"
    index = tmp_path / "model.safetensors.index.json"
    _write_safetensors(first, "alpha")
    _write_safetensors(second, "beta")
    index.write_text(
        json.dumps({"metadata": {"total_size": 8}, "weight_map": {"alpha": first.name, "beta": second.name}}),
        encoding="utf-8",
    )

    metadata, tensors, _ = read_model_header(str(index))

    assert list(tensors) == ["alpha", "beta"]
    assert [item["shard_id"] for item in tensors.values()] == [1, 2]
    assert metadata["smi.shard_manifest"]["manifest_path"] == str(index)
    assert iter_model_paths([str(index), str(first), str(second)], recursive=False) == [
        str(first)
    ]


def test_shard_ids_preserve_filename_indices_and_manifest_order_with_gaps(tmp_path):
    first = tmp_path / "model-00001-of-00003.safetensors"
    third = tmp_path / "model-00003-of-00003.safetensors"
    _write_safetensors(first, "alpha")
    _write_safetensors(third, "gamma")
    metadata, tensors, _ = read_model_header(str(third))
    assert [item["shard_id"] for item in tensors.values()] == [1, 3]
    assert [item["source_index"] for item in metadata["smi.shard_manifest"]["members"]] == [1, 2]

    index = tmp_path / "indexed.safetensors.index.json"
    index.write_text(json.dumps({"weight_map": {"gamma": third.name, "alpha": first.name}}), encoding="utf-8")
    metadata, tensors, _ = read_model_header(str(index))
    assert [item["shard_id"] for item in tensors.values()] == [1, 3]
    assert [item["source_index"] for item in metadata["smi.shard_manifest"]["members"]] == [2, 1]


def test_filename_partial_shards_warn_through_inspection_without_expanding_indices(tmp_path):
    first = tmp_path / "model-00001-of-00003.safetensors"
    third = tmp_path / "model-00003-of-00003.safetensors"
    _write_safetensors(first, "alpha")
    _write_safetensors(third, "gamma", 6)

    result = inspect_file(str(third), {"include_sidecars": False})

    assert result["file_size"] == first.stat().st_size + third.stat().st_size
    assert result["metadata"]["smi.shard_manifest"]["expected_count"] == 3
    assert result["shard_identity"]["expected_count"] == 3
    assert any("1 shard indices are missing" in warning for warning in result["warnings"])


def test_shard_parser_rejects_huge_or_unconvertible_numeric_tokens(monkeypatch, tmp_path):
    huge = "9" * 10_000
    assert _parse_shard_name(tmp_path / f"model-{huge}-of-{huge}.safetensors") is None
    if not hasattr(sys, "set_int_max_str_digits"):
        return
    previous_limit = sys.get_int_max_str_digits()
    sys.set_int_max_str_digits(640)
    try:
        monkeypatch.setattr(shard_discovery, "MAX_SHARD_NUMBER_DIGITS", 641)
        limited = "9" * 641
        assert _parse_shard_name(tmp_path / f"model-{limited}-of-{limited}.safetensors") is None
    finally:
        sys.set_int_max_str_digits(previous_limit)


def test_stale_safetensors_index_is_not_discovered_or_canonicalized(tmp_path):
    index = tmp_path / "model.safetensors.index.json"
    index.write_text(
        json.dumps(
            {
                "weight_map": {
                    "alpha": "model-00001-of-00004.safetensors",
                    "beta": "model-00002-of-00004.safetensors",
                }
            }
        ),
        encoding="utf-8",
    )

    assert discover_shard_set(index) is None
    assert iter_model_paths([str(index)], recursive=False) == []
    try:
        read_model_header(str(index))
    except ValueError as exc:
        assert "manifest" in str(exc).lower()
    else:
        raise AssertionError("stale shard manifest must be rejected")


def test_stale_index_does_not_hide_an_unrelated_gguf(tmp_path):
    index = tmp_path / "model.safetensors.index.json"
    index.write_text(
        json.dumps(
            {
                "weight_map": {
                    "alpha": "model-00001-of-00004.safetensors",
                    "beta": "model-00002-of-00004.safetensors",
                }
            }
        ),
        encoding="utf-8",
    )
    gguf = tmp_path / "unrelated.gguf"
    gguf.write_bytes(b"")

    assert iter_model_paths([str(tmp_path)], recursive=False) == [str(gguf)]


def test_partial_index_uses_existing_primary_and_preserves_missing_identity(tmp_path):
    existing = tmp_path / "model-00002-of-00002.safetensors"
    missing = tmp_path / "model-00001-of-00002.safetensors"
    index = tmp_path / "model.safetensors.index.json"
    _write_safetensors(existing, "beta")
    index.write_text(
        json.dumps({"weight_map": {"alpha": missing.name, "beta": existing.name}}),
        encoding="utf-8",
    )

    shard_set = discover_shard_set(index)
    metadata, tensors, _ = read_model_header(str(index))

    assert shard_set is not None
    assert shard_set.primary_path == str(existing)
    assert iter_model_paths([str(index)], recursive=False) == [str(existing)]
    assert shard_set.expected_count == 2
    assert shard_set.manifest()["members"][0]["exists"] is False
    assert shard_set.manifest()["members"][1]["exists"] is True
    assert list(tensors) == ["beta"]
    assert any("could not be read" in warning for warning in metadata["smi.warnings"])
