"""Regression checks for the fixed normal and advanced card field policies."""

import os
import sys
from pathlib import Path
from typing import Any, cast

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QPoint, Qt
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import QApplication, QLabel

from front.model_card import ModelCard
from front.selection_controller import SelectionControllerMixin


_APPLICATION: QApplication | None = None


def _app() -> QApplication:
    global _APPLICATION
    application = QApplication.instance()
    _APPLICATION = application if isinstance(application, QApplication) else QApplication([])
    return _APPLICATION


def _data() -> dict:
    return {
        "filepath": "R:/models/example.safetensors",
        "filename": "example.safetensors",
        "format": "SAFETENSORS",
        "architecture": "ExampleArchitecture",
        "model_type": "LoRA",
        "quantization": "Q6",
        "adapter_type": "LoRA",
        "components": {"unet": True},
        "named_text_encoders": {"Clip-L": 1},
        "total_params_friendly": "1.2B",
        "precision_display": "FP16",
        "file_size_friendly": "2.4 GB",
        "tensor_count": 42,
        "lora_rank": 64,
        "extra": {"base_model": "Example Base", "empty": ""},
        "training_meta": {"epochs": 12, "steps": 500, "unused": None},
    }


def _stat_labels(card: ModelCard) -> list[str]:
    labels = []
    for index in range(card.stats_layout.count()):
        if card.stats_layout.getItemPosition(index)[1] not in (0, 2):
            continue
        item = card.stats_layout.itemAt(index)
        assert item is not None
        widget = item.widget()
        assert isinstance(widget, QLabel)
        labels.append(widget.text())
    return labels


class _CopyTarget(SelectionControllerMixin):
    pass


def test_normal_cards_always_render_only_the_four_core_statistics():
    _app()
    card = ModelCard(_data(), simple_view=True, card_fields={"parameters": False})

    assert _stat_labels(card) == ["Parameters", "Precision", "File Size", "Tensors"]


def test_mixed_precision_is_aggregated_on_normal_cards_and_copies():
    _app()
    data = _data()
    data["precision_display"] = "Mixed FP16/BF16"
    data["component_precisions"] = {"unet": "FP16", "vae": "BF16"}

    normal = ModelCard(data, simple_view=True)
    advanced = ModelCard(data, simple_view=False, vertical_stats=True)
    copied = _CopyTarget()._build_card_info_text(data, True)

    assert _stat_labels(normal) == ["Parameters", "Precision", "File Size", "Tensors"]
    assert "Precision: Mixed FP16/BF16" in copied
    assert "UNet Precision" not in copied and "VAE Precision" not in copied
    assert "UNet Precision" in _stat_labels(advanced)
    assert "VAE Precision" in _stat_labels(advanced)


def test_advanced_cards_render_all_available_statistics_despite_legacy_masks():
    _app()
    card = ModelCard(
        _data(),
        simple_view=False,
        card_fields={"parameters": False, "precision": False, "lora_rank": False},
        vertical_stats=True,
    )

    assert _stat_labels(card) == [
        "Parameters", "Precision", "File Size", "Tensors", "LoRA Rank",
        "Base Model", "Epochs", "Steps",
    ]


def test_card_headers_actions_and_copy_info_keep_the_fixed_policy():
    app = _app()
    data = _data()
    card = ModelCard(data, simple_view=True, card_fields={"parameters": False})
    opened: list[str] = []
    selected: list[tuple[str, bool]] = []
    card.advanced_requested.connect(opened.append)
    card.checkbox_toggled.connect(lambda path, checked: selected.append((path, checked)))
    card.show()
    app.processEvents()

    assert {"example.safetensors", "SAFETENSORS", "ExampleArchitecture", "LoRA", "Q6", "UNet", "Clip-L"} <= {
        label.text() for label in card.findChildren(QLabel)
    }
    card.select_cb.click()
    cast(Any, QTest).mouseClick(
        card,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
        QPoint(card.width() - 2, card.height() - 2),
    )
    assert selected == [(data["filepath"], True)]
    assert opened == [data["filepath"]]

    class CopyTarget(SelectionControllerMixin):
        _simple_card_field_visibility = {"parameters": False}
        _card_field_visibility = {"parameters": False}

    target = CopyTarget()
    normal = target._build_card_info_text(data, simple_view=True)
    advanced = target._build_card_info_text(data, simple_view=False)
    assert "LoRA Rank" not in normal and "Base Model" not in normal
    assert "LoRA Rank: 64" in advanced and "Base Model: Example Base" in advanced
    card.close()
