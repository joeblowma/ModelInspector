"""Focused regression coverage for the Phase 2 backend contracts."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.cache_verifier import (
    ACTIVE,
    HISTORIC,
    CacheAvailability,
    verify_cache_entries,
)
from back.estimator import (
    facts_from_inspection,
    project_resources,
    runtime_configuration,
)
from back.theme_loader import (
    BUILTIN_THEME,
    list_themes,
    load_theme,
    parse_jsonc,
    validate_theme,
)


def _inspection() -> dict:
    return {
        "filepath": "not-a-vision-model.safetensors",
        "architecture": "LlamaForCausalLM",
        "model_type": "LLM",
        "total_params": "7B",
        "expert_count": 8,
        "expert_used_count": 2,
        "components": {},
        "arch_details": {
            "num_hidden_layers": 32,
            "hidden_size": 4096,
            "num_attention_heads": 32,
            "num_key_value_heads": 8,
            "max_position_embeddings": 8192,
            "rope_theta": 500000,
            "num_mtp_layers": 2,
        },
        "metadata": {"tool_use": True, "thinking": True},
    }


def test_jsonc_comments_and_trailing_commas_preserve_string_content() -> None:
    raw = r'''{
      // A URL should not be treated as a comment: https://example.invalid/x
      "url": "https://example.invalid/a//b",
      /* block comment */
      "values": [1, 2,],
    }'''
    assert parse_jsonc(raw) == {
        "url": "https://example.invalid/a//b",
        "values": [1, 2],
    }


def test_theme_schema_rejects_missing_and_invalid_colors() -> None:
    valid, errors = validate_theme({"id": "bad", "name": "Bad", "colors": {}})
    assert not valid
    assert any("missing required colors" in error for error in errors)
    assert BUILTIN_THEME.colors["background"].startswith("#")


def test_external_themes_are_enumerated_and_default_is_safe() -> None:
    ids = {theme.id for theme in list_themes()}
    assert {"default", "catppuccin", "cursor", "github", "gruvbox"} <= ids
    loaded = load_theme("catppuccin")
    assert loaded.theme.id == "catppuccin"
    assert not loaded.used_fallback
    fallback = load_theme("missing-theme-for-test")
    assert fallback.used_fallback
    assert fallback.theme.id == "default"


def test_facts_extract_dimensions_context_rope_mtp_and_capabilities() -> None:
    facts = facts_from_inspection(_inspection())
    assert facts.total_params == 7_000_000_000
    assert facts.layer_count == 32
    assert facts.expert_count == 8
    assert facts.active_expert_count == 2
    assert facts.max_context == 8192
    assert facts.rope["rope_theta"] == 500000
    assert facts.mtp["num_mtp_layers"] == 2
    assert facts.capabilities == ("Tool Use", "Thinking")
    assert facts.domains == ("LLM",)


def test_filename_alone_does_not_claim_a_domain_or_capability() -> None:
    facts = facts_from_inspection({"filepath": "vision-thinking-tools.safetensors"})
    assert facts.domains == ()
    assert facts.capabilities == ()


def test_projection_uses_explicit_dimensions_and_quantization() -> None:
    projection = project_resources(
        _inspection(),
        context_length=4096,
        batch_size=2,
        quantization="Q4_K_M",
        kv_cache_dtype="bf16",
    )
    assert projection.weight_bits == 4
    assert projection.kv_cache_bits == 16
    assert projection.context_length == 4096
    assert projection.batch_size == 2
    assert projection.kv_cache_bytes > 0
    assert projection.vram_bytes > projection.weight_bytes


def test_projection_records_conservative_fallbacks_when_metadata_is_missing() -> None:
    projection = project_resources({"total_params": 1_000_000})
    assert projection.context_length == 4096
    assert projection.kv_cache_bytes > 0
    assert any("fallback" in assumption for assumption in projection.assumptions)
    assert "Estimated VRAM:" in runtime_configuration(projection)


def test_cache_verifier_classifies_active_historic_and_changed_entries() -> None:
    entries = [
        {"identity": {"resolved_filepath": "active.bin", "file_size": 10, "mtime_ns": 2}},
        {"identity": {"resolved_filepath": "missing.bin", "file_size": 10, "mtime_ns": 2}},
        {"identity": {"resolved_filepath": "changed.bin", "file_size": 10, "mtime_ns": 2}},
    ]
    report = verify_cache_entries(
        entries,
        filesystem={
            "active.bin": {"size": 10, "mtime_ns": 2},
            "changed.bin": {"size": 11, "mtime_ns": 2},
        },
    )
    assert [item.classification for item in report.entries] == [ACTIVE, HISTORIC, ACTIVE]
    assert report.entries[0].action == "none"
    assert report.entries[1].action == "archive"
    assert report.entries[2].candidate
    assert report.entries[2].current_size == 11


def test_cache_verifier_handles_legacy_missing_identity_and_path_aliases() -> None:
    entry = {
        "data": {"filepath": "old-name.bin"},
        "identity": {"resolved_filepath": "canonical.bin"},
    }
    report = verify_cache_entries(
        [entry], filesystem={"canonical.bin": {"size": 12, "mtime_ns": 4}}
    )
    item = report.entries[0]
    assert item.classification == ACTIVE
    assert item.action == "refresh"
    assert item.candidate
    assert set(item.path_aliases) == {"old-name.bin", "canonical.bin"}


def test_cache_availability_is_conditional_and_serializable() -> None:
    report = verify_cache_entries(
        [{"filepath": "one.bin", "file_size": 1, "mtime_ns": 1}],
        filesystem={},
    )
    availability: CacheAvailability = report.availability
    assert availability.total_count == 1
    assert availability.active_count == 0
    assert availability.historic_count == 1
    assert availability.load_cache
    assert not availability.load_cache_all
    assert availability.load_cache_archived
    assert report.as_dict()["availability"]["Load Cache Archived"]["count"] == 1


def test_theme_can_load_by_explicit_path(tmp_path: Path) -> None:
    source = Path("assets/themes/github.jsonc")
    target = tmp_path / source.name
    target.write_text(source.read_text(encoding="utf-8"), encoding="utf-8")
    loaded = load_theme(target)
    assert loaded.theme.id == "github"


def test_vision_tower_keys_classify_as_mllm_without_mislabeling_text_models():
    from back.model_classification import classify_model_type, has_vision_component

    components = {
        "unet": False,
        "transformer": True,
        "vae": False,
        "text_encoder": False,
        "text_encoder_2": False,
        "lora": False,
    }
    components["vision"] = has_vision_component(
        [
            "model.vision_tower.vision_model.encoder.layers.0.self_attn.q_proj.weight",
            "model.vision_tower.vision_model.encoder.layers.0.self_attn.k_proj.weight",
        ]
    )

    assert components["vision"] is True
    assert classify_model_type(components, "Qwen2VLForConditionalGeneration") == "MLLM"
    assert has_vision_component(["model.layers.0.self_attn.q_proj.weight"]) is False


def test_partial_vision_roots_do_not_claim_an_mllm():
    from back.model_classification import has_vision_component

    assert not has_vision_component(
        [
            "model.vision_tower.marker.weight",
            "model.vision_tower.marker.bias",
        ]
    )
    assert not has_vision_component(
        [
            "visual.patch_embed.proj.weight",
            "visual.patch_embed.proj.bias",
        ]
    )


def test_pipeline_vision_flag_rejects_partial_vision_tower(monkeypatch, tmp_path):
    from back import inspection_pipeline

    tensor_info = {
        "model.layers.0.self_attn.q_proj.weight": {"dtype": "F16", "shape": [2, 2]},
        "model.layers.0.self_attn.k_proj.weight": {"dtype": "F16", "shape": [2, 2]},
        "model.vision_tower.marker.weight": {"dtype": "F16", "shape": [2, 2]},
        "model.vision_tower.marker.bias": {"dtype": "F16", "shape": [2]},
    }
    monkeypatch.setattr(inspection_pipeline, "get_cached_inspection", lambda *_: None)
    monkeypatch.setattr(
        inspection_pipeline,
        "read_model_header",
        lambda *_: ({}, tensor_info, 16),
    )
    monkeypatch.setattr(inspection_pipeline, "store_cached_inspection", lambda *_: None)

    result = inspection_pipeline.inspect_file(str(tmp_path / "partial.safetensors"))

    assert result["components"]["vision"] is False
    assert result["model_type"] != "MLLM"
