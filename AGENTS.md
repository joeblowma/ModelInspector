# Repository Guidelines

## Project Structure & Module Organization

This is a growing Python desktop/CLI utility for inspecting various language and diffusion model files.

- `src/` contains .py source code
  - `back/cache_invalidation.py` holds the shared raw-cache invalidation helper used by targeted rescan guards.
  - `build_version.py` derives the wheel/sdist package version from the Windows resource-version source, with installed-distribution fallbacks.
  - `app_paths.py` owns JSONC settings and legacy INI migration paths; fresh application data/settings/cache and default save/output use `~/.local/share/ModelInspector` via `ensure_output_dir()` (override `SMI_OUTPUT_DIR`), while an existing `.model-inspector` location is retained. `cache_dir()` (`SMI_CACHE_DIR`) holds the inspection cache plus sidecars/raw dumps/directory scans, and `model_cache_dir()` (`SMI_MODEL_CACHE_DIR`, falling back to the root) holds only the primary inspection cache; `resource_base_dir()` resolves checkout, installed-wheel, and PyInstaller (`sys._MEIPASS`) layouts.
  - `gui.py` Thin compatibility/bootstrap wrapper that composes and re-exports `MainWindow`, while delegating application startup to `front.application`.
  - `inspect_model.py` Minimal CLI bootstrap that invokes `back.cli`.
  - `model_cache.py` Persistent inspection-result cache
   - `model_readers.py` owns read-only safetensors headers and dispatch helpers;
     `read_gguf_header()` calls bounded native GGUF parsing in
     `back/gguf_reader.py` directly and authoritatively, with no optional-library
     fallback for any error.
  - `modelinfo.py` Model-info dump helpers for Model Inspector
  - `front/` GUI presentation and application layer: `application` bootstraps Qt and applies themes; `window_core`, `window_layout`, and `window_lifecycle` compose `MainWindow`; card-surface drop relaying dispatches exact `QEvent.Type.DragEnter`, `DragMove`, and `Drop` events to the window, accepting URL moves but only queuing work on Drop; `analysis_controller`, `discovery_controller`, `selection_controller`, `startup_cache_controller`, `view_controller`, and `integration_controller` manage UI workflows; `explorer_tab`/`explorer_data` provide header-only inspection exploration; `advanced_viewer` provides live resource projections and delegates construction to `advanced_viewer_layout`; `tensor_root_summary` formats compact tensor-root facts; `settings_data_tab` owns Data-column editing and single-row side-button reordering, with `settings_data_support` holding its durable row state and cleanup helpers; `theme_tab` provides live theme editing, with `theme_editor_support` holding palette labels and Qt color conversion; `smart_column_controller` applies runtime smart-column masks; `data_columns` holds the canonical ordered Data-column labels/default widths and locked-column keys shared by table construction, Settings reset, and width fallback; `cache_load_controller`/`cache_load_worker` project persisted cache summaries off the GUI thread in bounded, cancel/close-safe batches; `startup_arguments` parses GUI startup arguments before Qt starts; `cache_identity` is the read-only bridge projecting persisted cache identity metadata for cache verification and background sync; `file_operation_controller` (`FileOperationControllerMixin`) owns long file operations (move, dump) with modal progress, no-clobber failure retention, and cooperative cancel between files, backed by `file_operation_worker` (`FileOperationWorker` thread plus safe move helpers); `explorer_metadata` performs read-only embedded-metadata actions (Inspect decoded text, Save readable artifact, Extract exact source JSON bytes for locatable safetensors/GGUF metadata; tensor payloads are never read); `help_window` shows `--help` in a window for frozen builds with no stdout; `model_card`, `filter_widgets`, `settings_dialog`, and `scan_projection` provide reusable widgets, dialogs, and scan-event delivery.
  - `back/` Backend inspection and CLI layer: `cli` owns command-line parsing and dispatch; `inspection_pipeline`, `model_classification`, `adapter_detection`, `architecture_keys`, `architecture_metadata`, `architecture_variants`, and `tensor_summary` perform read-only inspection and detection; `companion_discovery` performs bounded resolved-parent JSON/Jinja discovery and normalized architecture facts, while `capability_facts` derives conservative domain/chat evidence and `capability_evidence` projects evidence-backed capabilities (filtering weak evidence) shared by the GUI, reports, and estimator; `reader_registry`, `checkpoint_reader`, `gguf_reader`, and `onnx_reader` provide safe format-reader dispatch. `gguf_reader` owns bounded native GGUF parsing; malformed or unsafe native input must not fall back to an optional library. `shard_discovery` and `sidecar_discovery` discover associated files; `cache_storage` persists cache records; `cache_location` resolves the cache root vs model-cache directory (`--cache`/`--cachedir`) and the most-recently-used history; `estimator`, `estimator_metadata` (labeled KV/runtime metadata projection helper), `theme_loader`, `theme_store`, `settings_store`, and `cache_verifier` provide UI-safe backend services; `reporting` writes reports; `modelinfo_diagnostics` projects header-only `.modelinfo` diagnostics with credential-key redaction; `inspection_summary` supplies compact GUI-facing result state.
   - `front/metadata_ui.py` owns bounded metadata projection and the asynchronous header-loader/controller handoff used by the Advanced Viewer; keep its payload boundary header-only.
   - `front/filter_projection.py` owns QTimer-sliced cards/Data filter projection;
     replace pending work on a newer selection and never perform a large
     projection synchronously on the GUI event loop.
   - `front/layout_batch.py` owns the nestable, idempotent Cards-layout lease:
     preserve the layout's original enabled state, disable it once per nested
     batch, and release safely on errors, cancellation, close, or destruction.
     `front/scan_projection.py` drains cache and new-scan updates in bounded
     layout leases and acknowledges each payload only after release.
   - `front/view_removal.py` owns incremental exact-path removal. Retain
     unaffected Cards/Data widgets, selection, sorting maps, facets, and Raw
     selection; reserve `rebuild_views_from_results()` for explicit full
     rebuilds, guarded as one layout/format batch.
   - `back/cache_entries.py` chooses the first persisted summary per path and
     retains its stable cache key/options for cache verification and projection.
   - `assets/ResizeSplash.py` is a standalone image utility: return Boolean
     operation status and map its command-line paths to process exit status.
