"""Conservative Think/Tool/VLM evidence regressions for capability facts."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.capability_facts import build_capability_facts


def _keys() -> list[str]:
    return ["model.embed_tokens.weight", "model.layers.0.self_attn.q_proj.weight"]


def test_structural_template_markers_are_strong() -> None:
    companion = {
        "chat_templates": [
            {
                "source": "chat_template.jinja",
                "text": (
                    "{% if enable_thinking %}<think>{% endif %}"
                    "{% if tools %}<|tool|>{{ tool_call_id }}{% endif %}"
                ),
            }
        ]
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["capabilities"] == ["thinking", "tools"]
    assert facts["evidence_strength"] == {"thinking": "strong", "tools": "strong"}
    assert facts["evidence"]["thinking"] == ["chat_template.jinja:thinking marker"]
    assert facts["evidence"]["tools"] == ["chat_template.jinja:tool marker"]


def test_bare_prose_is_weak_and_comments_and_negation_are_ignored() -> None:
    companion = {
        "chat_templates": [
            {
                "source": "chat_template.jinja",
                "text": (
                    "{# thinking is disabled in this build #}"
                    "You may use tools, but do not use reasoning traces."
                ),
            }
        ]
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["capabilities"] == ["tools"]
    assert facts["evidence_strength"] == {"tools": "weak"}
    assert facts["evidence"]["tools"] == ["chat_template.jinja:tool marker (weak)"]


def test_explicit_negative_config_flags_are_not_capabilities() -> None:
    companion = {
        "config": {"supports_tools": False, "thinking": "not supported"},
        "tokenizer_config": {"chat_template": "Plain chat, no special tags."},
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["capabilities"] == []
    assert facts["evidence_strength"] == {}


def test_processor_image_processor_is_vision_evidence() -> None:
    companion = {
        "processor_config": {"image_processor_type": "CLIPImageProcessor"}
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["domain"] == "VLM"
    assert "processor_config.json:image_processor_type" in facts["evidence"]["domain"]


def test_multimodal_word_alone_does_not_imply_other_modalities() -> None:
    facts = build_capability_facts(
        _keys(),
        {"general.architecture": "MultimodalLlamaForCausalLM"},
        {},
        "MultimodalLlamaForCausalLM",
        {},
    )

    assert facts["domain"] == "LLM"


def test_omni_architecture_remains_other_modality() -> None:
    facts = build_capability_facts(
        _keys(),
        {"general.architecture": "qwen2_5_omni"},
        {},
        "Qwen2.5-Omni",
        {},
    )

    assert facts["domain"] == "MLM"


def test_diffusion_components_with_an_llm_text_encoder_are_not_language_models() -> None:
    facts = build_capability_facts(
        ["text_encoders.qwen3_4b.model.layers.0.self_attn.q_proj.weight"],
        {},
        {
            "config": {
                "text_config": {"num_hidden_layers": 28},
                "audio_config": {"num_hidden_layers": 12},
            }
        },
        "LTX 2",
        {"unet": True, "text_encoder": True},
    )

    assert facts["domain"] is None


def test_qwen_image_diffusion_is_not_language_while_qwen35_stays_llm() -> None:
    for architecture in ("Qwen Image", "Qwen Image 2.1", "Qwen Image 2.1 VAE"):
        diffusion = build_capability_facts(
            ["transformer_blocks.0.img_mlp.gate_up.weight"],
            {},
            {},
            architecture,
            {},
        )
        assert diffusion["domain"] is None
        assert diffusion["capabilities"] == []

    prompt_enhancer = build_capability_facts(
        _keys(),
        {"general.architecture": "qwen35"},
        {},
        "qwen35",
        {},
    )
    assert prompt_enhancer["domain"] == "LLM"


def test_false_containers_and_arbitrary_nested_data_are_not_capabilities() -> None:
    companion = {
        "config": {
            "supports_tools": {"enabled": False},
            "thinking": ["disabled"],
            "tools": {"nested": {"deep": True}},
            "function_calling": {"mode": "auto"},
        }
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["capabilities"] == []
    assert facts["evidence_strength"] == {}


def test_positive_schema_leaf_is_still_strong_evidence() -> None:
    companion = {
        "config": {
            "supports_tools": {"enabled": True},
            "thinking": ["supported"],
        }
    }

    facts = build_capability_facts(_keys(), {}, companion, "LlamaForCausalLM", {})

    assert facts["capabilities"] == ["thinking", "tools"]
    assert facts["evidence_strength"] == {"thinking": "strong", "tools": "strong"}


def test_no_tools_string_and_postfix_negation_are_negative() -> None:
    config_facts = build_capability_facts(
        _keys(),
        {},
        {"config": {"supports_tools": "no tools"}},
        "LlamaForCausalLM",
        {},
    )
    assert config_facts["capabilities"] == []

    template_facts = build_capability_facts(
        _keys(),
        {},
        {
            "chat_templates": [
                {"source": "t", "text": "This template does not support tools"}
            ]
        },
        "LlamaForCausalLM",
        {},
    )
    assert template_facts["capabilities"] == []
    assert template_facts["evidence_strength"] == {}
