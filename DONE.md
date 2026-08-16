# Completed

Fully completed items of the plan

## Reorganize Project Layout

- [x] Move executable Python source files from the repository root into `src/`, for example `src/gui.py` and `src/inspect_model.py`.
- [x] Move icons and bundled assets out of `src/assets/` into a dedicated resource directory, for example `resources/icons/`.
- [x] Update all imports after the move; prefer explicit module imports over path hacks.
- [x] Update asset lookup helpers so development and PyInstaller-frozen runs resolve `resources/icons/icon.png` consistently.
- [x] Update `compile.bat` paths for the new GUI entry point and icon location.
- [x] Update `ModelInspector.spec` `Analysis`, `datas`, and `icon` paths.
- [x] Update `README.md` and `AGENTS.md` command examples after the layout change.
- [x] Run `py src/gui.py`, `py src/inspect_model.py --help`, and `compile.bat` after the move.

## Explorer Filtering & Progress UX

- [x] Add format filters for `.safetensors`, `.gguf`, `.ckpt`, `.pt`, and `.pth` in a separated section of the filters popup.
- [x] Keep architecture/type filters separate from file-format filters so users can combine both.
- [x] Sort filter menus with `ERROR` first, then `Unknown`, then alphabetical values.
- [x] Keep card and Raw dropdown ordering aligned with the current Data table sort order.
- [x] Replace vague progress percentages with visible metrics, such as files discovered, files parsed, bytes scanned, and current directory.
- [x] Keep the progress bar visible during long directory scans and model-info loading.
- [x] Surface cancellation and partial-results behavior for long scans.

## Resolve Real Paths for Dump Targets

- [x] Investigate how Windows symlinks behave with `Path.resolve()` and file IDs.
- [x] Decide whether `.modelinfo` should be written beside the user-provided path or the resolved target path.
- [x] Add an option if both behaviors are useful, for example `--resolve-output-path`.
- [x] Preserve the user-provided path for default `.modelinfo` output and expose `resolved_filepath` separately.
- [x] Handle failures conservatively and show the chosen output path in CLI/GUI results.

## Library Linking & Path Resolution

## Add Configurable Parallel Loading

- [x] Audit current `AnalysisWorker` behavior and CLI folder scanning for safe concurrency points.
- [x] Add a setting/CLI option such as `--threads N` for batch inspection.
- [x] Use bounded worker pools only for independent file reads; avoid parallel UI mutation.
- [x] Benchmark on large folders before enabling a default above one thread.
- [x] Surface per-file errors without cancelling the full batch.

## Add JSON `.modelinfo` Dumps

- [x] Add a CLI option such as `--write-modelinfo-json`.
- [x] Reuse the existing `.modelinfo` naming schema and append `.json`, for example `model.safetensors.modelinfo.json`.
- [x] Serialize existing inspection output with the standard `json` module unless a stronger need appears.
- [x] Add matching GUI setting/action for JSON dump generation.
- [x] Verify output is stable, pretty-printed, and contains parsed metadata, tensor summaries, architecture details, and warnings.

## Add GGUF Support

- [x] Add a reader abstraction that can dispatch by extension: `.safetensors` first, then `.gguf`.
- [x] Use the installed `gguf` package from `.venv\Lib\site-packages\gguf`.
- [x] Review `.venv\Lib\site-packages\gguf\scripts\gguf_editor_gui.py` for PySide/PyQt patterns, metadata parsing, and tensor listing behavior.
- [x] Implement GGUF metadata extraction, tensor summaries, dtype counts, architecture hints, and model size reporting.
- [x] Keep GGUF support read-only for now; do not expose editing behavior.
- [x] Add CLI and GUI smoke checks with at least one representative `.gguf` file.

## Research Safetensors Library Integration

- [x] Evaluate the official `safetensors` Python package as a replacement or supplement for the current custom header reader.
- [x] Confirm whether `safe_open` can provide metadata, keys, tensor shapes, and dtypes without loading full tensor payloads or requiring Torch.
- [x] Test `framework="numpy"` and metadata-only/key-only flows to avoid a full Torch dependency.
- [x] If unsuitable, document why the custom header parser remains preferable.

## Caching & Default Libraries

- [x] Add a cache for parsed model summaries to speed up repeated launches.
- [x] Store enough identity data to detect moved, deleted, or changed files, such as canonical path, size, modified time, and format.
- [x] Default settings/cache to a portable app-local data directory with relocation overrides.
- [x] Use a cache index with per-entry files instead of one monolithic cache blob.
- [x] Add a cache for scanned directories to speed up repeated launches.
- [x] Add a `load default libraries on startup` setting backed by the cached directory list.
- [x] Keep cached startup entries for missing or temporarily unavailable files instead of pruning stale paths.
- [x] Add a settings action to clear the cache entirely.
- [x] Organize settings into General, Cards, and Data Columns tabs.
- [x] Decide whether cache writes happen immediately after each scan or only after successful batch completion.

## Replace Raw Tab with Explorer Tab


## Add Checkpoint, onnx and `.pt`/`.pth` Support

- [x] Research safe metadata-only handling for PyTorch checkpoint formats.
- [x] Treat pickle-based formats as unsafe by default; require explicit opt-in before loading.
- [x] Add clear warnings in CLI and GUI when a format may execute pickle deserialization.

## Refactor Overloaded Structures

- [x] Use graphify god-node results to split overloaded modules and classes.
- [x] Consider extracting reader modules, architecture detection modules, modelinfo dumping, and GUI widgets into separate files.
- [x] Prioritize reducing `MainWindow`, `inspect_file()`, `generate_modelinfo_dump()`, and architecture detection helper sprawl.
- [x] Add tests or smoke fixtures before large refactors so behavior stays stable.
- [x] After code changes, run `graphify update .` and review the updated god-node/community report.
