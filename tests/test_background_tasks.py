import sys
import threading
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import background_tasks


def _result(filepath: str) -> dict:
    return {
        "filepath": filepath,
        "filename": Path(filepath).name,
        "architecture": "Synthetic",
        "file_size": 1,
        "metadata": {"large": "forbidden"},
        "tensor_info": {"tensor": {"shape": [1]}},
        "arch_details": {"private": True},
        "cache_status": "hit",
    }


def test_parallel_window_and_event_delivery_are_bounded(monkeypatch):
    def inspect(filepath, options=None):
        time.sleep(0.001)
        if filepath.endswith("13"):
            raise ValueError("malformed")
        return _result(filepath)

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    worker = background_tasks.AnalysisWorker(
        [f"model-{index}" for index in range(100)], threads=3
    )
    results = []
    errors = []
    worker.result_ready.connect(
        lambda result: (results.append(result), worker.acknowledge_event())
    )
    worker.error_occurred.connect(
        lambda path, error: (errors.append((path, error)), worker.acknowledge_event())
    )

    worker.run()

    assert len(results) == 99
    assert errors == [("model-13", "malformed")]
    assert worker.peak_in_flight <= max(2, 2 * worker.threads)
    assert worker.peak_outstanding_events <= max(8, 2 * worker.threads)
    assert worker.outstanding_events == 0
    assert all("metadata" not in result for result in results)
    assert all(result["cache_status"] == "hit" for result in results)


def test_parallel_results_keep_completion_order_policy(monkeypatch):
    fast_finished = threading.Event()

    def inspect(filepath, options=None):
        if filepath == "slow":
            assert fast_finished.wait(1)
            time.sleep(0.02)
        else:
            fast_finished.set()
        return _result(filepath)

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    worker = background_tasks.AnalysisWorker(["slow", "fast"], threads=2)
    delivered = []
    worker.result_ready.connect(
        lambda result: (delivered.append(result["filepath"]), worker.acknowledge_event())
    )

    worker.run()

    assert delivered == ["fast", "slow"]


def test_cancellation_wakes_worker_blocked_by_event_backpressure(monkeypatch):
    active = 0
    active_lock = threading.Lock()

    def inspect(filepath, options=None):
        nonlocal active
        with active_lock:
            active += 1
        try:
            time.sleep(0.002)
            return _result(filepath)
        finally:
            with active_lock:
                active -= 1

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    worker = background_tasks.AnalysisWorker(
        [f"model-{index}" for index in range(200)], threads=2
    )
    worker.start()
    deadline = time.monotonic() + 2
    while (
        worker.outstanding_events < worker.max_outstanding_events
        and time.monotonic() < deadline
    ):
        time.sleep(0.005)

    assert worker.outstanding_events == worker.max_outstanding_events
    started = time.monotonic()
    worker.cancel()
    assert worker.wait(2000)
    cancellation_seconds = time.monotonic() - started

    assert cancellation_seconds < 1
    assert worker.was_cancelled
    assert worker.peak_in_flight <= worker.max_in_flight
    assert worker.peak_outstanding_events == worker.max_outstanding_events
    with active_lock:
        assert active == 0


def test_sequential_worker_applies_shared_backpressure_to_errors(monkeypatch):
    def inspect(filepath, options=None):
        if int(filepath) % 2:
            raise RuntimeError(f"bad {filepath}")
        return _result(filepath)

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    worker = background_tasks.AnalysisWorker(
        [str(index) for index in range(24)], threads=1
    )
    event_kinds = []
    worker.result_ready.connect(
        lambda _: (event_kinds.append("result"), worker.acknowledge_event())
    )
    worker.error_occurred.connect(
        lambda *_: (event_kinds.append("error"), worker.acknowledge_event())
    )

    worker.run()

    assert event_kinds.count("result") == 12
    assert event_kinds.count("error") == 12
    assert worker.peak_outstanding_events <= worker.max_outstanding_events
    assert worker.peak_in_flight == 1


