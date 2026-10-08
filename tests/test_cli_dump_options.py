"""CLI ``--dump-keys`` option forwarding and failure-status coverage."""

from __future__ import annotations

from back import cli


def _configure_cli(monkeypatch, paths: list[str]) -> None:
    monkeypatch.setattr(cli, "_configure_stdio_encoding", lambda: None)
    monkeypatch.setattr(cli, "settings_path", lambda: "settings.jsonc")
    monkeypatch.setattr(cli, "legacy_settings_path", lambda: "settings.ini")
    monkeypatch.setattr(cli, "open_settings", lambda *_args, **_kwargs: object())
    monkeypatch.setattr(cli, "apply_cache_location", lambda *_args: None)
    monkeypatch.setattr(cli, "_iter_model_paths", lambda *_args: paths)
    monkeypatch.setattr(cli, "iter_checkpoint_paths", lambda *_args: [])


def test_dump_keys_forwards_cli_options_to_ordinary_and_checkpoint_routes(monkeypatch) -> None:
    ordinary = "ordinary.safetensors"
    checkpoint = "checkpoint.pt"
    _configure_cli(monkeypatch, [ordinary, checkpoint])
    expected = {
        "allow_filename_alias_detection": True,
        "checkpoint_safety": "metadata",
        "cache_full_data": True,
    }
    ordinary_options = []
    checkpoint_options = []

    def generate_dump(filepath, options=None):
        assert filepath == ordinary
        ordinary_options.append(options)
        return "ordinary dump"

    def inspect_checkpoint(filepath, options=None):
        assert filepath == checkpoint
        checkpoint_options.append(options)
        return {"filepath": filepath}

    def read_checkpoint_header(filepath, options=None):
        assert filepath == checkpoint
        checkpoint_options.append(options)
        return {}, {}, 0

    monkeypatch.setattr(cli, "generate_modelinfo_dump", generate_dump)
    monkeypatch.setattr(cli, "inspect_file", inspect_checkpoint)
    monkeypatch.setattr(cli, "read_model_header", read_checkpoint_header)
    monkeypatch.setattr(cli, "print_report", lambda *_args, **_kwargs: None)

    assert cli.main([
        "--dump-keys",
        "--checkpoint-safety",
        "metadata",
        "--allow-filename-alias-detection",
        "target",
    ]) == 0
    assert ordinary_options == [expected]
    assert checkpoint_options == [expected, expected]


def test_dump_keys_returns_nonzero_when_any_file_fails(monkeypatch, capsys) -> None:
    _configure_cli(monkeypatch, ["good.safetensors", "bad.safetensors"])

    def generate_dump(filepath, options=None):
        if filepath == "bad.safetensors":
            raise OSError("unreadable")
        return "dump"

    monkeypatch.setattr(cli, "generate_modelinfo_dump", generate_dump)

    assert cli.main(["--dump-keys", "target"]) == 1
    assert "[ERROR] bad.safetensors: unreadable" in capsys.readouterr().err

    monkeypatch.setattr(cli, "generate_modelinfo_dump", lambda *_args, **_kwargs: "dump")
    assert cli.main(["--dump-keys", "target"]) == 0
