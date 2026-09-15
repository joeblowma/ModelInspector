"""Model-cache directory selection history, precedence, and flag wiring."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from back.cache_location import (
    apply_cache_location,
    existing_cache_dir_history,
    last_used_cache_dir,
    record_cache_dir,
)
from back.settings_store import open_settings


def _store(tmp_path: Path):
    return open_settings(tmp_path / "settings.jsonc", defer_initial_save=True)


def test_record_cache_dir_prepends_dedupes_and_persists(tmp_path):
    store = _store(tmp_path)
    record_cache_dir(store, tmp_path / "a")
    record_cache_dir(store, tmp_path / "b")
    record_cache_dir(store, tmp_path / "a")  # dedupe: "a" moves to the front
    history = store.value("cache_dir_history", [])
    assert history[:2] == [str(tmp_path / "a"), str(tmp_path / "b")]
    assert history.count(str(tmp_path / "a")) == 1


def test_existing_cache_dir_history_excludes_stale_paths(tmp_path):
    store = _store(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    stale = tmp_path / "stale"
    record_cache_dir(store, existing)
    record_cache_dir(store, stale)
    assert existing_cache_dir_history(store) == [str(existing)]


def test_last_used_cache_dir_is_first_existing(tmp_path):
    store = _store(tmp_path)
    existing = tmp_path / "existing"
    existing.mkdir()
    stale = tmp_path / "stale"
    record_cache_dir(store, stale)
    record_cache_dir(store, existing)
    assert last_used_cache_dir(store) == str(existing)


def test_apply_cache_location_explicit_cache_wins_over_cachedir(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    store = _store(tmp_path)
    cache = tmp_path / "cache-flag"
    cachedir = tmp_path / "cachedir-flag"
    apply_cache_location(cache, cachedir, store)
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(cache)
    assert os.environ.get("SMI_CACHE_DIR") == ""
    assert store.value("cache_dir_history", [])[0] == str(cache)


def test_apply_cache_location_cachedir_is_transient(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    store = _store(tmp_path)
    cachedir = tmp_path / "cachedir-flag"
    apply_cache_location(None, cachedir, store)
    assert os.environ["SMI_CACHE_DIR"] == str(cachedir)
    assert store.value("cache_dir_history", []) == []


def test_apply_cache_location_persisted_last_used_default(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    store = _store(tmp_path)
    existing = tmp_path / "last-used"
    existing.mkdir()
    record_cache_dir(store, existing)
    apply_cache_location(None, None, store)
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(existing)
    assert os.environ.get("SMI_CACHE_DIR") == ""


def test_cache_flag_relocates_only_model_cache(tmp_path, monkeypatch):
    """--cache relocates the model cache; ancillary caches stay at the root."""
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "data"))
    store = _store(tmp_path)
    model = tmp_path / "model-cache"
    apply_cache_location(model, None, store)
    from app_paths import cache_dir, model_cache_dir

    assert model_cache_dir() == model
    assert cache_dir() == tmp_path / "data" / "cache"


def test_apply_cache_location_respects_existing_env(tmp_path, monkeypatch):
    env = tmp_path / "env-cache"
    monkeypatch.setenv("SMI_CACHE_DIR", str(env))
    store = _store(tmp_path)
    apply_cache_location(None, None, store)
    assert os.environ["SMI_CACHE_DIR"] == str(env)


def test_startup_arguments_parse_cache_flags():
    from front.startup_arguments import parse_startup_arguments

    args = parse_startup_arguments(["--cachedir", "R:/c", "--cache", "R:/m"])
    assert args.cachedir == Path("R:/c")
    assert args.cache == Path("R:/m")


def test_cli_cache_flags_set_env(tmp_path, monkeypatch):
    from back.cli import main

    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_SETTINGS_PATH", "")
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "data"))
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main(["--cachedir", str(tmp_path / "c"), str(empty)]) == 1
    assert os.environ["SMI_CACHE_DIR"] == str(tmp_path / "c")


def test_explicit_flags_combination_precedence(tmp_path, monkeypatch):
    """Deterministic precedence: --cache > --cachedir > persisted > env > default."""
    store = _store(tmp_path)
    persisted = tmp_path / "persisted"
    persisted.mkdir()
    record_cache_dir(store, persisted)
    cache = tmp_path / "cache-flag"
    cachedir = tmp_path / "cachedir-flag"

    # --cache + --cachedir: the more specific --cache wins for the model cache.
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    apply_cache_location(cache, cachedir, store)
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(cache)

    # --cachedir alone overrides the persisted default (relocates the root).
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    apply_cache_location(None, cachedir, store)
    assert os.environ["SMI_CACHE_DIR"] == str(cachedir)

    # No flags: the persisted most-recently-used directory is the model default.
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    apply_cache_location(None, None, store)
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(persisted)


def test_cli_honors_persisted_last_used_cache(tmp_path, monkeypatch):
    from back.cli import main

    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    monkeypatch.setenv("SMI_SETTINGS_PATH", "")
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "data"))
    persisted = tmp_path / "persisted-cache"
    persisted.mkdir()
    store = open_settings(tmp_path / "data" / "settings.jsonc", defer_initial_save=True)
    record_cache_dir(store, persisted)
    empty = tmp_path / "empty"
    empty.mkdir()
    assert main([str(empty)]) == 1
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(persisted)


def test_settings_dialog_accept_redirects_live_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "data"))
    from PyQt6.QtWidgets import QApplication

    app = QApplication.instance() or QApplication([])
    from front.settings_dialog import SettingsDialog

    dialog = SettingsDialog(data_columns=[])
    try:
        new_dir = tmp_path / "new-cache"
        new_dir.mkdir()
        dialog.cache_dir_combo.setCurrentText(str(new_dir))
        dialog.accept()
    finally:
        dialog.deleteLater()
        app.processEvents()
    # Live redirect: the model cache now points at the new directory...
    assert os.environ["SMI_MODEL_CACHE_DIR"] == str(new_dir)
    # ...while the settings file location is unchanged.
    assert os.environ["SMI_SETTINGS_PATH"] == str(tmp_path / "settings.jsonc")
    store = open_settings(tmp_path / "settings.jsonc", defer_initial_save=True)
    assert store.value("cache_dir_history", [])[0] == str(new_dir)


def test_settings_dialog_skips_redirect_while_cache_worker_running(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_CACHE_DIR", "")
    monkeypatch.setenv("SMI_MODEL_CACHE_DIR", "")
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_DATA_DIR", str(tmp_path / "data"))
    from PyQt6.QtWidgets import QApplication, QDialog, QMessageBox, QWidget

    app = QApplication.instance() or QApplication([])
    from front.settings_dialog import SettingsDialog

    class RunningWorker:
        def isRunning(self):
            return True

    warnings = []
    monkeypatch.setattr(
        QMessageBox,
        "warning",
        lambda *args: warnings.append(args),
    )

    parent = QWidget()
    parent._worker = RunningWorker()
    dialog = SettingsDialog(parent, data_columns=[])
    try:
        new_dir = tmp_path / "new-cache"
        new_dir.mkdir()
        dialog.cache_dir_combo.setCurrentText(str(new_dir))
        dialog.accept()
        # The dialog stays open (not accepted) and surfaces the busy state.
        assert dialog.result() != QDialog.DialogCode.Accepted
        assert warnings, "expected a busy warning, not a silent discard"
    finally:
        dialog.deleteLater()
        parent.deleteLater()
        app.processEvents()
    # A running cache worker blocks the live switch so caches are never mixed.
    assert os.environ.get("SMI_MODEL_CACHE_DIR") == ""
    store = open_settings(tmp_path / "settings.jsonc", defer_initial_save=True)
    assert store.value("cache_dir_history", []) == []
