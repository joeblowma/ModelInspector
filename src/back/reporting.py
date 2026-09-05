"""Human-readable reports and ``.modelinfo`` compatibility wrappers.

The report printer intentionally consumes the same header tuple as the legacy
``inspect_model.print_report`` function.  It does not call the structured
inspection operation, which keeps report output independent from cache state
and allows callers that already have a header to print it directly.
"""

from collections import Counter
from pathlib import Path

from model_readers import analyze_tensors, model_format_for_path

from .architecture_metadata import detect_architecture
from .inspection_pipeline import inspect_file
from .model_classification import (
    _friendly_encoder_name,
    classify_model_type,
    format_params,
    format_size,
)
from .tensor_summary import DTYPE_BITS, DTYPE_FRIENDLY, _numeric_sort_key, detect_components


__all__ = [
    "print_report",
    "generate_modelinfo_dump",
    "generate_modelinfo_json",
    "write_modelinfo_dump",
    "write_modelinfo_json",
    "_inspect_and_write_modelinfo",
    "_resolve_display_path",
]


def _resolve_display_path(filepath: str) -> str:
    """Resolve an existing path for display without requiring it to exist."""
    try:
        return str(Path(filepath).resolve(strict=True))
    except OSError:
        return str(Path(filepath).absolute())


def _descriptor_bytes(descriptor: object) -> int | None:
    if not isinstance(descriptor, dict):
        return None
    value = descriptor.get("n_bytes")
    if value is None:
        offsets = descriptor.get("data_offsets")
        if isinstance(offsets, (list, tuple)) and len(offsets) == 2:
            try:
                value = int(offsets[1]) - int(offsets[0])
            except (TypeError, ValueError, OverflowError):
                value = None
    try:
        return max(0, int(value)) if value is not None else None
    except (TypeError, ValueError, OverflowError):
        return None


def _descriptor_shard_id(descriptor: object) -> int:
    if not isinstance(descriptor, dict):
        return 0
    try:
        return int(descriptor.get("shard_id", 0))
    except (TypeError, ValueError, OverflowError):
        return 0


