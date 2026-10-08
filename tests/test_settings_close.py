"""Settings close responsiveness, size memory, and resize contracts."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from PyQt6.QtWidgets import QApplication

from back.settings_store import open_settings
from front.settings_dialog import SettingsDialog


@pytest.fixture(scope="module")
def app() -> QApplication:
    return QApplication.instance() or QApplication([])


def _window(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    window = MainWindow()
    window._settings_path = lambda: tmp_path / "settings.jsonc"
    window._legacy_settings_path = lambda: tmp_path / "legacy.ini"
    return window


@pytest.mark.parametrize("accepted", [0, 1])
def test_settings_close_persists_size_for_x_and_ok(app, monkeypatch, tmp_path: Path, accepted: int):
    """The seam saves the dialog size on X/close (0) and OK (1)."""
    window = _window(monkeypatch, tmp_path)
    captured: dict[str, tuple[int, int]] = {}

    def fake_exec(self):
        captured["size"] = self.dialog_size()
        return accepted

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    try:
        window._open_settings()
    finally:
        window.close()

    stored = open_settings(tmp_path / "settings.jsonc").value("settings_size")
    assert stored == {"width": captured["size"][0], "height": captured["size"][1]}


def test_settings_open_uses_remembered_size(app, monkeypatch, tmp_path: Path):
    window = _window(monkeypatch, tmp_path)
    open_settings(tmp_path / "settings.jsonc").setValue(
        "settings_size", {"width": 700, "height": 500}
    )
    captured: dict[str, tuple[int, int]] = {}

    def fake_exec(self):
        captured["size"] = self.dialog_size()
        return 0

    monkeypatch.setattr(SettingsDialog, "exec", fake_exec)
    try:
        window._open_settings()
    finally:
        window.close()

    assert captured["size"] == (700, 500)


def test_settings_rebuild_skips_full_card_rebuild(app, monkeypatch, tmp_path: Path):
    """Settings close must not pay for an unnecessary full card rebuild."""
    window = _window(monkeypatch, tmp_path)
    calls: list[int] = []
    monkeypatch.setattr(window, "_rebuild_active_cards_time_sliced", lambda: calls.append(1))
    try:
        window._data_layout = window._capture_data_layout()
        window._schedule_settings_rebuild()
        for _ in range(20):
            app.processEvents()
    finally:
        window.close()

    assert calls == []
    assert open_settings(tmp_path / "settings.jsonc").value("default_tab") == "cards"