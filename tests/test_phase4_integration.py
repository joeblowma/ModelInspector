# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Integration contracts for JSONC settings, live theme, and MainWindow wiring."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtCore import QSettings, Qt
from PyQt6.QtWidgets import QApplication

from back.settings_store import open_settings
from front.application import apply_theme
from conftest import _summary


def test_jsonc_store_migrates_ini_and_recovers_malformed_content(tmp_path: Path) -> None:
    legacy = tmp_path / "settings.ini"
    ini = QSettings(str(legacy), QSettings.Format.IniFormat)
    ini.setValue("analysis_threads", "4")
    ini.setValue("default_tab", "data")
    ini.sync()
    destination = tmp_path / "settings.jsonc"
    migrated = open_settings(destination, legacy)
    assert migrated.value("analysis_threads") == "4"
    assert migrated.value("default_tab") == "data"
    assert "Migrated" in migrated.diagnostic
    destination.write_text("{ invalid", encoding="utf-8")
    recovered = open_settings(destination, legacy)
    assert recovered.value("analysis_threads") == 2
    assert destination.with_suffix(".jsonc.invalid").exists()
    assert "Malformed" in recovered.diagnostic


def test_settings_cache_load_replaces_prior_results_with_cached_summaries(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    from gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    existing_a = "R:/existing/a.safetensors"
    existing_b = "R:/existing/b.gguf"
    cached = "R:/cached/c.ckpt"
    existing_results = [
        _summary(existing_a, "Architecture A", "Checkpoint"),
        _summary(existing_b, "Architecture B", "LoRA"),
    ]
    snapshots = {
        existing_a: _summary(existing_a, "Architecture A", "Checkpoint"),
        cached: _summary(cached, "Architecture C", "Text Encoder"),
    }
    try:
        for data in existing_results:
            window._normalize_result_data(data)
            window._results.append(data)
            window._add_card(data)
            window._add_table_row(data)
        window.arch_filter_btn.replace_items(
            data["architecture"] for data in window._results
        )
        window.tag_filter_btn.replace_items(
            tag for data in window._results for tag in window._filter_tags_for_data(data)
        )
        window.format_filter_btn.replace_items(
            window._format_filter_for_data(data) for data in window._results
        )
        window.arch_filter_btn._arch_checks["Architecture B"].setChecked(False)
        window.tag_filter_btn._arch_checks["LoRA"].setChecked(False)
        window.format_filter_btn._arch_checks[".gguf"].setChecked(False)
        window._selected_paths.add(existing_a)
        monkeypatch.setattr(
            window,
            "_cache_report",
            lambda: SimpleNamespace(
                entries=[
                    SimpleNamespace(path=existing_a, classification="active"),
                    SimpleNamespace(path=cached, classification="active"),
                ]
            ),
        )
        monkeypatch.setattr(
            window,
            "_get_cached_inspection_summary_snapshots",
            lambda _paths: snapshots,
        )

        window._load_cache_all()

        assert set(window.arch_filter_btn._arch_checks) == {
            "Architecture A", "Architecture C"
        }
        assert set(window.tag_filter_btn._arch_checks) == {
            "Checkpoint", "Text Encoder"
        }
        assert set(window.format_filter_btn._arch_checks) == {".safetensors", ".ckpt"}
        assert window.arch_filter_btn._arch_checks["Architecture A"].isChecked()
        assert window.arch_filter_btn._arch_checks["Architecture C"].isChecked()
        assert window.tag_filter_btn._arch_checks["Checkpoint"].isChecked()
        assert window.tag_filter_btn._arch_checks["Text Encoder"].isChecked()
        assert window.format_filter_btn._arch_checks[".safetensors"].isChecked()
        assert window.format_filter_btn._arch_checks[".ckpt"].isChecked()
        assert not window.table.isRowHidden(window._row_for_filepath(cached))
        assert window.raw_combo.findData(existing_a) >= 0
        assert window.raw_combo.findData(cached) >= 0
        assert window.selected_count_label.text() == window.table_selected_count_label.text() == "0 selected"
        assert window.progress_label.text() == "Loaded 2 cached summaries"
    finally:
        window.close()


def test_table_sorting_is_atomic_for_rows_and_full_path_toggles(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    from gui import MainWindow

    app = QApplication.instance() or QApplication([])
    window = MainWindow()
    first = _summary("Z:/models/a.safetensors", "First", "First Type")
    second = _summary("A:/models/z.safetensors", "Second", "Second Type")
    try:
        window.table.setSortingEnabled(True)
        window.table.sortItems(1)
        for data in (first, second):
            window._results.append(data)
            window._add_table_row(data)

        def paths() -> list[str]:
            return [
                window.table.item(row, 1).data(Qt.ItemDataRole.UserRole)
                for row in range(window.table.rowCount())
            ]

        assert paths() == [first["filepath"], second["filepath"]]
        assert [window.table.item(row, 5).text() for row in range(2)] == ["First Type", "Second Type"]
        window._on_show_full_path_changed(Qt.CheckState.Checked.value)
        assert paths() == [second["filepath"], first["filepath"]]
        window._on_show_full_path_changed(Qt.CheckState.Unchecked.value)
        assert paths() == [first["filepath"], second["filepath"]]
        window._on_show_full_path_changed(Qt.CheckState.Checked.value)
        window._rebuild_views_from_results()
        assert paths() == [second["filepath"], first["filepath"]]
        assert all(window._row_for_filepath(path) is not None for path in paths())
    finally:
        window.close()
        app.processEvents()


def test_capability_filter_tags_require_strong_evidence(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    from gui import MainWindow

    window = MainWindow()
    strong = _summary("R:/strong.safetensors", "Strong", "LLM")
    strong["capability_facts"] = {
        "capabilities": ["tools"],
        "evidence": {"tools": ["config.json:supports_tools"]},
        "evidence_strength": {"tools": "strong"},
    }
    weak = _summary("R:/weak.safetensors", "Weak", "LLM")
    weak["capability_facts"] = {
        "capabilities": ["thinking"],
        "evidence": {"thinking": ["template:thinking marker (weak)"]},
        "evidence_strength": {"thinking": "weak"},
    }
    try:
        assert window._filter_tags_for_data(strong)[-1] == "Tool Use"
        assert "Thinking" not in window._filter_tags_for_data(weak)
        window._active_tag_filter = {"Tool Use"}
        assert window._is_data_visible(strong)
        assert not window._is_data_visible(weak)
    finally:
        window.close()


def test_theme_application_and_mainwindow_explorer_wiring(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    app = QApplication.instance() or QApplication([])
    theme_id, diagnostics = apply_theme(app, "github")
    assert theme_id == "github"
    assert diagnostics == ()
    from gui import MainWindow

    window = MainWindow()
    try:
        assert not hasattr(window, "raw_sections")
        assert not hasattr(window, "advanced_viewer_btn")
        assert callable(window._show_advanced_viewer_for_path)
        assert callable(window._open_table_row_in_advanced_viewer)
        assert not hasattr(window, "explorer_tab")
        layout = window._capture_data_layout()
        assert {entry["key"] for entry in layout["columns"]} >= {"selection", "column_1"}
        window._apply_data_layout({
            "columns": [
                {"key": "column_2", "visible": False, "width": 123},
                {"key": "selection", "visible": True, "width": 34},
            ],
            "theme": "github",
        })
        assert window.table.isColumnHidden(2)
        window.table.setColumnHidden(2, False)
        assert window.table.columnWidth(2) == 123
        header = window.table.horizontalHeader()
        # Selection is a locked invariant: always the first, visible column.
        # The requested order is otherwise honored (column_2 moves to index 1).
        assert header.visualIndex(0) == 0
        assert not window.table.isColumnHidden(0)
        assert header.visualIndex(2) == 1
        assert window.table.columnWidth(0) == 34
    finally:
        window.close()


def test_settings_store_default_no_load_default_libraries(tmp_path: Path) -> None:
    """load_default_libraries_on_startup is removed from defaults."""
    from back.settings_store import DEFAULTS
    assert "load_default_libraries_on_startup" not in DEFAULTS
