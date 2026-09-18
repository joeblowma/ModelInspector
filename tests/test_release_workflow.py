"""Static contracts for downloadable build artifacts and tag releases."""

import importlib.util
from pathlib import Path
import zipfile

import pytest


ROOT = Path(__file__).resolve().parents[1]
BUILD = (ROOT / ".github" / "workflows" / "build.yml").read_text(encoding="utf-8")
RELEASE = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
SCRIPT = (ROOT / ".github" / "scripts" / "prepare_release.py").read_text(encoding="utf-8")
SCRIPT_PATH = ROOT / ".github" / "scripts" / "prepare_release.py"


def _release_module():
    spec = importlib.util.spec_from_file_location("prepare_release", SCRIPT_PATH)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _wheel(path: Path, filename_version: str, metadata_version: str) -> Path:
    wheel = path / f"modelinspector-{filename_version}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(
            f"modelinspector-{filename_version}.dist-info/METADATA",
            f"Metadata-Version: 2.1\nName: modelinspector\nVersion: {metadata_version}\n",
        )
    return wheel


def test_build_artifacts_are_revision_named_and_reusable() -> None:
    assert "workflow_call:" in BUILD
    assert 'branches-ignore:\n      - "v*"' in BUILD
    assert "modelinspector-wheel-${{ matrix.os }}-${{ matrix.python-version }}-${{ github.sha }}" in BUILD
    assert "modelinspector-windows-${{ github.sha }}" in BUILD
    assert BUILD.count("if-no-files-found: error") >= 2


def test_tag_release_reuses_build_and_publishes_only_after_it() -> None:
    assert 'tags:\n      - "v*"' in RELEASE
    assert "uses: ./.github/workflows/build.yml" in RELEASE
    assert "needs: build" in RELEASE
    assert "contents: write" in RELEASE
    assert "gh release create" in RELEASE
    assert "--verify-tag" in RELEASE
    assert "release-dist/*" in RELEASE
    assert "RELEASE_TAG: ${{ github.ref_name }}" in RELEASE
    assert '"$RELEASE_TAG"' in RELEASE


def test_release_staging_preserves_standard_wheel_and_validates_tag_version() -> None:
    assert "Tag {tag!r} does not match version {version!r}" in SCRIPT
    assert "modelinspector_{version}-win-x86_64.zip" in SCRIPT
    assert "wheel_version(wheel) != version" in SCRIPT
    assert "merge-multiple: true" not in RELEASE
    assert "modelinspector-wheel-ubuntu-latest-3.12-${{ github.sha }}" in RELEASE


def test_release_staging_rejects_wheel_filename_metadata_version_mismatch(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    _wheel(wheel_dir, "1.0.1", "1.0.0")
    windows_dir = tmp_path / "windows"
    windows_dir.mkdir()
    (windows_dir / "ModelInspector.exe").write_bytes(b"exe")

    with pytest.raises(ValueError, match="Wheel filename version"):
        _release_module().prepare_release(
            "v1.0.0", ROOT / "_setVersionHere.txt", wheel_dir, windows_dir, tmp_path / "output"
        )


def test_release_staging_accepts_matching_wheel_metadata(tmp_path: Path) -> None:
    wheel_dir = tmp_path / "wheels"
    wheel_dir.mkdir()
    wheel = _wheel(wheel_dir, "1.0.0", "1.0.0")
    windows_dir = tmp_path / "windows"
    windows_dir.mkdir()
    (windows_dir / "ModelInspector.exe").write_bytes(b"exe")

    assets = _release_module().prepare_release(
        "v1.0.0", ROOT / "_setVersionHere.txt", wheel_dir, windows_dir, tmp_path / "output"
    )
    assert assets[0].name == wheel.name
    assert assets[0].is_file()
