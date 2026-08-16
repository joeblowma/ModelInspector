"""Model card widget used by the Model Inspector cards view."""

from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QContextMenuEvent, QMouseEvent
from PyQt6.QtWidgets import (
    QApplication,
    QCheckBox,
    QFrame,
    QGridLayout,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
)

__all__ = ["ModelCard"]


class ModelCard(QFrame):
    selection_requested = pyqtSignal(str, object)
    checkbox_toggled = pyqtSignal(str, bool)
    drag_over_requested = pyqtSignal(str)
    context_requested = pyqtSignal(str, bool, object)

    def __init__(self, data: dict, simple_view=False, card_fields=None):
        super().__init__()
        self.data = data
        self.filepath = data.get("filepath", "")
        self._selected = False
        self._filter_visible = True
        self._simple_view = bool(simple_view)
        self._card_fields = card_fields or {}
        precision_text = (
            data.get("precision_display")
            or data.get("component_precision_summary")
            or data.get("precision_summary", "-")
        )
        component_precisions = data.get("component_precisions") or {}
        component_precision_labels = [
            ("unet", "UNet Precision"),
            ("transformer", "Transformer Precision"),
            ("vae", "VAE Precision"),
            ("text_encoder", "Text Encoder Precision"),
            ("text_encoder_2", "Text Encoder 2 Precision"),
        ]
        self.setStyleSheet("""
            ModelCard {
                background-color: #181825;
                border: 1px solid #313244;
                border-radius: 10px;
            }
            ModelCard:hover {
                border-color: #74c7ec;
            }
        """)
        self.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(8)

        # Filename header
        header_row = QHBoxLayout()
        header_row.setSpacing(8)
        self.select_cb = QCheckBox()
        self.select_cb.setToolTip("Select model")
        self.select_cb.clicked.connect(self._on_checkbox_clicked)
        header_row.addWidget(self.select_cb)

        name_label = QLabel(data["filename"])
        name_label.setWordWrap(True)
        name_label.setStyleSheet(
            "font-size: 14px; font-weight: bold; color: #f5c2e7; background: transparent; border: none;"
        )
        header_row.addWidget(name_label, stretch=1)
        layout.addLayout(header_row)

        # Architecture + model type row
        arch_row = QHBoxLayout()
        file_format = data.get("format")
        if file_format:
            arch_row.addWidget(
                self._make_tag(str(file_format).upper(), "#f38ba8", "#1e1e2e")
            )
        arch_tag = self._make_tag(data["architecture"], "#74c7ec", "#1e1e2e")
        type_tag = self._make_tag(data["model_type"], "#a6e3a1", "#1e1e2e")
        arch_row.addWidget(arch_tag)
        arch_row.addWidget(type_tag)
        quantization = data.get("quantization")
        if quantization:
            arch_row.addWidget(self._make_tag(str(quantization), "#cba6f7", "#1e1e2e"))
        adapter_type = data.get("adapter_type")
        if adapter_type:
            arch_row.addWidget(self._make_tag(adapter_type, "#f9e2af", "#1e1e2e"))
        if data.get("is_moe"):
            expert_count = data.get("expert_count")
            expert_used_count = data.get("expert_used_count")
            moe_label = "MoE"
            if expert_count:
                moe_label += f" {expert_count}"
                if expert_used_count:
                    moe_label += f"/{expert_used_count}"
            arch_row.addWidget(self._make_tag(moe_label, "#fab387", "#1e1e2e"))

        # Component tags at top
        comp_colors = {
            "unet": ("#fab387", "#1e1e2e"),
            "transformer": ("#fab387", "#1e1e2e"),
            "vae": ("#cba6f7", "#1e1e2e"),
            "text_encoder": ("#94e2d5", "#1e1e2e"),
            "text_encoder_2": ("#89dceb", "#1e1e2e"),
        }
        comp_labels = {
            "unet": "UNet",
            "transformer": "Transformer",
            "vae": "VAE",
            "text_encoder": "Text Enc",
            "text_encoder_2": "Text Enc 2",
        }
        for key, label in comp_labels.items():
            if data["components"].get(key):
                fg, bg = comp_colors.get(key, ("#cdd6f4", "#1e1e2e"))
                arch_row.addWidget(self._make_tag(label, fg, bg))

        for enc_name in data.get("named_text_encoders", {}):
            arch_row.addWidget(self._make_tag(enc_name, "#94e2d5", "#1e1e2e"))
        arch_row.addStretch()
        layout.addLayout(arch_row)

        if self._simple_view:
            simple_stats = []
            if self._card_fields.get("parameters", True):
                simple_stats.append(("Parameters", data["total_params_friendly"]))
            if self._card_fields.get("precision", True):
                added_component_precision = False
                for comp_key, comp_label in component_precision_labels:
                    comp_precision = component_precisions.get(comp_key)
                    if not comp_precision:
                        continue
                    simple_stats.append((comp_label, comp_precision))
                    added_component_precision = True
                if not added_component_precision:
                    simple_stats.append(("Precision", precision_text))
            if self._card_fields.get("file_size", False):
                simple_stats.append(("File Size", data["file_size_friendly"]))
            if self._card_fields.get("tensors", False):
                simple_stats.append(("Tensors", str(data["tensor_count"])))
            lora_rank = data.get("lora_rank")
            if lora_rank and self._card_fields.get("lora_rank", False):
                simple_stats.append(("LoRA Rank", str(lora_rank)))
            if self._card_fields.get("extra_meta", False):
                for key, val in data.get("extra", {}).items():
                    simple_stats.append((key.replace("_", " ").title(), str(val)))
            if self._card_fields.get("training_meta", False):
                for key, val in data.get("training_meta", {}).items():
                    simple_stats.append((key.replace("_", " ").title(), str(val)))

            if simple_stats:
                mini_grid = QGridLayout()
                mini_grid.setSpacing(6)
                for i, (label, value) in enumerate(simple_stats):
                    lbl = QLabel(label)
                    lbl.setStyleSheet(
                        "color: #6c7086; font-size: 11px; background: transparent; border: none;"
                    )
                    val = QLabel(value)
                    if "Precision" in label:
                        val.setWordWrap(True)
                    val.setStyleSheet(
                        "color: #cdd6f4; font-size: 13px; font-weight: bold; background: transparent; border: none;"
                    )
                    mini_grid.addWidget(lbl, i // 2, (i % 2) * 2)
                    mini_grid.addWidget(val, i // 2, (i % 2) * 2 + 1)
                layout.addLayout(mini_grid)
            return

        # Stats grid
        grid = QGridLayout()
        grid.setSpacing(6)

        stats = []
        if self._card_fields.get("parameters", True):
            stats.append(("Parameters", data["total_params_friendly"]))
        if self._card_fields.get("file_size", True):
            stats.append(("File Size", data["file_size_friendly"]))
        if self._card_fields.get("precision", True):
            added_component_precision = False
            for comp_key, comp_label in component_precision_labels:
                comp_precision = component_precisions.get(comp_key)
                if not comp_precision:
                    continue
                stats.append((comp_label, comp_precision))
                added_component_precision = True
            if not added_component_precision:
                stats.append(("Precision", precision_text))
        if self._card_fields.get("tensors", True):
            stats.append(("Tensors", str(data["tensor_count"])))
        # Add LoRA rank if present
        lora_rank = data.get("lora_rank")
        if lora_rank and self._card_fields.get("lora_rank", True):
            stats.append(("LoRA Rank", str(lora_rank)))
        # Add extra metadata
        if self._card_fields.get("extra_meta", True):
            for key, val in data.get("extra", {}).items():
                label = key.replace("_", " ").title()
                stats.append((label, str(val)))
        # Training metadata
        if self._card_fields.get("training_meta", True):
            for key, val in data.get("training_meta", {}).items():
                label = key.replace("_", " ").title()
                stats.append((label, str(val)))

        for i, (label, value) in enumerate(stats):
            lbl = QLabel(label)
            lbl.setStyleSheet(
                "color: #6c7086; font-size: 11px; background: transparent; border: none;"
            )
            val = QLabel(value)
            if "Precision" in label:
                val.setWordWrap(True)
            val.setStyleSheet(
                "color: #cdd6f4; font-size: 13px; font-weight: bold; background: transparent; border: none;"
            )
            grid.addWidget(lbl, i // 2, (i % 2) * 2)
            grid.addWidget(val, i // 2, (i % 2) * 2 + 1)

        layout.addLayout(grid)

        # no bottom tags; tags are intentionally kept at top

    def mousePressEvent(self, a0: QMouseEvent | None):
        if a0 is None:
            return
        event = a0
        if event.button() == Qt.MouseButton.LeftButton and self.filepath:
            self.selection_requested.emit(self.filepath, event.modifiers())
            event.accept()
            return
        super().mousePressEvent(event)

    def enterEvent(self, event):
        if self.filepath and (QApplication.mouseButtons() & Qt.MouseButton.LeftButton):
            self.drag_over_requested.emit(self.filepath)
        super().enterEvent(event)

    def contextMenuEvent(self, a0: QContextMenuEvent | None):
        if a0 is None:
            return
        event = a0
        if self.filepath:
            self.context_requested.emit(
                self.filepath, self._simple_view, event.globalPos()
            )
            event.accept()
            return
        super().contextMenuEvent(event)

    def set_selected(self, selected: bool):
        if self._selected == selected:
            return
        self._selected = selected
        self.select_cb.blockSignals(True)
        self.select_cb.setChecked(selected)
        self.select_cb.blockSignals(False)
        self._refresh_style()

    def _refresh_style(self):
        if self._selected:
            self.setStyleSheet("""
                ModelCard {
                    background-color: #181825;
                    border: 2px solid #a6e3a1;
                    border-radius: 10px;
                }
                ModelCard:hover {
                    border-color: #89dceb;
                }
            """)
        else:
            self.setStyleSheet("""
                ModelCard {
                    background-color: #181825;
                    border: 1px solid #313244;
                    border-radius: 10px;
                }
                ModelCard:hover {
                    border-color: #74c7ec;
                }
            """)

    def set_filter_visible(self, visible: bool):
        visible = bool(visible)
        if self._filter_visible == visible:
            return
        self._filter_visible = visible
        self.setVisible(visible)
        self.setMaximumHeight(16777215 if visible else 0)
        self.updateGeometry()

    def _on_checkbox_clicked(self, checked):
        if self.filepath:
            self.checkbox_toggled.emit(self.filepath, bool(checked))

    @staticmethod
    def _make_tag(text: str, fg: str, bg: str) -> QLabel:
        tag = QLabel(text)
        tag.setStyleSheet(
            f"background-color: {fg}; color: {bg}; padding: 3px 10px; "
            f"border-radius: 4px; font-size: 11px; font-weight: bold; border: none;"
        )
        tag.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        return tag
