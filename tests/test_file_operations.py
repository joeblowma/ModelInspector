# pyright: reportAttributeAccessIssue=false, reportUnusedExpression=false
"""File-operation controller/worker tests using only temp fixtures.

No real model files are read or moved; dump routines are stubbed at the worker
boundary so the tests never touch tensor headers.
"""

from __future__ import annotations

import errno
import os
import sys
import time
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QFileDialog, QMessageBox

import front.file_operation_worker as fow
from front import selection_controller
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


# --- Worker-level ----------------------------------------------------------


def test_move_worker_reports_mixed_results(tmp_path):
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    good = src_dir / "good.safetensors"
    good.write_bytes(b"payload")
    missing = src_dir / "missing.safetensors"

    worker = FileOperationWorker(
        "move",
        [
            (str(good), str(dst_dir / "good.safetensors")),
            (str(missing), str(dst_dir / "missing.safetensors")),
        ],
    )
    done = []
    worker.operation_done.connect(done.append)

    worker.run()

    result = done[0]
    assert result["mode"] == "move"
    assert result["moved"] == [str(good)]
    assert len(result["failed"]) == 1
    assert result["failed"][0][0] == str(missing)
    assert (dst_dir / "good.safetensors").exists()
    assert not good.exists()


def test_dump_worker_reuses_dump_routines_and_reports_failures(tmp_path, monkeypatch):
    written = []

    def fake_dump(filepath, **kwargs):
        out = filepath + ".modelinfo"
        written.append(out)
        return out

    monkeypatch.setattr(fow, "write_modelinfo_dump", fake_dump)
    monkeypatch.setattr(
        fow,
        "write_modelinfo_json",
        lambda filepath, options=None, **kwargs: filepath + ".modelinfo.json",
    )

    worker = FileOperationWorker(
        "dump",
        ["a.safetensors", "b.safetensors"],
        dump_json=True,
        dump_options={"allow_filename_alias_detection": True},
    )
    done = []
    worker.operation_done.connect(done.append)

    worker.run()

    result = done[0]
    assert result["mode"] == "dump"
    assert [entry["filepath"] for entry in result["dumped"]] == [
        "a.safetensors",
        "b.safetensors",
    ]
    assert result["failed"] == []
    assert written == ["a.safetensors.modelinfo", "b.safetensors.modelinfo"]


def test_posix_same_device_uses_link_not_rename(tmp_path, monkeypatch):
    """POSIX same-device moves must not use ``os.rename`` (which would silently
    replace an existing destination); ``os.link`` is atomic no-clobber even when
    the ``lexists`` fast path is bypassed by a concurrent writer."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"original")
    dst = tmp_path / "dst.bin"
    dst.write_bytes(b"racer")

    def forbid_rename(a, b):
        raise AssertionError("os.rename must not be used on the POSIX path")

    def colliding_link(a, b):
        raise FileExistsError(errno.EEXIST, "File exists", b)

    monkeypatch.setattr(fow.os, "name", "posix")
    monkeypatch.setattr(fow.os.path, "lexists", lambda p: False)
    monkeypatch.setattr(fow.os, "rename", forbid_rename)
    monkeypatch.setattr(fow.os, "link", colliding_link)
    status = fow.safe_move(str(src), str(dst))
    assert status == "skipped_exists"
    assert src.read_bytes() == b"original"
    assert dst.read_bytes() == b"racer"


def test_same_device_race_after_check_skips_without_clobber(tmp_path, monkeypatch):
    """A destination created between the existence check and the same-device
    mutation is skipped, never overwritten (closes the ``os.rename`` TOCTOU)."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"original")
    dst = tmp_path / "dst.bin"

    def racing_link(s, d):
        # Simulate a concurrent writer creating dst after our lexists check
        # but before the atomic link mutation.
        Path(d).write_bytes(b"racer")
        raise FileExistsError(errno.EEXIST, "File exists", d)

    monkeypatch.setattr(fow.os, "name", "posix")
    monkeypatch.setattr(fow.os, "link", racing_link)
    status = fow.safe_move(str(src), str(dst))
    assert status == "skipped_exists"
    assert src.read_bytes() == b"original"
    assert dst.read_bytes() == b"racer"


