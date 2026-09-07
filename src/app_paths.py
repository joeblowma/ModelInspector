#!/usr/bin/env python3
"""Application data paths for portable defaults."""

import os
import sys
from pathlib import Path


def app_base_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def resource_base_dir() -> Path:
    """Return the root containing read-only application resources.

    PyInstaller extracts one-file resources below ``sys._MEIPASS``.  During
    normal Python execution the repository root contains the bundled assets
    beside ``src``.  Keeping this distinction here prevents each GUI/backend
    caller from growing its own packaging-specific path calculation.
    """
    extracted_dir = getattr(sys, "_MEIPASS", None)
    if extracted_dir:
        return Path(extracted_dir)
    return app_base_dir() if getattr(sys, "frozen", False) else app_base_dir().parent


def resource_path(*parts: str | os.PathLike[str]) -> Path:
    """Resolve a path relative to the application resource root."""
    return resource_base_dir().joinpath(*parts)


def asset_path(*parts: str | os.PathLike[str]) -> Path:
    """Resolve a path below the bundled ``assets`` directory."""
    return resource_path("assets", *parts)


def themes_dir() -> Path:
    """Return the directory containing bundled JSONC themes."""
    return asset_path("themes")


def user_themes_dir() -> Path:
    """Return the writable user theme directory below application data."""
    return app_data_dir() / "themes"


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
