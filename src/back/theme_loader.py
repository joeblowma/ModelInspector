"""Dependency-free JSONC theme loading and validation.

Themes are data, not Python code.  Loading is deliberately fail-safe: callers
receive the built-in theme and diagnostics when an external file is malformed,
missing, or does not contain strict six/eight digit hexadecimal colors.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any, Iterable, Mapping

from app_paths import themes_dir, user_themes_dir


_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}(?:[0-9a-fA-F]{2})?$")
_DEFAULT_COLORS = {
    "background": "#1e1e1e",
    "surface": "#252526",
    "surface_alt": "#333333",
    "text": "#f0f0f0",
    "muted": "#aaaaaa",
    "accent": "#4fc3f7",
    "accent_text": "#101010",
    "border": "#454545",
    "success": "#6acb78",
    "warning": "#e5c07b",
    "error": "#e06c75",
    # Display / highlight colors used by card widgets, badges, and status labels
    "highlight": "#74c7ec",
    "highlight_selected": "#89dceb",
    "stat_label": "#6c7086",
    "accent_adapter": "#cba6f7",
    "accent_moe": "#fab387",
    "accent_component": "#94e2d5",
    "accent_display": "#f5c2e7",
    "tab_inactive_hover": "#3b3b3b",
}
_OPTIONAL_COLOR_DEFAULTS = {"tab_inactive_hover": _DEFAULT_COLORS["tab_inactive_hover"]}


@dataclass(frozen=True)
class Theme:
    """Validated theme contract shared by Qt and non-Qt callers."""

    id: str
    name: str
    colors: Mapping[str, str]
    description: str = ""
    source: str = "builtin"
    variables: Mapping[str, str] = field(default_factory=dict)

    def qt_variables(self) -> dict[str, str]:
        """Return CSS-like variable names suitable for stylesheet generation."""
        values = dict(self.colors)
        values.update(self.variables)
        return {f"--smi-{key.replace('_', '-').lower()}": value for key, value in values.items()}

    def stylesheet(self) -> str:
        """Generate a compact Qt stylesheet using the validated palette."""
        colors = self.colors
        return "\n".join(
            (
                "QWidget { background-color: %s; color: %s; }" % (colors["background"], colors["text"]),
                "QLineEdit, QTextEdit, QPlainTextEdit, QComboBox { background-color: %s; border: 1px solid %s; }" % (colors["surface"], colors["border"]),
                "QPushButton { background-color: %s; color: %s; border: 1px solid %s; padding: 4px 8px; }" % (colors["accent"], colors["accent_text"], colors["border"]),
                "QPushButton:hover { background-color: %s; }" % colors["surface_alt"],
                "QToolTip { background-color: %s; color: %s; border: 1px solid %s; }" % (colors["surface"], colors["text"], colors["border"]),
                "QLabel[themeRole=highlight] { color: %s; }" % colors["highlight"],
                "QLabel[themeRole=highlight_selected] { color: %s; }" % colors["highlight_selected"],
                "QLabel[themeRole=stat_label] { color: %s; }" % colors["stat_label"],
                "QLabel[themeRole=accent_adapter] { color: %s; }" % colors["accent_adapter"],
                "QLabel[themeRole=accent_moe] { color: %s; }" % colors["accent_moe"],
                "QLabel[themeRole=accent_component] { color: %s; }" % colors["accent_component"],
                "QLabel[themeRole=accent_display] { color: %s; }" % colors["accent_display"],
            )
        )


@dataclass(frozen=True)
class ThemeLoadResult:
    theme: Theme
    diagnostics: tuple[str, ...] = ()
    used_fallback: bool = False


BUILTIN_THEME = Theme("default", "Default Dark", dict(_DEFAULT_COLORS), "Safe built-in fallback")


def _strip_jsonc_comments(text: str) -> str:
    """Strip // and /* */ comments while preserving quoted comment-like text."""
    output: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(text):
        char = text[index]
        if quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char in ('"', "'"):
            # JSON only permits double quotes, but preserving a single-quoted
            # section gives a clearer JSON parser error than corrupting it.
            quote = char
            output.append(char)
            index += 1
        elif text.startswith("//", index):
            newline = text.find("\n", index + 2)
            if newline < 0:
                break
            output.append("\n")
            index = newline + 1
        elif text.startswith("/*", index):
            end = text.find("*/", index + 2)
            if end < 0:
                raise ValueError("unterminated block comment")
            output.extend("\n" if c == "\n" else " " for c in text[index : end + 2])
            index = end + 2
        else:
            output.append(char)
            index += 1
    if quote:
        # Let json.loads produce the normal malformed-string error.
        return "".join(output)
    return "".join(output)


