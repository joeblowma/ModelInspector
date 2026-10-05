import json

from back.cache_entries import list_cache_paths, select_cache_entries


def _record(
    cache_key: str,
    filepath: str,
    resolved_filepath: str,
    allow_aliases: bool,
) -> tuple[str, dict]:
    return cache_key, {
        "cache_options": {"allow_filename_alias_detection": allow_aliases},
        "data": {"filepath": filepath, "resolved_filepath": resolved_filepath},
        "identity": {"resolved_filepath": resolved_filepath},
    }


def test_duplicate_primary_path_does_not_promote_resolved_alias() -> None:
    display_path = r"U:\Comfy\models\model.safetensors"
    resolved_path = r"X:\models\model.safetensors"
    records = [
        _record("first", display_path, resolved_path, True),
        _record("option-variant", display_path, resolved_path, False),
    ]

    selected = select_cache_entries(records)

    assert len(selected) == 1
    assert selected[0]["filepath"] == display_path
    assert selected[0]["cache_key"] == "first"
    assert selected[0]["cache_options"] == {
        "allow_filename_alias_detection": True
    }
    assert list_cache_paths(records) == [display_path]


def test_path_identity_normalizes_case_and_separators() -> None:
    records = [
        _record(
            "first",
            r"U:\old\same.safetensors",
            "X:/models/Same.safetensors",
            True,
        ),
        _record(
            "alias",
            r"U:\different\same.safetensors",
            r"x:\MODELS\SAME.SAFETENSORS",
            False,
        ),
    ]

    selected = select_cache_entries(records)

    assert len(selected) == 1
    assert selected[0]["filepath"] == r"U:\old\same.safetensors"
    assert selected[0]["cache_key"] == "first"
    assert selected[0]["cache_options"] == {
        "allow_filename_alias_detection": True
    }


def test_distinct_missing_targets_keep_same_legacy_display_alias() -> None:
    legacy_alias = r"U:\old-library\same.safetensors"
    records = [
        _record(
            "historic-a", legacy_alias, r"X:\archive\a\same.safetensors", True
        ),
        _record(
            "historic-b",
            r"u:/OLD-LIBRARY/SAME.safetensors",
            r"X:\archive\b\same.safetensors",
            False,
        ),
    ]

    selected = select_cache_entries(records)

    assert [entry["cache_key"] for entry in selected] == [
        "historic-a",
        "historic-b",
    ]
    assert [entry["filepath"] for entry in selected] == [
        legacy_alias,
        r"u:/OLD-LIBRARY/SAME.safetensors",
    ]
    assert list_cache_paths(records) == [legacy_alias]


def test_cache_key_path_is_used_when_persisted_identity_is_missing() -> None:
    options = {"allow_filename_alias_detection": True}
    cache_key = json.dumps([r"X:\canonical\model.safetensors", options])
    records = [
        (cache_key, {"data": {"filepath": r"U:\old\model.safetensors"}}),
        (
            json.dumps([r"x:/CANONICAL/model.safetensors", {**options, "other": 1}]),
            {"data": {"filepath": r"U:\new\model.safetensors"}},
        ),
    ]

    selected = select_cache_entries(records)

    assert len(selected) == 1
    assert selected[0]["cache_key"] == cache_key
    assert selected[0]["cache_options"] == options


def test_selection_stops_between_records_when_cancelled() -> None:
    records = [
        _record(
            "first", r"C:\models\one.safetensors", r"C:\models\one.safetensors", True
        ),
        _record(
            "second", r"C:\models\two.safetensors", r"C:\models\two.safetensors", True
        ),
    ]
    cancellations = iter((False, True))

    selected = select_cache_entries(records, lambda: next(cancellations))

    assert [entry["cache_key"] for entry in selected] == ["first"]
