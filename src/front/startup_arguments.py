"""Startup argument parsing shared by the GUI entry point.

Parsing lives here (not in the ``gui`` wrapper) so ``--help`` terminates
before any ``QApplication`` is created and the wrapper stays thin.
"""

import argparse
import sys
from pathlib import Path


def _prog_name() -> str:
    """Program label for help text: the executable name in frozen builds."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).name
    return "gui.py"


def build_startup_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=_prog_name(),
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
        "--cachedir",
        metavar="PATH",
        type=Path,
        help=(
            "Relocate ALL application caches to PATH for this run "
            "(sets SMI_CACHE_DIR; not persisted)"
        ),
    )
    parser.add_argument(
        "--cache",
        metavar="PATH",
        type=Path,
        help=(
            "Select the model-cache directory (sets SMI_MODEL_CACHE_DIR) and "
            "remember it in settings history; the most recently used directory "
            "becomes the default on the next launch"
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


def help_requested(argv: list[str] | None = None) -> bool:
    """Return True when the argument list asks for help."""
    raw = list(sys.argv[1:] if argv is None else argv)
    return "-h" in raw or "--help" in raw


def format_help() -> str:
    """Return the parser help text without printing or exiting."""
    return build_startup_parser().format_help()


__all__ = [
    "build_startup_parser",
    "format_help",
    "help_requested",
    "parse_startup_arguments",
]
