"""Startup argument parsing, settings override, and queued startup targets."""

import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import front.application as application
from front.startup_arguments import parse_startup_arguments


def test_no_argument_launch_is_unchanged():
    args = parse_startup_arguments([])
    assert args.settings is None
    assert args.targets == []


def test_settings_override_and_positional_target_parse():
    args = parse_startup_arguments(["-s", "my.jsonc", "R:/models", "model.safetensors"])
    assert args.settings == Path("my.jsonc")
    assert args.targets == ["R:/models", "model.safetensors"]
    long_form = parse_startup_arguments(["--settings", "other.jsonc"])
    assert long_form.settings == Path("other.jsonc")


def test_help_terminates_before_qapplication(monkeypatch, capsys):
    created = []
    monkeypatch.setattr(
        application, "QApplication", lambda argv: created.append(argv)
    )
    try:
        application.run(["--help"])
    except SystemExit as exit_error:
        assert exit_error.code == 0
    else:
        raise AssertionError("--help must exit")
    assert created == [], "--help must not create a QApplication"
    assert "usage:" in capsys.readouterr().out


def test_help_exits_zero_when_streams_are_none(monkeypatch):
    """Frozen windowed builds set sys.stdout/stderr to None; --help must still
    terminate cleanly (argparse guards the missing stream on supported Python)."""
    monkeypatch.setattr(sys, "stdout", None)
    monkeypatch.setattr(sys, "stderr", None)
    try:
        parse_startup_arguments(["--help"])
    except SystemExit as exit_error:
        assert exit_error.code == 0
    else:
        raise AssertionError("--help must exit")


def test_settings_override_applied_before_settings_load(monkeypatch, tmp_path):
    monkeypatch.delenv("SMI_SETTINGS_PATH", raising=False)
    application._apply_settings_override(tmp_path / "chosen.jsonc")
    assert os.environ["SMI_SETTINGS_PATH"] == str(tmp_path / "chosen.jsonc")
    # Explicit CLI beats a pre-existing environment value.
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "env.jsonc"))
    application._apply_settings_override(tmp_path / "chosen.jsonc")
    assert os.environ["SMI_SETTINGS_PATH"] == str(tmp_path / "chosen.jsonc")
    # No flag leaves the environment untouched.
    before = os.environ["SMI_SETTINGS_PATH"]
    application._apply_settings_override(None)
    assert os.environ["SMI_SETTINGS_PATH"] == before


class StubWindow:
    def __init__(self) -> None:
        self.calls: list[tuple[str, object]] = []
        self._lifecycle_closed = False

    def _start_discovery(self, roots, *args, **kwargs) -> None:
        self.calls.append(("discovery", roots))

    def _add_files(self, paths) -> None:
        self.calls.append(("files", paths))


def _run_queued(monkeypatch, window: StubWindow, targets: list[str]) -> None:
    monkeypatch.setattr(
        application.QTimer, "singleShot", lambda delay, callback: callback()
    )
    application._queue_startup_targets(window, targets)


def test_startup_file_queues_through_add_files(monkeypatch, tmp_path):
    window = StubWindow()
    model = tmp_path / "model.safetensors"
    model.write_bytes(b"")
    _run_queued(monkeypatch, window, [str(model)])
    assert window.calls == [("files", [str(model)])]


def test_startup_folder_queues_through_discovery(monkeypatch, tmp_path):
    window = StubWindow()
    folder = tmp_path / "models"
    folder.mkdir()
    _run_queued(monkeypatch, window, [str(folder)])
    assert window.calls == [("discovery", [str(folder)])]


def test_startup_missing_or_unsupported_path_warns_without_queueing(
    monkeypatch, tmp_path
):
    window = StubWindow()
    warnings = []
    monkeypatch.setattr(
        application.QMessageBox,
        "warning",
        lambda parent, title, text: warnings.append(text),
    )
    plain = tmp_path / "notes.txt"
    plain.write_bytes(b"")
    _run_queued(monkeypatch, window, [str(tmp_path / "missing"), str(plain)])
    assert window.calls == []
    assert len(warnings) == 2


def test_startup_targets_skipped_after_window_close(monkeypatch, tmp_path):
    window = StubWindow()
    window._lifecycle_closed = True
    folder = tmp_path / "models"
    folder.mkdir()
    _run_queued(monkeypatch, window, [str(folder)])
    assert window.calls == []


def test_cli_settings_flag_sets_env_before_inspection(monkeypatch, tmp_path, capsys):
    from back.cli import main

    monkeypatch.delenv("SMI_SETTINGS_PATH", raising=False)
    empty = tmp_path / "empty"
    empty.mkdir()
    # Empty folder target: no supported files, no model bytes read.
    assert main(["-s", str(tmp_path / "cli.jsonc"), str(empty)]) == 1
    assert os.environ["SMI_SETTINGS_PATH"] == str(tmp_path / "cli.jsonc")
    assert "No supported model files found" in capsys.readouterr().err
