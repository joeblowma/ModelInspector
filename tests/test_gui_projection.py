from __future__ import annotations

import json
import os
import sys
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QApplication, QLabel, QCheckBox, QStyle, QStyleOptionButton

from front.scan_projection import ProjectionEvent, ScanProjectionBuffer
from front.window_layout import SMART_COLUMN_GROUPS


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


_APP: QApplication | None = None


def _window(monkeypatch, tmp_path: Path):
    global _APP
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    import gui

    _APP = _app()  # hold a module-level reference: GC would destroy all widgets
    window = gui.MainWindow()
    _APP.processEvents()
    return window


def _row_data(filepath: str, **overrides) -> dict:
    data = {
        "filepath": filepath,
        "filename": Path(filepath).name,
        "format": "SAFETENSORS",
        "file_size_friendly": "1 KB",
        "architecture": "Arch",
        "model_type": "Checkpoint",
        "adapter_type": None,
        "quantization": None,
        "precision_summary": "FP16",
        "components": {},
        "component_precisions": {},
        "named_text_encoders": {},
        "total_params_friendly": "1",
        "tensor_count": 1,
        "training_meta": {},
        "is_moe": False,
        "expert_count": None,
        "expert_used_count": None,
        "lora_rank": None,
    }
    data.update(overrides)
    return data


_GROUPED_COLUMNS = {
    name
    for spec in SMART_COLUMN_GROUPS.values()
    for name in spec["columns"]
}
_COMMON_COLUMNS = (
    "File", "Format", "File Size", "Architecture", "Model Type",
    "Quantization", "Precision", "Parameters", "Tensors",
    "Software", "Images", "Resolution", "Epochs", "Steps",
)


def test_projection_buffer_enforces_item_budget_and_final_flush():
    _app()
    projected = []
    reconciled = []
    completed = []
    acknowledgements = []
    buffer = ScanProjectionBuffer(
        lambda kind, payload: projected.append((kind, payload)),
        reconciled.append,
        completed.append,
        max_items=8,
        max_milliseconds=1000,
    )
    generation = buffer.begin()
    for value in range(17):
        buffer.enqueue(
            ProjectionEvent(
                generation,
                "result",
                value,
                lambda value=value: acknowledgements.append(value),
            )
        )
    buffer.mark_terminal(generation, "done")

    buffer.drain_now()
    assert len(projected) == 8
    assert buffer.pending_count == 9
    assert completed == []
    buffer.drain_now()
    assert len(projected) == 16
    buffer.drain_now()

    assert len(projected) == 17
    assert sorted(acknowledgements) == list(range(17))
    assert reconciled[-1] is True
    assert completed == ["done"]


def test_projection_buffer_discards_and_acknowledges_stale_events():
    _app()
    projected = []
    acknowledged = []
    buffer = ScanProjectionBuffer(
        lambda kind, payload: projected.append(payload),
        lambda final: None,
        lambda terminal: None,
    )
    stale_generation = buffer.begin()
    buffer.begin()
    buffer.enqueue(
        ProjectionEvent(
            stale_generation,
            "result",
            "stale",
            lambda: acknowledged.append(True),
        )
    )
    assert projected == []
    assert acknowledged == [True]
    assert buffer.pending_count == 0



def test_vlm_model_type_projects_to_card_and_table():
    import gui

    app = QApplication.instance() or QApplication([])
    window = gui.MainWindow()
    data = {
        "filepath": "mllm.safetensors",
        "filename": "mllm.safetensors",
        "format": "SAFETENSORS",
        "file_size_friendly": "1.0 KB",
        "architecture": "Qwen2VLForConditionalGeneration",
        "model_type": "VLM",
        "adapter_type": None,
        "quantization": None,
        "precision_summary": "FP16",
        "components": {"transformer": True, "vision": True},
        "named_text_encoders": {},
        "total_params_friendly": "7B",
        "tensor_count": 1,
        "training_meta": {},
    }
    try:
        window._add_card(data)
        window._add_table_row(data)

        card = window._path_to_card[data["filepath"]]
        assert any("VLM" in label.text() for label in card.findChildren(QLabel))
        assert window.table.item(0, 5).text() == "VLM"
    finally:
        window.close()
        app.processEvents()


def test_vlm_result_auto_enables_diffusion_group_only(monkeypatch, tmp_path: Path) -> None:
    import gui

    window = _window(monkeypatch, tmp_path)
    try:
        window._add_table_row(_row_data(
            "mllm.safetensors",
            architecture="Qwen2VLForConditionalGeneration",
            model_type="VLM",
            components={"transformer": True, "vision": True},
        ))
        assert window._smart_group_state["diffusion"] is True
        assert window._smart_group_checkboxes["diffusion"].isChecked()
        assert window._smart_group_state["llm"] is False
        assert window._smart_group_state["adapter"] is False
        assert not window.table.isColumnHidden(window._table_columns.index("Transformer Precision"))
    finally:
        window.close()
        _app().processEvents()


# ---------------------------------------------------------------------------
# Smart Data-column groups
# ---------------------------------------------------------------------------


