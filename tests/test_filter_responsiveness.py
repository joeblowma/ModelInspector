"""Event-loop and latest-request checks for large GUI filter projections."""

import os
import sys
import time
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QTimer
from PyQt6.QtWidgets import QApplication

from gui import MainWindow


def test_large_filter_projection_yields_and_keeps_latest_selection(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        window._results = [
            {
                "filepath": str(tmp_path / f"model_{index}.safetensors"),
                "filename": f"model_{index}.safetensors",
                "format": "SAFETENSORS",
                "file_size": 1,
                "file_size_friendly": "1 B",
                "architecture": f"Family {index}",
                "model_type": f"Type {index % 12}",
                "quantization": f"Q{index % 5}",
                "precision_summary": "FP16",
                "total_params": 1,
                "total_params_friendly": "1",
                "tensor_count": 1,
                "components": {},
                "named_text_encoders": {},
                "component_precisions": {},
                "training_meta": {},
                "capability_facts": {},
                "is_moe": bool(index % 2),
            }
            for index in range(420)
        ]
        window._rebuild_views_from_results()
        event_loop_observations = []
        QTimer.singleShot(
            0,
            lambda: event_loop_observations.append(
                (window._filter_projection.index, window.progress_label.text())
            ),
        )

        window.arch_filter_btn.set_all_checked(False)
        window.arch_filter_btn._arch_checks["Family 7"].setChecked(True)

        deadline = time.monotonic() + 5
        while window._filter_projection.pending and time.monotonic() < deadline:
            app.processEvents()
            time.sleep(0.001)

        assert not window._filter_projection.pending
        assert event_loop_observations
        completed, status = event_loop_observations[0]
        assert 0 < completed < len(window._results)
        assert status.startswith("Updating filters:")
        assert window.arch_filter_btn.active_filter() == {"Family 7"}
        assert sum(not window.table.isRowHidden(row) for row in range(420)) == 1
        assert sum(not card.isHidden() for card in window._cards) == 1
        assert window.arch_filter_btn._counts["Family 7"] == 1
        assert window.arch_filter_btn._counts["Family 8"] == 1
    finally:
        window.close()
        app.processEvents()
