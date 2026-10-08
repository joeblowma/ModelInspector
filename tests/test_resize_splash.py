"""ResizeSplash image processing and process exit-status coverage."""

from __future__ import annotations

import importlib.util
from pathlib import Path
import subprocess
import sys

from PIL import Image


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "assets" / "ResizeSplash.py"


def _resize_splash_module():
    spec = importlib.util.spec_from_file_location("resize_splash", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_alter_image_resizes_and_reports_success(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    Image.new("RGB", (20, 10)).save(source)

    assert _resize_splash_module().alter_image(str(source), str(output), 10, 10) is True
    with Image.open(output) as resized:
        assert resized.size == (10, 5)


def test_resize_splash_subprocess_exit_statuses(tmp_path: Path) -> None:
    source = tmp_path / "source.png"
    output = tmp_path / "output.png"
    Image.new("RGB", (20, 10)).save(source)

    missing = subprocess.run(
        [sys.executable, str(SCRIPT), str(tmp_path / "missing.png"), str(output)],
    )
    invalid_dimensions = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), str(output), "wide", "10"],
    )
    success = subprocess.run(
        [sys.executable, str(SCRIPT), str(source), str(output), "10", "10"],
    )

    assert missing.returncode == 1
    assert invalid_dimensions.returncode == 1
    assert success.returncode == 0
