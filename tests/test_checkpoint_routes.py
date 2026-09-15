"""Checkpoint safety routing for GUI-only metadata inspection paths."""

from __future__ import annotations

import os
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

from back.checkpoint_reader import CHECKPOINT_SAFETY_METADATA, UnsafeCheckpointError
from back import reporting
from front import integration_controller, metadata_ui, window_lifecycle
import modelinfo


class _Signal:
    def connect(self, _callback) -> None:
        pass


class _AnalysisWorkerDouble:
    instance = None

    def __init__(self, filepaths, inspect_options, threads, checkpoint_safety=None):
        self.filepaths = filepaths
        self.inspect_options = inspect_options
        self.threads = threads
        self.checkpoint_safety = checkpoint_safety
        self.result_ready = _Signal()
        self.error_occurred = _Signal()
        self.all_done = _Signal()

    def start(self) -> None:
        _AnalysisWorkerDouble.instance = self


class _CacheSyncHost(integration_controller.IntegrationMixin):
    _allow_filename_alias_detection = False
    _cache_sync_worker = None

    def _cache_report(self):
        return SimpleNamespace(
            entries=(
                SimpleNamespace(
                    path="changed.pt",
                    action="refresh",
                    is_active=True,
                ),
            )
        )

    def _on_cache_sync_completed(self) -> None:
        pass


class _RawWidget:
    def setPlainText(self, _text: str) -> None:
        pass


class _Progress:
    def setVisible(self, _visible: bool) -> None:
        pass

    def setRange(self, _minimum: int, _maximum: int) -> None:
        pass


class _Button:
    def setEnabled(self, _enabled: bool) -> None:
        pass

    def setText(self, _text: str) -> None:
        pass


class _RawDumpHost(window_lifecycle.WindowLifecycleMixin):
    def __init__(self) -> None:
        self._results = []
        self.raw_text = _RawWidget()
        self.progress = _Progress()
        self.raw_load_btn = _Button()
        self._raw_loaded_filepath = None

    def _get_cached_raw_dump(self, _filepath: str):
        return None

    def _set_progress_status(self, _message: str) -> None:
        pass

    def _clear_progress_status(self, delay_ms: int = 0) -> None:
        pass


def test_cache_sync_uses_metadata_only_checkpoint_policy(monkeypatch) -> None:
    _AnalysisWorkerDouble.instance = None
    monkeypatch.setattr(
        integration_controller, "AnalysisWorker", _AnalysisWorkerDouble
    )

    _CacheSyncHost()._schedule_cache_sync()

    worker = _AnalysisWorkerDouble.instance
    assert worker is not None
    assert worker.filepaths == ["changed.pt"]
    assert worker.inspect_options["checkpoint_safety"] == CHECKPOINT_SAFETY_METADATA


def test_full_dump_gui_route_uses_metadata_only_checkpoint_policy(
    monkeypatch, tmp_path: Path
) -> None:
    QApplication.instance() or QApplication([])
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"\x80\x04not deserialized")
    options_seen = []
    monkeypatch.setattr(
        window_lifecycle,
        "generate_modelinfo_dump",
        lambda _filepath, options=None: options_seen.append(options) or "keys",
    )
    monkeypatch.setattr(window_lifecycle, "store_raw_dump", lambda *_args: None)

    _RawDumpHost()._load_raw_dump(str(checkpoint))

    assert options_seen == [{"checkpoint_safety": CHECKPOINT_SAFETY_METADATA}]


def test_reporting_and_modelinfo_forward_explicit_header_policy(monkeypatch) -> None:
    options = {"checkpoint_safety": CHECKPOINT_SAFETY_METADATA}
    reporting_seen = []
    with monkeypatch.context() as patch:
        patch.setattr(
            modelinfo,
            "generate_modelinfo_dump",
            lambda _filepath, options=None, inspection=None: reporting_seen.append(options) or "dump",
        )
        assert reporting.generate_modelinfo_dump("model.pt", options=options) == "dump"
        assert reporting_seen == [options]

    header_seen = []
    monkeypatch.setattr(
        modelinfo,
        "_read_header_or_cached",
        lambda _filepath, options=None: header_seen.append(options) or ({}, {}, 0),
    )
    modelinfo.generate_modelinfo_dump("model.pt", options=options)
    assert header_seen == [options]


def test_advanced_header_loader_uses_metadata_only_checkpoint_policy(monkeypatch) -> None:
    options_seen = []
    monkeypatch.setattr(
        metadata_ui,
        "get_cached_model_data",
        lambda _filepath, options=None: options_seen.append(options) or None,
    )
    monkeypatch.setattr(
        metadata_ui,
        "read_model_header",
        lambda _filepath, options=None: options_seen.append(options) or ({}, {}, 0),
    )

    metadata_ui.load_header_only("model.pt")

    assert options_seen == [
        {"checkpoint_safety": CHECKPOINT_SAFETY_METADATA},
        {"checkpoint_safety": CHECKPOINT_SAFETY_METADATA},
    ]


def test_modelinfo_api_default_still_rejects_raw_pickle_checkpoint(tmp_path: Path) -> None:
    checkpoint = tmp_path / "model.pt"
    checkpoint.write_bytes(b"\x80\x04never deserialize this")

    with pytest.raises(UnsafeCheckpointError):
        reporting.generate_modelinfo_dump(str(checkpoint))
