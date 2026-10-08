"""Build-time package version derived from the Windows version source."""

from importlib import metadata
from pathlib import Path
import re


_VERSION_RE = re.compile(r"\d+(?:\.\d+){1,3}\Z")


def _release_version(source_version: str) -> str:
    version = source_version.strip()
    if not _VERSION_RE.fullmatch(version):
        raise ValueError(f"Invalid version in _setVersionHere.txt: {version!r}")
    parts = version.split(".")
    return ".".join(parts[:-1]) if len(parts) == 4 and parts[-1] == "0" else version


def _version_source() -> str:
    source = Path(__file__).resolve().parents[1] / "_setVersionHere.txt"
    if source.is_file():
        return source.read_text(encoding="utf-8")
    package_info = Path(__file__).with_name("modelinspector.egg-info") / "PKG-INFO"
    if package_info.is_file():
        for line in package_info.read_text(encoding="utf-8").splitlines():
            if line.startswith("Version: "):
                return line.removeprefix("Version: ")
        raise ValueError("Missing Version field in sdist PKG-INFO")
    try:
        return metadata.version("modelinspector")
    except metadata.PackageNotFoundError as exc:
        raise ValueError("Missing installed modelinspector distribution metadata") from exc


__version__ = _release_version(_version_source())
