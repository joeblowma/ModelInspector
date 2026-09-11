"""Focused coverage for bundled resource and theme path resolution."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

import pytest

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app_paths
from back import theme_loader
from back import theme_store


_COLORS = {
    "background": "#101010",
    "surface": "#202020",
    "surface_alt": "#303030",
    "text": "#f0f0f0",
    "muted": "#aaaaaa",
    "accent": "#4fc3f7",
    "accent_text": "#101010",
    "border": "#454545",
    "success": "#6acb78",
    "warning": "#e5c07b",
    "error": "#e06c75",
    "highlight": "#74c7ec",
    "highlight_selected": "#89dceb",
    "stat_label": "#6c7086",
    "accent_adapter": "#cba6f7",
    "accent_moe": "#fab387",
    "accent_component": "#94e2d5",
    "accent_display": "#f5c2e7",
}


def _write_theme(root: Path, theme_id: str = "packaged") -> Path:
    directory = root / "assets" / "themes"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{theme_id}.jsonc"
    path.write_text(
        "{\n"
        f'  "id": "{theme_id}",\n'
        '  "name": "Packaged Test",\n'
        f'  "colors": {json.dumps(_COLORS)}\n'
        "}\n",
        encoding="utf-8",
    )
    return path


def test_resource_paths_use_pyinstaller_extraction_root(monkeypatch, tmp_path):
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    assert app_paths.resource_base_dir() == tmp_path
    assert app_paths.asset_path("icon.ico") == tmp_path / "assets" / "icon.ico"
    assert app_paths.themes_dir() == tmp_path / "assets" / "themes"


def test_default_theme_discovery_uses_extracted_assets(monkeypatch, tmp_path):
    default_path = _write_theme(tmp_path, "default")
    theme_path = _write_theme(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "app-data"))

    themes = theme_loader.list_themes()
    user_default = tmp_path / "app-data" / "themes" / "default.jsonc"
    user_default.write_text(
        json.dumps({"id": "default", "name": "Edited User Default", "colors": _COLORS}),
        encoding="utf-8",
    )
    default_loaded = theme_loader.load_theme("default")
    loaded = theme_loader.load_theme("packaged")

    assert next(theme for theme in themes if theme.id == "default").source == str(default_path)
    assert default_loaded.theme.name == "Packaged Test"
    assert default_loaded.theme.source == str(default_path)
    assert any(theme.id == "packaged" for theme in themes)
    assert loaded.theme.id == "packaged"
    assert loaded.theme.source == str(tmp_path / "app-data" / "themes" / theme_path.name)
    assert not loaded.used_fallback


def test_development_resource_root_still_points_to_repository_assets(monkeypatch):
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert app_paths.asset_path("themes").is_dir()
    assert app_paths.themes_dir().name == "themes"


def test_pyinstaller_theme_data_entries_target_themes_directory():
    spec_path = Path(__file__).resolve().parents[1] / "ModelInspector.spec"
    tree = ast.parse(spec_path.read_text(encoding="utf-8"))
    analysis_call = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and isinstance(node.value, ast.Call)
        and isinstance(node.value.func, ast.Name)
        and node.value.func.id == "Analysis"
    )
    datas_node = next(keyword.value for keyword in analysis_call.keywords if keyword.arg == "datas")
    data_entries = {tuple(ast.literal_eval(item)) for item in datas_node.elts}
    theme_entries = {
        entry for entry in data_entries if entry[0].startswith("assets/themes/")
    }

    assert theme_entries
    assert {destination for _source, destination in theme_entries} == {"assets/themes"}


def test_win_compile_collects_the_complete_theme_directory():
    script = (Path(__file__).resolve().parents[1] / "win_compile.bat").read_text(
        encoding="utf-8"
    )

    assert '--add-data "assets/themes:assets/themes"' in script
    assert "if exist ModelInspector.spec del /q ModelInspector.spec" in script


def test_bundled_themes_are_exported_once_without_overwriting_edits(tmp_path):
    source = tmp_path / "bundled"
    user = tmp_path / "app-data" / "themes"
    source.mkdir()
    source_file = source / "base.jsonc"
    source_file.write_text('{"id": "base", "name": "Base", "colors": %s}\n' % json.dumps(_COLORS))

    exported = theme_store.ensure_bundled_themes(source, user)
    assert exported == (user / "base.jsonc",)
    user_file = user / "base.jsonc"
    user_file.write_text("// user edit\n" + user_file.read_text(encoding="utf-8"), encoding="utf-8")
    source_file.write_text("// changed bundle\n" + source_file.read_text(encoding="utf-8"), encoding="utf-8")

    assert theme_store.ensure_bundled_themes(source, user) == exported
    assert user_file.read_text(encoding="utf-8").startswith("// user edit")


def test_user_theme_enumeration_skips_invalid_files_and_uses_first_duplicate(tmp_path):
    user = tmp_path / "themes"
    user.mkdir()
    first = user / "01-first.jsonc"
    second = user / "02-second.jsonc"
    first.write_text(
        json.dumps({"id": "duplicate", "name": "First", "colors": _COLORS}), encoding="utf-8"
    )
    second.write_text(
        json.dumps({"id": "duplicate", "name": "Second", "colors": _COLORS}), encoding="utf-8"
    )
    (user / "broken.jsonc").write_text("{ not json", encoding="utf-8")

    themes = theme_loader.list_themes(user)
    assert themes[0].id == "default"
    duplicates = [theme for theme in themes if theme.id == "duplicate"]
    assert len(duplicates) == 1
    assert duplicates[0].name == "First"
    assert duplicates[0].source == str(first)


def test_malformed_and_missing_user_themes_return_diagnostics_and_builtin_fallback(tmp_path):
    user = tmp_path / "themes"
    user.mkdir()
    (user / "broken.jsonc").write_text("{ not json", encoding="utf-8")

    malformed = theme_loader.load_theme("broken", user)
    missing = theme_loader.load_theme("does-not-exist", user)

    assert malformed.used_fallback and malformed.theme.id == "default"
    assert any("could not load theme broken" in item for item in malformed.diagnostics)
    assert missing.used_fallback and missing.theme.id == "default"
    assert any("could not load theme does-not-exist" in item for item in missing.diagnostics)


def test_save_save_as_and_theme_id_path_safety(tmp_path):
    user = tmp_path / "themes"
    theme = {"id": "saved", "name": "Saved", "colors": _COLORS}
    outside = tmp_path / "outside.jsonc"
    outside.write_text(json.dumps({"id": "outside", "name": "Outside", "colors": _COLORS}), encoding="utf-8")

    saved = theme_store.save_user_theme(theme, user)
    renamed = theme_store.save_user_theme(
        {**theme, "id": "save-as", "name": "Save As"}, user, filename="palette.jsonc"
    )

    assert saved == user / "saved.jsonc"
    assert renamed == user / "palette.jsonc"
    assert theme_loader.load_theme("saved", user).theme.name == "Saved"
    assert theme_loader.load_theme("save-as", user).theme.name == "Save As"
    with pytest.raises(ValueError):
        theme_store.save_user_theme(theme, user, filename="../escaped.jsonc")
    assert not (tmp_path / "escaped.jsonc").exists()
    unsafe_load = theme_loader.load_theme("../outside", user)
    assert unsafe_load.used_fallback and unsafe_load.theme.id == "default"


def test_new_theme_ids_skip_existing_files_and_editor_ids_without_overwriting(tmp_path):
    user = tmp_path / "themes"
    user.mkdir()
    (user / "new_theme_1.jsonc").write_text("{ malformed", encoding="utf-8")
    assert theme_store.next_available_user_theme_id(("new_theme_2",), user) == "new_theme_3"

    theme = {"id": "new_theme_3", "name": "New Theme 3", "colors": _COLORS}
    saved = theme_store.save_new_user_theme(theme, user)

    assert saved == user / "new_theme_3.jsonc"
    with pytest.raises(FileExistsError):
        theme_store.save_new_user_theme(theme, user)


def test_reset_user_themes_removes_only_user_files_and_reextracts(tmp_path):
    source = tmp_path / "bundled"
    app_data = tmp_path / "app-data"
    user = app_data / "themes"
    source.mkdir()
    app_data.mkdir()
    sentinel = app_data / "settings.jsonc"
    sentinel.write_text("keep", encoding="utf-8")
    bundled = source / "base.jsonc"
    bundled.write_text(json.dumps({"id": "base", "name": "Base", "colors": _COLORS}), encoding="utf-8")
    theme_store.ensure_bundled_themes(source, user)
    theme_store.save_user_theme({"id": "custom", "name": "Custom", "colors": _COLORS}, user)
    (user / "base.jsonc").write_text("edited", encoding="utf-8")

    reset = theme_store.reset_user_themes(user, source)

    assert reset == (user / "base.jsonc",)
    assert not (user / "custom.jsonc").exists()
    assert (user / "base.jsonc").read_text(encoding="utf-8") == bundled.read_text(encoding="utf-8")
    assert sentinel.read_text(encoding="utf-8") == "keep"
