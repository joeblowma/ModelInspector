from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import front.analysis_controller as analysis_controller
import front.discovery_controller as discovery_controller
import gui
from PyQt6.QtGui import QDropEvent
from PyQt6.QtWidgets import QApplication, QMessageBox


_APPLICATION: QApplication | None = None


class _Url:
    def __init__(self, path: Path):
        self._path = path

    def toLocalFile(self) -> str:
        return str(self._path)


class _DropEvent:
    def __init__(self, *paths: Path):
        self._urls = [_Url(path) for path in paths]
        self.accepted = False

    def mimeData(self):
        return self

    def urls(self):
        return self._urls

    def acceptProposedAction(self) -> None:
        self.accepted = True


class _Signal:
    def connect(self, _callback) -> None:
        pass


class _AnalysisWorkerDouble:
    instances: list["_AnalysisWorkerDouble"] = []

    def __init__(self, filepaths, inspect_options, threads, checkpoint_safety):
        self.filepaths = filepaths
        self.inspect_options = inspect_options
        self.threads = threads
        self.checkpoint_safety = checkpoint_safety
        self.result_ready = _Signal()
        self.error_occurred = _Signal()
        self.all_done = _Signal()
        self.started = False
        self.instances.append(self)

    def start(self) -> None:
        self.started = True

    def isRunning(self) -> bool:
        return False


def _window(tmp_path, monkeypatch):
    global _APPLICATION
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    _APPLICATION = cast(QApplication, QApplication.instance() or QApplication([]))
    window = gui.MainWindow()
    monkeypatch.setattr(window, "_analyze_all", lambda *args, **kwargs: None)
    return window


def _fail_on_prompt(*_args, **_kwargs):
    raise AssertionError("checkpoint routing must not show a consent prompt")


def test_direct_checkpoint_drop_queues_without_prompt(tmp_path, monkeypatch):
    checkpoint = tmp_path / "dropped.pt"
    checkpoint.write_bytes(b"not inspected")
    monkeypatch.setattr(QMessageBox, "question", _fail_on_prompt)
    window = _window(tmp_path, monkeypatch)
    try:
        event = _DropEvent(checkpoint)
        window.dropEvent(cast(QDropEvent, event))
        assert event.accepted
        assert window._queued_files == [str(checkpoint)]
    finally:
        window.close()


def test_checkpoint_file_dialog_queues_without_prompt(tmp_path, monkeypatch):
    checkpoint = tmp_path / "selected.ckpt"
    checkpoint.write_bytes(b"not inspected")
    monkeypatch.setattr(QMessageBox, "question", _fail_on_prompt)
    monkeypatch.setattr(
        discovery_controller.QFileDialog,
        "getOpenFileNames",
        lambda *_args: ([str(checkpoint)], ""),
    )
    window = _window(tmp_path, monkeypatch)
    try:
        window._browse_files()
        assert window._queued_files == [str(checkpoint)]
    finally:
        window.close()


def test_checkpoint_folder_routes_without_prompt(tmp_path, monkeypatch):
    folder = tmp_path / "checkpoints"
    folder.mkdir()
    monkeypatch.setattr(QMessageBox, "question", _fail_on_prompt)
    monkeypatch.setattr(
        discovery_controller.QFileDialog,
        "getExistingDirectory",
        lambda *_args: str(folder),
    )
    window = _window(tmp_path, monkeypatch)
    started = []
    monkeypatch.setattr(
        window,
        "_start_discovery",
        lambda roots, seed_paths=None, *, checkpoint_safety: started.append(
            (roots, seed_paths, checkpoint_safety)
        ),
    )
    try:
        window._browse_folder_recursive()
        assert started == [([str(folder)], None, "metadata")]
    finally:
        window.close()


def test_checkpoint_analysis_always_uses_metadata_only(tmp_path, monkeypatch):
    checkpoint = tmp_path / "analysis.pth"
    checkpoint.write_bytes(b"not inspected")
    _AnalysisWorkerDouble.instances.clear()
    monkeypatch.setattr(analysis_controller, "AnalysisWorker", _AnalysisWorkerDouble)
    window = _window(tmp_path, monkeypatch)
    try:
        window._start_analysis([str(checkpoint)], clear_existing=False)
        worker = _AnalysisWorkerDouble.instances[-1]
        assert worker.filepaths == [str(checkpoint)]
        assert worker.checkpoint_safety == "metadata"
        assert worker.started
    finally:
        window.close()
