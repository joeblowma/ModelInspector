"""Shared test helpers for model-inspector integration tests."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

# Held for the whole session: PyQt6 crashes (0xC0000409) if the QApplication is
# garbage-collected. Tests still obtain the same instance via
# ``QApplication.instance()``.
_QAPP = None


@pytest.fixture(scope="session", autouse=True)
def _qapp_holder():
    global _QAPP
    from PyQt6.QtWidgets import QApplication

    _QAPP = QApplication.instance() or QApplication([])
    return _QAPP


def _summary(path: str, architecture: str, model_type: str) -> dict:
    return {
        "filepath": path,
        "filename": Path(path).name,
        "format": Path(path).suffix.lstrip(".").upper(),
        "file_size": 1,
        "file_size_friendly": "1 B",
        "tensor_count": 1,
        "total_params": 1,
        "total_params_friendly": "1",
        "architecture": architecture,
        "model_type": model_type,
        "components": {},
        "named_text_encoders": {},
        "precision_summary": "FP16",
        "component_precision_summary": "FP16",
        "component_precisions": {},
        "precision_display": "FP16",
        "training_meta": {},
        "extra": {},
    }