def print_report(filepath: str, metadata: dict, tensor_info: dict, file_size: int):
    """Print the traditional terminal report for an already-read model header."""
    keys = sorted(tensor_info.keys(), key=_numeric_sort_key)
    dtypes, total_params, shapes = analyze_tensors(tensor_info)
    components = detect_components(keys)
    arch, arch_details = detect_architecture(
        keys, shapes, total_params, components, metadata
    )
    model_type = classify_model_type(components, arch)

    sep = "=" * 60
    print(f"\n{sep}")
    print("  MODEL INSPECTOR")
    print(sep)

    print(f"\n  File:           {Path(filepath).name}")
    print(f"  Path:           {filepath}")
    resolved_filepath = _resolve_display_path(filepath)
    if resolved_filepath != filepath:
        print(f"  Resolved path:  {resolved_filepath}")
    print(f"  File size:      {format_size(file_size)}")
    print(
        f"  Format:         {metadata.get('smi.format') or model_format_for_path(filepath)}"
    )
    if metadata.get("smi.quantization"):
        print(f"  Quantization:   {metadata['smi.quantization']}")
    print(f"  Tensor count:   {len(tensor_info)}")
    print(f"  Parameters:     {format_params(total_params)} ({total_params:,})")

    print(f"\n  Architecture:   {arch}")
    print(f"  Model type:     {model_type}")

    if arch_details:
        for key, value in arch_details.items():
            label = key.replace("_", " ").title()
            print(f"  {label + ':':<18}{value}")

    print("\n  Components detected:")
    comp_labels = {
        "unet": "UNet",
        "transformer": "Transformer / DiT",
        "vae": "VAE",
        "text_encoder": "Text Encoder (CLIP / T5)",
        "text_encoder_2": "Text Encoder 2",
        "lora": "LoRA layers",
    }
    any_found = False
    for key, label in comp_labels.items():
        if key == "text_encoders":
            continue
        if components[key]:
            print(f"    [x] {label}")
            any_found = True
    if components["text_encoders"]:
        any_found = True
        for enc_name, enc_count in sorted(components["text_encoders"].items()):
            friendly = _friendly_encoder_name(enc_name)
            print(f"    [x] Text Encoder: {friendly} ({enc_count} tensors)")
    if not any_found:
        print("    (none of the standard components detected)")

    print("\n  Precision / dtype distribution:")
    for dtype, count in dtypes.most_common():
        friendly = DTYPE_FRIENDLY.get(dtype, dtype)
        bits = DTYPE_BITS.get(dtype, "?")
        pct = count / len(tensor_info) * 100
        print(f"    {friendly:<20} {count:>6} tensors  ({pct:.1f}%)  [{bits}-bit]")

    if len(dtypes) == 1:
        only_dtype = list(dtypes.keys())[0]
        print(f"  >> Uniform precision: {DTYPE_FRIENDLY.get(only_dtype, only_dtype)}")
    elif len(dtypes) > 1:
        dominant_count = dtypes.most_common(1)[0][1]
        dominant_dtype = dtypes.most_common(1)[0][0]
        dominant_pct = dominant_count / len(tensor_info) * 100
        if dominant_pct >= 99.0:
            print(
                f"  >> Effectively {DTYPE_FRIENDLY.get(dominant_dtype, dominant_dtype)}"
                f" ({dominant_pct:.1f}%, {len(tensor_info) - dominant_count}"
                f" outlier tensor(s) in other dtype)"
            )
        else:
            print("  >> Mixed precision model")

    print("\n  Original tensor/block order:")
    for order, key in enumerate(tensor_info, 1):
        print(f"    {order:>6}. {key}")

    print("\n  Tensor/block details (sorted presentation):")
    for key in keys:
        descriptor = tensor_info.get(key, {})
        shape = descriptor.get("shape", []) if isinstance(descriptor, dict) else []
        dtype = descriptor.get("dtype", "?") if isinstance(descriptor, dict) else "?"
        n_bytes = _descriptor_bytes(descriptor)
        print(
            f"    {key}  {shape}  [{dtype}]  n_bytes={n_bytes if n_bytes is not None else '?'}"
            f"  shard_id={_descriptor_shard_id(descriptor)}"
        )

    if metadata:
        print("\n  Embedded metadata:")
        for metadata_key, metadata_value in sorted(metadata.items()):
            value_string = str(metadata_value)
            if len(value_string) > 120:
                value_string = value_string[:117] + "..."
            print(f"    {metadata_key}: {value_string}")

    print("\n  Top-level key prefixes (first 20):")
    prefixes = Counter()
    for key in keys:
        prefix = key.split(".")[0]
        if len(key.split(".")) > 1:
            prefix += "." + key.split(".")[1]
        prefixes[prefix] += 1
    for prefix, count in prefixes.most_common(20):
        print(f"    {prefix:<45} {count:>5} tensors")

    print(f"\n{sep}\n")


def generate_modelinfo_dump(filepath: str) -> str:
    """Generate a detailed text dump for one model file."""
    from modelinfo import generate_modelinfo_dump as _generate_modelinfo_dump

    return _generate_modelinfo_dump(filepath)


def generate_modelinfo_json(filepath: str, options: dict | None = None) -> str:
    """Generate pretty-printed ``.modelinfo`` JSON for one model file."""
    from modelinfo import generate_modelinfo_json as _generate_modelinfo_json

    return _generate_modelinfo_json(filepath, options=options)


def write_modelinfo_dump(filepath: str, resolve_output_path: bool = False) -> str:
    """Write a text ``.modelinfo`` file beside the inspected model."""
    from modelinfo import write_modelinfo_dump as _write_modelinfo_dump

    return _write_modelinfo_dump(filepath, resolve_output_path=resolve_output_path)


def write_modelinfo_json(
    filepath: str,
    options: dict | None = None,
    resolve_output_path: bool = False,
) -> str:
    """Write a JSON ``.modelinfo`` file beside the inspected model."""
    from modelinfo import write_modelinfo_json as _write_modelinfo_json

    return _write_modelinfo_json(
        filepath,
        options=options,
        resolve_output_path=resolve_output_path,
    )


def _inspect_and_write_modelinfo(
    filepath: str,
    options: dict,
    write_text: bool,
    write_json: bool,
    resolve_output_path: bool,
) -> dict:
    """Inspect a file and optionally write either modelinfo representation."""
    info = inspect_file(filepath, options=options)
    outputs = []
    if write_text:
        outputs.append(
            write_modelinfo_dump(filepath, resolve_output_path=resolve_output_path)
        )
    if write_json:
        outputs.append(
            write_modelinfo_json(
                filepath,
                options=options,
                resolve_output_path=resolve_output_path,
            )
        )
    if outputs:
        info["modelinfo_outputs"] = outputs
    return info
