"""Validate a release tag and stage the wheel plus Windows distribution."""

from __future__ import annotations

import argparse
from email.parser import BytesParser
from email.policy import default
import re
import shutil
import zipfile
from pathlib import Path


VERSION_RE = re.compile(r"\d+(?:\.\d+){1,3}\Z")
WHEEL_RE = re.compile(
    r"modelinspector-(?P<version>[A-Za-z0-9_.!+]+)-py3-none-any\.whl\Z"
)


def release_version(source_version: str) -> str:
    """Map the four-part Windows resource version to its release tag form."""
    version = source_version.strip()
    if not VERSION_RE.fullmatch(version):
        raise ValueError(f"Invalid version in _setVersionHere.txt: {version!r}")
    parts = version.split(".")
    return ".".join(parts[:-1]) if len(parts) == 4 and parts[-1] == "0" else version


def single_path(root: Path, pattern: str, label: str) -> Path:
    paths = sorted(root.rglob(pattern))
    if len(paths) != 1:
        raise ValueError(f"Expected one {label} below {root}, found: {paths}")
    return paths[0]


def wheel_version(wheel: Path) -> str:
    """Return the version only when the universal wheel agrees with METADATA."""
    match = WHEEL_RE.fullmatch(wheel.name)
    if not match:
        raise ValueError(f"Expected a modelinspector universal wheel, found: {wheel.name}")
    with zipfile.ZipFile(wheel) as archive:
        metadata_paths = [
            path
            for path in archive.namelist()
            if re.fullmatch(r"modelinspector-[^/]+\.dist-info/METADATA", path)
        ]
        if len(metadata_paths) != 1:
            raise ValueError(f"Expected one wheel METADATA file in {wheel.name}")
        metadata = BytesParser(policy=default).parsebytes(archive.read(metadata_paths[0]))
    if metadata["Name"] != "modelinspector" or not metadata["Version"]:
        raise ValueError(f"Invalid wheel METADATA in {wheel.name}")
    if metadata["Version"] != match["version"]:
        raise ValueError(
            f"Wheel filename version {match['version']!r} does not match "
            f"METADATA version {metadata['Version']!r}"
        )
    return metadata["Version"]


def prepare_release(
    tag: str, version_file: Path, wheel_dir: Path, windows_dir: Path, output_dir: Path
) -> list[Path]:
    version = release_version(version_file.read_text(encoding="utf-8"))
    if tag != f"v{version}":
        raise ValueError(f"Tag {tag!r} does not match version {version!r}")

    wheel = single_path(wheel_dir, "*.whl", "canonical universal wheel")
    if wheel_version(wheel) != version:
        raise ValueError(f"Wheel version does not match release version {version!r}: {wheel.name}")
    executable = single_path(windows_dir, "ModelInspector.exe", "Windows executable")

    output_dir.mkdir(parents=True, exist_ok=True)
    wheel_output = output_dir / wheel.name
    shutil.copy2(wheel, wheel_output)
    windows_output = output_dir / f"modelinspector_{version}-win-x86_64.zip"
    with zipfile.ZipFile(windows_output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.write(executable, executable.name)
    return [wheel_output, windows_output]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--tag", required=True)
    parser.add_argument("--version-file", type=Path, required=True)
    parser.add_argument("--wheel-dir", type=Path, required=True)
    parser.add_argument("--windows-dir", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    print("Release assets:")
    for asset in prepare_release(**vars(args)):
        print(asset)


if __name__ == "__main__":
    main()
