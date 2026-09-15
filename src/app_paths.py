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

    PyInstaller extracts one-file resources below ``sys._MEIPASS``.  A wheel
    install places ``app_paths.py`` in site-packages with ``assets`` beside
    it, while a source checkout keeps the bundled assets at the repository
    root beside ``src``.  Keeping this distinction here prevents each
    GUI/backend caller from growing its own packaging-specific path
    calculation.
    """
    extracted_dir = getattr(sys, "_MEIPASS", None)
    if extracted_dir:
        return Path(extracted_dir)
    base = app_base_dir()
    if getattr(sys, "frozen", False):
        return base
    # Installed layout: assets sit beside app_paths.py in site-packages.
    # Checkout layout: assets live at the repository root above ``src``.
    if (base / "assets").is_dir():
        return base
    return base.parent


def default_output_dir() -> Path:
    """Default user-visible save/output location (reports, moved files).

    Deliberately independent from :func:`app_data_dir`: existing installs
    keep their legacy settings/cache in place while save dialogs still
    default to the per-user home folder.  ``SMI_OUTPUT_DIR`` overrides
    explicitly.
    """
    override = os.environ.get("SMI_OUTPUT_DIR")
    if override:
        return Path(override)
    return Path.home() / ".local" / "ModelInspector"


def ensure_output_dir() -> Path:
    """Return the writable default output directory, creating it if needed.

    Save dialogs must never silently open in the process CWD when the default
    output directory does not exist yet, so a missing directory is created
    here.  When creation fails (e.g. a permission error), the user home
    directory is the fallback so the dialog still opens somewhere sensible.
    """
    target = default_output_dir()
    try:
        target.mkdir(parents=True, exist_ok=True)
        return target
    except OSError:
        return Path.home()


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
    # Existing installs keep their in-place data; fresh installs default to
    # the per-user ~/.local/ModelInspector location.
    legacy = app_base_dir() / ".model-inspector"
    if legacy.is_dir():
        return legacy
    return Path.home() / ".local" / "ModelInspector"


def cache_dir() -> Path:
    """Root for all application caches (inspection, sidecars, dumps, scans)."""
    override = os.environ.get("SMI_CACHE_DIR")
    if override:
        return Path(override)
    return app_data_dir() / "cache"


def model_cache_dir() -> Path:
    """Directory for the primary inspection cache (index/entries/data).

    ``SMI_MODEL_CACHE_DIR`` relocates only the model cache, leaving ancillary
    caches (sidecars, raw dumps, directory scans) at :func:`cache_dir`.
    """
    override = os.environ.get("SMI_MODEL_CACHE_DIR")
    if override:
        return Path(override)
    return cache_dir()


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
