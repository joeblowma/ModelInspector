"""Cache-sync option identity regressions."""

from __future__ import annotations

import json
import struct
from pathlib import Path

from back.cache_verifier import verify_cache_entries
import background_tasks
from front import integration_controller
from front.cache_identity import get_cached_inspection_entry_identity_snapshots
import model_cache


def _write_safetensors(path: Path, marker: str) -> None:
    header = json.dumps({"__metadata__": {"marker": marker}}).encode()
    path.write_bytes(struct.pack("<Q", len(header)) + header)


class _CacheSyncHost(integration_controller.IntegrationMixin):
    _allow_filename_alias_detection = True
    _cache_sync_worker = None

    def _on_cache_sync_completed(self) -> None:
        self._cache_sync_worker = None


def _verification_report() -> tuple[list[dict], object]:
    selected = model_cache.list_cached_inspection_entries()
    identities = get_cached_inspection_entry_identity_snapshots(selected)
    report = verify_cache_entries(
        [identities[entry["cache_key"]] for entry in selected]
    )
    return selected, report


def test_cache_sync_refreshes_the_selected_false_alias_cache_key(
    monkeypatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("SMI_CACHE_DIR", str(tmp_path / "cache"))
    model = tmp_path / "model.safetensors"
    _write_safetensors(model, "before")

    initial = background_tasks.AnalysisWorker(
        [str(model)], {"allow_filename_alias_detection": False}
    )
    initial.run()
    selected, report = _verification_report()
    selected_key = selected[0]["cache_key"]
    assert selected[0]["cache_options"] == {"allow_filename_alias_detection": False}
    assert report.entries[0].action == "none"

    _write_safetensors(model, "after-with-a-different-size")
    selected, report = _verification_report()
    assert selected[0]["cache_key"] == selected_key
    assert report.entries[0].action == "refresh"

    monkeypatch.setattr(background_tasks.AnalysisWorker, "start", lambda worker: worker.run())
    _CacheSyncHost()._schedule_cache_sync(report)

    selected, report = _verification_report()
    assert selected[0]["cache_key"] == selected_key
    assert report.entries[0].action == "none"


def test_analysis_worker_applies_only_snapshotted_alias_options(monkeypatch) -> None:
    options_seen = []
    path_options = {
        "false": {
            "allow_filename_alias_detection": False,
            "checkpoint_safety": "reject",
            "include_sidecars": True,
        },
        "true": {"allow_filename_alias_detection": True},
    }
    worker = background_tasks.AnalysisWorker(
        ["false", "true", "legacy"],
        {
            "allow_filename_alias_detection": True,
            "checkpoint_safety": "metadata",
        },
        per_path_options=path_options,
    )
    path_options["false"]["allow_filename_alias_detection"] = True
    monkeypatch.setattr(
        background_tasks,
        "inspect_file",
        lambda _path, options=None: options_seen.append(dict(options or {}))
        or {"filepath": _path},
    )
    worker.result_ready.connect(lambda _result: worker.acknowledge_event())
    worker.run()

    assert options_seen == [
        {"allow_filename_alias_detection": False, "checkpoint_safety": "metadata"},
        {"allow_filename_alias_detection": True, "checkpoint_safety": "metadata"},
        {"allow_filename_alias_detection": True, "checkpoint_safety": "metadata"},
    ]

    plain_worker = background_tasks.AnalysisWorker(
        ["plain"], {"allow_filename_alias_detection": False}
    )
    plain_worker.result_ready.connect(lambda _result: plain_worker.acknowledge_event())
    plain_worker.run()
    assert options_seen[-1] == {"allow_filename_alias_detection": False}
