# Repository Guidelines

## Project Structure & Module Organization

This is a small Python desktop/CLI utility for inspecting various language and diffusion model files.

- `src/` contains .py source code
  - `app_paths.py` Application data paths, including JSONC settings and legacy INI migration location
  - `gui.py` Thin compatibility/bootstrap wrapper that composes and re-exports `MainWindow`, while delegating application startup to `front.application`.
  - `inspect_model.py` Minimal CLI bootstrap that invokes `back.cli`.
  - `model_cache.py` Persistent inspection-result cache
  - `model_readers.py` Read-only model file readers and discovery helpers
  - `modelinfo.py` Model-info dump helpers for Model Inspector
  - `front/` GUI presentation and application layer: `application` bootstraps Qt and applies themes; `window_core`, `window_layout`, and `window_lifecycle` compose `MainWindow`; `analysis_controller`, `discovery_controller`, `selection_controller`, `startup_cache_controller`, `view_controller`, and `integration_controller` manage UI workflows; `explorer_tab`/`explorer_data` provide header-only inspection exploration; `advanced_viewer` provides live resource projections and delegates construction to `advanced_viewer_layout`; `tensor_root_summary` formats compact tensor-root facts; `settings_data_tab` owns Data-column editing and single-row side-button reordering, with `settings_data_support` holding its durable row state and cleanup helpers; `theme_tab` provides live theme editing, with `theme_editor_support` holding palette labels and Qt color conversion; `smart_column_controller` applies runtime smart-column masks; `cache_identity` is the read-only bridge projecting persisted cache identity metadata for cache verification and background sync; `model_card`, `filter_widgets`, `settings_dialog`, and `scan_projection` provide reusable widgets, dialogs, and scan-event delivery.
  - `back/` Backend inspection and CLI layer: `cli` owns command-line parsing and dispatch; `inspection_pipeline`, `model_classification`, `adapter_detection`, `architecture_keys`, `architecture_metadata`, `architecture_variants`, and `tensor_summary` perform read-only inspection and detection; `companion_discovery` performs bounded resolved-parent JSON/Jinja discovery and normalized architecture facts, while `capability_facts` derives conservative domain/chat evidence; `reader_registry`, `checkpoint_reader`, and `onnx_reader` provide safe format-reader dispatch; `shard_discovery` and `sidecar_discovery` discover associated files; `cache_storage` persists cache records; `estimator`, `theme_loader`, `theme_store`, `settings_store`, and `cache_verifier` provide UI-safe backend services; `reporting` writes reports; `inspection_summary` supplies compact GUI-facing result state.
- `assets/` stores bundled application assets, such as icons and splash screen used by the GUI and PyInstaller build.
- `requirements.txt` lists runtime dependencies.
- `requirements-dev.txt` lists build dependencies.
- `compile.bat`, `clean.bat`, `ModelInspector.spec`, `build/`, and `dist/` support PyInstaller packaging.
  - Treat `ModelInspector.spec`, `version.txt`, `build/` and `dist/` as generated output.
- `README.md` github front page, extremely out of date, ignore for now
- `graphify-out/` contains the repository knowledge graph used by agents for architecture navigation.

## Build, Test, and Development Commands

- `py src/gui.py` launches the desktop UI.
- `py src/inspect_model.py --help` checks CLI argument wiring.
- `py src/inspect_model.py path\to\model.safetensors` inspects one file from the CLI.
- `py src/inspect_model.py path\to\folder --recursive --json` runs a recursive CLI smoke test with JSON output.
- `venv_create.bat` creates the local virtual environment and installs dependencies.
- `venv_activate.bat` activates the environment for manual work.
- `win_compile.bat` builds a distributable with PyInstaller.
- `win_clean.bat` cleans up stray bits from compile and direct python execution

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, `snake_case` for functions and variables, `PascalCase` for Qt widget classes, and uppercase constants where appropriate. Keep GUI-only behavior in `gui.py` and GUI functionality in `front/` submodule; keep model parsing, detection heuristics, and report formatting in `inspect_model.py` and the related `back/` submodule. Prefer small helper functions for architecture detection and avoid loading full tensor data unless required.

## Testing Guidelines

- Settings data tests cover single-row selection, side-button reordering, persistence, and embedded-control cleanup.
- Settings dialog tests cover compact fixed 840x460 sizing with screen clamping, dedicated Theme-tab selection, and bounded Data-list/scrollbar geometry; Theme owns its color-editor scroll area.

Validate changes with targeted CLI smoke checks against representative model files and launch `py src/gui.py` for UI changes. For detection changes, verify both human-readable output and `--json` output. If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

Existing tests:
- `.\tests\conftest.py` — documented shared test helpers.
- `.\tests\test_gui_scan_lifecycle.py`
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
- `.\tests\test_tooltip_audit.py`
- `.\tests\test_companion_metadata.py` — bounded companion facts and companion-cache identity regressions.
- `.\tests\test_unknown_reduction.py` — header-only architecture and domain fallbacks.
- `.\tests\test_tensor_root_summary.py`

## Agent-Specific Instructions

- When project structure changes or tests are added, update this file.
- When spawning subagents use `fork_turns = "none"`. Provide specific scoped tasks and their context for subagents.
- ModelInspector implementation files live under `src/`; start with `rg --files src` and read `src/model_cache.py` or `src/modelinfo.py`, never root-level names.
- Establish session environment state once in a reusable command or wrapper: package-cache variables, `PYTHONPATH`, and Qt headless variables. Reuse that canonical invocation rather than prepending environment setup to every command.


### Guardrails & Limits

- **Hard Module Ceiling (500 Lines)**: Any generated or extracted file exceeding 500 lines is automatically flagged as an invalid God Node. It must immediately be queued for a second split by a worker before progressing to linkage repair. No "cohesive file exceptions" without explicit Lead Architect approval.
- **Model Type Enforcement**: Before spawning subagents, verify that requested subagent models map strictly to  `gpt-5.6-sol`, `gpt-5.6-luna`, `gpt-5.6-terra`,`glm-5.3-flash`, `deepseek-v4-flash-high`, or `deepseek-v4-pro` . If a model alias resolves incorrectly or defaults to `gpt-6-astra`, halt execution immediately.
- **Wrapper Boundary Policy**: Entry-point wrappers (`gui.py`, `inspect_model.py`) may contain thin re-exports, MRO composition, and compatibility hooks, but zero domain logic.