def test_cross_device_exclusive_race_after_check_skips_without_clobber(
    tmp_path, monkeypatch
):
    """A destination created between the existence check and the ``O_EXCL``
    reservation is skipped, never overwritten."""
    src = tmp_path / "src.bin"
    src.write_bytes(b"original")
    dst = tmp_path / "dst.bin"

    def exdev(a, b):
        raise OSError(errno.EXDEV, "cross-device link")

    monkeypatch.setattr(fow.os, "rename", exdev)

    def racing_open(path, flags, *args, **kwargs):
        # Simulate a concurrent writer creating dst just before our exclusive
        # open reservation.
        Path(path).write_bytes(b"racer")
        raise FileExistsError(errno.EEXIST, "File exists", path)

    monkeypatch.setattr(fow.os, "open", racing_open)
    status = fow.safe_move(str(src), str(dst))
    assert status == "skipped_exists"
    assert src.read_bytes() == b"original"
    assert dst.read_bytes() == b"racer"


def test_copy_symlink_exclusive_collision_preserves_existing_dst(tmp_path):
    """A symlink re-creation that loses the race must not unlink the concurrent
    writer's destination (owned partial cleanup only)."""
    target = tmp_path / "real.bin"
    target.write_bytes(b"payload")
    link = tmp_path / "link.bin"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlinks unavailable: {exc}")
    dst = tmp_path / "dst.bin"
    dst.write_bytes(b"racer")

    with pytest.raises(FileExistsError):
        fow._copy_symlink_exclusive(str(link), str(dst))
    assert dst.read_bytes() == b"racer"
    assert link.is_symlink()


# --- GUI integration -------------------------------------------------------


def test_dump_uses_modal_progress_and_updates_button(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])

    def fake_dump(filepath, **kwargs):
        out = filepath + ".modelinfo"
        Path(out).write_text("dump", encoding="utf-8")
        return out

    monkeypatch.setattr(fow, "write_modelinfo_dump", fake_dump)
    monkeypatch.setattr(
        fow,
        "write_modelinfo_json",
        lambda filepath, options=None, **kwargs: filepath + ".modelinfo.json",
    )

    window = MainWindow()
    path = str(tmp_path / "model.safetensors")
    _populate(window, path)
    window._dump_json_modelinfo = False
    window._selected_action = "dump_modelinfo"
    try:
        window._dump_all()
        assert window._file_op_worker is not None
        assert _drain_until(app, lambda: window._file_op_worker is None)
        assert window._file_op_dialog is None
        assert "Dumped 1 file" in window.selected_action_btn.text()
        assert (tmp_path / "model.safetensors.modelinfo").exists()
    finally:
        window.close()



