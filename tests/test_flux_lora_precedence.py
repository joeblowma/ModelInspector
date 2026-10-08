"""Regression coverage for ambiguous FLUX/Qwen adapter headers."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.architecture_metadata import detect_architecture


def _components(*, lora: bool = True) -> dict:
    return {
        "unet": False,
        "transformer": True,
        "vae": False,
        "text_encoder": False,
        "text_encoder_2": False,
        "lora": lora,
    }


def _flux_header(*, rank: int = 64, dual_blocks: int = 19, single_blocks: int = 38):
    """Build a header-only representation of the ambiguous adapter shape."""
    shapes = {}
    keys = []

    def add_weight(path: str, shape: list[int]) -> None:
        keys.append(path)
        shapes[path] = shape

    for index in range(dual_blocks):
        for projection in ("add_k_proj", "add_q_proj"):
            prefix = f"transformer.transformer_blocks.{index}.attn.{projection}"
            add_weight(f"{prefix}.lora_A.weight", [rank, 4096])
            add_weight(f"{prefix}.lora_B.weight", [4096, rank])

    for index in range(single_blocks):
        prefix = f"transformer.single_transformer_blocks.{index}.attn.to_q"
        add_weight(f"{prefix}.lora_A.weight", [rank, 3072])
        add_weight(f"{prefix}.lora_B.weight", [3072, rank])

    return keys, shapes


def _detect(keys, shapes, *, components=None, metadata=None):
    return detect_architecture(
        keys,
        shapes,
        sum(shape[0] * shape[1] for shape in shapes.values()),
        components or _components(),
        metadata or {},
    )


def test_standard_flux_lora_header_beats_qwen_edit_heuristic() -> None:
    keys, shapes = _flux_header()

    architecture, details = _detect(keys, shapes)

    assert architecture == "Flux.1 Dev"
    assert details["lora_rank"] == 64
    assert details["double_blocks"] == 19
    assert details["single_blocks"] == 38
    assert details["adapter_type"] == "LoRA"


def test_nearby_rank_or_block_mismatch_does_not_claim_flux() -> None:
    rank_mismatch = _flux_header(rank=32)
    block_mismatch = _flux_header(dual_blocks=18)

    assert _detect(*rank_mismatch)[0] == "Qwen Edit"
    assert _detect(*block_mismatch)[0] == "Qwen Edit"


def test_generic_qwen_edit_header_still_uses_qwen_detection() -> None:
    keys = [
        "transformer.transformer_blocks.0.attn.add_k_proj.lora_A.weight",
        "transformer.transformer_blocks.0.attn.add_k_proj.lora_B.weight",
    ]
    shapes = {keys[0]: [64, 4096], keys[1]: [4096, 64]}

    assert _detect(keys, shapes)[0] == "Qwen Edit"