- `assets/` stores bundled application assets, such as icons and splash screen used by the GUI and PyInstaller build.
- `src/front/model_path_label.py` owns the compact one-line `Model: <path>`
  label, middle-elided tooltip, and file/folder path copy behavior. Keep this
  display/copy logic in that module.
- Explorer metadata remains bounded and read-only: source JSON recovery is
  limited to locatable safetensors/GGUF metadata, never reads tensor payloads,
  and supported loaded-model Inspect must not add files or trigger reanalysis.
  Sorted/filterable metadata and embedded rows retain Qt payload mappings; Save
  and Extract prefer an existing requested path, then resolved/legacy paths, so
  cached previews never replace live metadata or require a cache purge. Metadata
  tab activation requests a live header even when cached descriptors exist;
  controller-local read provenance ignores stale persisted completion flags and
  chooses the first existing requested, filepath, or resolved source. Missing
  files retain cached fallback and are explicitly incomplete.
- `requirements.txt` lists runtime dependencies.
- `requirements-dev.txt` lists build dependencies.
- `win_compile.bat`, `win_clean.bat`, `ModelInspector.spec`, `build/`, and `dist/` support PyInstaller packaging.
  - Treat `ModelInspector.spec`, `version.txt`, `build/` and `dist/` as generated output.
- `pyproject.toml` declares the setuptools flat-layout wheel: top-level modules plus `front`/`back`/`assets` packages, with `modelinspector` and `modelinspector-gui` console scripts.
- `.github/workflows/build.yml` builds and validates the wheel and the Windows PyInstaller executable.
- `.github/workflows/release.yml` runs the tag-triggered release workflow; `.github/scripts/prepare_release.py` validates the tag/version and stages the wheel plus versioned Windows zip. Hosted end-to-end release validation remains open.
- `README.md` is the current install, usage, safety, and validation-status guide; `DONE.md` records completed work and `TODO.md` records open verification/product work.
- `graphify-out/` contains the repository knowledge graph used by agents for architecture navigation.

## Build, Test, and Development Commands

