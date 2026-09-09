"""Scoped classification for standalone GGUF CLIP projectors."""

from __future__ import annotations

import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back import inspection_pipeline
from back.model_classification import classify_model_type


def test_clip_mmproj_gguf_is_projector_even_with_vision_components() -> None:
    assert (
        classify_model_type(
            {"vision": True},
            "clip",
            "models/CLIP-MMPROJ.GGUF",
            "GGUF",
        )
        == "mmproj"
    )


def test_projector_detection_is_scoped_to_clip_gguf_filename_evidence() -> None:
    assert classify_model_type({}, "clip", "models/clip.gguf") == "Unknown"
    assert (
        classify_model_type({}, "llama", "models/llama-mmproj.gguf", "GGUF")
        == "Unknown"
    )
    assert (
        classify_model_type({}, "clip", "models/clip-mmproj.safetensors", "SAFETENSORS")
        == "Unknown"
    )
    assert (
        classify_model_type({}, "CLIPVisionModel", "models/clip-mmproj.gguf", "GGUF")
        == "Unknown"
    )


def _cached_entry(cache_dir: Path, filepath: Path) -> tuple[Path, dict]:
    for entry_path in (cache_dir / "entries").glob("*.json"):
        entry = json.loads(entry_path.read_text(encoding="utf-8"))
        if entry.get("data", {}).get("filepath") == str(filepath):
            return entry_path, entry
    raise AssertionError("inspection cache entry was not written")


def test_pipeline_classifies_clip_mmproj_and_upgrades_cached_unknown(
    monkeypatch, tmp_path: Path
) -> None:
    cache_dir = tmp_path / "cache"
    monkeypatch.setenv("SMI_CACHE_DIR", str(cache_dir))
    monkeypatch.delenv("SMI_CACHE_PATH", raising=False)
    model = tmp_path / "vision-MmPrOj.GgUf"
    model.touch()

    tensor_info = {
        "mmproj.0.weight": {"dtype": "F16", "shape": [8, 8]},
        "mmproj.1.weight": {"dtype": "F16", "shape": [8, 8]},
    }
    monkeypatch.setattr(
        inspection_pipeline,
        "read_model_header",
        lambda *_: ({"general.architecture": "clip"}, tensor_info, model.stat().st_size),
    )

    first = inspection_pipeline.inspect_file(str(model))
    assert first["architecture"] == "clip"
    assert first["model_type"] == "mmproj"
    assert first["capability_facts"]["domain"] is None

    entry_path, entry = _cached_entry(cache_dir, model)
    entry["data"]["model_type"] = "Unknown"
    entry_path.write_text(json.dumps(entry), encoding="utf-8")

    refreshed = inspection_pipeline.inspect_file(str(model))
    assert refreshed["model_type"] == "mmproj"
    persisted = json.loads(entry_path.read_text(encoding="utf-8"))
    assert persisted["data"]["model_type"] == "mmproj"
