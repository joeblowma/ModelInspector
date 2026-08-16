import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.inspection_summary import (
    GUI_SUMMARY_KEYS,
    MAX_DISPLAY_CONTAINER_ITEMS,
    MAX_DISPLAY_DEPTH,
    MAX_SUMMARY_STRING_CHARS,
    TRUNCATED_BUDGET_MARKER,
    TRUNCATED_DEPTH_MARKER,
    TRUNCATED_ITEMS_KEY,
    TRUNCATED_TEXT_MARKER,
    compact_inspection_summary,
)
import model_cache
from front.cache_identity import get_cached_inspection_identity_snapshots


def _full_result():
    return {
        "filepath": "model.safetensors",
        "filename": "model.safetensors",
        "architecture": "Synthetic",
        "components": {"unet": True},
        "warnings": ["warning"],
        "training_meta": {"step": "1"},
        "metadata": {"secret": "large"},
        "tensor_info": {"tensor": {"shape": [1, 2]}},
        "arch_details": {"keys": ["tensor"]},
        "dtypes": [{"dtype": "F16"}],
    }


def test_compaction_obeys_schema_and_shallow_copy_isolation():
    full = _full_result()

    summary = compact_inspection_summary(full)

    assert set(summary) <= set(GUI_SUMMARY_KEYS)
    assert "metadata" not in summary
    assert "tensor_info" not in summary
    assert "arch_details" not in summary
    assert "dtypes" not in summary
    assert summary is not full
    assert summary["components"] is not full["components"]
    assert summary["warnings"] is not full["warnings"]
    assert summary["training_meta"] is not full["training_meta"]
    summary["components"]["unet"] = False
    summary["warnings"].append("other")
    assert full["components"]["unet"] is True
    assert full["warnings"] == ["warning"]


def test_compaction_does_not_mutate_source():
    full = _full_result()
    before = dict(full)

    compact_inspection_summary(full)

    assert full == before


def test_compact_cache_snapshot_preserves_full_cache_api(monkeypatch):
    full = _full_result()
    monkeypatch.setattr(model_cache, "get_cached_inspection_snapshot", lambda _: full)

    summary = model_cache.get_cached_inspection_summary_snapshot("model")

    assert summary["filepath"] == full["filepath"]
    assert "metadata" not in summary
    assert model_cache.get_cached_inspection_snapshot("model") is full


def test_compact_bulk_cache_snapshots_do_not_materialize_full_bulk(
    monkeypatch, tmp_path
):
    first_path = str(tmp_path / "a.safetensors")
    second_path = str(tmp_path / "b.safetensors")
    first = _full_result()
    first["filepath"] = first_path
    second = _full_result()
    second["filepath"] = second_path
    entries = [
        {
            "identity": {"resolved_filepath": first_path},
            "data": first,
        },
        {
            "identity": {"resolved_filepath": second_path},
            "data": second,
        },
    ]
    monkeypatch.setattr(
        model_cache,
        "get_cached_inspection_snapshots",
        lambda paths: (_ for _ in ()).throw(
            AssertionError("compact bulk must not call full bulk")
        ),
    )
    monkeypatch.setattr(model_cache, "_iter_cached_entries", lambda: iter(entries))

    snapshots = model_cache.get_cached_inspection_summary_snapshots(
        [first_path, second_path]
    )

    assert set(snapshots) == {first_path, second_path}
    assert all("metadata" not in summary for summary in snapshots.values())
    assert all(
        summary["cache_status"] == "snapshot" for summary in snapshots.values()
    )


def test_compact_bulk_matching_is_equivalent_to_compacted_full_bulk(
    monkeypatch, tmp_path
):
    requested = str(tmp_path / "requested.safetensors")
    ignored = str(tmp_path / "ignored.safetensors")
    matched_data = _full_result()
    matched_data["filepath"] = requested
    ignored_data = _full_result()
    ignored_data["filepath"] = ignored
    entries = [
        {"identity": {"resolved_filepath": ignored}, "data": ignored_data},
        {"identity": {"resolved_filepath": requested}, "data": matched_data},
    ]

    monkeypatch.setattr(model_cache, "_iter_cached_entries", lambda: iter(entries))
    full = model_cache.get_cached_inspection_snapshots([requested])
    monkeypatch.setattr(model_cache, "_iter_cached_entries", lambda: iter(entries))
    compact = model_cache.get_cached_inspection_summary_snapshots([requested])

    assert set(full) == set(compact) == {requested}
    assert compact[requested] == compact_inspection_summary(full[requested])
    assert "metadata" in full[requested]
    assert "metadata" not in compact[requested]