- `py src/gui.py` launches the desktop UI.
- `py src/gui.py path\to\model.safetensors` (or a folder) queues a safe startup scan after the window is shown; `py src/gui.py --help` exits before Qt starts.
- `py src/gui.py -s path\to\settings.jsonc` selects an explicit settings file for the GUI.
- `py src/inspect_model.py --help` checks CLI argument wiring.
- `py src/inspect_model.py path\to\model.safetensors` inspects one file from the CLI.
- `py src/inspect_model.py path\to\folder --recursive --json` runs a recursive CLI smoke test with JSON output.
- `py src/inspect_model.py -s path\to\settings.jsonc path\to\model.safetensors` selects an explicit settings file for the CLI.
- `--cache PATH` selects the model-cache directory (`SMI_MODEL_CACHE_DIR`) and records it in settings history; `--cachedir PATH` relocates the whole cache root (`SMI_CACHE_DIR`) transiently and, absent `--cache`, aligns the model-cache root with it. Both work for the CLI and GUI.
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
- Reader-bound tests cover exact safetensors header reads and native GGUF
  limits/truncation, including OSError, RuntimeError, unsupported-version, and
  no-library-fallback boundaries. Shard/checkpoint tests cover bounded
  shard-number parsing, partial-set warnings, and the private
  `zipfile._EndRecData` ZIP central-directory preflight before `ZipFile`
  construction. The compatibility boundary retains the 2 MiB directory limit,
  does not deserialize pickle or read tensor payloads, and supports legacy versus
  current ZIP64 end-record positions by checking the four-byte signature.
- Layout-batch tests cover nested/idempotent lease restoration, errors,
  scan acknowledgement after release, synchronous/asynchronous filter release,
  cancellation, close, and owner destruction. Incremental-removal tests must
  retain unaffected widgets, selection, sorting, facet, queue, and Raw-combo
  state, and must restore the placeholder when the last result is removed.
- Cards use `QLayout.SizeConstraint.SetDefaultConstraint` so the resizable
  scroll area, rather than accumulated content minimum size, owns geometry.
  `test_cards_layout_geometry.py` must retain scroll, resize, filter/restore,
  bottom-card, and final-placeholder coverage.
- `tests/conftest.py` autouse-isolates `SMI_CACHE_DIR`, `SMI_MODEL_CACHE_DIR`,
  and legacy `SMI_CACHE_PATH` with `pytest.MonkeyPatch.context()`; cache-location
  tests must not rely on environment state from another test.

Validate changes with targeted CLI smoke checks against representative model files and launch `py src/gui.py` for UI changes. For detection changes, verify both human-readable output and `--json` output. If tests are added, place them under `tests/`, use `pytest`, and name files `test_*.py`.

The current canonical suites each passed **534, with 4 skipped** (exit 0):
Python 3.12.15 in **150.89 seconds**, `$env:PYTHONPATH='src';
$env:QT_QPA_PLATFORM='offscreen'; &'.venv\Scripts\python.exe' -m pytest tests
--capture=tee-sys` (`R:\Temp\opencode\modelinspector-zip-suite-312.log`); and
system Python 3.14.8 in **151.82 seconds**, `$env:PYTHONPATH='src';
$env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests --capture=tee-sys`
(`R:\Temp\opencode\modelinspector-zip-suite-314.log`). Cache-load geometry is
improved, but residual initial-load/RSS debt remains in `TODO.md`.
The live-file header loader reads directly and retains cached fallback only for
missing files. Header-only CLI evidence covers the current
Flux/SDXL/Qwen/Boogu/LongCat/LoRA cases; preserve unknown or null-domain/capability
results where metadata is insufficient. Keep packaged visual QA, the existing
strict-pylint blocker, hosted/tagged native-SHA workflow validation, and Graphify
refresh open. Mypy is not a configured clean gate: the current unbaselined run
reports 211 errors.

`.\tests\AGENTS.md` - contains a list of existing tests and their uses. Read before creating new tests, update when tests change.

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
- Synthetic responsiveness tests do not replace a packaged/manual run over 420+
  representative live models when investigating multi-second UI delays.
- Do not guess dtype widths or precision from unsupported metadata; preserve unknown values and state the evidence boundary.


### Guardrails & Limits

- **Hard Module Ceiling (500 Lines)**: Any generated or extracted file exceeding 500 lines is automatically flagged as an invalid God Node. It must immediately be queued for a second split by a worker before progressing to linkage repair. No "cohesive file exceptions" without explicit Lead Architect approval.
- **Model Type Enforcement**: Before spawning subagents, verify that requested subagent models map strictly to models documented in `.opencode/agents/*.md`. If a model alias resolves incorrectly or defaults to `gpt-6-astra`, halt execution immediately.
- **Wrapper Boundary Policy**: Entry-point wrappers (`gui.py`, `inspect_model.py`) may contain thin re-exports, MRO composition, and compatibility hooks, but zero domain logic.
- **Existing legacy ceiling follow-up**: `explorer_tab.py` (541 lines),
  `settings_dialog.py` (501), and `theme_tab.py` (510) predate this batch;
  do not expand them, but leave splitting to a scoped maintenance owner.
