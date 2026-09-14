# pyright: reportAttributeAccessIssue=false, reportOptionalMemberAccess=false, reportCallIssue=false
"""Startup feedback: splash ordering, failure close, and single cache report."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

import front.application as application
import gui

_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    instance = QApplication.instance()
    _APPLICATION = instance if isinstance(instance, QApplication) else QApplication([])
    return _APPLICATION


class FakeSplash:
    """Records the splash lifecycle calls the startup path must make."""

    def __init__(self) -> None:
        self.events: list[str] = []

    def show(self) -> None:
        self.events.append("show")

    def repaint(self) -> None:
        self.events.append("repaint")

    def finish(self, window) -> None:
        self.events.append(f"finish:{type(window).__name__}")

    def close(self) -> None:
        self.events.append("close")


class FakeApp:
    def __init__(self, argv) -> None:
        pass

    def exec(self) -> int:
        return 0


def test_show_startup_splash_shows_and_paints_before_returning(monkeypatch):
    _app()
    events = []

    class RecordingSplash:
        def __init__(self, pixmap) -> None:
            events.append("construct")

        def show(self) -> None:
            events.append("show")

        def repaint(self) -> None:
            events.append("repaint")

    monkeypatch.setattr(application, "QSplashScreen", RecordingSplash)
    splash = application.show_startup_splash()
    assert isinstance(splash, RecordingSplash)
    # Explicit paint must happen before returning, i.e. before the blocking
    # MainWindow construction that follows in gui.main().
    assert events == ["construct", "show", "repaint"]


def test_show_startup_splash_returns_none_without_asset(monkeypatch, tmp_path):
    _app()
    monkeypatch.setattr(application, "asset_path", lambda *parts: tmp_path / "missing.png")
    assert application.show_startup_splash() is None


def test_main_shows_splash_before_window_and_finishes_after_show(monkeypatch):
    _app()
    splash = FakeSplash()

    class FakeWindow:
        def __init__(self) -> None:
            splash.events.append("construct")

        def show(self) -> None:
            splash.events.append("window-show")

    def fake_show_startup_splash():
        # ``gui.main`` delegates to ``show_startup_splash``, which shows and
        # paints before returning; record that ordering on the fake.
        splash.events.append("show")
        splash.events.append("repaint")
        return splash

    monkeypatch.setattr(gui, "QApplication", FakeApp)
    monkeypatch.setattr(gui, "configure_application", lambda app: None)
    monkeypatch.setattr(gui, "show_startup_splash", fake_show_startup_splash)
    monkeypatch.setattr(gui, "MainWindow", FakeWindow)
    monkeypatch.setattr(gui, "close_startup_splash", lambda: splash.events.append("pyi-close"))
    assert gui.main() == 0
    events = splash.events
    # Splash is on screen before expensive construction...
    assert events.index("show") < events.index("repaint") < events.index("construct")
    # ...and is finished only after the window can be shown.
    assert events.index("window-show") < events.index("finish:FakeWindow")
    assert events[-1] == "finish:FakeWindow"


def test_main_closes_splash_when_window_construction_fails(monkeypatch):
    _app()
    splash = FakeSplash()

    def boom() -> None:
        raise RuntimeError("construction failed")

    monkeypatch.setattr(gui, "QApplication", FakeApp)
    monkeypatch.setattr(gui, "configure_application", lambda app: None)
    monkeypatch.setattr(gui, "show_startup_splash", lambda: splash)
    monkeypatch.setattr(gui, "MainWindow", boom)
    try:
        gui.main()
    except RuntimeError:
        pass
    else:
        raise AssertionError("expected construction failure to propagate")
    assert splash.events[-1] == "close"


def test_configure_extended_ui_reuses_one_cache_report(monkeypatch):
    from front.integration_controller import IntegrationMixin

    class FakeSignal:
        def connect(self, callback) -> None:
            pass

    class FakeHeader:
        sectionMoved = FakeSignal()
        sectionResized = FakeSignal()

    class FakeTable:
        def horizontalHeader(self):
            return FakeHeader()

    class FakeTimer:
        @staticmethod
        def singleShot(delay, callback) -> None:
            scheduled.append(callback)

    scheduled: list = []

    class Stub(IntegrationMixin):
        def __init__(self) -> None:
            self.report_calls = 0
            self.refresh_reports: list = []
            self.sync_reports: list = []
            self.table = FakeTable()

        def _settings_data_layout(self):
            return {}

        def _apply_data_layout(self, layout) -> None:
            pass

        def _init_smart_groups(self) -> None:
            pass

        def _cache_report(self):
            self.report_calls += 1
            return {"report": self.report_calls}

        def _refresh_cache_controls(self, report=None) -> None:
            self.refresh_reports.append(report)

        def _schedule_cache_sync(self, report=None) -> None:
            self.sync_reports.append(report)

    monkeypatch.setattr("front.integration_controller.QTimer", FakeTimer)
    stub = Stub()
    stub._configure_extended_ui()
    # Exactly one expensive enumeration during startup; both consumers share it.
    assert stub.report_calls == 1
    assert stub.refresh_reports == [{"report": 1}]
    assert scheduled, "deferred cache sync must still be scheduled"
    scheduled[0]()
    assert stub.sync_reports == [{"report": 1}]
