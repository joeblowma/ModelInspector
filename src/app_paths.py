#!/usr/bin/env python3
"""Application data paths for portable defaults."""

import os
import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    source_dir = Path(__file__).resolve().parent
    if source_dir.name == "src":
        return source_dir.parent
    return source_dir


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
        return Path(override)
    return app_data_dir() / "settings.ini"
