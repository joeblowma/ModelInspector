#!/usr/bin/env python3
"""Repeatable pre-refactor scan and GUI baseline for the approved goal.

The probe creates only synthetic header-only model files and disposable directory
trees beneath R:\\codexTemp (or the system temporary directory). It never reads or
modifies user model files.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import struct
import sys
import tempfile
import threading
import time
import tracemalloc
from concurrent.futures import ThreadPoolExecutor as RealThreadPoolExecutor
from pathlib import Path
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[2]
SRC_DIR = REPO_ROOT / "src"
sys.path.insert(0, str(SRC_DIR))

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

TEMP_ROOT = Path(r"R:\codexTemp")
if not TEMP_ROOT.is_dir():
    TEMP_ROOT = Path(tempfile.gettempdir())


def _rss_bytes() -> int:
    """Return current Windows working set using only the standard library."""

    class ProcessMemoryCounters(ctypes.Structure):
        _fields_ = [
            ("cb", ctypes.c_ulong),
            ("PageFaultCount", ctypes.c_ulong),
            ("PeakWorkingSetSize", ctypes.c_size_t),
            ("WorkingSetSize", ctypes.c_size_t),
            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPagedPoolUsage", ctypes.c_size_t),
            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
            ("PagefileUsage", ctypes.c_size_t),
            ("PeakPagefileUsage", ctypes.c_size_t),
        ]

    counters = ProcessMemoryCounters()
    counters.cb = ctypes.sizeof(counters)
    get_current_process = ctypes.windll.kernel32.GetCurrentProcess
    get_current_process.restype = ctypes.c_void_p
    get_process_memory_info = ctypes.windll.psapi.GetProcessMemoryInfo
    get_process_memory_info.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ProcessMemoryCounters),
        ctypes.c_ulong,
    ]
    get_process_memory_info.restype = ctypes.c_int
    handle = get_current_process()
    ok = get_process_memory_info(
        handle, ctypes.byref(counters), counters.cb
    )
    return int(counters.WorkingSetSize) if ok else 0


def _deep_size(value: Any, seen: set[int] | None = None) -> int:
    if seen is None:
        seen = set()
    identity = id(value)
    if identity in seen:
        return 0
    seen.add(identity)
    size = sys.getsizeof(value)
    if isinstance(value, dict):
        size += sum(
            _deep_size(key, seen) + _deep_size(item, seen)
            for key, item in value.items()
        )
    elif isinstance(value, (list, tuple, set, frozenset)):
        size += sum(_deep_size(item, seen) for item in value)
    return size


def _write_safetensors(path: Path, tensor_count: int = 64) -> None:
    header: dict[str, Any] = {
        "__metadata__": {
            "modelspec.title": path.stem,
            "modelspec.architecture": "stable-diffusion-v1",
            "ss_output_name": path.stem,
        }
    }
    offset = 0
    for index in range(tensor_count):
        name = f"model.diffusion_model.input_blocks.{index}.weight"
        header[name] = {
            "dtype": "F16",
            "shape": [4, 4],
            "data_offsets": [offset, offset + 32],
        }
        offset += 32
    encoded = json.dumps(header, separators=(",", ":")).encode("utf-8")
    path.write_bytes(struct.pack("<Q", len(encoded)) + encoded)


def _result_payload(index: int) -> dict[str, Any]:
    filepath = str(TEMP_ROOT / "synthetic_models" / f"model_{index:05d}.safetensors")
    metadata = {
        f"synthetic.meta.{item}": (f"value-{index}-{item}-" + "x" * 480)
        for item in range(64)
    }
    return {
        "filepath": filepath,
        "resolved_filepath": filepath,
        "format": "SAFETENSORS",
        "filename": Path(filepath).name,
        "file_size": 1_048_576 + index,
        "file_size_friendly": "1.0 MB",
        "tensor_count": 128,
        "total_params": 1_000_000 + index,
        "total_params_friendly": "1.0M",
        "architecture": "SD 1.5",
        "arch_details": {"synthetic": True, "index": index},
        "model_type": "Checkpoint",
        "components": {"unet": True, "vae": True, "text_encoder": True},
        "named_text_encoders": {"CLIP": 1},
        "lora_rank": None,
        "adapter_type": None,
        "quantization": None,
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "training_meta": {"software": "synthetic", "steps": index},
        "dtypes": [
            {"dtype": "F16", "friendly": "FP16", "bits": 16, "count": 128, "pct": 100.0}
        ],
        "precision_summary": "FP16",
        "component_precision_summary": "UNet FP16",
        "component_precisions": {"unet": "FP16", "vae": "FP16"},
        "precision_display": "FP16",
        "metadata": metadata,
        "extra": {"model_title": f"Synthetic {index}"},
        "warnings": [],
    }


def _qt_app():
    from PyQt6.QtWidgets import QApplication

    return QApplication.instance() or QApplication([])


def probe_discovery(size: str) -> dict[str, Any]:
    from PyQt6.QtCore import QEventLoop, QTimer
    from gui import MainWindow

    directory_count = 100 if size == "small" else 1_000
    app = _qt_app()
    with tempfile.TemporaryDirectory(prefix="smi_discovery_", dir=TEMP_ROOT) as raw:
        root = Path(raw)
        for index in range(directory_count):
            directory = root / f"group_{index // 100:03d}" / f"model_{index:05d}"
            directory.mkdir(parents=True)
            _write_safetensors(directory / f"model_{index:05d}.safetensors", 1)
            (directory / "ignored.txt").write_text("synthetic", encoding="utf-8")

        settings = root / "settings.ini"
        os.environ["SMI_SETTINGS_PATH"] = str(settings)
        os.environ["SMI_CACHE_DIR"] = str(root / "cache")
        window = MainWindow()
        timer_gaps: list[float] = []
        last_tick = time.perf_counter()
        timer = QTimer()
        timer.setInterval(10)

        def heartbeat() -> None:
            nonlocal last_tick
            now = time.perf_counter()
            timer_gaps.append((now - last_tick) * 1_000)
            last_tick = now

        timer.timeout.connect(heartbeat)
        timer.start()
        loop = QEventLoop()
        result: dict[str, Any] = {}

        started = 0.0

        def finish_when_discovered() -> None:
            worker = window._discovery_worker
            if worker is not None and not worker.isRunning():
                result.update(
                    elapsed_ms=(time.perf_counter() - started) * 1_000,
                    found=len(window._queued_files),
                )
                QTimer.singleShot(80, loop.quit)
                return
            QTimer.singleShot(10, finish_when_discovered)

        def run() -> None:
            nonlocal started
            started = time.perf_counter()
            window._auto_analyze_on_add = False
            window._start_discovery([str(root)])
            QTimer.singleShot(0, finish_when_discovered)
            QTimer.singleShot(120_000, loop.quit)

        QTimer.singleShot(120, run)
        loop.exec()
        timer.stop()
        window.close()
        app.processEvents()
        result.update(
            mode="discovery",
            size=size,
            directories=directory_count,
            max_event_gap_ms=max(timer_gaps, default=0.0),
            heartbeat_samples=len(timer_gaps),
        )
        return result


def probe_gui(size: str) -> dict[str, Any]:
    from PyQt6.QtCore import QCoreApplication, QEvent, QEventLoop, QTimer
    from gui import MainWindow

    result_count = 25 if size == "small" else 250
    app = _qt_app()
    with tempfile.TemporaryDirectory(prefix="smi_gui_", dir=TEMP_ROOT) as raw:
        root = Path(raw)
        os.environ["SMI_SETTINGS_PATH"] = str(root / "settings.ini")
        os.environ["SMI_CACHE_DIR"] = str(root / "cache")
        window = MainWindow()
        tracemalloc.start()
        payloads = [_result_payload(index) for index in range(result_count)]
        payload_bytes = _deep_size(payloads)
        rss_before = _rss_bytes()
        timer_gaps: list[float] = []
        last_tick = time.perf_counter()
        timer = QTimer()
        timer.setInterval(10)

        def heartbeat() -> None:
            nonlocal last_tick
            now = time.perf_counter()
            timer_gaps.append((now - last_tick) * 1_000)
            last_tick = now

        timer.timeout.connect(heartbeat)
        timer.start()
        loop = QEventLoop()
        measured: dict[str, Any] = {}

        class TerminalWorker:
            was_cancelled = False

            def isRunning(self) -> bool:
                return False

        terminal_worker = TerminalWorker()
        projection_started = 0.0

        def finish_when_projected() -> None:
            if (
                len(window._results) == result_count
                and window._projection.pending_count == 0
            ):
                measured["projection_elapsed_ms"] = (
                    time.perf_counter() - projection_started
                ) * 1_000
                QTimer.singleShot(80, loop.quit)
                return
            QTimer.singleShot(10, finish_when_projected)

        def ingest() -> None:
            nonlocal projection_started
            projection_started = time.perf_counter()
            window._worker = terminal_worker
            window._analysis_total_count = result_count
            started = time.perf_counter()
            for payload in payloads:
                window._on_result(payload)
            measured["ingest_ms"] = (time.perf_counter() - started) * 1_000
            # The generated full-detail inputs belong to the workload driver, not
            # the application. Release them once compact projection has accepted
            # each item so retained allocations measure GUI/orchestration state.
            payloads.clear()
            del payload
            window._projection.mark_terminal(window._scan_generation, terminal_worker)
            QTimer.singleShot(0, finish_when_projected)
            QTimer.singleShot(120_000, loop.quit)

        QTimer.singleShot(150, ingest)
        loop.exec()
        timer.stop()
        current, peak = tracemalloc.get_traced_memory()
        rss_after = _rss_bytes()
        retained_result_bytes = _deep_size(window._results)
        detailed_card_count = len(window._path_to_card)
        simple_card_count = len(window._path_to_simple_card)
        table_row_count = window.table.rowCount()
        window._clear_all()
        window._worker = None
        payloads.clear()
        app.processEvents()
        QCoreApplication.sendPostedEvents(None, QEvent.Type.DeferredDelete)
        app.processEvents()
        after_clear, _ = tracemalloc.get_traced_memory()
        rss_after_clear = _rss_bytes()
        tracemalloc.stop()
        window.close()
        app.processEvents()
        measured.update(
            mode="gui",
            size=size,
            results=result_count,
            payload_bytes=payload_bytes,
            retained_result_bytes=retained_result_bytes,
            tracemalloc_current_bytes=current,
            tracemalloc_peak_bytes=peak,
            tracemalloc_after_clear_bytes=after_clear,
            rss_before_bytes=rss_before,
            rss_after_bytes=rss_after,
            rss_after_clear_bytes=rss_after_clear,
            max_event_gap_ms=max(timer_gaps, default=0.0),
            heartbeat_samples=len(timer_gaps),
            detailed_cards=detailed_card_count,
            simple_cards=simple_card_count,
            table_rows=table_row_count,
        )
        return measured


def probe_analysis(size: str) -> dict[str, Any]:
    from inspect_model import inspect_file

    file_count = 10 if size == "small" else 100
    tensors = 64 if size == "small" else 128
    with tempfile.TemporaryDirectory(prefix="smi_analysis_", dir=TEMP_ROOT) as raw:
        root = Path(raw)
        os.environ["SMI_CACHE_DIR"] = str(root / "cache")
        paths = []
        for index in range(file_count):
            path = root / f"model_{index:05d}.safetensors"
            _write_safetensors(path, tensors)
            paths.append(str(path))
        rss_before = _rss_bytes()
        tracemalloc.start()
        started = time.perf_counter()
        results = [inspect_file(path) for path in paths]
        elapsed = time.perf_counter() - started
        current, peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()
        return {
            "mode": "analysis",
            "size": size,
            "files": file_count,
            "tensors_per_file": tensors,
            "elapsed_ms": elapsed * 1_000,
            "files_per_second": file_count / elapsed,
            "tracemalloc_current_bytes": current,
            "tracemalloc_peak_bytes": peak,
            "rss_delta_bytes": _rss_bytes() - rss_before,
            "result_bytes": _deep_size(results),
        }


def probe_worker(size: str) -> dict[str, Any]:
    import background_tasks

    path_count = 25 if size == "small" else 500
    tracker: dict[str, int] = {"submitted": 0, "pending": 0, "max_pending": 0}
    lock = threading.Lock()

    class TrackingExecutor(RealThreadPoolExecutor):
        def submit(self, fn, /, *args, **kwargs):
            with lock:
                tracker["submitted"] += 1
                tracker["pending"] += 1
                tracker["max_pending"] = max(tracker["max_pending"], tracker["pending"])
            future = super().submit(fn, *args, **kwargs)

            def completed(_future) -> None:
                with lock:
                    tracker["pending"] -= 1

            future.add_done_callback(completed)
            return future

    original_executor = background_tasks.ThreadPoolExecutor
    original_inspect = background_tasks.inspect_file

    def synthetic_inspect(filepath: str, options=None) -> dict[str, Any]:
        time.sleep(0.002)
        return {"filepath": filepath, "file_size": 1}

    try:
        background_tasks.ThreadPoolExecutor = TrackingExecutor
        background_tasks.inspect_file = synthetic_inspect
        worker = background_tasks.AnalysisWorker(
            [f"synthetic-{index}" for index in range(path_count)], threads=2
        )
        worker.result_ready.connect(lambda _: worker.acknowledge_event())
        worker.error_occurred.connect(lambda *_: worker.acknowledge_event())
        started = time.perf_counter()
        worker._run_parallel()
        elapsed = time.perf_counter() - started
    finally:
        background_tasks.ThreadPoolExecutor = original_executor
        background_tasks.inspect_file = original_inspect

    return {
        "mode": "worker",
        "size": size,
        "paths": path_count,
        "threads": 2,
        "submitted": tracker["submitted"],
        "max_pending": tracker["max_pending"],
        "pending_multiple_of_threads": tracker["max_pending"] / 2,
        "elapsed_ms": elapsed * 1_000,
    }


def probe_cancel_and_error() -> dict[str, Any]:
    import background_tasks
    from PyQt6.QtCore import QEventLoop, QTimer

    app = _qt_app()
    original_inspect = background_tasks.inspect_file
    results: list[str] = []
    errors: list[tuple[str, str]] = []
    completion: dict[str, Any] = {}

    def synthetic_inspect(filepath: str, options=None) -> dict[str, Any]:
        time.sleep(0.01)
        if filepath == "bad-model":
            raise ValueError("synthetic malformed header")
        return {"filepath": filepath, "file_size": 1}

    background_tasks.inspect_file = synthetic_inspect
    try:
        paths = [f"model-{index}" for index in range(100)]
        paths.insert(2, "bad-model")
        worker = background_tasks.AnalysisWorker(paths, threads=2)
        worker.result_ready.connect(
            lambda data: (results.append(data["filepath"]), worker.acknowledge_event())
        )
        worker.error_occurred.connect(
            lambda path, error: (
                errors.append((path, error)),
                worker.acknowledge_event(),
            )
        )
        loop = QEventLoop()
        cancel_started = 0.0

        def request_cancel() -> None:
            nonlocal cancel_started
            cancel_started = time.perf_counter()
            worker.cancel()

        def finished() -> None:
            completion["cancel_to_done_ms"] = (
                (time.perf_counter() - cancel_started) * 1_000 if cancel_started else 0.0
            )
            loop.quit()

        worker.all_done.connect(finished)
        worker.start()
        QTimer.singleShot(45, request_cancel)
        QTimer.singleShot(5_000, loop.quit)
        loop.exec()
        worker.wait(5_000)
        app.processEvents()
        completion.update(
            mode="cancel_error",
            input_paths=len(paths),
            result_count=len(results),
            error_count=len(errors),
            was_cancelled=worker.was_cancelled,
            running_after_wait=worker.isRunning(),
        )
        return completion
    finally:
        background_tasks.inspect_file = original_inspect


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "mode", choices=("discovery", "gui", "analysis", "worker", "cancel_error")
    )
    parser.add_argument("--size", choices=("small", "large"), default="small")
    args = parser.parse_args()
    probes = {
        "discovery": probe_discovery,
        "gui": probe_gui,
        "analysis": probe_analysis,
        "worker": probe_worker,
    }
    if args.mode == "cancel_error":
        result = probe_cancel_and_error()
    else:
        result = probes[args.mode](args.size)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
