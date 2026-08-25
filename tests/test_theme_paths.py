"""Focused coverage for bundled resource and theme path resolution."""

from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

SRC_DIR = Path(__file__).resolve().parents[1] / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

import app_paths
from back import theme_loader


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
}


def _write_theme(root: Path, theme_id: str = "packaged") -> Path:
    directory = root / "assets" / "themes"
    directory.mkdir(parents=True)
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
    theme_path = _write_theme(tmp_path)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path), raising=False)

    themes = theme_loader.list_themes()
    loaded = theme_loader.load_theme("packaged")

    assert any(theme.id == "packaged" for theme in themes)
    assert loaded.theme.id == "packaged"
    assert loaded.theme.source == str(theme_path)
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
