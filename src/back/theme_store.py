"""Crash-safe storage primitives for editable user themes.

Bundled themes are read-only application resources.  The first storage access
copies them into ``app_paths.user_themes_dir()`` and never replaces an
existing user file.  Theme files are JSONC-compatible JSON documents, while
the writer emits deterministic JSON so Save and Save As are easy to diff.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import shutil
import tempfile
from typing import Any, Iterable, Mapping

import app_paths
from back.theme_loader import Theme, ThemeLoadResult
from back.theme_loader import load_theme as _load_theme, list_themes as _list_themes
from back.theme_loader import validate_theme


def _directory(path: str | Path | None, default: Path) -> Path:
    return Path(path) if path is not None else default


def _resolved(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _safe_child(directory: Path, name: str) -> Path:
    """Return a direct child path, rejecting traversal and symlink escapes."""
    if not name or Path(name).name != name or name in {".", ".."}:
        raise ValueError(f"theme filename must be a direct child: {name!r}")
    candidate = directory / name
    try:
        _resolved(candidate).relative_to(_resolved(directory))
    except ValueError as exc:
        raise ValueError(f"theme filename escapes theme directory: {name!r}") from exc
    if candidate.is_symlink():
        raise ValueError(f"refusing to write through theme symlink: {name!r}")
    return candidate


def _atomic_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", dir=path.parent, prefix=f".{path.name}.", suffix=".tmp", delete=False
        ) as temporary:
            temporary_name = temporary.name
            temporary.write(content)
            temporary.flush()
            os.fsync(temporary.fileno())
        os.replace(temporary_name, path)
        temporary_name = None
    finally:
        if temporary_name:
            try:
                Path(temporary_name).unlink()
            except OSError:
                pass


def _prepare_directory(directory: Path) -> Path:
    if directory.is_symlink():
        raise ValueError(f"refusing to use a symlink as the theme directory: {directory}")
    if directory.exists() and not directory.is_dir():
        raise ValueError(f"theme directory is not a directory: {directory}")
    directory.mkdir(parents=True, exist_ok=True)
    return directory


def _theme_payload(theme: Theme | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(theme, Theme):
        payload: dict[str, Any] = {
            "id": theme.id,
            "name": theme.name,
            "colors": dict(theme.colors),
        }
        if theme.description:
            payload["description"] = theme.description
        if theme.variables:
            payload["variables"] = dict(theme.variables)
        return payload
    if isinstance(theme, Mapping):
        return dict(theme)
    raise TypeError("theme must be a Theme or mapping")


def _filename_for_theme(payload: Mapping[str, Any], filename: str | None) -> str:
    theme_id = payload.get("id")
    if not isinstance(theme_id, str):
        raise ValueError("theme id must be a string")
    selected = filename or f"{theme_id}.jsonc"
    if "\\" in selected or "/" in selected:
        raise ValueError("theme filename must not contain path separators")
    if not selected.lower().endswith(".jsonc"):
        selected += ".jsonc"
    if Path(selected).suffix.lower() != ".jsonc":
        raise ValueError("theme filename must end in .jsonc")
    return selected


def ensure_bundled_themes(
    bundled_directory: str | Path | None = None,
    user_directory: str | Path | None = None,
) -> tuple[Path, ...]:
    """Copy missing bundled ``*.jsonc`` files into the writable user folder.

    Existing files are intentionally left byte-for-byte untouched, including
    malformed or edited files.  The returned paths are deterministic and
    include both newly copied and already present bundled filenames.
    """
    source = _directory(bundled_directory, app_paths.themes_dir())
    target = _directory(user_directory, app_paths.user_themes_dir())
    _prepare_directory(target)
    if not source.is_dir():
        return ()

    exported: list[Path] = []
    for source_path in sorted(source.glob("*.jsonc"), key=lambda item: (item.name.casefold(), item.name)):
        if not source_path.is_file():
            continue
        destination = _safe_child(target, source_path.name)
        if not destination.exists():
            _atomic_bytes(destination, source_path.read_bytes())
        exported.append(destination)
    return tuple(exported)


def export_bundled_themes(
    bundled_directory: str | Path | None = None,
    user_directory: str | Path | None = None,
) -> tuple[Path, ...]:
    """Compatibility alias for :func:`ensure_bundled_themes`."""
    return ensure_bundled_themes(bundled_directory, user_directory)


def reset_user_themes(
    user_directory: str | Path | None = None,
    bundled_directory: str | Path | None = None,
) -> tuple[Path, ...]:
    """Clear only the user theme directory, then copy bundled themes again."""
    target = _directory(user_directory, app_paths.user_themes_dir())
    if target.is_symlink():
        raise ValueError(f"refusing to reset a symlink theme directory: {target}")
    if target.exists() and not target.is_dir():
        raise ValueError(f"theme directory is not a directory: {target}")
    if target.exists():
        resolved_target = _resolved(target)
        if resolved_target == resolved_target.parent:
            raise ValueError("refusing to reset a filesystem root")
        for child in tuple(target.iterdir()):
            try:
                _resolved(child).relative_to(resolved_target)
            except ValueError as exc:
                raise ValueError(f"theme entry escapes theme directory: {child}") from exc
            if child.is_symlink() or child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child)
    return ensure_bundled_themes(bundled_directory, target)


def save_user_theme(
    theme: Theme | Mapping[str, Any],
    user_directory: str | Path | None = None,
    *,
    filename: str | None = None,
) -> Path:
    """Validate and atomically save a user theme, returning its file path.

    ``filename`` is optional for Save As workflows.  It is always constrained
    to one ``.jsonc`` file directly below the user theme directory; the theme
    id remains the stable lookup key.
    """
    payload = _theme_payload(theme)
    valid, errors = validate_theme(payload)
    if not valid:
        raise ValueError("invalid theme: " + "; ".join(errors))
    if user_directory is None:
        ensure_bundled_themes()
    target = _directory(user_directory, app_paths.user_themes_dir())
    _prepare_directory(target)
    path = _safe_child(target, _filename_for_theme(payload, filename))
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    _atomic_bytes(path, encoded)
    return path


def next_available_user_theme_id(
    existing_ids: Iterable[str] = (), user_directory: str | Path | None = None
) -> str:
    """Return the first ``new_theme_N`` absent from both disk and editor state."""
    if user_directory is None:
        ensure_bundled_themes()
    target = _prepare_directory(_directory(user_directory, app_paths.user_themes_dir()))
    occupied = {str(theme_id).casefold() for theme_id in existing_ids}
    occupied.update(theme.id.casefold() for theme in _list_themes(target))
    occupied.update(path.stem.casefold() for path in target.glob("*.jsonc"))
    number = 1
    while f"new_theme_{number}" in occupied:
        number += 1
    return f"new_theme_{number}"


def save_new_user_theme(
    theme: Theme | Mapping[str, Any], user_directory: str | Path | None = None
) -> Path:
    """Create a new user theme without replacing an existing theme file."""
    payload = _theme_payload(theme)
    valid, errors = validate_theme(payload)
    if not valid:
        raise ValueError("invalid theme: " + "; ".join(errors))
    if user_directory is None:
        ensure_bundled_themes()
    target = _prepare_directory(_directory(user_directory, app_paths.user_themes_dir()))
    path = _safe_child(target, _filename_for_theme(payload, None))
    encoded = (json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True) + "\n").encode(
        "utf-8"
    )
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL)
    except FileExistsError as exc:
        raise FileExistsError(f"theme file already exists: {path.name}") from exc
    try:
        with os.fdopen(descriptor, "wb") as created:
            created.write(encoded)
            created.flush()
            os.fsync(created.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def list_themes(directory: str | Path | None = None) -> tuple[Theme, ...]:
    """Expose validated themes through the storage module for UI workers."""
    return _list_themes(directory)


def load_theme(theme_id_or_path: str | Path | None, directory: str | Path | None = None) -> ThemeLoadResult:
    """Expose fail-safe theme loading through the storage module."""
    return _load_theme(theme_id_or_path, directory)


__all__ = [
    "ensure_bundled_themes",
    "export_bundled_themes",
    "reset_user_themes",
    "save_user_theme",
    "next_available_user_theme_id",
    "save_new_user_theme",
    "list_themes",
    "load_theme",
]
