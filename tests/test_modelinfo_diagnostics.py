"""Header-only diagnostic coverage for text and JSON ``.modelinfo`` output."""

from __future__ import annotations

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import modelinfo
from back.modelinfo_diagnostics import safe_metadata


def test_safe_metadata_redacts_credentials_without_tokenizer_overreach() -> None:
    value = {
        "tokenizer.chat_template": "{{ user }}",
        "token_types": ["bos"],
        "num_tokens": 100,
        "bos_token_id": 1,
        "general.architecture": "llama",
        "api_key": "SECRET",
        "token": "SECRET",
        "access_token": "SECRET",
        "password": "SECRET",
        "passes": 5,
        "secret": "SECRET",
    }
    redacted = safe_metadata(value)
    assert redacted["tokenizer.chat_template"] == "{{ user }}"
    assert redacted["token_types"] == ["bos"]
    assert redacted["num_tokens"] == 100
    assert redacted["bos_token_id"] == 1
    assert redacted["api_key"] == "[redacted]"
    assert redacted["token"] == "[redacted]"
    assert redacted["access_token"] == "[redacted]"
    assert redacted["password"] == "[redacted]"
    assert redacted["passes"] == 5
    assert redacted["secret"] == "[redacted]"


def test_unknown_header_diagnostics_are_consistent_and_reuse_inspection(monkeypatch) -> None:
    tensor_info = {"opaque.weight": {"dtype": "F16", "shape": [2, 3]}}
    inspection = {
        "format": "SAFETENSORS",
        "architecture": "Unknown",
        "model_type": "Unknown",
        "capability_facts": {
            "domain": None,
            "capabilities": ["tools", "thinking"],
            "evidence": {
                "domain": ["tensor header:opaque"],
                "tools": ["config.json:tool_calls"],
                "thinking": ["template marker (weak)"],
            },
            "evidence_strength": {"tools": "strong", "thinking": "weak"},
        },
        "shard_manifest": {"member_count": 2, "expected_count": 2},
        "companion_identities": [{"path": "config.json", "exists": True}],
    }
    monkeypatch.setattr(
        modelinfo,
        "_read_header_or_cached",
        lambda _filepath, options=None: ({"smi.format": "SAFETENSORS", "api_key": "nope"}, tensor_info, 12),
    )
    monkeypatch.setattr(
        modelinfo,
        "inspect_file",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("inspection repeated")),
    )

    text = modelinfo.generate_modelinfo_dump("unknown.safetensors", inspection=inspection)
    data = modelinfo.build_modelinfo_json_data("unknown.safetensors", inspection=inspection)

    assert "Header-only diagnosis:" in text
    assert "Architecture: Unknown" in text
    assert "Model type: Unknown" in text
    assert "Capabilities: tools" in text
    assert "Dtypes: F16 (1)" in text
    assert "Shards: 2/2" in text
    assert "Companion files: config.json" in text
    assert "Fingerprint substring" not in text
    assert "nope" not in text
    assert data["diagnostics"]["architecture"] == "Unknown"
    assert data["diagnostics"]["model_type"] == "Unknown"
    assert data["diagnostics"]["capabilities"] == ["tools"]
    assert data["diagnostics"]["evidence"]["tools"] == ["config.json:tool_calls"]
    assert data["diagnostics"]["shard_manifest"]["member_count"] == 2
    assert data["diagnostics"]["companion_files"] == [{"path": "config.json", "exists": True}]
    assert data["metadata"]["api_key"] == "[redacted]"
