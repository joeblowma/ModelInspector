#!/usr/bin/env python3
"""Legacy compatibility facade and command-line bootstrap for Model Inspector.

Inspection logic lives in :mod:`back`; the imports below preserve the historic
``inspect_model`` API for GUI code and third-party scripts.
"""

from back.adapter_detection import _collect_lora_up_dims, _detect_lora_rank, _max_block_index, detect_adapter_type
from back.architecture_keys import FINGERPRINTS, _detect_from_keys
from back.architecture_metadata import _build_metadata_blob, _detect_from_metadata, detect_architecture
from back.architecture_variants import (
    _detect_flux_variant,
    _detect_from_dims,
    _detect_sd_variant,
    _detect_sdxl_pony_ilxl,
    _detect_wan_variant,
    _detect_zimage_variant,
    _zimage_label,
)
from back.cli import _build_arg_parser, _configure_stdio_encoding, _iter_model_paths, main
from back.inspection_pipeline import _resolve_display_path, inspect_file
from back.model_classification import (
    _apply_filename_alias_detection,
    _extract_training_meta,
    _friendly_encoder_name,
    _safe_json_loads,
    classify_model_type,
    detect_moe,
    format_params,
    format_size,
)
from back.reporting import (
    _inspect_and_write_modelinfo,
    generate_modelinfo_dump,
    generate_modelinfo_json,
    print_report,
    write_modelinfo_dump,
    write_modelinfo_json,
)
from back.tensor_summary import (
    DTYPE_BITS,
    DTYPE_FRIENDLY,
    _numeric_sort_key,
    _summarize_dtype_mix,
    _tensor_component_bucket,
    analyze_component_precisions,
    build_component_precision_map,
    build_component_precision_summary,
    detect_components,
)


__all__ = [
    "DTYPE_BITS", "DTYPE_FRIENDLY", "FINGERPRINTS", "_apply_filename_alias_detection",
    "_build_arg_parser", "_build_metadata_blob", "_collect_lora_up_dims", "_configure_stdio_encoding",
    "_detect_flux_variant", "_detect_from_dims", "_detect_from_keys", "_detect_from_metadata",
    "_detect_lora_rank", "_detect_sd_variant", "_detect_sdxl_pony_ilxl", "_detect_wan_variant",
    "_detect_zimage_variant", "_extract_training_meta", "_friendly_encoder_name", "_inspect_and_write_modelinfo",
    "_iter_model_paths", "_max_block_index", "_numeric_sort_key", "_resolve_display_path", "_safe_json_loads",
    "_summarize_dtype_mix", "_tensor_component_bucket", "_zimage_label", "analyze_component_precisions",
    "build_component_precision_map", "build_component_precision_summary", "classify_model_type", "detect_adapter_type",
    "detect_architecture", "detect_components", "detect_moe", "format_params", "format_size",
    "generate_modelinfo_dump", "generate_modelinfo_json", "inspect_file", "main", "print_report",
    "write_modelinfo_dump", "write_modelinfo_json",
]


if __name__ == "__main__":
    raise SystemExit(main())
