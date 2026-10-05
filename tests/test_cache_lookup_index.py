from pathlib import Path

import model_cache
from back.companion_discovery import companion_identities, discover_companion_metadata


def test_cached_inspection_lookup_skips_unused_index_load(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"cached model")
    options = {"allow_filename_alias_detection": True}
    companions = companion_identities(discover_companion_metadata(model))
    cached = {
        "filepath": str(model),
        "filename": model.name,
        "format": "SAFETENSORS",
        "marker": "persisted result",
        "companion_identities": companions,
    }
    model_cache.store_cached_inspection(str(model), cached, options)
    entry = model_cache._read_entry(
        model_cache._entry_id(model_cache._cache_key(str(model), options))
    )
    assert entry["data"]["companion_identities"] == companions

    def unexpected_index_load():
        raise AssertionError("direct entry lookup must not load the cache index")

    monkeypatch.setattr(model_cache, "_load_index", unexpected_index_load)

    result = model_cache.get_cached_inspection(str(model), options)

    assert result is not None
    assert result["marker"] == "persisted result"
    assert result["filepath"] == str(model)
    assert model_cache.get_cached_inspection(
        str(model), {"allow_filename_alias_detection": False}
    ) is None

    model.write_bytes(b"changed model content")
    assert model_cache.get_cached_inspection(str(model), options) is None
