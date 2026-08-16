#!/usr/bin/env python3
"""Application data paths for portable defaults."""

import os
import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def app_data_dir() -> Path:
    override = os.environ.get("SMI_DATA_DIR")
    if override:
        return Path(override)
    return app_base_dir() / ".model-inspector"


def cache_dir() -> Path:
    override = os.environ.get("SMI_CACHE_DIR")
    if override:
        return Path(override)
    return app_data_dir() / "cache"


def settings_path() -> Path:
    override = os.environ.get("SMI_SETTINGS_PATH")
    if override:
        requested = Path(override)
        return requested.with_suffix(".jsonc") if requested.suffix.lower() == ".ini" else requested
    return app_data_dir() / "settings.jsonc"


def legacy_settings_path() -> Path:
    """The pre-JSONC QSettings location, retained solely for migration."""
    override = os.environ.get("SMI_SETTINGS_PATH")
    return Path(override) if override and Path(override).suffix.lower() == ".ini" else app_data_dir() / "settings.ini"
