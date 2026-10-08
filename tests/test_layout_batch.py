from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from PyQt6.QtCore import QCoreApplication, QEvent, QObject
from PyQt6.QtWidgets import QApplication

from front.filter_projection import FilterProjection
from front.layout_batch import cards_layout_batch
from front.scan_projection import ProjectionEvent, ScanProjectionBuffer
from gui import MainWindow


class _Layout:
    def __init__(self, enabled: bool = True) -> None:
        self.enabled = enabled
        self.disable_calls = 0
        self.enable_calls = 0
        self.activations = 0

    def isEnabled(self) -> bool:
        return self.enabled

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled
        if enabled:
            self.enable_calls += 1
        else:
            self.disable_calls += 1

    def activate(self) -> bool:
        self.activations += 1
        return True


class _Owner:
    def __init__(self, layout) -> None:
        self.cards_layout = layout


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_layout_batch_nests_and_restores_only_the_original_enabled_state() -> None:
    layout = _Layout()
    owner = _Owner(layout)
    outer = cards_layout_batch(owner)
    inner = cards_layout_batch(owner)

    outer.__enter__()
    inner.__enter__()
    outer.__exit__(None, None, None)
    assert not layout.enabled
    assert layout.activations == 0
    inner.__exit__(None, None, None)
    inner.__exit__(None, None, None)
    assert layout.enabled
    assert (layout.disable_calls, layout.enable_calls, layout.activations) == (1, 1, 1)

    disabled = _Layout(enabled=False)
    with cards_layout_batch(_Owner(disabled)):
        with cards_layout_batch(_Owner(disabled)):
            assert not disabled.enabled
    assert (disabled.disable_calls, disabled.enable_calls, disabled.activations) == (0, 0, 0)

    with pytest.raises(ValueError):
        with cards_layout_batch(owner):
            raise ValueError("release on error")
    assert layout.enabled
    assert layout.activations == 2


def test_scan_projection_batches_each_drain_and_acknowledges_after_release() -> None:
    _app()
    layout = _Layout()
    owner = _Owner(layout)
    projected = []
    reconciled = []
    completed = []
    acknowledgements = []
    buffer = ScanProjectionBuffer(
        lambda kind, payload: projected.append((kind, payload, layout.enabled)),
        lambda final: reconciled.append((final, layout.enabled)),
        lambda terminal: completed.append((terminal, layout.enabled)),
        max_items=2,
        max_milliseconds=1000,
        layout_context_factory=lambda: cards_layout_batch(owner),
    )
    generation = buffer.begin()
    for value in range(5):
        buffer.enqueue(
            ProjectionEvent(
                generation,
                "result",
                value,
                lambda value=value: acknowledgements.append(
                    (value, layout.enabled, layout.activations)
                ),
            )
        )
    buffer.mark_terminal(generation, "done")

    buffer.drain_now()
    assert len(projected) == 2
    assert buffer.pending_count == 3
    assert layout.enabled
    assert len(acknowledgements) == 2
    buffer.drain_now()
    assert len(projected) == 4
    buffer.drain_now()

    assert [item[2] for item in projected] == [False] * 5
    assert reconciled == [(False, False)] * 3 + [(True, False)]
    assert completed == [("done", False)]
    assert [item[0] for item in acknowledgements] == list(range(5))
    assert all(enabled and activated >= 1 for _, enabled, activated in acknowledgements)
    assert layout.activations == 3


def test_scan_projection_acknowledges_errors_and_invalidated_cache_payloads() -> None:
    _app()
    layout = _Layout()
    owner = _Owner(layout)
    acknowledged = []

    def fail_projection(kind, payload):
        raise RuntimeError("projection failed")

    buffer = ScanProjectionBuffer(
        fail_projection,
        lambda _final: None,
        lambda _terminal: None,
        max_items=1,
        layout_context_factory=lambda: cards_layout_batch(owner),
    )
    generation = buffer.begin()
    for value in range(2):
        buffer.enqueue(
            ProjectionEvent(
                generation,
                "cache_result",
                value,
                lambda value=value: acknowledged.append((value, layout.enabled)),
            )
        )
    with pytest.raises(RuntimeError, match="projection failed"):
        buffer.drain_now()
    assert layout.enabled
    assert acknowledged == [(0, True)]

    buffer.invalidate()
    assert buffer.pending_count == 0
    assert acknowledged == [(0, True), (1, True)]


