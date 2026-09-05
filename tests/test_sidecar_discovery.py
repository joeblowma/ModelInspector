import json
from pathlib import Path
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back import inspection_pipeline
from back.sidecar_discovery import discover_sidecars
from model_readers import iter_model_paths


def _write_safetensors(path: Path, name: str) -> None:
    raw = json.dumps({name: {"dtype": "F16", "shape": [2], "data_offsets": [0, 4]}}).encode()
    path.write_bytes(struct.pack("<Q", len(raw)) + raw + b"data")


def test_sidecars_use_conservative_roles_and_do_not_become_primary_paths(tmp_path):
    primary = tmp_path / "vision-model.safetensors"
    mmproj = tmp_path / "vision-model-mmproj.safetensors"
    draft = tmp_path / "vision-model-draft.safetensors"
    unrelated = tmp_path / "vision-model-drafting.safetensors"
    for path, name in ((primary, "main"), (mmproj, "projection"), (draft, "draft"), (unrelated, "noise")):
        _write_safetensors(path, name)

    records = discover_sidecars(primary)
    assert [(record.role, Path(record.path).name) for record in records] == [
        ("mmproj", mmproj.name),
        ("draft", draft.name),
    ]
    assert iter_model_paths([str(tmp_path)], recursive=False) == [
        str(primary),
        str(unrelated),
    ]


def test_pipeline_attaches_full_sidecar_records_and_compact_identities(monkeypatch, tmp_path):
    primary = tmp_path / "model.safetensors"
    sidecar = tmp_path / "model-mmproj.safetensors"
    _write_safetensors(primary, "main")
    _write_safetensors(sidecar, "projection")
    monkeypatch.setattr(inspection_pipeline, "get_cached_inspection", lambda *_: None)
    monkeypatch.setattr(inspection_pipeline, "store_cached_inspection", lambda *_: None)

    result = inspection_pipeline.inspect_file(str(primary))

    assert result["sidecar_roles"] == ["mmproj"]
    assert result["sidecar_identities"][0]["role"] == "mmproj"
    assert result["sidecars"][0]["sidecar_role"] == "mmproj"
    assert result["sidecars"][0]["filepath"] == str(sidecar.resolve())
    assert "sidecars" not in result["sidecars"][0]


def test_all_roles_keep_duplicates_and_bare_role_models_are_primary_candidates(tmp_path):
    primary = tmp_path / "model.safetensors"
    bare_eagle = tmp_path / "eagle.safetensors"
    roles = ["mmproj", "dflash", "dspark", "eagle", "draft", "mtp"]
    _write_safetensors(primary, "main")
    _write_safetensors(bare_eagle, "standalone")
    for role in roles:
        _write_safetensors(tmp_path / f"model-{role}.safetensors", role)
    _write_safetensors(tmp_path / "model-mmproj-f16.safetensors", "projection")

    records = discover_sidecars(primary)
    assert [record.role for record in records] == ["mmproj", "mmproj", *roles[1:]]
    assert [Path(record.path).name for record in records[:2]] == [
        "model-mmproj-f16.safetensors", "model-mmproj.safetensors"
    ]
    assert str(bare_eagle) in iter_model_paths([str(tmp_path)], recursive=False)