def _remove_trailing_commas(text: str) -> str:
    output: list[str] = []
    index = 0
    quote: str | None = None
    escaped = False
    while index < len(text):
        char = text[index]
        if quote:
            output.append(char)
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            index += 1
            continue
        if char == '"':
            quote = char
            output.append(char)
            index += 1
            continue
        if char == ",":
            lookahead = index + 1
            while lookahead < len(text) and text[lookahead].isspace():
                lookahead += 1
            if lookahead < len(text) and text[lookahead] in "}]":
                index += 1
                continue
        output.append(char)
        index += 1
    return "".join(output)


def parse_jsonc(text: str) -> Any:
    """Parse JSON with line/block comments and trailing commas."""
    if not isinstance(text, str):
        raise TypeError("JSONC input must be text")
    return json.loads(_remove_trailing_commas(_strip_jsonc_comments(text)))


def validate_theme(raw: Mapping[str, Any]) -> tuple[bool, tuple[str, ...]]:
    """Validate a theme mapping and return all actionable diagnostics."""
    errors: list[str] = []
    if not isinstance(raw, Mapping):
        return False, ("theme root must be an object",)
    theme_id = raw.get("id")
    if not isinstance(theme_id, str) or not re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", theme_id):
        errors.append("id must contain 2-64 lowercase letters, digits, '_' or '-'")
    if not isinstance(raw.get("name"), str) or not str(raw.get("name")).strip():
        errors.append("name must be a non-empty string")
    colors = raw.get("colors")
    if not isinstance(colors, Mapping):
        errors.append("colors must be an object")
    else:
        missing = sorted(set(_DEFAULT_COLORS) - set(_OPTIONAL_COLOR_DEFAULTS) - set(colors))
        if missing:
            errors.append("missing required colors: " + ", ".join(missing))
        for key, value in colors.items():
            if key not in _DEFAULT_COLORS:
                continue
            if not isinstance(key, str) or not _COLOR_RE.fullmatch(str(value)):
                errors.append(f"colors.{key} must be a #RRGGBB or #RRGGBBAA value")
    variables = raw.get("variables", {})
    if variables is not None and not isinstance(variables, Mapping):
        errors.append("variables must be an object when provided")
    return not errors, tuple(errors)


def _theme_from_mapping(raw: Mapping[str, Any], source: str) -> Theme:
    valid, errors = validate_theme(raw)
    if not valid:
        raise ValueError("; ".join(errors))
    variables = {str(key): str(value) for key, value in (raw.get("variables") or {}).items()}
    return Theme(
        id=str(raw["id"]),
        name=str(raw["name"]),
        colors={**_OPTIONAL_COLOR_DEFAULTS, **{str(key): str(value) for key, value in raw["colors"].items()}},
        description=str(raw.get("description") or ""),
        source=source,
        variables=variables,
    )


def _theme_files(directory: Path) -> Iterable[Path]:
    if not directory.is_dir():
        return ()
    resolved_directory = directory.resolve(strict=False)
    return tuple(
        path
        for path in sorted(directory.glob("*.jsonc"), key=lambda item: (item.name.casefold(), item.name))
        if path.is_file()
        and not path.is_symlink()
        and _is_within(path, resolved_directory)
    )


def _is_within(path: Path, directory: Path) -> bool:
    try:
        path.resolve(strict=False).relative_to(directory)
    except ValueError:
        return False
    return True


def _user_theme_directory() -> Path:
    """Ensure the editable theme projection exists before default discovery."""
    from back.theme_store import ensure_bundled_themes

    ensure_bundled_themes()
    return user_themes_dir()


def _load_bundled_default_theme() -> ThemeLoadResult:
    """Load the read-only default from the replaceable application asset."""
    try:
        directory = themes_dir()
        path = _safe_requested_filename(directory, "default.jsonc")
        theme = _theme_from_mapping(parse_jsonc(path.read_text(encoding="utf-8")), str(path))
        if theme.id != BUILTIN_THEME.id:
            raise ValueError("bundled default theme must use id 'default'")
        return ThemeLoadResult(theme)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return ThemeLoadResult(
            BUILTIN_THEME,
            (f"could not load bundled default theme: {exc}",),
            True,
        )


