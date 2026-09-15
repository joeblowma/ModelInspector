"""app_paths defaults, env precedence, and legacy data-dir fallback."""

import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import app_paths


def _patch_home(monkeypatch, tmp_path: Path) -> Path:
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", lambda: home)
    return home


def test_default_app_data_dir_is_home_local_model_inspector(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_DATA_DIR", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: tmp_path)
    home = _patch_home(monkeypatch, tmp_path)
    assert app_paths.app_data_dir() == home / ".local" / "ModelInspector"


def test_existing_legacy_data_dir_stays_in_place(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_DATA_DIR", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: tmp_path)
    home = _patch_home(monkeypatch, tmp_path)
    legacy = tmp_path / ".model-inspector"
    legacy.mkdir()
    (legacy / "settings.jsonc").write_text("{}", encoding="utf-8")
    # Existing installs must keep reading/writing their old location.
    assert app_paths.app_data_dir() == legacy
    assert app_paths.settings_path() == legacy / "settings.jsonc"
    assert app_paths.cache_dir() == legacy / "cache"
    assert app_paths.user_themes_dir() == legacy / "themes"


def test_explicit_data_dir_override_beats_default_and_legacy(monkeypatch, tmp_path):
    override = tmp_path / "explicit"
    monkeypatch.setenv("SMI_DATA_DIR", str(override))
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: tmp_path)
    _patch_home(monkeypatch, tmp_path)
    (tmp_path / ".model-inspector").mkdir()
    assert app_paths.app_data_dir() == override


def test_settings_path_env_override_and_ini_rewrite(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_DATA_DIR", raising=False)
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "custom.jsonc"))
    assert app_paths.settings_path() == tmp_path / "custom.jsonc"
    # Legacy .ini references keep routing to the JSONC file for migration.
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "old.ini"))
    assert app_paths.settings_path() == tmp_path / "old.jsonc"
    assert app_paths.legacy_settings_path() == tmp_path / "old.ini"


def test_cache_dir_env_override(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_DATA_DIR", raising=False)
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache-here"))
    assert app_paths.cache_dir() == tmp_path / "cache-here"


def test_ensure_output_dir_creates_missing_directory(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_OUTPUT_DIR", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: tmp_path)
    home = _patch_home(monkeypatch, tmp_path)
    target = home / ".local" / "ModelInspector"
    assert not target.exists()
    assert app_paths.ensure_output_dir() == target
    assert target.is_dir()


def test_ensure_output_dir_obeys_override(monkeypatch, tmp_path):
    override = tmp_path / "out-here"
    monkeypatch.setenv("SMI_OUTPUT_DIR", str(override))
    assert app_paths.ensure_output_dir() == override
    assert override.is_dir()


def test_ensure_output_dir_falls_back_to_home_on_error(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_OUTPUT_DIR", raising=False)
    home = _patch_home(monkeypatch, tmp_path)

    def fail_mkdir(*args, **kwargs):
        raise OSError("permission denied")

    monkeypatch.setattr(Path, "mkdir", fail_mkdir)
    assert app_paths.ensure_output_dir() == home


# ------------------------------------------------------------- resource roots


def test_resource_base_dir_prefers_same_dir_assets_installed_layout(
    monkeypatch, tmp_path
):
    site_packages = tmp_path / "site-packages"
    (site_packages / "assets").mkdir(parents=True)
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: site_packages)
    assert app_paths.resource_base_dir() == site_packages
    assert (
        app_paths.asset_path("icon.ico") == site_packages / "assets" / "icon.ico"
    )


def test_resource_base_dir_uses_checkout_root_when_assets_not_beside_module(
    monkeypatch, tmp_path
):
    repo_root = tmp_path / "checkout"
    (repo_root / "assets").mkdir(parents=True)
    (repo_root / "src").mkdir()
    monkeypatch.delattr(sys, "frozen", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: repo_root / "src")
    assert app_paths.resource_base_dir() == repo_root
    assert app_paths.asset_path("icon.ico") == repo_root / "assets" / "icon.ico"


def test_resource_base_dir_frozen_uses_meipass_then_exe_dir(monkeypatch, tmp_path):
    extracted = tmp_path / "_MEIPASS" / "assets"
    extracted.mkdir(parents=True)
    exe_dir = tmp_path / "dist"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(tmp_path / "_MEIPASS"), raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: exe_dir)
    assert app_paths.resource_base_dir() == tmp_path / "_MEIPASS"
    # One-file fallback without _MEIPASS keeps the executable directory.
    monkeypatch.delattr(sys, "_MEIPASS")
    assert app_paths.resource_base_dir() == exe_dir


# --------------------------------------------------------------- output paths


def test_default_output_dir_is_home_local_model_inspector(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_OUTPUT_DIR", raising=False)
    home = _patch_home(monkeypatch, tmp_path)
    assert app_paths.default_output_dir() == home / ".local" / "ModelInspector"


def test_default_output_dir_override_and_independence_from_legacy_data(
    monkeypatch, tmp_path
):
    monkeypatch.setenv("SMI_OUTPUT_DIR", str(tmp_path / "out"))
    assert app_paths.default_output_dir() == tmp_path / "out"
    # A legacy in-place data dir must not pull save dialogs back to it.
    monkeypatch.delenv("SMI_OUTPUT_DIR", raising=False)
    monkeypatch.setattr(app_paths, "app_base_dir", lambda: tmp_path)
    (tmp_path / ".model-inspector").mkdir()
    home = _patch_home(monkeypatch, tmp_path)
    assert app_paths.app_data_dir() == tmp_path / ".model-inspector"
    assert app_paths.default_output_dir() == home / ".local" / "ModelInspector"
