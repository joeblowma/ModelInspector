"""Weak capability evidence must not become a definite report/fact."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.estimator import facts_from_inspection
from back.reporting import print_report


def _tensor_info() -> dict:
    return {"block.0.weight": {"dtype": "F16", "shape": [2, 2], "n_bytes": 8}}


def _inspection() -> dict:
    return {
        "architecture": "LlamaForCausalLM",
        "model_type": "LLM",
        "capability_facts": {
            "domain": "LLM",
            "capabilities": ["thinking", "tools"],
            "evidence": {
                "thinking": ["chat_template.jinja:thinking marker (weak)"],
                "tools": ["config.json:supports_tools"],
            },
            "evidence_strength": {"thinking": "weak", "tools": "strong"},
        },
    }


def test_terminal_report_suppresses_weak_capabilities(capsys) -> None:
    print_report("model.safetensors", {}, _tensor_info(), 8, inspection=_inspection())
    output = capsys.readouterr().out

    assert "Capabilities:   tools" in output
    assert "thinking" not in output


def test_terminal_report_keeps_legacy_capabilities_without_strength(capsys) -> None:
    print_report(
        "model.safetensors",
        {},
        _tensor_info(),
        8,
        inspection={
            "architecture": "Llama",
            "capability_facts": {"domain": "LLM", "capabilities": ["tools"]},
        },
    )
    output = capsys.readouterr().out

    assert "Capabilities:   tools" in output


def test_estimator_agrees_with_the_report_projection() -> None:
    facts = facts_from_inspection(_inspection())

    assert facts.capabilities == ("Tool Use",)
    assert facts.evidence.get("Tool Use") == ("config.json:supports_tools",)
    assert "Thinking" not in facts.evidence