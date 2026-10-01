# Test harness index

## Existing tests:
- `.\tests\test_ptq_precision.py` — actual PTQ142/PTQ143 header mapping and precision preservation.
- `.\tests\test_rescan_selected.py` — selected-model invalidation, selection preservation, and busy-operation guards.
- `.\tests\test_release_workflow.py` — static revision-artifact, release-zip, and tag-release workflow contracts; hosted validation is still required.
- `.\tests\conftest.py` — shared test helpers, including the session-scoped `_qapp_holder` fixture that holds one `QApplication` reference for the whole session (PyQt6 crashes with 0xC0000409 if the QApplication is garbage-collected); tests obtain the same instance via `QApplication.instance()`.
- `.\tests\test_gui_scan_lifecycle.py` — compact card mode, asynchronous discovery with queued terminal paths, one-file append/drain and cancel/close behavior, terminal projection waiting, Analyze visibility, and exact enter/move/drop relay behavior across all Cards surfaces and the main window; also raw-dump cached/generated prefixing and modelinfo dump content.
- `.\tests\test_checkpoint_no_prompt.py` — GUI checkpoint metadata-only routing without consent prompts.
- `.\tests\test_inspection_summary.py`
- `.\tests\test_integrated_scan_behavior.py`
- `.\tests\test_background_tasks.py`
- `.\tests\test_gui_projection.py`
- `.\tests\test_explorer_tab.py` — bounded metadata/tensor exploration, stable sorted/filterable metadata and embedded-row previews, and non-destructive loaded-model Inspect behavior.
- `.\tests\test_card_advanced_flow.py` — full non-tensor Advanced values, supported replace/additive Inspect flow, cached drag/drop source reuse without list reset, and three-model persisted-cache reloads through `MainWindow._clear_all`, `_load_cache_all`/`CacheLoadWorker`, summary projection, and two-window live-header/detail verification.
- `.\tests\test_advanced_viewer.py` — bounded tensor presentation alongside full non-tensor values and the explicit incomplete Metadata tab without a live path.
- `.\tests\test_filter_widgets.py` — facet counts under other active filters, preserved choices, upward popup placement, and scroll indicators.
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
- `.\tests\test_cache_load.py` - bounded async cache-load projection, Historic visibility/tagging, cancel/close safety, and filter/selection preservation.
- `.\tests\test_app_paths.py` - output-dir defaults/override and installed-wheel resource resolution.
- `.\tests\test_startup_arguments.py` - GUI `--settings`/`-s` and optional startup targets; `--help` before Qt.
- `.\tests\test_packaging.py` - static packaging contract (setuptools backend, flat layout, entry points, packaged assets).
- `.\tests\test_tooltip_audit.py`
- `.\tests\test_companion_metadata.py` — bounded companion facts, companion-cache identity, and current model-family metadata regressions.
- `.\tests\test_unknown_reduction.py` — header-only architecture signatures, Flux/SDXL/Qwen/Boogu/LongCat/LoRA evidence cases, and conservative domain fallbacks including negative cases that must remain Unknown.
- `.\tests\test_tensor_root_summary.py` — bounded tensor-root grouping/search plus Advanced Viewer header-descriptor loading.
- `.\tests\test_capability_evidence.py` — shared evidence-backed capability projection, weak-evidence filtering, and the diffusion/domain boundary.
- `.\tests\test_reporting_capabilities.py` — report capability lines use evidence-backed projection.
- `.\tests\test_file_operations.py` — threaded modal move/dump workflow and feedback.
- `.\tests\test_file_operation_safety.py` — no-clobber failure retention and cooperative cancel.
- `.\tests\test_startup_feedback.py` — startup action feedback and unknown summary retention.
- `.\tests\test_cache_locations.py` — model-cache vs cache-root separation, history precedence, live-redirect busy guard, and flag wiring.
- `.\tests\test_explorer_metadata.py` — bounded read-only embedded-metadata Inspect/Save/raw-source semantics, readable-content handling, stored previews, requested/resolved-path recovery, and exact safetensors/GGUF source bytes without tensor reads.
- `.\tests\test_metadata_ui.py` — live-file header loading without full-data cache scans, tab-triggered reads despite cached descriptors, requested/filepath/resolved existing-path preference despite stale persisted flags, missing-file incomplete fallback, full detail access, metadata/domain/capability badge projection, and Advanced Viewer metadata UI contracts.
- `.\tests\test_checkpoint_routes.py` — metadata-only checkpoint routing: existing files reach the reader with the policy, while missing files do not invoke it.
- `.\tests\test_frozen_help.py` — windowed `--help` for frozen builds without stdout.
- `.\tests\test_modelinfo_diagnostics.py` — header-only `.modelinfo` diagnostics and credential redaction without tokenizer over-reach.
- `.\tests\test_ui_release_gates.py` — release-gate UI regressions for uniform Cards scroll sizing, always-analyze behavior after removal of the legacy toggle, default modelinfo dumping/tooltips, unchanged Settings close, and sliced changed-Data progress.

## Current validation note

- Canonical full suite: **487 passed, 4 skipped in 135.80 seconds**, exit 0:
  `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests`.
  Log: `R:\Temp\opencode\modelinspector-regression-2026-10-01.log`. This run
  preceded the supplemental existing-test extension below.
- Supplemental post-extension test: **7 passed in 0.73 seconds**, exit 0:
  `PYTHONPATH=src QT_QPA_PLATFORM=offscreen python -m pytest
  tests/test_card_advanced_flow.py -q`. No full suite was rerun.
- Header-only model CLI smokes passed in human-readable and JSON modes; retain
  null-domain/empty-capability or Unknown outcomes where metadata lacks evidence.
