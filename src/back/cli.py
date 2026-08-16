"""Command-line entry point for Model Inspector.

Argument handling, target discovery, and worker scheduling live here so the
inspection and reporting modules remain reusable by the GUI and by scripts.
The order of collected results follows the order returned by target discovery,
even when independent inspections run concurrently.
"""

import argparse
import json
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Iterable

from model_readers import (
    CHECKPOINT_FORMAT_WARNING,
    SUPPORTED_MODEL_EXTENSIONS,
    iter_checkpoint_paths,
    iter_model_paths,
    read_model_header,
)

from .inspection_pipeline import inspect_file
from .reporting import (
    _inspect_and_write_modelinfo,
    generate_modelinfo_dump,
    print_report,
)


__all__ = [
    "main",
    "_configure_stdio_encoding",
    "_iter_model_paths",
    "_build_arg_parser",
]


def _configure_stdio_encoding():
    """Make terminal output robust for model metadata containing Unicode."""
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore


def _iter_model_paths(targets: Iterable[str], recursive: bool) -> list[str]:
    """Return supported model files in the requested target order."""
    return iter_model_paths(targets, recursive, extensions=SUPPORTED_MODEL_EXTENSIONS)


def _build_arg_parser() -> argparse.ArgumentParser:
    """Build the public CLI parser and preserve its historical options."""
    parser = argparse.ArgumentParser(
        prog="inspect_model.py",
        description="Inspect model files from file and folder targets.",
    )
    parser.add_argument(
        "targets",
        nargs="+",
        help="File(s) or folder(s) to inspect",
    )
    parser.add_argument(
        "-r",
        "--recursive",
        action="store_true",
        help="Recurse into subfolders for directory targets",
    )
    parser.add_argument(
        "--allow-filename-alias-detection",
        action="store_true",
        help="Allow filename token fallback aliases for SDXL-family names",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Print JSON output (single object for one file, list for many)",
    )
    parser.add_argument(
        "--dump-keys",
        action="store_true",
        help="Print detailed key-dump report text for each file",
    )
    parser.add_argument(
        "--write-modelinfo",
        action="store_true",
        help="Write .modelinfo files next to each inspected model",
    )
    parser.add_argument(
        "--write-modelinfo-json",
        action="store_true",
        help="Write .modelinfo.json files next to each inspected model",
    )
    parser.add_argument(
        "--resolve-output-path",
        action="store_true",
        help=(
            "Write .modelinfo outputs beside the resolved target path instead of "
            "the user-provided path"
        ),
    )
    parser.add_argument(
        "--threads",
        type=int,
        default=1,
        help="Number of worker threads for independent file inspection (default: 1)",
    )
    return parser


def main(argv=None):
    """Run the CLI and return its historical integer exit status."""
    _configure_stdio_encoding()
    parser = _build_arg_parser()
    args = parser.parse_args(argv)

    paths = _iter_model_paths(args.targets, args.recursive)
    checkpoint_paths = iter_checkpoint_paths(args.targets, args.recursive)
    if checkpoint_paths:
        print(
            f"[WARN] {CHECKPOINT_FORMAT_WARNING} Ignored {len(checkpoint_paths)} checkpoint file(s).",
            file=sys.stderr,
        )
    if not paths:
        formats = ", ".join(SUPPORTED_MODEL_EXTENSIONS)
        print(
            f"No supported model files found ({formats}) in provided targets.",
            file=sys.stderr,
        )
        return 1

    if args.dump_keys:
        for filepath in paths:
            try:
                print(generate_modelinfo_dump(filepath))
            except Exception as error:
                print(f"[ERROR] {filepath}: {error}", file=sys.stderr)
        return 0

    inspect_options = {
        "allow_filename_alias_detection": args.allow_filename_alias_detection
    }
    thread_count = max(1, min(int(args.threads or 1), len(paths)))
    results_by_input_path = {}
    if thread_count == 1:
        for filepath in paths:
            try:
                results_by_input_path[filepath] = _inspect_and_write_modelinfo(
                    filepath,
                    inspect_options,
                    args.write_modelinfo,
                    args.write_modelinfo_json,
                    args.resolve_output_path,
                )
            except Exception as error:
                print(f"[ERROR] {filepath}: {error}", file=sys.stderr)
    else:
        with ThreadPoolExecutor(max_workers=thread_count) as executor:
            future_to_path = {
                executor.submit(
                    _inspect_and_write_modelinfo,
                    filepath,
                    inspect_options,
                    args.write_modelinfo,
                    args.write_modelinfo_json,
                    args.resolve_output_path,
                ): filepath
                for filepath in paths
            }
            for future in as_completed(future_to_path):
                filepath = future_to_path[future]
                try:
                    results_by_input_path[filepath] = future.result()
                except Exception as error:
                    print(f"[ERROR] {filepath}: {error}", file=sys.stderr)
    results = [
        results_by_input_path[filepath]
        for filepath in paths
        if filepath in results_by_input_path
    ]

    if not results:
        return 1

    if args.json:
        if len(results) == 1:
            print(json.dumps(results[0], indent=2, ensure_ascii=False))
        else:
            print(json.dumps(results, indent=2, ensure_ascii=False))
        return 0

    results_by_path = {result.get("filepath"): result for result in results}
    for filepath in paths:
        try:
            metadata, tensor_info, file_size = read_model_header(filepath)
            print_report(filepath, metadata, tensor_info, file_size)
            outputs = results_by_path.get(filepath, {}).get("modelinfo_outputs") or []
            if outputs:
                print("  Modelinfo output:")
                for output_path in outputs:
                    print(f"    {output_path}")
        except Exception as error:
            print(f"[ERROR] {filepath}: {error}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