def test_filter_projection_releases_on_close_and_owner_destruction(
    monkeypatch, tmp_path: Path
) -> None:
    app = _app()
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    window = MainWindow()
    projection = FilterProjection(window)
    window._filter_projection = projection
    rows = [{"filepath": str(index)} for index in range(64)]
    projection.request(
        rows,
        None,
        None,
        None,
        get_tags=lambda _data: [],
        get_format=lambda _data: "",
        apply_visibility=lambda _path, _visible: None,
        report_progress=lambda _done, _total: None,
        complete=lambda *_counts: None,
        responsive=True,
    )
    assert projection.pending
    assert not window.cards_layout.isEnabled()
    assert projection._timer.isActive()
    window.close()
    assert not projection.pending
    assert not projection._timer.isActive()
    assert window.cards_layout.isEnabled()

    owner = QObject()
    layout = _Layout()
    owner.cards_layout = layout
    destroyed_projection = FilterProjection(owner)
    destroyed_projection.request(
        rows,
        None,
        None,
        None,
        get_tags=lambda _data: [],
        get_format=lambda _data: "",
        apply_visibility=lambda _path, _visible: None,
        report_progress=lambda _done, _total: None,
        complete=lambda *_counts: None,
        responsive=True,
    )
    assert not layout.enabled
    owner.deleteLater()
    QCoreApplication.sendPostedEvents(owner, QEvent.Type.DeferredDelete)
    app.processEvents()
    assert layout.enabled
    assert not destroyed_projection.pending
    assert layout.activations == 0


def test_synchronous_filter_holds_layout_through_final_refresh(
    monkeypatch, tmp_path: Path
) -> None:
    _app()
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    window = MainWindow()
    window._results = [{"filepath": str(tmp_path / "one.safetensors")}]
    observed = []
    refresh = window._refresh_card_layout_geometry

    def capture_refresh():
        observed.append(window.cards_layout.isEnabled())
        refresh()

    monkeypatch.setattr(window, "_refresh_card_layout_geometry", capture_refresh)
    try:
        window._apply_arch_filter()
        assert observed == [False]
        assert window.cards_layout.isEnabled()
    finally:
        window.close()


def test_reentrant_filter_request_keeps_lease_and_latest_generation() -> None:
    _app()
    owner = QObject()
    layout = _Layout()
    owner.cards_layout = layout
    projection = FilterProjection(owner)
    callback_states = []
    reentered = False

    def apply_visibility(_path, _visible):
        nonlocal reentered
        if reentered:
            return
        reentered = True
        projection.request(
            [{"filepath": "latest"}],
            None,
            None,
            None,
            get_tags=lambda _data: [],
            get_format=lambda _data: "",
            apply_visibility=apply_visibility,
            report_progress=lambda _done, _total: None,
            complete=lambda *_counts: None,
            responsive=False,
        )
        callback_states.append(layout.enabled)

    projection.request(
        [{"filepath": str(index)} for index in range(64)],
        None,
        None,
        None,
        get_tags=lambda _data: [],
        get_format=lambda _data: "",
        apply_visibility=apply_visibility,
        report_progress=lambda _done, _total: None,
        complete=lambda *_counts: None,
        responsive=True,
    )

    assert callback_states == [False]
    assert projection.index == 1
    assert not projection.pending
    assert layout.enabled
    assert layout.activations == 1


def test_cache_projection_shows_each_bounded_batch_before_terminal(
    monkeypatch, tmp_path: Path
) -> None:
    app = _app()
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.jsonc"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    window = MainWindow()

    class Worker:
        outcome = SimpleNamespace(was_cancelled=False, stale_count=0)

        def __init__(self) -> None:
            self.acknowledged = []

        def acknowledge_event(self) -> None:
            self.acknowledged.append((window.cards_layout.isEnabled(), window.table.rowCount()))

        def isRunning(self) -> bool:
            return False

    worker = Worker()
    generation = window._projection.begin()
    window._cache_load_worker = worker
    window._cache_load_generation = generation
    window._cache_load_progress_total = 2
    window._cache_load_projected_count = 0
    window._projection.max_items = 1
    activations = []
    activate = window.cards_layout.activate
    monkeypatch.setattr(
        window.cards_layout,
        "activate",
        lambda: (activations.append(True), activate())[1],
    )

    try:
        for index in range(2):
            filepath = str(tmp_path / f"cache-{index}.safetensors")
            window._on_cache_load_summary(
                generation,
                worker,
                {
                    "filepath": filepath,
                    "filename": Path(filepath).name,
                    "format": "SAFETENSORS",
                    "file_size": 1,
                    "file_size_friendly": "1 B",
                    "architecture": "Unknown",
                    "model_type": "Unknown",
                    "quantization": "Unknown",
                    "precision_summary": "Unknown",
                    "total_params": 0,
                    "total_params_friendly": "0",
                    "tensor_count": 0,
                    "components": {},
                    "named_text_encoders": {},
                    "component_precisions": {},
                    "training_meta": {},
                    "capability_facts": {},
                    "is_moe": False,
                },
            )
        window._projection.mark_terminal(generation, worker)

        window._projection.drain_now()
        assert len(window._results) == window.table.rowCount() == 1
        assert window._cache_load_worker is worker
        assert worker.acknowledged == [(True, 1)]
        window._projection.drain_now()
        app.processEvents()

        assert len(window._results) == window.table.rowCount() == 2
        assert window._cache_load_worker is None
        assert worker.acknowledged == [(True, 1), (True, 2)]
        assert window.cards_layout.isEnabled()
        assert activations == [True, True]
    finally:
        window.close()