def test_discovery_deduplicates_and_emits_terminal_progress(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    (first / "one.safetensors").write_bytes(b"")
    (second / "two.GGUF").write_bytes(b"")
    (second / "ignored.txt").write_text("ignored", encoding="utf-8")
    progress = []
    terminal = []
    worker = background_tasks.DiscoveryWorker(str(tmp_path))
    worker.progress_updated.connect(progress.append)
    worker.discovery_done.connect(terminal.append)

    worker.run()

    assert len(terminal) == 1
    assert {Path(path).name for path in terminal[0]["paths"]} == {
        "one.safetensors",
        "two.GGUF",
    }
    assert terminal[0]["scanned_directories"] == 3
    assert not terminal[0]["cancelled"]
    assert progress[-1]["discovered_files"] == 2
    assert progress[-1]["scanned_directories"] == 3


def test_discovery_ignores_stale_safetensors_indexes(tmp_path):
    index = tmp_path / "model.safetensors.index.json"
    index.write_text(
        (
            '{"weight_map": {"alpha": "model-00001-of-00004.safetensors", '
            '"beta": "model-00002-of-00004.safetensors"}}'
        ),
        encoding="utf-8",
    )
    gguf = tmp_path / "unrelated.gguf"
    gguf.write_bytes(b"")
    terminal = []
    worker = background_tasks.DiscoveryWorker(str(tmp_path))
    worker.discovery_done.connect(terminal.append)

    worker.run()

    assert terminal[0]["paths"] == (str(gguf),)


def test_discovery_includes_checkpoints_only_after_metadata_opt_in(tmp_path):
    checkpoint = tmp_path / "untrusted.pt"
    checkpoint.write_bytes(b"not deserialized")
    default_terminal = []
    default = background_tasks.DiscoveryWorker(str(tmp_path))
    default.discovery_done.connect(default_terminal.append)
    default.run()
    assert default_terminal[0]["paths"] == ()

    metadata_terminal = []
    metadata = background_tasks.DiscoveryWorker(str(tmp_path), checkpoint_safety="metadata")
    metadata.discovery_done.connect(metadata_terminal.append)
    metadata.run()
    assert metadata_terminal[0]["paths"] == (str(checkpoint),)
    assert metadata_terminal[0]["checkpoint_safety"] == "metadata"


def test_analysis_worker_passes_only_explicit_checkpoint_metadata_opt_in(monkeypatch):
    options_seen = []

    def inspect(filepath, options=None):
        options_seen.append(dict(options or {}))
        return _result(filepath)

    monkeypatch.setattr(background_tasks, "inspect_file", inspect)
    worker = background_tasks.AnalysisWorker(["model.pt"], checkpoint_safety="metadata")
    worker.result_ready.connect(lambda _: worker.acknowledge_event())
    worker.run()
    assert options_seen == [{"checkpoint_safety": "metadata"}]


def test_discovery_cancellation_is_checked_between_directories(monkeypatch):
    def directories(root, onerror=None):
        for index in range(100):
            yield str(Path(root) / str(index)), [], [f"{index}.safetensors"]

    monkeypatch.setattr(background_tasks.os, "walk", directories)
    terminal = []
    worker = background_tasks.DiscoveryWorker("synthetic")
    worker.progress_updated.connect(lambda _: worker.cancel())
    worker.discovery_done.connect(terminal.append)

    worker.run()

    assert terminal[0]["cancelled"]
    assert terminal[0]["scanned_directories"] == 1


def test_discovery_progress_is_throttled_plus_final(monkeypatch):
    def directories(root, onerror=None):
        for index in range(30):
            yield str(Path(root) / str(index)), [], []

    ticks = iter(index / 100 for index in range(100))
    monkeypatch.setattr(background_tasks.os, "walk", directories)
    monkeypatch.setattr(background_tasks.time, "monotonic", lambda: next(ticks))
    progress = []
    worker = background_tasks.DiscoveryWorker("synthetic")
    worker.progress_updated.connect(progress.append)

    worker.run()

    # Thirty directories take 0.30 synthetic seconds: no more than three
    # periodic emissions plus the required terminal update.
    assert len(progress) <= 4
    assert progress[-1]["scanned_directories"] == 30


def test_discovery_reports_per_path_errors_and_completes(monkeypatch):
    error = PermissionError(13, "denied", "private")

    def failing_walk(root, onerror=None):
        if error is not None:
            if onerror is not None:
                onerror(error)
        return iter(())

    monkeypatch.setattr(background_tasks.os, "walk", failing_walk)
    errors = []
    terminal = []
    worker = background_tasks.DiscoveryWorker("synthetic")
    worker.error_occurred.connect(lambda path, message: errors.append((path, message)))
    worker.discovery_done.connect(terminal.append)

    worker.run()

    assert errors[0][0] == "private"
    assert "denied" in errors[0][1]
    assert terminal[0]["paths"] == ()
    assert not terminal[0]["cancelled"]


def test_empty_analysis_still_emits_all_done(monkeypatch):
    worker = background_tasks.AnalysisWorker([], threads=4)
    completions = []
    worker.all_done.connect(lambda: completions.append(True))

    worker.run()

    assert completions == [True]
    assert worker.peak_in_flight == 0
