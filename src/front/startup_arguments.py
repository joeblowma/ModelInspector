"""Startup argument parsing shared by the GUI entry point.

Parsing lives here (not in the ``gui`` wrapper) so ``--help`` terminates
before any ``QApplication`` is created and the wrapper stays thin.
"""

import argparse
from pathlib import Path


def build_startup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gui.py",
        description="Model Inspector desktop application.",
    )
    parser.add_argument(
        "-s",
        "--settings",
        metavar="PATH",
        type=Path,
        help=(
            "Explicit settings JSONC location override; strongest precedence, "
            "applied before any settings load (overrides SMI_SETTINGS_PATH)"
        ),
    )
    parser.add_argument(
        "targets",
        nargs="*",
        metavar="FILE_OR_FOLDER",
        help="Optional model file or folder queued for inspection after startup",
    )
    return parser


def parse_startup_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    return build_startup_parser().parse_args(argv)


__all__ = ["build_startup_parser", "parse_startup_arguments"]
