"""Release gates for cards and the always-analyze settings policy."""

from __future__ import annotations

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

from back.settings_store import DEFAULTS, open_settings
from front.settings_dialog import SettingsDialog
from gui import MainWindow


def _summary(index: int) -> dict:
    return {
        "filepath": f"R:/synthetic/card-{index}.safetensors",
        "filename": f"card-{index}.safetensors", "format": "SAFETENSORS",
        "file_size": 1, "file_size_friendly": "1 B", "tensor_count": 1,
        "total_params": 1, "total_params_friendly": "1", "architecture": "Test",
        "model_type": "Checkpoint", "components": {}, "named_text_encoders": {},
        "precision_summary": "FP16", "component_precision_summary": "FP16",
        "component_precisions": {}, "precision_display": "FP16", "training_meta": {}, "extra": {},
    }


def _window(tmp_path, monkeypatch) -> MainWindow:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    QApplication.instance() or QApplication([])
    return MainWindow()


def test_four_fixed_cards_leave_only_viewport_whitespace(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    app = QApplication.instance()
    assert app is not None
    try:
        for index in range(4):
            window._add_card(_summary(index))
        window.resize(1200, 1200)
        window.show()
        app.processEvents()
        window._refresh_card_layout_geometry()
        app.processEvents()
        viewport = window.cards_scroll.viewport()
        assert viewport is not None
        assert all(card.height() == card.CARD_HEIGHT for card in window._cards)
        assert window.cards_container.minimumSizeHint().height() <= viewport.height()
        assert window.cards_scroll.verticalScrollBar().maximum() == 0
        assert window.cards_container.height() == viewport.height()
    finally:
        window.close()


def test_new_files_always_start_analysis_and_legacy_toggle_is_not_loaded(tmp_path, monkeypatch):
    settings_path = tmp_path / "settings.jsonc"
    settings_path.write_text('{"values": {"auto_analyze_on_add": false}}', encoding="utf-8")
    window = _window(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(
        window, "_analyze_all",
        lambda paths=None, *, clear_existing=True: started.append((paths, clear_existing)),
    )
    try:
        window._add_files(["new-model.safetensors"])
        assert started == [(["new-model.safetensors"], True)]
        assert "auto_analyze_on_add" not in DEFAULTS
        assert open_settings(settings_path).value("auto_analyze_on_add") is None
    finally:
        window.close()


def test_unchanged_settings_cancel_does_not_reapply_the_theme(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    try:
        dialog = SettingsDialog(window)
        changed = []
        dialog.themeChanged.connect(changed.append)
        dialog.reject()
        assert changed == []
    finally:
        window.close()


def test_unchanged_settings_ok_does_not_schedule_a_rebuild(tmp_path, monkeypatch):
    window = _window(tmp_path, monkeypatch)
    scheduled = []
    monkeypatch.setattr(SettingsDialog, "exec", lambda _dialog: 1)
    monkeypatch.setattr(
        window, "_schedule_settings_rebuild", lambda **kwargs: scheduled.append(kwargs)
    )
    try:
        window._open_settings()
        assert scheduled == []
    finally:
        window.close()
