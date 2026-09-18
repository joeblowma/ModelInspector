"""Focused linkage checks for the selected-model cache-bypassing rescan action."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

from front import selection_controller
from gui import MainWindow


def _result(filepath: str) -> dict:
    return {
        "filepath": filepath,
        "filename": Path(filepath).name,
        "format": "SAFETENSORS",
        "file_size": 1,
        "file_size_friendly": "1 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": "Test",
        "model_type": "Checkpoint",
        "components": {},
        "named_text_encoders": {},
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }


def test_rescan_selected_invalidates_only_selected_and_preserves_selection(
    tmp_path, monkeypatch
):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    first = str(tmp_path / "first.safetensors")
    second = str(tmp_path / "second.safetensors")
    invalidated = []
    started = []
    monkeypatch.setattr(
        selection_controller,
        "invalidate_cached_inspection",
        lambda path, options: invalidated.append((path, options)),
    )
    monkeypatch.setattr(
        window,
        "_start_analysis",
        lambda paths, clear_existing, *, replace_existing=False: started.append(
            (paths, clear_existing, replace_existing)
        ),
    )
    try:
        for path in (first, second):
            data = _result(path)
            window._results.append(data)
            window._add_card(data)
            window._add_table_row(data)
        window._selected_paths.add(first)

        assert window._selected_actions()["rescan_selected"][0] == "Rescan selected"
        window._rescan_selected_results()

        assert invalidated == [
            (first, {"allow_filename_alias_detection": False})
        ]
        assert started == [([first], False, True)]
        assert window._selected_paths == {first}
        assert [result["filepath"] for result in window._results] == [first, second]

        window._selected_action = "rescan_selected"
        monkeypatch.setattr(window, "_file_operation_running", lambda: True)
        window._run_selected_action()
        assert invalidated == [
            (first, {"allow_filename_alias_detection": False})
        ]
        assert started == [([first], False, True)]
        assert window.progress_label.text() == "Cannot rescan while another operation is running."

        class BusyCacheLoad:
            running = True

            def isRunning(self):
                return self.running

        monkeypatch.setattr(window, "_file_operation_running", lambda: False)
        cache_load_worker = BusyCacheLoad()
        window._cache_load_worker = cache_load_worker
        window._rescan_selected_results()
        assert invalidated == [
            (first, {"allow_filename_alias_detection": False})
        ]
        assert started == [([first], False, True)]
        assert window.progress_label.text() == "Cannot rescan while another operation is running."
        cache_load_worker.running = False
    finally:
        window.close()
        app.processEvents()
