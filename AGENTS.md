# Repository Guidelines

## Project Structure & Module Organization

This is a small Python desktop/CLI utility for inspecting various language and diffusion model files.

- `src/` contains .py source code
  - `back/cache_invalidation.py` holds the shared raw-cache invalidation helper used by targeted rescan guards.
  - `build_version.py` derives the wheel/sdist package version from the Windows resource-version source, with installed-distribution fallbacks.
  - `app_paths.py` Application data paths: JSONC settings and legacy INI migration location; user data/cache in `.model-inspector`; default save/output under `~/.local/ModelInspector` via `ensure_output_dir()` (override `SMI_OUTPUT_DIR`); `cache_dir()` is the cache root (`SMI_CACHE_DIR`) holding the inspection cache plus sidecars/raw dumps/directory scans, and `model_cache_dir()` (`SMI_MODEL_CACHE_DIR`, falling back to the root) holds only the primary inspection cache; and `resource_base_dir()` resolution for checkout, installed-wheel (assets beside `app_paths.py`), and PyInstaller (`sys._MEIPASS`) layouts.
  - `gui.py` Thin compatibility/bootstrap wrapper that composes and re-exports `MainWindow`, while delegating application startup to `front.application`.
  - `inspect_model.py` Minimal CLI bootstrap that invokes `back.cli`.
  - `model_cache.py` Persistent inspection-result cache
  - `model_readers.py` Read-only model file readers and discovery helpers
  - `modelinfo.py` Model-info dump helpers for Model Inspector
  - `front/` GUI presentation and application layer: `application` bootstraps Qt and applies themes; `window_core`, `window_layout`, and `window_lifecycle` compose `MainWindow`; `analysis_controller`, `discovery_controller`, `selection_controller`, `startup_cache_controller`, `view_controller`, and `integration_controller` manage UI workflows; `explorer_tab`/`explorer_data` provide header-only inspection exploration; `advanced_viewer` provides live resource projections and delegates construction to `advanced_viewer_layout`; `tensor_root_summary` formats compact tensor-root facts; `settings_data_tab` owns Data-column editing and single-row side-button reordering, with `settings_data_support` holding its durable row state and cleanup helpers; `theme_tab` provides live theme editing, with `theme_editor_support` holding palette labels and Qt color conversion; `smart_column_controller` applies runtime smart-column masks; `data_columns` holds the canonical ordered Data-column labels/default widths and locked-column keys shared by table construction, Settings reset, and width fallback; `cache_load_controller`/`cache_load_worker` project persisted cache summaries off the GUI thread in bounded, cancel/close-safe batches; `startup_arguments` parses GUI startup arguments before Qt starts; `cache_identity` is the read-only bridge projecting persisted cache identity metadata for cache verification and background sync; `file_operation_controller` (`FileOperationControllerMixin`) owns long file operations (move, dump) with modal progress, no-clobber failure retention, and cooperative cancel between files, backed by `file_operation_worker` (`FileOperationWorker` thread plus safe move helpers); `explorer_metadata` performs read-only embedded-metadata actions (Inspect decoded text, Save readable artifact, Extract exact source JSON bytes for locatable safetensors/GGUF metadata; tensor payloads are never read); `help_window` shows `--help` in a window for frozen builds with no stdout; `model_card`, `filter_widgets`, `settings_dialog`, and `scan_projection` provide reusable widgets, dialogs, and scan-event delivery.
  - `back/` Backend inspection and CLI layer: `cli` owns command-line parsing and dispatch; `inspection_pipeline`, `model_classification`, `adapter_detection`, `architecture_keys`, `architecture_metadata`, `architecture_variants`, and `tensor_summary` perform read-only inspection and detection; `companion_discovery` performs bounded resolved-parent JSON/Jinja discovery and normalized architecture facts, while `capability_facts` derives conservative domain/chat evidence and `capability_evidence` projects evidence-backed capabilities (filtering weak evidence) shared by the GUI, reports, and estimator; `reader_registry`, `checkpoint_reader`, and `onnx_reader` provide safe format-reader dispatch; `shard_discovery` and `sidecar_discovery` discover associated files; `cache_storage` persists cache records; `cache_location` resolves the cache root vs model-cache directory (`--cache`/`--cachedir`) and the most-recently-used history; `estimator`, `estimator_metadata` (labelled KV/runtime metadata projection helper), `theme_loader`, `theme_store`, `settings_store`, and `cache_verifier` provide UI-safe backend services; `reporting` writes reports; `modelinfo_diagnostics` projects header-only `.modelinfo` diagnostics with credential-key redaction; `inspection_summary` supplies compact GUI-facing result state.
