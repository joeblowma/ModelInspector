"""Frozen windowed --help shows a readable window instead of console output."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import front.application as application
from front.startup_arguments import format_help, help_requested


def test_help_requested_detects_short_and_long():
    assert help_requested(["--help"])
    assert help_requested(["-h"])
    assert help_requested(["model.safetensors", "--help"])
    assert not help_requested([])
    assert not help_requested(["model.safetensors"])


def test_format_help_contains_usage_and_cache_flags():
    text = format_help()
    assert "usage:" in text
    assert "--cachedir" in text
    assert "--cache" in text


def test_frozen_help_prog_label_uses_executable_name(monkeypatch):
    from front.startup_arguments import _prog_name

    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", "R:/dist/ModelInspector.exe")
    assert _prog_name() == "ModelInspector.exe"
    assert "usage: ModelInspector.exe" in format_help()


def test_stdout_unavailable_detects_missing_stream(monkeypatch):
    assert not application._stdout_unavailable()  # pytest capture provides one
    monkeypatch.setattr(sys, "stdout", None)
    assert application._stdout_unavailable()


def test_frozen_help_shows_window_and_closes_splash(monkeypatch):
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    captured = {}
    monkeypatch.setattr(
        application,
        "close_startup_splash",
        lambda: captured.__setitem__("splash", True),
    )
    monkeypatch.setattr(
        application,
        "show_help_window",
        lambda text: captured.__setitem__("text", text),
    )
    result = application.run(["--help"])
    assert result == 0
    assert captured.get("splash") is True
    assert "usage:" in captured.get("text", "")
