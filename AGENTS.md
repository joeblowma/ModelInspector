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
- `assets/` stores bundled application assets, such as icons and splash screen used by the GUI and PyInstaller build.
- `requirements.txt` lists runtime dependencies.
- `requirements-dev.txt` lists build dependencies.
- `compile.bat`, `clean.bat`, `ModelInspector.spec`, `build/`, and `dist/` support PyInstaller packaging.
  - Treat `ModelInspector.spec`, `version.txt`, `build/` and `dist/` as generated output.
- `graphify-out/` contains the repository knowledge graph used by agents for architecture navigation.

## Build, Test, and Development Commands

- `venv_create.bat` creates the local virtual environment and installs dependencies.
- `venv_activate.bat` activates the environment for manual work.
- `py src/gui.py` launches the desktop UI.
- `py src/inspect_model.py --help` checks CLI argument wiring.
- `py src/inspect_model.py path\to\model.safetensors` inspects one file from the CLI.
- `py src/inspect_model.py path\to\folder --recursive --json` runs a recursive CLI smoke test with JSON output.
- `compile.bat` builds the distributable with PyInstaller.

## Coding Style & Naming Conventions

Use standard Python style with 4-space indentation, `snake_case` for functions and variables, `PascalCase` for Qt widget classes, and uppercase constants where appropriate. Keep GUI-only behavior in `gui.py`; keep model parsing, detection heuristics, and report formatting in `inspect_model.py`. Prefer small helper functions for architecture detection and avoid loading full tensor data unless required.

## Testing Guidelines

There is currently no committed automated test suite. Validate changes with targeted CLI smoke checks against representative `.safetensors` files and launch `py gui.py` for UI changes. For detection changes, verify both human-readable output and `--json` output. If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

## Commit & Pull Request Guidelines

Recent history uses short, imperative or descriptive commit subjects, for example `Improved ZiT detection` and `revert a UI change from a prior commit`. Keep commits focused and mention the affected area when useful. Pull requests should include a concise description, manual validation commands, screenshots for visible GUI changes, and notes about any model files or edge cases used for verification.

## Agent-Specific Instructions

Before answering architecture or cross-module codebase questions, read `graphify-out/GRAPH_REPORT.md`. Prefer `graphify query`, `graphify path`, or `graphify explain` for relationship questions. After modifying code files, run `graphify update .` to refresh the AST graph.