- `assets/` stores bundled application assets, such as icons and splash screen used by the GUI and PyInstaller build.
- `requirements.txt` lists runtime dependencies.
- `requirements-dev.txt` lists build dependencies.
- `win_compile.bat`, `win_clean.bat`, `ModelInspector.spec`, `build/`, and `dist/` support PyInstaller packaging.
  - Treat `ModelInspector.spec`, `version.txt`, `build/` and `dist/` as generated output.
- `pyproject.toml` declares the setuptools flat-layout wheel: top-level modules plus `front`/`back`/`assets` packages, with `modelinspector` and `modelinspector-gui` console scripts.
- `.github/workflows/build.yml` builds and validates the wheel and the Windows PyInstaller executable.
- `.github/workflows/release.yml` runs the tag-triggered release workflow; `.github/scripts/prepare_release.py` validates the tag/version and stages the wheel plus versioned Windows zip. Hosted end-to-end release validation remains open.
- `README.md` github front page, extremely out of date, ignore for now
- `graphify-out/` contains the repository knowledge graph used by agents for architecture navigation.

## Build, Test, and Development Commands

- `py src/gui.py` launches the desktop UI.
- `py src/gui.py path\to\model.safetensors` (or a folder) queues a safe startup scan after the window is shown; `py src/gui.py --help` exits before Qt starts.
- `py src/gui.py -s path\to\settings.jsonc` selects an explicit settings file for the GUI.
- `py src/inspect_model.py --help` checks CLI argument wiring.
- `py src/inspect_model.py path\to\model.safetensors` inspects one file from the CLI.
- `py src/inspect_model.py path\to\folder --recursive --json` runs a recursive CLI smoke test with JSON output.
- `py src/inspect_model.py -s path\to\settings.jsonc path\to\model.safetensors` selects an explicit settings file for the CLI.
- `--cache PATH` selects the model-cache directory (`SMI_MODEL_CACHE_DIR`) and records it in settings history; `--cachedir PATH` relocates the whole cache root (`SMI_CACHE_DIR`) transiently. Both work for the CLI and GUI.
- `python -m pytest tests` runs the suite; `python -m pytest tests/test_packaging.py -q` checks only the packaging contract.
- `python -m build --wheel` builds the distributable wheel from `pyproject.toml`.
- `pip install dist\modelinspector-*.whl` installs the wheel; `modelinspector` and `modelinspector-gui` console scripts are then available.
- `venv_create.bat` creates the local virtual environment and installs dependencies.
- `venv_activate.bat` activates the environment for manual work.
- `win_compile.bat` builds a distributable with PyInstaller.
- `win_clean.bat` cleans up stray bits from compile and direct python execution
- `.github/workflows/build.yml` builds the wheel and Windows executable and validates a clean wheel install.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, `snake_case` for functions and variables, `PascalCase` for Qt widget classes, and uppercase constants where appropriate. Keep GUI-only behavior in `gui.py` and GUI functionality in `front/` submodule; keep model parsing, detection heuristics, and report formatting in `inspect_model.py` and the related `back/` submodule. Prefer small helper functions for architecture detection and avoid loading full tensor data unless required.

## Testing Guidelines

- Settings data tests cover single-row selection, side-button reordering, persistence, and embedded-control cleanup.
- Settings dialog tests cover the resizable, remembered 900x640 default with screen clamping, dedicated Theme-tab selection, and bounded Data-list/scrollbar geometry. Theme owns its color-editor scroll area. Canonical Data-column labels and default widths live in `front/data_columns.py`; the selection column is locked first/always-visible and hidden columns retain their last valid width.

Validate changes with targeted CLI smoke checks against representative model files and launch `py src/gui.py` for UI changes. For detection changes, verify both human-readable output and `--json` output. If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

