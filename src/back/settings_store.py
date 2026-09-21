"""Recoverable JSONC settings persistence and one-time INI migration."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any

import app_paths
from back.theme_loader import parse_jsonc

DEFAULTS: dict[str, Any] = {
    "allow_filename_alias_detection": False,
    "dump_json_modelinfo": False,
    "auto_load_raw_dump": False,
    "cache_full_data_on_analyze": False,
    "analysis_threads": 2,
    "add_mode": "replace",
    "default_tab": "cards",
    "table_columns": {},
    "data_layout": {"columns": [], "theme": "default"},
    # Remembered Settings dialog size; 900x640 is the release default.
    "settings_size": {"width": 900, "height": 640},
    # Most-recently-used model-cache directories (most recent first).
    "cache_dir_history": [],
}

_TEMPLATE = (
    "// Model Inspector settings (JSONC: comments and trailing commas are accepted).\n"
    "// This file is written atomically; malformed content safely falls back to defaults.\n"
    "// Editable themes are stored in: {themes_path}\n"
    "// Bundled themes are copied there on first use and existing user files are never overwritten.\n"
    "// Each theme is a JSONC object with id, name, colors, optional description, and optional variables.\n"
    "// id is 2-64 lowercase letters, digits, '_' or '-'; name must be non-empty.\n"
    "// Required colors: background, surface, surface_alt, text, muted, accent, accent_text,\n"
    "// border, success, warning, and error; values are #RRGGBB or #RRGGBBAA.\n"
    "// The selected theme is the string setting values.data_layout.theme (for example, \"default\").\n"
    "{\n  \"settings_version\": 1,\n  \"values\": {payload}\n}\n"
)


def _render_template(payload: str) -> str:
    return _TEMPLATE.replace("{themes_path}", str(app_paths.user_themes_dir())).replace(
        "{payload}", payload
    )


class SettingsStore:
    """Small QSettings-like adapter backed by a documented JSONC file."""

    def __init__(
        self,
        path: str | Path,
        legacy_ini_path: str | Path | None = None,
        *,
        defer_initial_save: bool = False,
    ) -> None:
        self.path = Path(path)
        self.legacy_ini_path = Path(legacy_ini_path) if legacy_ini_path else None
        self._defer_initial_save = defer_initial_save
        self.diagnostic = ""
        self.values = dict(DEFAULTS)
        self._load()

    def value(self, key: str, default: Any = None) -> Any:
        return self.values.get(key, default)

    def setValue(self, key: str, value: Any) -> None:
        self.values[key] = value
        self.save()

    def setValues(self, values: dict[str, Any]) -> None:
        """Atomically persist a related group of settings with one write."""
        self.values.update(values)
        self.save()

    def _load(self) -> None:
        if self.path.exists():
            try:
                raw = parse_jsonc(self.path.read_text(encoding="utf-8"))
                values = raw.get("values", raw) if isinstance(raw, dict) else None
                if not isinstance(values, dict):
                    raise ValueError("settings root must contain an object")
                self.values.update(values)
                self.values.pop("auto_analyze_on_add", None)
                return
            except (OSError, ValueError, TypeError, json.JSONDecodeError) as exc:
                self.diagnostic = f"Malformed settings.jsonc; using defaults: {exc}"
                try:
                    self.path.replace(self.path.with_suffix(self.path.suffix + ".invalid"))
                except OSError:
                    pass
                if not self._defer_initial_save:
                    self.save()
                return
        migrated = self._migrate_ini()
        if not self._defer_initial_save:
            self.save()
        if migrated:
            self.diagnostic = "Migrated existing Model Inspector INI settings to settings.jsonc."

    def _migrate_ini(self) -> bool:
        path = self.legacy_ini_path
        if path is None or not path.exists():
            return False
        try:
            from PyQt6.QtCore import QSettings

            ini = QSettings(str(path), QSettings.Format.IniFormat)
            for key in DEFAULTS:
                value = ini.value(key, None)
                if value is not None:
                    self.values[key] = value
            return True
        except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
            self.diagnostic = f"Could not migrate legacy INI settings: {exc}"
            return False

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(self.values, indent=2, ensure_ascii=False, sort_keys=True)
        temporary_name: str | None = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.path.parent,
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                delete=False,
            ) as temporary:
                temporary_name = temporary.name
                temporary.write(_render_template(payload))
                temporary.flush()
                os.fsync(temporary.fileno())
            os.replace(temporary_name, self.path)
            temporary_name = None
        finally:
            if temporary_name:
                try:
                    Path(temporary_name).unlink()
                except OSError:
                    pass


def open_settings(
    path: str | Path,
    legacy_ini_path: str | Path | None = None,
    *,
    defer_initial_save: bool = False,
) -> SettingsStore:
    """Open settings with safe defaults, migration, and atomic persistence."""
    return SettingsStore(path, legacy_ini_path, defer_initial_save=defer_initial_save)


__all__ = ["DEFAULTS", "SettingsStore", "open_settings"]
