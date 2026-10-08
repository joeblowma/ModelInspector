# pyright: reportPrivateUsage=false
"""Structural responsiveness checks for deferred Settings reprojection."""

import os
import sys
import gc
import weakref
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from back.settings_store import open_settings
from front import integration_controller
from front.integration_controller import IntegrationMixin
from gui import MainWindow


def test_settings_rebuild_is_zero_delay_deferred_and_coalesced(monkeypatch):
    callbacks = []
    monkeypatch.setattr(
        integration_controller.QTimer,
        "singleShot",
        lambda delay, callback: callbacks.append((delay, callback)),
    )

    class RebuildTarget(IntegrationMixin):
        def __init__(self):
            self._settings_rebuild_generation = 0
            self._close_pending = False
            self._lifecycle_closed = False
            self._data_layout = {}
            self.applied = 0
            self.saved = 0
            self.card_rebuilds = 0

        def _apply_data_layout(self, layout):
            self.applied += 1

        def _save_accepted_settings(self):
            self.saved += 1

        def _update_raw_controls(self):
            pass

        def _update_analyze_slot(self):
            pass

        def _apply_default_tab(self):
            pass

        def _rebuild_active_cards_time_sliced(self):
            self.card_rebuilds += 1

    target = RebuildTarget()
    target._schedule_settings_rebuild()
    target._schedule_settings_rebuild()

    assert target.applied == 0
    assert [delay for delay, _callback in callbacks] == [0, 0]
    # Only the newest generation runs; the superseded one is dropped.
    callbacks[0][1]()
    assert (target.applied, target.saved) == (0, 0)
    callbacks[1][1]()
    assert (target.applied, target.saved) == (1, 1)
    # Settings never rebuild the loaded cards (the old multi-second freeze).
    assert target.card_rebuilds == 0


def test_settings_rebuild_is_ignored_after_shutdown(monkeypatch):
    callbacks = []
    monkeypatch.setattr(
        integration_controller.QTimer,
        "singleShot",
        lambda delay, callback: callbacks.append((delay, callback)),
    )

    class RebuildTarget(IntegrationMixin):
        def __init__(self):
            self._settings_rebuild_generation = 0
            self._close_pending = False
            self._lifecycle_closed = False
            self.applied = 0

        def _apply_data_layout(self, layout):
            self.applied += 1

        def _save_accepted_settings(self):
            self.applied += 1

    target = RebuildTarget()
    target._schedule_settings_rebuild()
    target._lifecycle_closed = True

    callbacks[0][1]()

    assert target.applied == 0


def test_deferred_settings_rebuild_does_not_keep_deleted_wrapper_alive(monkeypatch):
    callbacks = []
    monkeypatch.setattr(
        integration_controller.QTimer,
        "singleShot",
        lambda delay, callback: callbacks.append((delay, callback)),
    )

    class RebuildTarget(IntegrationMixin):
        def __init__(self):
            self._settings_rebuild_generation = 0

        def _rebuild_views_from_results(self):
            raise AssertionError("deleted window callback must not rebuild")

    target = RebuildTarget()
    target._schedule_settings_rebuild()
    target_ref = weakref.ref(target)
    del target
    gc.collect()

    assert target_ref() is None
    callbacks[0][1]()


def _synthetic_result(index):
    return {
        "filepath": f"C:/synthetic/model-{index}.safetensors",
        "filename": f"model-{index}.safetensors",
        "format": "SafeTensors",
        "file_size": 1,
        "file_size_friendly": "1 B",
        "architecture": "Synthetic",
        "model_type": "Test",
        "adapter_type": None,
        "quantization": None,
        "precision_summary": "FP16",
        "components": {},
        "component_precisions": {},
        "named_text_encoders": {},
        "total_params": 1,
        "total_params_friendly": "1",
        "tensor_count": 1,
        "training_meta": {},
    }


def test_settings_close_keeps_600_loaded_results_and_event_loop_responsive(tmp_path):
    """The deferred close path persists settings without rebuilding 600 cards."""
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window._settings_path = lambda: tmp_path / "settings.jsonc"
        window._legacy_settings_path = lambda: tmp_path / "legacy.ini"
        window._results = [_synthetic_result(index) for index in range(600)]
        for result in window._results:
            window._add_table_row(result)
            window._add_card(result)
        window._selected_paths = {window._results[0]["filepath"]}

        heartbeats = []

        def heartbeat():
            heartbeats.append(len(window._cards))
            if len(heartbeats) < 250:
                QTimer.singleShot(0, heartbeat)

        QTimer.singleShot(0, heartbeat)
        window._schedule_settings_rebuild()
        # Drain the queued close work; the heartbeat proves the loop stayed live.
        for _ in range(50):
            app.processEvents()

        settings_file = tmp_path / "settings.jsonc"
        assert settings_file.exists()
        # Cards are untouched by a Settings close: no full rebuild churn.
        assert len(window._cards) == 600
        assert window.table.rowCount() == 600
        assert heartbeats
        assert all(count == 600 for count in heartbeats)
        assert window._cards[0].filepath in window._selected_paths
        assert open_settings(settings_file).value("default_tab") == "cards"
    finally:
        window.close()
