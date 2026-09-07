# pyright: reportArgumentType=false, reportOptionalMemberAccess=false
"""Smart column group auto-enable contracts for cached inspection results."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from PyQt6.QtWidgets import QApplication

from conftest import _summary


def test_cache_load_auto_enables_llm_smart_group(monkeypatch, tmp_path: Path) -> None:
    """Loading cached results that use MoE data auto-enables the LLM group."""
    monkeypatch.setenv("SMI_SETTINGS_PATH", str(tmp_path / "settings.ini"))
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    from gui import MainWindow

    _ = QApplication.instance() or QApplication([])
    window = MainWindow()
    try:
        cached = "R:/cached/moe.safetensors"
        summary = _summary(cached, "Architecture C", "MoE LLM")
        summary.update({"is_moe": True, "expert_count": 8, "expert_used_count": 2})
        monkeypatch.setattr(
            window, "_cache_report",
            lambda: SimpleNamespace(
                entries=[SimpleNamespace(path=cached, classification="active")],
                availability=SimpleNamespace(
                    total=1, active=1, historic=0, refresh_candidates=0, sync_candidates=0,
                    load_cache=True, load_cache_all=True, load_cache_archived=False,
                    total_count=1, active_count=1, historic_count=0,
                ),
            ),
        )
        monkeypatch.setattr(
            window, "_get_cached_inspection_summary_snapshots", lambda _paths: {cached: summary}
        )
        window._load_cache_all()
        assert window._smart_group_state["llm"] is True
        assert window._smart_group_checkboxes["llm"].isChecked()
        assert not window.table.isColumnHidden(window._table_columns.index("MoE"))
        # Groups without usage stay off.
        assert window._smart_group_state["diffusion"] is False
        assert window._smart_group_state["adapter"] is False
    finally:
        window.close()