def test_selection_column_checkbox_is_centered_and_data_cells_are_not(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        window._add_table_row(_row_data("R:/a.safetensors"))
        cb = window.table.cellWidget(0, 0)
        assert isinstance(cb, QCheckBox), "selection cell must stay a native QCheckBox"
        assert "subcontrol-position: center" in cb.styleSheet()
        # The indicator must actually paint centered in the cell.
        option = QStyleOptionButton()
        cb.initStyleOption(option)
        rect = cb.style().subElementRect(QStyle.SubElement.SE_CheckBoxIndicator, option, cb)
        assert rect.width() > 0
        assert abs((rect.x() + rect.width() / 2) - cb.width() / 2) <= 1
        # Only the selection column is centered; data cells keep native alignment.
        for col in range(1, window.table.columnCount()):
            item = window.table.item(0, col)
            if item is not None:
                assert not (item.textAlignment() & Qt.AlignmentFlag.AlignHCenter), col
    finally:
        window.close()
        _app().processEvents()


def test_smart_group_membership_is_exact() -> None:
    assert set(SMART_COLUMN_GROUPS) == {"llm", "diffusion", "adapter"}
    assert set(SMART_COLUMN_GROUPS["llm"]["columns"]) == {"MoE", "Experts", "Exp Act"}
    assert set(SMART_COLUMN_GROUPS["diffusion"]["columns"]) == {
        "UNet Precision", "VAE Precision", "Text Encoder Precision", "Transformer Precision",
    }
    assert set(SMART_COLUMN_GROUPS["adapter"]["columns"]) == {"Adapter", "LoRA Rank"}


def test_smart_group_checkboxes_pinned_right_of_data_toolbar(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        labels = [window._smart_group_checkboxes[key].text() for key in ("llm", "diffusion", "adapter")]
        assert labels == ["LLM", "Diffusion", "Adapter"]
        window.show()
        _app().processEvents()
        row_widgets = (
            window.table_select_all_cb,
            window.show_full_path_cb,
            window._smart_group_checkboxes["llm"],
            window._smart_group_checkboxes["diffusion"],
            window._smart_group_checkboxes["adapter"],
        )
        parents = {widget.parentWidget() for widget in row_widgets}
        assert len(parents) == 1, "group toggles must share the Data toolbar row"
        ys = {widget.y() for widget in row_widgets}
        assert len(ys) == 1, "group toggles must sit in the same toolbar row"
        xs = [widget.x() for widget in row_widgets]
        assert xs == sorted(xs), "group toggles must be pinned right of Select All / Show Full Path"
    finally:
        window.close()
        _app().processEvents()


def test_smart_groups_default_unchecked_and_masked(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        for key in SMART_COLUMN_GROUPS:
            assert not window._smart_group_checkboxes[key].isChecked()
            assert window._smart_group_state[key] is False
            assert key not in window._smart_group_manual
        for name in _GROUPED_COLUMNS:
            assert window.table.isColumnHidden(window._table_columns.index(name)), name
        for name in _COMMON_COLUMNS:
            assert not window.table.isColumnHidden(window._table_columns.index(name)), name
    finally:
        window.close()
        _app().processEvents()


def test_smart_group_tooltips_document_columns_and_precedence(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        for key, spec in SMART_COLUMN_GROUPS.items():
            tooltip = window._smart_group_checkboxes[key].toolTip()
            assert spec["label"] in tooltip
            for name in spec["columns"]:
                assert name in tooltip
            assert "Settings > Data" in tooltip
            assert "automatically" in tooltip.lower()
        for widget in (
            window.cards_select_all_cb,
            window.table_select_all_cb,
            window.show_full_path_cb,
            window.analyze_btn,
            window.cancel_btn,
            window.clear_results_btn,
            window.raw_load_btn,
            window.open_btn,
            window.selected_action_menu_btn,
        ):
            assert widget.toolTip().strip(), type(widget).__name__
    finally:
        window.close()
        _app().processEvents()


def test_each_family_auto_enables_from_loaded_results(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        cases = {
            "llm": _row_data("R:/moe.safetensors", is_moe=True, expert_count=8, expert_used_count=2),
            "diffusion": _row_data("R:/diffusion.safetensors", component_precisions={"vae": "FP16"}),
            "adapter": _row_data("R:/lora.safetensors", adapter_type="LoRA", lora_rank=32),
        }
        for key, data in cases.items():
            window._note_result_for_smart_groups(data)
            assert window._smart_group_state[key] is True, key
            assert window._smart_group_checkboxes[key].isChecked(), key
            for name in SMART_COLUMN_GROUPS[key]["columns"]:
                assert not window.table.isColumnHidden(window._table_columns.index(name)), name
        # Plain checkpoint data triggers no family and changes no group state.
        before = dict(window._smart_group_state)
        window._note_result_for_smart_groups(_row_data("R:/plain.safetensors"))
        assert window._smart_group_state == before
    finally:
        window.close()
        _app().processEvents()


def test_user_off_toggle_overrides_auto_enable_for_the_session(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        window._note_result_for_smart_groups(_row_data("R:/a.safetensors", is_moe=True))
        assert window._smart_group_state["llm"] is True
        # The user explicitly unchecks the group (manual state wins).
        window._smart_group_checkboxes["llm"].setChecked(False)
        assert window._smart_group_state["llm"] is False
        assert "llm" in window._smart_group_manual
        for name in SMART_COLUMN_GROUPS["llm"]["columns"]:
            assert window.table.isColumnHidden(window._table_columns.index(name)), name
        # Later loads must not re-enable it.
        window._note_result_for_smart_groups(_row_data("R:/b.safetensors", is_moe=True))
        assert window._smart_group_state["llm"] is False
        assert not window._smart_group_checkboxes["llm"].isChecked()
    finally:
        window.close()
        _app().processEvents()


def test_baseline_hidden_column_stays_hidden_even_when_group_on(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        moe_index = window._table_columns.index("MoE")
        window._apply_data_layout({
            "columns": [{"key": "column_16", "visible": False, "width": 60}],
            "theme": "default",
        })
        assert window.table.isColumnHidden(moe_index)
        # Group on reveals only baseline-visible columns.
        window._on_smart_group_toggled("llm", True)
        assert window.table.isColumnHidden(moe_index), "persisted hidden must win"
        assert not window.table.isColumnHidden(window._table_columns.index("Experts"))
        assert not window.table.isColumnHidden(window._table_columns.index("Exp Act"))
        # Auto-enable in a fresh session honours the same precedence.
        second = _window(monkeypatch, tmp_path)
        try:
            second._apply_data_layout({
                "columns": [{"key": "column_16", "visible": False, "width": 60}],
                "theme": "default",
            })
            second._note_result_for_smart_groups(_row_data("R:/moe.safetensors", is_moe=True))
            assert second._smart_group_state["llm"] is True
            assert second.table.isColumnHidden(moe_index)
            assert not second.table.isColumnHidden(second._table_columns.index("Experts"))
        finally:
            second.close()
            _app().processEvents()
    finally:
        window.close()
        _app().processEvents()


def test_common_columns_are_unaffected_by_group_toggles(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        common_state = {
            name: window.table.isColumnHidden(window._table_columns.index(name))
            for name in _COMMON_COLUMNS
        }
        window._note_result_for_smart_groups(_row_data("R:/moe.safetensors", is_moe=True))
        window._on_smart_group_toggled("diffusion", True)
        window._on_smart_group_toggled("adapter", True)
        window._on_smart_group_toggled("diffusion", False)
        window._on_smart_group_toggled("adapter", False)
        for name, hidden in common_state.items():
            assert window.table.isColumnHidden(window._table_columns.index(name)) == hidden, name
    finally:
        window.close()
        _app().processEvents()


def test_clear_all_resets_auto_groups_but_keeps_manual(monkeypatch, tmp_path: Path) -> None:
    import gui

    window = _window(monkeypatch, tmp_path)
    try:
        window._results.append(_row_data("R:/moe.safetensors", is_moe=True))
        window._add_table_row(window._results[0])
        assert window._smart_group_state["llm"] is True
        # A manual toggle survives clear.
        window._on_smart_group_toggled("diffusion", True)
        window._clear_all()
        _app().processEvents()
        assert window._smart_group_state["llm"] is False
        assert not window._smart_group_checkboxes["llm"].isChecked()
        assert window._smart_group_state["diffusion"] is True
        assert window._smart_group_checkboxes["diffusion"].isChecked()
        assert not window.table.isColumnHidden(window._table_columns.index("UNet Precision"))
        assert window.table.isColumnHidden(window._table_columns.index("MoE"))
    finally:
        window.close()
        _app().processEvents()


def test_load_transition_reapplies_masks_and_auto_enables(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        # Start from a cleared session with a manual LLM off override.
        window._on_smart_group_toggled("llm", False)
        window._note_result_for_smart_groups(_row_data("R:/unet.safetensors", components={"unet": True}))
        assert window._smart_group_state["diffusion"] is True
        assert window._smart_group_state["llm"] is False
        for name in SMART_COLUMN_GROUPS["llm"]["columns"]:
            assert window.table.isColumnHidden(window._table_columns.index(name)), name
        for name in SMART_COLUMN_GROUPS["diffusion"]["columns"]:
            assert not window.table.isColumnHidden(window._table_columns.index(name)), name
    finally:
        window.close()
        _app().processEvents()


def test_persistence_excludes_smart_group_masks(monkeypatch, tmp_path: Path) -> None:
    window = _window(monkeypatch, tmp_path)
    try:
        window._note_result_for_smart_groups(_row_data("R:/moe.safetensors", is_moe=True))
        layout = window._capture_data_layout()
        by_key = {entry["key"]: entry for entry in layout["columns"]}
        assert by_key["column_16"]["visible"] is True, "masked MoE must persist as baseline-visible"
        assert window._persisted_column_visible(window._table_columns.index("MoE")) is True
        # table_columns preference JSON keeps the baseline too.
        window._save_ui_settings()
        from front.window_core import _settings
        stored = json.loads(_settings().value("table_columns", "{}"))
        assert stored.get("MoE") is True
        assert stored.get("Experts") is True
    finally:
        window.close()
        _app().processEvents()
