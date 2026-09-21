# Test harness index

## Existing tests:
- `.\tests\test_ptq_precision.py` — actual PTQ142/PTQ143 header mapping and precision preservation.
- `.\tests\test_rescan_selected.py` — selected-model invalidation, selection preservation, and busy-operation guards.
- `.\tests\test_release_workflow.py` — static revision-artifact, release-zip, and tag-release workflow contracts; hosted validation is still required.
- `.\tests\conftest.py` — shared test helpers, including the session-scoped `_qapp_holder` fixture that holds one `QApplication` reference for the whole session (PyQt6 crashes with 0xC0000409 if the QApplication is garbage-collected); tests obtain the same instance via `QApplication.instance()`.
- `.\tests\test_gui_scan_lifecycle.py` — compact card mode, asynchronous discovery with queued terminal paths, terminal projection waiting, redundant selection-style suppression, close deferred until analysis and cache-sync workers finish, raw-dump cached/generated prefixing, and modelinfo dump content.
- `.\tests\test_checkpoint_no_prompt.py` — GUI checkpoint metadata-only routing without consent prompts.
- `.\tests\test_inspection_summary.py`
- `.\tests\test_integrated_scan_behavior.py`
- `.\tests\test_background_tasks.py`
- `.\tests\test_gui_projection.py`
- `.\tests\test_explorer_tab.py` — bounded metadata/tensor exploration, stable sorted/filterable metadata and embedded-row previews, and non-destructive loaded-model Inspect behavior.
- `.\tests\test_card_advanced_flow.py` — full non-tensor Advanced values, supported replace/additive Inspect flow, and cached drag/drop source reuse without list reset.
- `.\tests\test_advanced_viewer.py` — bounded tensor presentation alongside full non-tensor values.
- `.\tests\test_filter_widgets.py`
- `.\tests\test_model_card_fields.py` — planned fixed simple/advanced card-field contracts; legacy masks are ignored.
- `.\tests\test_settings_data_tab.py`
- `.\tests\test_backend_phase2.py`
- `.\tests\test_phase4_integration.py`
- `.\tests\test_cache_sync_ui.py`
- `.\tests\test_cache_menu_integration.py`
- `.\tests\test_smart_column_groups.py`
- `.\tests\test_reader_registry.py`
- `.\tests\test_onnx_reader.py`
- `.\tests\test_shard_discovery.py`
- `.\tests\test_sidecar_discovery.py`
- `.\tests\test_cache_sidecar_integration.py`
- `.\tests\test_reporting_shards.py`
- `.\tests\test_theme_tab.py`
- `.\tests\test_theme_color_picker.py`
- `.\tests\test_theme_live_updates.py` — QSS inactive-tab hover, cached live-theme refresh linkage, and Open-theme styling.
- `.\tests\test_theme_paths.py` — bundled default asset resolution and safe new-theme storage.
- `.\tests\test_settings_geometry.py`
- `.\tests\test_settings_close.py` - Settings close skips the full card rebuild and persists the remembered size.
- `.\tests\test_cache_load.py` - bounded async cache-load projection, cancel/close safety, and filter/selection preservation.
- `.\tests\test_app_paths.py` - output-dir defaults/override and installed-wheel resource resolution.
- `.\tests\test_startup_arguments.py` - GUI `--settings`/`-s` and optional startup targets; `--help` before Qt.
- `.\tests\test_packaging.py` - static packaging contract (setuptools backend, flat layout, entry points, packaged assets).
- `.\tests\test_tooltip_audit.py`
- `.\tests\test_companion_metadata.py` — bounded companion facts and companion-cache identity regressions.
- `.\tests\test_unknown_reduction.py` — header-only architecture signatures and conservative domain fallbacks, including negative cases that must remain Unknown.
- `.\tests\test_tensor_root_summary.py` — bounded tensor-root grouping/search plus Advanced Viewer header-descriptor loading.
- `.\tests\test_capability_evidence.py` — shared evidence-backed capability projection, weak-evidence filtering, and the diffusion/domain boundary.
- `.\tests\test_reporting_capabilities.py` — report capability lines use evidence-backed projection.
- `.\tests\test_file_operations.py` — threaded modal move/dump workflow and feedback.
- `.\tests\test_file_operation_safety.py` — no-clobber failure retention and cooperative cancel.
- `.\tests\test_startup_feedback.py` — startup action feedback and unknown summary retention.
- `.\tests\test_cache_locations.py` — model-cache vs cache-root separation, history precedence, live-redirect busy guard, and flag wiring.
- `.\tests\test_explorer_metadata.py` — bounded read-only embedded-metadata Inspect/Save/raw-source semantics, readable-content handling, stored previews, requested/resolved-path recovery, and exact safetensors/GGUF source bytes without tensor reads.
- `.\tests\test_metadata_ui.py` — live-file header loading without full-data cache scans, missing-file fallback, metadata/domain/capability badge projection, and Advanced Viewer metadata UI contracts.
- `.\tests\test_frozen_help.py` — windowed `--help` for frozen builds without stdout.
- `.\tests\test_modelinfo_diagnostics.py` — header-only `.modelinfo` diagnostics and credential redaction without tokenizer over-reach.
- `.\tests\test_ui_release_gates.py` — release-gate UI regressions for uniform Cards scroll sizing, always-analyze behavior after removal of the legacy toggle, unchanged Settings close, and sliced changed-Data progress.

## Current validation note

- Canonical full suite: **470 passed, 4 skipped in 52.11 seconds**, exit 0;
  focused Explorer/metadata/Advanced coverage: 55 passed. Real-header Qwen smokes passed in
  human-readable and JSON modes.
- Generic Qwen Image2.1 is guarded against the diffusion-as-LLM false positive;
  unsupported diffusion projects a null domain and empty capabilities, while
  Qwen35 prompt enhancers remain LLM with thinking/tools.
