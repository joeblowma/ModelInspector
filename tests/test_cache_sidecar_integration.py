"""Portable cache integration coverage for shards and associated sidecars."""

import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.inspection_pipeline import inspect_file
from back.cache_verifier import verify_cache_entries


def _write_safetensors(path: Path, name: str, size: int = 4) -> None:
    header = {name: {"dtype": "F16", "shape": [size // 2], "data_offsets": [0, size]}}
    raw = json.dumps(header).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"x" * size)


def _primary_entry(cache_dir: Path, filepath: Path) -> dict:
    for path in (cache_dir / "entries").glob("*.json"):
        entry = json.loads(path.read_text(encoding="utf-8"))
        data = entry.get("data", {})
        if data.get("filepath") == str(filepath):
            return entry
    raise AssertionError("primary cache entry was not written")


def test_sidecar_records_are_separate_but_rehydrated_on_cache_hit(
    monkeypatch, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("SMI_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    primary = tmp_path / "model.safetensors"
    sidecar = tmp_path / "model-mmproj.safetensors"
    _write_safetensors(primary, "main")
    _write_safetensors(sidecar, "projection", 6)

    first = inspect_file(str(primary))
    entry = _primary_entry(cache_dir, primary)
    assert first["sidecars"][0]["sidecar_role"] == "mmproj"
    assert "sidecars" not in entry["data"]
    assert "sidecar_inspections" not in entry["data"]
    assert entry["data"]["sidecar_identities"][0]["role"] == "mmproj"
    sidecar_file = cache_dir / entry["sidecar_data_file"]
    assert sidecar_file == cache_dir / "sidecars" / sidecar_file.name
    persisted = json.loads(sidecar_file.read_text(encoding="utf-8"))
    assert persisted["sidecar_records"][0]["sidecar_role"] == "mmproj"

    second = inspect_file(str(primary))
    assert second["sidecars"][0]["filepath"] == str(sidecar.resolve())
    assert second["sidecars"][0]["sidecar_role"] == "mmproj"


def test_sidecar_change_and_removal_invalidate_primary_cache(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    primary = tmp_path / "model.safetensors"
    sidecar = tmp_path / "model-mmproj.safetensors"
    _write_safetensors(primary, "main")
    _write_safetensors(sidecar, "projection", 4)

    first = inspect_file(str(primary))
    assert "sidecars" not in first["sidecars"][0]
    _write_safetensors(sidecar, "projection", 10)
    changed = inspect_file(str(primary))
    assert changed["sidecars"][0]["file_size"] != first["sidecars"][0]["file_size"]

    sidecar.unlink()
    removed = inspect_file(str(primary))
    assert removed["sidecars"] == []
    assert removed["sidecar_roles"] == []


def test_changed_non_primary_shard_invalidates_full_shard_identity(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    first_shard = tmp_path / "model-00001-of-00002.safetensors"
    second_shard = tmp_path / "model-00002-of-00002.safetensors"
    _write_safetensors(first_shard, "first", 4)
    _write_safetensors(second_shard, "second", 6)

    first = inspect_file(str(second_shard))
    assert first["shard_identity"]["members"][0]["file_size"] == first_shard.stat().st_size
    _write_safetensors(first_shard, "first", 12)
    refreshed = inspect_file(str(second_shard))

    assert refreshed["shard_identity"] != first["shard_identity"]
    assert refreshed["file_size"] == first_shard.stat().st_size + second_shard.stat().st_size


def test_cache_verifier_reports_sidecar_identity_changes_without_reading_payload(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    primary = tmp_path / "model.safetensors"
    sidecar = tmp_path / "model-mmproj.safetensors"
    _write_safetensors(primary, "main")
    _write_safetensors(sidecar, "projection", 4)

    inspect_file(str(primary))
    entry = _primary_entry(tmp_path / "cache", primary)
    unchanged = verify_cache_entries([entry])
    assert not unchanged.entries[0].candidate

    _write_safetensors(sidecar, "projection", 10)
    changed = verify_cache_entries([entry])
    assert changed.entries[0].candidate
    assert changed.entries[0].sidecar_identity_changed


def test_legacy_cache_keeps_sidecar_records_in_a_sibling_store(
    monkeypatch, tmp_path: Path
) -> None:
    legacy_path = tmp_path / "inspection-cache.json"
    monkeypatch.setenv("SMI_CACHE_PATH", str(legacy_path))
    monkeypatch.delenv("SMI_CACHE_DIR", raising=False)
    primary = tmp_path / "model.safetensors"
    sidecar = tmp_path / "model-mmproj.safetensors"
    _write_safetensors(primary, "main")
    _write_safetensors(sidecar, "projection")

    inspect_file(str(primary))
    payload = json.loads(legacy_path.read_text(encoding="utf-8"))
    primary_entry = next(
        entry
        for entry in payload["entries"].values()
        if entry.get("data", {}).get("filepath") == str(primary)
    )
    assert "sidecars" not in primary_entry["data"]
    assert Path(primary_entry["sidecar_data_file"]).is_file()
    assert inspect_file(str(primary))["sidecars"][0]["sidecar_role"] == "mmproj"


def test_cache_verifier_reports_changed_non_primary_shard(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    first_shard = tmp_path / "model-00001-of-00002.safetensors"
    second_shard = tmp_path / "model-00002-of-00002.safetensors"
    _write_safetensors(first_shard, "first", 4)
    _write_safetensors(second_shard, "second", 6)

    inspect_file(str(second_shard))
    entry = _primary_entry(tmp_path / "cache", second_shard)
    _write_safetensors(first_shard, "first", 12)
    report = verify_cache_entries([entry])

    assert report.entries[0].candidate
    assert report.entries[0].shard_identity_changed


def test_cache_verifier_honors_injected_stats_for_all_companions():
    primary = "virtual/model.safetensors"
    shard = "virtual/model-00002-of-00002.safetensors"
    sidecar = "virtual/model-mmproj.safetensors"
    entry = {
        "filepath": primary, "file_size": 4, "mtime_ns": 1,
        "shard_identity": {"members": [{"path": shard, "exists": True, "file_size": 4, "mtime_ns": 1}]},
        "sidecar_identities": [{"path": sidecar, "exists": True, "file_size": 4, "mtime_ns": 1, "role": "mmproj"}],
    }
    filesystem = {
        primary: {"size": 4, "mtime_ns": 1},
        shard: {"size": 4, "mtime_ns": 2},
        sidecar: {"size": 5, "mtime_ns": 1},
    }
    verification = verify_cache_entries([entry], filesystem=filesystem).entries[0]
    assert verification.candidate
    assert verification.shard_identity_changed
    assert verification.sidecar_identity_changed