def test_move_uses_modal_progress_and_cleans_up(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    model = src_dir / "model.safetensors"
    model.write_bytes(b"payload")

    real_move = fow.safe_move

    def slow_move(src, dst):
        time.sleep(0.15)
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
        worker = window._file_op_worker
        assert worker is not None
        dialog = window._file_op_dialog
        assert dialog is not None
        assert dialog.windowModality() == Qt.WindowModality.WindowModal

        # Reentrancy: a second invocation while running is ignored.
        window._move_selected_files()
        assert window._file_op_worker is worker

        assert _drain_until(app, lambda: "Moving" in window.progress_label.text())
        assert _drain_until(app, lambda: window._file_op_worker is None)
        assert window._file_op_dialog is None
        assert not model.exists()
        assert (dst_dir / model.name).exists()
        assert str(model) not in [r.get("filepath") for r in window._results]
    finally:
        window.close()


def test_move_dialog_defaults_to_output_dir(tmp_path, monkeypatch):
    """The move destination dialog opens in the default output directory,
    not the process CWD."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    output = tmp_path / "out"
    monkeypatch.setenv("SMI_OUTPUT_DIR", str(output))
    app = QApplication.instance() or QApplication([])

    captured = {}

    def fake_dialog(*args, **kwargs):
        captured["args"] = args
        return ""  # cancel the dialog; no worker starts

    monkeypatch.setattr(QFileDialog, "getExistingDirectory", staticmethod(fake_dialog))

    window = MainWindow()
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"x")
    _populate(window, str(model))
    try:
        window._move_selected_files()
        # getExistingDirectory(parent, caption, initial_dir)
        assert captured["args"][2] == str(output)
        assert output.is_dir()
        assert window._file_op_worker is None
    finally:
        window.close()


def test_move_reports_mixed_failures_and_keeps_failed_rows(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    good = src_dir / "good.safetensors"
    good.write_bytes(b"x")
    missing = src_dir / "missing.safetensors"  # never created

    monkeypatch.setattr(
        QFileDialog,
        "getExistingDirectory",
        staticmethod(lambda *a, **k: str(dst_dir)),
    )
    warnings = []
    monkeypatch.setattr(
        QMessageBox, "warning", staticmethod(lambda *a, **k: warnings.append(a))
    )

    window = MainWindow()
    _populate(window, str(good))
    _populate(window, str(missing))
    try:
        window._move_selected_files()
        assert _drain_until(app, lambda: window._file_op_worker is None)
        assert (dst_dir / "good.safetensors").exists()
        assert not good.exists()
        remaining = [r.get("filepath") for r in window._results]
        assert str(good) not in remaining
        assert str(missing) in remaining
        assert len(warnings) == 1
        assert warnings[0][1] == "Move incomplete"
    finally:
        window.close()


def test_quick_ops_show_status(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])

    class FakeClipboard:
        def __init__(self):
            self.text = None
            self.mime = None

        def setText(self, text):
            self.text = text

        def setMimeData(self, mime):
            self.mime = mime

    fake = FakeClipboard()
    monkeypatch.setattr(selection_controller, "_clipboard", lambda: fake)

    window = MainWindow()
    path = str(tmp_path / "model.safetensors")
    _populate(window, path)
    try:
        window._copy_selected_files_to_clipboard()
        assert "clipboard" in window.progress_label.text().lower()
        assert fake.mime is not None

        window._copy_selected_names()
        assert "Copied 1 file name" in window.progress_label.text()
        assert fake.text == "model.safetensors"

        window._copy_selected_paths()
        assert "Copied 1 file path" in window.progress_label.text()
        assert fake.text == path

        window._remove_selected_results()
        assert "Removed 1 selected entry" in window.progress_label.text()
        assert window._results == []
    finally:
        window.close()


def test_close_is_deferred_until_file_operation_finishes(tmp_path, monkeypatch):
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    app = QApplication.instance() or QApplication([])
    src_dir = tmp_path / "src"
    dst_dir = tmp_path / "dst"
    src_dir.mkdir()
    dst_dir.mkdir()
    model = src_dir / "model.safetensors"
    model.write_bytes(b"x")

    real_move = fow.safe_move

    def slow_move(src, dst):
        time.sleep(0.3)
        return real_move(src, dst)

    monkeypatch.setattr(fow, "safe_move", slow_move)

    window = MainWindow()
    worker = FileOperationWorker(
        "move", [(str(model), str(dst_dir / "model.safetensors"))]
    )
    window._file_op_worker = worker
    worker.progress_updated.connect(lambda _p: None)
    worker.operation_done.connect(lambda _r: None)
    window.show()
    app.processEvents()
    worker.start()
    try:
        assert window.close() is False
        assert window._close_pending
        assert worker.isRunning()
        assert worker.wait(2000)
        deadline = time.monotonic() + 3
        while window.isVisible() and time.monotonic() < deadline:
            app.processEvents()
        assert not window.isVisible()
        assert not window._close_pending
    finally:
        if worker.isRunning():
            worker.wait(2000)
        if window.isVisible():
            window.close()
