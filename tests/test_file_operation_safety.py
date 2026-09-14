# pyright: reportAttributeAccessIssue=false, reportUnusedExpression=false
"""Safety-focused tests for the no-clobber move and worker lifetime rules.

No real model files are read or moved; every fixture is a small temp file.
Worker-level tests drive ``run()`` directly; GUI tests use offscreen Qt and
temporary settings/cache roots.
"""

from __future__ import annotations

import errno
import os
import sys
import threading
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog

import front.file_operation_worker as fow
from front.file_operation_worker import FileOperationWorker
from gui import MainWindow


def _summary(path: str) -> dict:
    return {
        "filepath": path,
        "filename": Path(path).name,
        "format": "SAFETENSORS",
        "file_size": 10,
        "file_size_friendly": "10 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": "Test",
        "model_type": "Checkpoint",
        "adapter_type": None,
        "quantization": None,
        "components": {},
        "named_text_encoders": {},
        "lora_rank": None,
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }


def _drain_until(app, predicate, timeout: float = 5.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return True
        time.sleep(0.005)
    return predicate()


def _populate(window, path: str) -> None:
    data = _summary(path)
    window._results.append(data)
    window._add_card(data)
    window._add_table_row(data)
    window._selected_paths.add(path)


# --- Worker-level no-clobber ------------------------------------------------


def test_same_basename_collision_skips_second(tmp_path):
    a = tmp_path / "a"
    b = tmp_path / "b"
    dst_dir = tmp_path / "dst"
    a.mkdir()
    b.mkdir()
    dst_dir.mkdir()
    (a / "model.safetensors").write_bytes(b"a")
    (b / "model.safetensors").write_bytes(b"b")

    worker = FileOperationWorker(
        "move",
        [
            (str(a / "model.safetensors"), str(dst_dir / "model.safetensors")),
            (str(b / "model.safetensors"), str(dst_dir / "model.safetensors")),
        ],
    )
    done = []
    worker.operation_done.connect(done.append)
    worker.run()

    result = done[0]
    assert len(result["moved"]) == 1
    assert len(result["skipped"]) == 1
    assert result["skipped"][0][1] == "destination already exists"
    # Exactly one file landed; the loser was not clobbered.
    assert len(list(dst_dir.iterdir())) == 1
    assert (a / "model.safetensors").exists() or (b / "model.safetensors").exists()


def test_same_path_move_is_noop(tmp_path):
    src = tmp_path / "model.safetensors"
    src.write_bytes(b"x")

    status = fow.safe_move(str(src), str(src))
    assert status == "skipped_same"
    assert src.exists()


def test_existing_directory_destination_skipped(tmp_path):
    src = tmp_path / "model.safetensors"
    src.write_bytes(b"x")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    status = fow.safe_move(str(src), str(dst_dir))
    assert status == "skipped_exists"
    assert src.exists()
    # The source must NOT have been swallowed into the directory.
    assert not (dst_dir / "model.safetensors").exists()


def test_symlink_source_moved_as_symlink(tmp_path):
    target = tmp_path / "real.bin"
    target.write_bytes(b"payload")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")

    status = fow.safe_move(str(link), str(tmp_path / "moved.bin"))
    assert status == "moved"
    assert not link.exists()
    moved = tmp_path / "moved.bin"
    assert moved.is_symlink()
    assert moved.read_bytes() == b"payload"


def test_copy_exclusive_failure_cleans_partial_dst(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst = tmp_path / "dst.bin"

    def boom(inp, out):
        raise OSError("disk full")

    monkeypatch.setattr(fow.shutil, "copyfileobj", boom)
    with pytest.raises(OSError):
        fow._copy_exclusive(str(src), str(dst))
    assert src.exists()
    assert not dst.exists()


def test_safe_move_cross_device_preserves_source_on_failure(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst = tmp_path / "dst.bin"

    def exdev(a, b):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(fow.os, "rename", exdev)

    def failing_copy(s, d):
        raise OSError("copy failed")

    monkeypatch.setattr(fow, "_copy_exclusive", failing_copy)
    with pytest.raises(OSError):
        fow.safe_move(str(src), str(dst))
    assert src.exists()
    assert not dst.exists()


def test_safe_move_cross_device_success(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"payload")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()
    dst = dst_dir / "src.bin"

    def exdev(a, b):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(fow.os, "rename", exdev)
    status = fow.safe_move(str(src), str(dst))
    assert status == "moved"
    assert not src.exists()
    assert dst.read_bytes() == b"payload"


def test_move_worker_failure_preserves_source(tmp_path, monkeypatch):
    src = tmp_path / "src.bin"
    src.write_bytes(b"x")
    dst = tmp_path / "dst.bin"

    def fail(s, d):
        raise OSError("boom")

    monkeypatch.setattr(fow, "safe_move", fail)
    worker = FileOperationWorker("move", [(str(src), str(dst))])
    done = []
    worker.operation_done.connect(done.append)
    worker.run()

    result = done[0]
    assert result["moved"] == []
    assert result["failed"][0][0] == str(src)
    assert src.exists()
    assert not dst.exists()


# --- GUI-level lifetime / gating --------------------------------------------


def test_worker_lifetime_kept_until_finished(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    src = tmp_path / "model.bin"
    src.write_bytes(b"x")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    tail = threading.Event()

    class SlowTailWorker(FileOperationWorker):
        def run(self):
            super().run()
            tail.set()
            time.sleep(0.4)

    window = MainWindow()
    worker = SlowTailWorker("move", [(str(src), str(dst_dir / "model.bin"))])
    try:
        window._start_file_operation(worker, "Move Files", "Moving 1 file(s)...")
        assert window._file_op_worker is worker
        assert tail.wait(3.0)
        # operation_done has fired but the thread is still in its tail; the
        # controller must keep the strong reference and the modal dialog alive.
        assert worker.isRunning()
        assert window._file_op_worker is worker
        assert window._file_op_dialog is not None
        assert _drain_until(app, lambda: window._file_op_worker is None)
        assert window._file_op_dialog is None
    finally:
        if worker.isRunning():
            worker.wait(2000)
        window.close()


def test_move_blocked_while_scan_running(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])

    class RunningStub:
        def isRunning(self):
            return True

        def cancel(self):
            pass

    window = MainWindow()
    window._worker = RunningStub()
    try:
        window._move_selected_files()
        assert window._file_op_worker is None
        assert window._file_op_dialog is None
        assert "scan" in window.progress_label.text().lower()
    finally:
        window._worker = None
        window.close()


def test_dump_blocked_while_scan_running(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])

    class RunningStub:
        def isRunning(self):
            return True

        def cancel(self):
            pass

    window = MainWindow()
    window._worker = RunningStub()
    try:
        window._dump_all()
        assert window._file_op_worker is None
        assert window._file_op_dialog is None
        assert "scan" in window.progress_label.text().lower()
    finally:
        window._worker = None
        window.close()


def test_analysis_blocked_while_file_op_active(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])

    class RunningStub:
        def isRunning(self):
            return True

        def cancel(self):
            pass

    window = MainWindow()
    window._file_op_worker = RunningStub()
    try:
        window._start_analysis([str(tmp_path / "model.bin")], clear_existing=True)
        assert window._worker is None
        assert "file operation" in window.progress_label.text().lower()
    finally:
        window._file_op_worker = None
        window.close()


def test_indeterminate_progress_dialog(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"x")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    real_move = fow.safe_move

    def slow_move(src, dst):
        time.sleep(0.1)
        return real_move(src, dst)

    monkeypatch.setattr(fow, "safe_move", slow_move)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: str(dst_dir)),
    )

    window = MainWindow()
    _populate(window, str(model))
    try:
        window._move_selected_files()
        dialog = window._file_op_dialog
        assert dialog is not None
        assert dialog.minimum() == 0 and dialog.maximum() == 0
        assert dialog.windowModality() == Qt.WindowModality.WindowModal
        assert _drain_until(app, lambda: window._file_op_worker is None)
    finally:
        window.close()


def test_cancel_cooperates_and_reports(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    src1 = tmp_path / "a.safetensors"
    src2 = tmp_path / "b.safetensors"
    src1.write_bytes(b"a")
    src2.write_bytes(b"b")
    dst_dir = tmp_path / "dst"
    dst_dir.mkdir()

    real_move = fow.safe_move
    started = threading.Event()

    def slow_move(src, dst):
        started.set()
        time.sleep(0.3)
        return real_move(src, dst)

    monkeypatch.setattr(fow, "safe_move", slow_move)
    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: str(dst_dir)),
    )

    window = MainWindow()
    _populate(window, str(src1))
    _populate(window, str(src2))
    try:
        window._move_selected_files()
        worker = window._file_op_worker
        dialog = window._file_op_dialog
        assert worker is not None and dialog is not None
        assert started.wait(3.0)
        window._on_file_operation_cancel_requested()
        assert worker.isInterruptionRequested()
        assert window._file_op_dialog is dialog  # modal retained through cancel
        assert _drain_until(app, lambda: window._file_op_worker is None)
        assert "cancel" in window.progress_label.text().lower()
    finally:
        if worker is not None and worker.isRunning():
            worker.wait(2000)
        window.close()
