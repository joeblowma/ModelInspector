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
  - `front/` GUI presentation and application layer: `application` bootstraps Qt and applies themes; `window_core`, `window_layout`, and `window_lifecycle` compose `MainWindow`; `analysis_controller`, `discovery_controller`, `selection_controller`, `startup_cache_controller`, `view_controller`, and `integration_controller` manage UI workflows; `explorer_tab`/`explorer_data` provide header-only inspection exploration; `advanced_viewer` provides live resource projections; `settings_data_tab` owns Data column/theme editing; `cache_identity` is the read-only bridge projecting persisted cache identity metadata for cache verification and background sync; `model_card`, `filter_widgets`, `settings_dialog`, and `scan_projection` provide reusable widgets, dialogs, and scan-event delivery.
  - `back/` Backend inspection and CLI layer: `cli` owns command-line parsing and dispatch; `inspection_pipeline`, `model_classification`, `adapter_detection`, `architecture_keys`, `architecture_metadata`, `architecture_variants`, and `tensor_summary` perform read-only inspection and detection; `estimator`, `theme_loader`, `settings_store`, and `cache_verifier` provide UI-safe backend services; `reporting` writes reports; `inspection_summary` supplies compact GUI-facing result state.
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

Validate changes with targeted CLI smoke checks against representative model files and launch `py src/gui.py` for UI changes. For detection changes, verify both human-readable output and `--json` output. If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

Existing tests:
- `.\test_gui_scan_lifecycle.py`
- `.\test_inspection_summary.py`
- `.\test_integrated_scan_behavior.py`
- `.\test_background_tasks.py`
- `.\test_gui_projection.py`
- `.\tests\test_explorer_tab.py`
- `.\tests\test_advanced_viewer.py`
- `.\tests\test_settings_data_tab.py`
- `.\tests\test_backend_phase2.py`
- `.\tests\test_phase4_integration.py`

## Agent-Specific Instructions

- When project structure changes or tests are added, update this file.
- When spawning subagents use `fork_turns = "none"`. Provide specific scoped tasks and their context for subagents.

### Guardrails & Limits

- **Hard Module Ceiling (500 Lines)**: Any generated or extracted file exceeding 500 lines is automatically flagged as an invalid God Node. It must immediately be queued for a second split by a worker before progressing to linkage repair. No "cohesive file exceptions" without explicit Lead Architect approval.
- **Model Type Enforcement**: Before spawning subagents, verify that requested subagent models map strictly to `luna-medium`, `luna-xhigh`, `terra-medium`, or `terra-high`. If a model alias resolves incorrectly or defaults to `sol-medium`, halt execution immediately.
- **Wrapper Boundary Policy**: Entry-point wrappers (`gui.py`, `inspect_model.py`) may contain thin re-exports, MRO composition, and compatibility hooks, but zero domain logic.
