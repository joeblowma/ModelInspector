# Repository Guidelines

## Project Structure & Module Organization

This is a small Python desktop/CLI utility for inspecting various language and diffusion model files.

- `src/` contains .py source code
  - `app_paths.py` Application data paths for portable defaults
  - `gui.py` contains the PyQt6 desktop application, including `MainWindow`, drag-and-drop input, cards, tables, filters, and background analysis workers.
  - `inspect_model.py` contains the parser, architecture detection, tensor summaries, `.modelinfo` generation, and CLI entry point.
  - `model_cache.py` Persistent inspection-result cache
  - `model_readers.py` Read-only model file readers and discovery helpers
  - `modelinfo.py` Model-info dump helpers for Model Inspector
  - `front/` Sub-module for GUI support functionality
    - `scan_projection.py` Time-sliced delivery of scan events to Qt widgets
  - `back/` Sub-module for backend/command line callable inspect_model.py
    - `inspection_summary.py` Compact inspection results for long-lived GUI presentation state
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

## Agent-Specific Instructions

- When project structure changes or tests are added, update this file.
- When spawning subagents use `fork_turns = "none"`. Provide specific scoped tasks and their context for subagents.
