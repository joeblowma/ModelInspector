# TODO

Actionable integration plan for repository organization, additional model formats, richer dumps, and UI expansion.


## 1. Reorganize Project Layout

- Move executable Python source files from the repository root into `src/`, for example `src/gui.py` and `src/inspect_model.py`.
- Move icons and bundled assets out of `src/assets/` into a dedicated resource directory, for example `resources/icons/`.
- Update all imports after the move; prefer explicit module imports over path hacks.
- Update asset lookup helpers so development and PyInstaller-frozen runs resolve `resources/icons/icon.png` consistently.
- Update `compile.bat` paths for the new GUI entry point and icon location.
- Update `SafetensorsModelInspector.spec` `Analysis`, `datas`, and `icon` paths.
- Update `README.md` and `AGENTS.md` command examples after the layout change.
- Run `py src/gui.py`, `py src/inspect_model.py --help`, and `compile.bat` after the move.

## 2. Explorer Filtering & Progress UX

- [x] Add format filters for `.safetensors`, `.gguf`, `.ckpt`, `.pt`, and `.pth` in a separated section of the filters popup.
- [x] Keep architecture/type filters separate from file-format filters so users can combine both.
- [x] Replace vague progress percentages with visible metrics, such as files discovered, files parsed, bytes scanned, and current directory.
- [x] Keep the progress bar visible during long directory scans and model-info loading.
- [x] Surface cancellation and partial-results behavior for long scans.

## 3. Resolve Real Paths for Dump Targets

- [x] Investigate how Windows symlinks behave with `Path.resolve()` and file IDs.
- [x] Decide whether `.modelinfo` should be written beside the user-provided path or the resolved target path.
- [x] Add an option if both behaviors are useful, for example `--resolve-output-path`.
- [x] Preserve the user-provided path for default `.modelinfo` output and expose `resolved_filepath` separately.
- [x] Handle failures conservatively and show the chosen output path in CLI/GUI results.

## 4. Library Linking & Path Resolution

- Add an option to create symbolic links alongside the existing move-file actions.
- Support destination templates for common model library layouts, such as `.\models\<type>\<model name>\<file>`.
- Add presets for ComfyUI and A1111 directory conventions, with editable templates.
- Resolve canonical target paths before creating links so the same model is not duplicated under symlink, junction, hardlink, or original-path aliases.
- Show the resolved source path and planned link path before applying bulk link operations.
- Detect existing destination files/links and offer skip, overwrite, or open-location behavior.

## 5. Add Configurable Parallel Loading

- [x] Audit current `AnalysisWorker` behavior and CLI folder scanning for safe concurrency points.
- [x] Add a setting/CLI option such as `--threads N` for batch inspection.
- [x] Use bounded worker pools only for independent file reads; avoid parallel UI mutation.
- [x] Benchmark on large folders before enabling a default above one thread.
- [x] Surface per-file errors without cancelling the full batch.

## 6. Add JSON `.modelinfo` Dumps

- [x] Add a CLI option such as `--write-modelinfo-json`.
- [x] Reuse the existing `.modelinfo` naming schema and append `.json`, for example `model.safetensors.modelinfo.json`.
- [x] Serialize existing inspection output with the standard `json` module unless a stronger need appears.
- [x] Add matching GUI setting/action for JSON dump generation.
- [x] Verify output is stable, pretty-printed, and contains parsed metadata, tensor summaries, architecture details, and warnings.

## 7. Add GGUF Support

- [x] Add a reader abstraction that can dispatch by extension: `.safetensors` first, then `.gguf`.
- [x] Use the installed `gguf` package from `.venv\Lib\site-packages\gguf`.
- [x] Review `.venv\Lib\site-packages\gguf\scripts\gguf_editor_gui.py` for PySide/PyQt patterns, metadata parsing, and tensor listing behavior.
- [x] Implement GGUF metadata extraction, tensor summaries, dtype counts, architecture hints, and model size reporting.
- [x] Keep GGUF support read-only for now; do not expose editing behavior.
- [x] Add CLI and GUI smoke checks with at least one representative `.gguf` file.

## 8. Research Safetensors Library Integration

- [x] Evaluate the official `safetensors` Python package as a replacement or supplement for the current custom header reader.
- [x] Confirm whether `safe_open` can provide metadata, keys, tensor shapes, and dtypes without loading full tensor payloads or requiring Torch.
- [x] Test `framework="numpy"` and metadata-only/key-only flows to avoid a full Torch dependency.
- If suitable, add `safetensors` to `requirements.txt` and isolate usage behind the reader abstraction.
- [x] If unsuitable, document why the custom header parser remains preferable.

## 9. Caching & Default Libraries

- [x] Add a cache for parsed model summaries to speed up repeated launches.
- [x] Store enough identity data to detect moved, deleted, or changed files, such as canonical path, size, modified time, and format.
- [x] Default settings/cache to a portable app-local data directory with relocation overrides.
- [x] Use a cache index with per-entry files instead of one monolithic cache blob.
- [x] Add a cache for scanned directories to speed up repeated launches.
- [x] Add a `load default libraries on startup` setting backed by the cached directory list.
- [x] Add optional startup pruning for missing files, with a warning before removing stale entries.
- [x] Add a settings action to clear the cache entirely.
- [x] Decide whether cache writes happen immediately after each scan or only after successful batch completion.

## 10. Replace Raw Tab with Explorer Tab

- Expand the current raw tab into an `Explorer` tab inspired by the GGUF editor UI, but read-only.
- Show parsed metadata as searchable key/value rows.
- Show parsed tensors in a sortable/filterable table with name, shape, dtype, component bucket, and parameter count.
- Show info regarding embedded "checkpoint" tensors (vae/encoder/decoder/lora/etc), and ability to extract them
- Support extracting individual useful fields such as jinja templates, training data, etc
- Support `.safetensors` and `.gguf` through the shared reader abstraction.
- Keep raw text/debug output available as a secondary panel.

## 11. Add Checkpoint and `.pt`/`.pth` Support

- [x] Research safe metadata-only handling for PyTorch checkpoint formats.
- [x] Treat pickle-based formats as unsafe by default; require explicit opt-in before loading.
- Prefer lightweight inspection paths that avoid importing Torch unless necessary.
- [x] Add clear warnings in CLI and GUI when a format may execute pickle deserialization.
- Add extension dispatch for `.ckpt`, `.pt`, and `.pth` only after the safety model is explicit.

## 12. Refactor Overloaded Structures

- Use graphify god-node results to split overloaded modules and classes.
- Consider extracting reader modules, architecture detection modules, modelinfo dumping, and GUI widgets into separate files.
- Prioritize reducing `MainWindow`, `inspect_file()`, `generate_modelinfo_dump()`, and architecture detection helper sprawl.
- Add tests or smoke fixtures before large refactors so behavior stays stable.
- After code changes, run `graphify update .` and review the updated god-node/community report.