def _theme_path_for_id(theme_id: str, directory: Path) -> Path:
    """Find the first deterministic file containing ``theme_id``."""
    candidate = directory / f"{theme_id}.jsonc"
    if candidate.exists():
        return _safe_requested_filename(directory, candidate.name)
    for path in _theme_files(directory):
        try:
            raw = parse_jsonc(path.read_text(encoding="utf-8"))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if isinstance(raw, Mapping) and raw.get("id") == theme_id:
            return path
    return candidate


def _safe_requested_filename(directory: Path, filename: str) -> Path:
    if not filename or Path(filename).name != filename or filename in {".", ".."}:
        raise ValueError("theme filename must be a direct child of the theme directory")
    path = directory / filename
    if not _is_within(path, directory.resolve(strict=False)):
        raise ValueError("theme filename escapes the theme directory")
    if path.is_symlink():
        raise ValueError("refusing to load a theme through a symlink")
    return path


def list_themes(directory: str | Path | None = None) -> tuple[Theme, ...]:
    """Enumerate validated user themes with deterministic duplicate handling."""
    folder = Path(directory) if directory is not None else _user_theme_directory()
    default_theme = _load_bundled_default_theme().theme
    themes: list[Theme] = [default_theme]
    seen_ids = {default_theme.id}
    for path in _theme_files(folder):
        try:
            theme = _theme_from_mapping(parse_jsonc(path.read_text(encoding="utf-8")), str(path))
        except (OSError, TypeError, ValueError, json.JSONDecodeError):
            continue
        if theme.id in seen_ids:
            continue
        seen_ids.add(theme.id)
        themes.append(theme)
    return tuple(sorted(themes, key=lambda theme: (theme.name.lower(), theme.id)))


def load_theme(theme_id_or_path: str | Path | None, directory: str | Path | None = None) -> ThemeLoadResult:
    """Load a theme by id or path, returning the fallback and diagnostics on error."""
    if theme_id_or_path is None:
        return _load_bundled_default_theme()
    if str(theme_id_or_path).lower() in {"default", "builtin"}:
        return _load_bundled_default_theme()
    diagnostics: list[str] = []
    try:
        explicit_path = isinstance(theme_id_or_path, Path)
        requested = Path(str(theme_id_or_path))
        folder = Path(directory) if directory is not None else _user_theme_directory()
        if explicit_path or requested.is_absolute():
            path = requested
        elif requested.suffix.lower() == ".jsonc" and requested.name == str(theme_id_or_path):
            path = _safe_requested_filename(folder, requested.name)
        elif re.fullmatch(r"[a-z0-9][a-z0-9_-]{1,63}", str(theme_id_or_path)):
            path = _theme_path_for_id(str(theme_id_or_path), folder)
        else:
            raise ValueError("requested theme id is not a safe theme identifier")
        raw = parse_jsonc(path.read_text(encoding="utf-8"))
        theme = _theme_from_mapping(raw, str(path))
        return ThemeLoadResult(theme)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        diagnostics.append(f"could not load theme {theme_id_or_path!s}: {exc}")
        return ThemeLoadResult(BUILTIN_THEME, tuple(diagnostics), True)


def load_theme_by_id(theme_id: str, directory: str | Path | None = None) -> ThemeLoadResult:
    return load_theme(theme_id, directory)


# Module-level theme accessor for widget construction
# This is set by the application layer at startup and provides
# theme colors to widgets that need them during construction.
_global_theme_colors: dict[str, str] | None = None


def set_global_theme_colors(colors: dict[str, str]) -> None:
    """Set the global theme colors for widget construction."""
    global _global_theme_colors
    _global_theme_colors = dict(colors)


def get_global_theme_colors() -> dict[str, str]:
    """Return the current global theme colors, falling back to defaults."""
    if _global_theme_colors is not None:
        return _global_theme_colors
    return dict(_DEFAULT_COLORS)


__all__ = [
    "Theme",
    "ThemeLoadResult",
    "BUILTIN_THEME",
    "parse_jsonc",
    "validate_theme",
    "list_themes",
    "load_theme",
    "load_theme_by_id",
    "set_global_theme_colors",
    "get_global_theme_colors",
]