Existing tests:
- `tests/test_ptq_precision.py` — actual PTQ142/PTQ143 header mapping and precision preservation.
- `tests/test_rescan_selected.py` — selected-model invalidation, selection preservation, and busy-operation guards.
- `tests/test_release_workflow.py` — static revision-artifact, release-zip, and tag-release workflow contracts; hosted validation is still required.
- `.\tests\conftest.py` — shared test helpers, including the session-scoped `_qapp_holder` fixture that holds one `QApplication` reference for the whole session (PyQt6 crashes with 0xC0000409 if the QApplication is garbage-collected); tests obtain the same instance via `QApplication.instance()`.
- `.\tests\test_gui_scan_lifecycle.py` — compact card mode, asynchronous discovery with queued terminal paths, terminal projection waiting, redundant selection-style suppression, close deferred until analysis and cache-sync workers finish, raw-dump cached/generated prefixing, and modelinfo dump content.
- `.\tests\test_checkpoint_no_prompt.py` — GUI checkpoint metadata-only routing without consent prompts.
- `.\tests\test_inspection_summary.py`
- `.\tests\test_integrated_scan_behavior.py`
- `.\tests\test_background_tasks.py`
- `.\tests\test_gui_projection.py`
- `.\tests\test_explorer_tab.py`
- `.\tests\test_advanced_viewer.py`
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
- `.\tests\test_theme_live_updates.py` — QSS inactive-tab hover and cached live-theme refresh linkage.
- `.\tests\test_theme_paths.py` — bundled default asset resolution and safe new-theme storage.
- `.\tests\test_settings_geometry.py`
- `.\tests\test_settings_close.py` - Settings close skips the full card rebuild and persists the remembered size.
- `.\tests\test_cache_load.py` - bounded async cache-load projection, cancel/close safety, and filter/selection preservation.
- `.\tests\test_app_paths.py` - output-dir defaults/override and installed-wheel resource resolution.
- `.\tests\test_startup_arguments.py` - GUI `--settings`/`-s` and optional startup targets; `--help` before Qt.
- `.\tests\test_packaging.py` - static packaging contract (setuptools backend, flat layout, entry points, packaged assets).
- `.\tests\test_tooltip_audit.py`
- `.\tests\test_companion_metadata.py` — bounded companion facts and companion-cache identity regressions.
- `.\tests\test_unknown_reduction.py` — header-only architecture and domain fallbacks.
- `.\tests\test_tensor_root_summary.py`
- `.\tests\test_capability_evidence.py` — shared evidence-backed capability projection; weak evidence filtered.
- `.\tests\test_reporting_capabilities.py` — report capability lines use evidence-backed projection.
- `.\tests\test_file_operations.py` — threaded modal move/dump workflow and feedback.
- `.\tests\test_file_operation_safety.py` — no-clobber failure retention and cooperative cancel.
- `.\tests\test_startup_feedback.py` — startup action feedback and unknown summary retention.
- `.\tests\test_cache_locations.py` — model-cache vs cache-root separation, history precedence, live-redirect busy guard, and flag wiring.
- `.\tests\test_explorer_metadata.py` — read-only embedded-metadata Inspect/Save/raw-source semantics and exact bytes.
- `.\tests\test_frozen_help.py` — windowed `--help` for frozen builds without stdout.
- `.\tests\test_modelinfo_diagnostics.py` — header-only `.modelinfo` diagnostics and credential redaction without tokenizer over-reach.

## Agent-Specific Instructions

- When project structure changes or tests are added, update this file.
- Subagents do not spawn subagents. Every task must honor exact file/scope ownership, preserve unrelated working-tree changes, and never revert another agent's or user's edits.
- Restart OpenCode after changing agent guidance; the allowed-model list is maintained separately.
- ModelInspector implementation files live under `src/`; start with `rg --files src` and read `src/model_cache.py` or `src/modelinfo.py`, never root-level names.
- Use CodeGraph of Graphify first for source/flow questions; use direct reads only for documentation, configuration, or details CodeGraph cannot provide.
- Establish session environment state once in a reusable command or wrapper: package-cache variables, `PYTHONPATH`, and Qt headless variables. Reuse that canonical invocation rather than prepending environment setup to every command.
- Canonical validation is `python -m pytest tests` with `PYTHONPATH=src` and `QT_QPA_PLATFORM=offscreen` set (PowerShell: `$env:PYTHONPATH="src"; $env:QT_QPA_PLATFORM="offscreen"; python -m pytest tests`). Always pass the `tests` directory explicitly so pytest does not collect vendored test modules in site-packages.
- Canonical Data-column labels and widths are defined once in `front/data_columns.py`; reference that module instead of duplicating the width table in docs or tests.
- Run relevant tests after each coherent change batch and report the exact command, result, and any tool error. Verify real flows and returned evidence rather than inferring success from static wiring.
- Do not guess dtype widths or precision from unsupported metadata; preserve unknown values and state the evidence boundary.


### Guardrails & Limits

- **Hard Module Ceiling (500 Lines)**: Any generated or extracted file exceeding 500 lines is automatically flagged as an invalid God Node. It must immediately be queued for a second split by a worker before progressing to linkage repair. No "cohesive file exceptions" without explicit Lead Architect approval.
- **Model Type Enforcement**: Before spawning subagents, verify that requested subagent models map strictly to models documented in `.opencode/agents/*.md`. If a model alias resolves incorrectly or defaults to `gpt-6-astra`, halt execution immediately.
- **Wrapper Boundary Policy**: Entry-point wrappers (`gui.py`, `inspect_model.py`) may contain thin re-exports, MRO composition, and compatibility hooks, but zero domain logic.