def test_identity_snapshot_preserves_identity_without_copying_inspection_data(
    monkeypatch, tmp_path
):
    requested = str(tmp_path / "requested.safetensors")
    full = _full_result()
    full["filepath"] = requested
    entries = [
        {
            "identity": {
                "resolved_filepath": requested,
                "file_size": 42,
                "mtime_ns": 123,
            },
            "data": full,
        }
    ]
    monkeypatch.setattr(model_cache, "_iter_cached_entries", lambda: iter(entries))

    snapshots = get_cached_inspection_identity_snapshots([requested])

    assert snapshots == {
        requested: {
            "filepath": requested,
            "identity": {
                "resolved_filepath": requested,
                "file_size": 42,
                "mtime_ns": 123,
            },
            "data": {"filepath": requested},
        }
    }


def test_user_sized_strings_and_containers_are_bounded_with_markers():
    full = _full_result()
    long_filepath = "C:\\" + "very-long-directory\\" * 40 + "model.safetensors"
    assert len(long_filepath) > MAX_SUMMARY_STRING_CHARS
    full["filepath"] = long_filepath
    full["resolved_filepath"] = long_filepath
    full["filename"] = "model.safetensors"
    full["warnings"] = [
        "w" * (MAX_SUMMARY_STRING_CHARS + 100)
        for _ in range(MAX_DISPLAY_CONTAINER_ITEMS + 10)
    ]
    full["extra"] = {
        f"key-{index}": f"value-{index}"
        for index in range(MAX_DISPLAY_CONTAINER_ITEMS + 10)
    }

    summary = compact_inspection_summary(full)

    assert summary["filepath"] == long_filepath
    assert summary["resolved_filepath"] == long_filepath
    assert summary["filename"] == "model.safetensors"
    assert len(summary["warnings"]) == MAX_DISPLAY_CONTAINER_ITEMS + 1
    assert summary["warnings"][-1] == "[truncated: 10 more items]"
    assert all(
        len(warning) <= MAX_SUMMARY_STRING_CHARS
        for warning in summary["warnings"][:-1]
    )
    assert summary["warnings"][0].endswith(TRUNCATED_TEXT_MARKER)
    assert summary["extra"][TRUNCATED_ITEMS_KEY] == 10


def test_nested_metadata_has_depth_and_total_budget_limits():
    full = _full_result()
    nested = "leaf"
    for _ in range(MAX_DISPLAY_DEPTH + 2):
        nested = {"child": nested}
    full["training_meta"] = nested
    full["extra"] = {
        f"branch-{branch}": {
            f"item-{item}": "x" * 20
            for item in range(MAX_DISPLAY_CONTAINER_ITEMS)
        }
        for branch in range(MAX_DISPLAY_CONTAINER_ITEMS)
    }

    summary = compact_inspection_summary(full)

    cursor = summary["training_meta"]
    for _ in range(MAX_DISPLAY_DEPTH):
        cursor = cursor["child"]
    assert cursor == TRUNCATED_DEPTH_MARKER

    def contains(value, wanted):
        if value == wanted:
            return True
        if isinstance(value, dict):
            return any(contains(item, wanted) for item in value.values())
        if isinstance(value, (list, tuple)):
            return any(contains(item, wanted) for item in value)
        return False

    assert contains(summary["extra"], TRUNCATED_BUDGET_MARKER)


def test_bounded_projection_is_deeply_isolated_but_structures_stay_compatible():
    full = _full_result()
    full["extra"] = {"nested": {"items": ["original"]}}
    full["modelinfo_outputs"] = {"json": ["first", "second"]}
    full["named_text_encoders"] = {"CLIP-L": 12}

    summary = compact_inspection_summary(full)
    summary["extra"]["nested"]["items"].append("summary-only")
    summary["modelinfo_outputs"]["json"].append("summary-only")
    summary["named_text_encoders"]["CLIP-L"] = 99

    assert full["extra"]["nested"]["items"] == ["original"]
    assert full["modelinfo_outputs"]["json"] == ["first", "second"]
    assert full["named_text_encoders"] == {"CLIP-L": 12}
    assert set(summary) <= set(GUI_SUMMARY_KEYS)


def test_operational_and_classification_strings_remain_exact():
    long_value = "x" * (MAX_SUMMARY_STRING_CHARS + 100)
    full = _full_result()
    for key in (
        "format",
        "architecture",
        "model_type",
        "cache_status",
        "precision_display",
    ):
        full[key] = long_value
    full["modelinfo_outputs"] = {"json": [long_value]}

    summary = compact_inspection_summary(full)

    for key in (
        "format",
        "architecture",
        "model_type",
        "cache_status",
        "precision_display",
    ):
        assert summary[key] == long_value
    assert summary["modelinfo_outputs"]["json"] == [long_value]
