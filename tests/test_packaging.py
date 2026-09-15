# pyright: reportUnknownMemberType=false
"""Packaging contract for the pre-release wheel and CLI entry points.

Static checks only: the wheel itself is exercised by CI, so this stays fast and
offline-friendly while still catching metadata regressions.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"


def _project() -> dict:
    with PYPROJECT.open("rb") as handle:
        return tomllib.load(handle)


def test_build_backend_is_declared() -> None:
    build_system = _project()["build-system"]
    assert build_system["build-backend"] == "setuptools.build_meta"
    assert build_system["requires"]


def test_entry_points_target_top_level_modules() -> None:
    scripts = _project()["project"]["scripts"]
    assert scripts["modelinspector-gui"] == "gui:main"
    assert scripts["modelinspector"] == "inspect_model:main"


def test_flat_layout_lists_every_top_level_module() -> None:
    setuptools = _project()["tool"]["setuptools"]
    assert setuptools["package-dir"][""] == "src"
    expected = {path.stem for path in (ROOT / "src").glob("*.py")}
    assert set(setuptools["py-modules"]) == expected
    assert expected  # guard against an empty/wrong src lookup


def test_front_and_back_packages_are_declared() -> None:
    packages = set(_project()["tool"]["setuptools"]["packages"])
    assert {"front", "back", "assets", "assets.themes"} <= packages
    assert (ROOT / "src" / "front").is_dir()
    assert (ROOT / "src" / "back").is_dir()


def test_assets_are_mapped_and_included() -> None:
    setuptools = _project()["tool"]["setuptools"]
    assert setuptools["package-dir"]["assets"] == "assets"
    assert "assets" in setuptools["packages"]
    patterns = setuptools["package-data"]["assets"]
    assert any("themes/" in pattern and pattern.endswith(".jsonc") for pattern in patterns)
    assert any(pattern.endswith(".ico") for pattern in patterns)
    assert any(pattern.endswith(".png") for pattern in patterns)
    assert (ROOT / "assets" / "themes" / "default.jsonc").is_file()


def test_project_metadata_and_runtime_dependencies() -> None:
    project = _project()["project"]
    assert project["name"] == "modelinspector"
    assert project["requires-python"] == ">=3.12"
    classifiers = set(project["classifiers"])
    assert {
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
        "Programming Language :: Python :: 3.14",
    } <= classifiers
    assert {"PyQt6", "gguf", "numpy"} <= set(project["dependencies"])
