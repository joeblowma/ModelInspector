# DONE: Completed Work

This file records implemented foundations and explicit product decisions. A
completed foundation does not imply that every refinement in `TODO.md` is done.

## 2026-09-21 — b8c0645 follow-up fixes

- [x] Uniform Cards scroll sizing now leaves only viewport whitespace for fixed
  card sets.
- [x] New files are always analyzed; the obsolete `auto_analyze_on_add` option
  and button were removed.
- [x] Unchanged Settings closes without reapplying work, while changed Data
  settings refresh only the affected slices and report progress.
- [x] Raw `.raw` metadata is unframed; readable-content extensions are handled,
  optional extra JSON remains governed by the existing option, and bounded
  previews are stored and reused by Inspect without replacing the model list.
- [x] Advanced Inspect preserves the model list, and QwenImage2.1/VAE plus LTX
  video-VAE architecture coverage was added.

### Final validation and boundary fixes

- [x] The canonical run at `2026-09-21T10:57:10.5414636-06:00` passed
  **466 tests, with 4 skipped, in 172.61 seconds** (exit 0):
  `$env:PYTHONPATH='src';
  $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests`. Log:
  `R:\Temp\opencode\modelinspector-metadata-full-20260921.log`.
- [x] Focused metadata coverage passed 12 tests. The real-header Qwen smokes
  passed in human-readable and JSON modes: the generic Qwen Image2.1 false
  positive is eliminated by the diffusion guard; unsupported diffusion projects
  a null domain and empty capabilities, without claiming image-domain or
  inference support. Qwen35 prompt enhancers remain LLM with thinking/tools.
- [x] The header-loader root cause was the live-file cache fallback scanning
  `data/*.json` after an exact-key miss (measured full call 5.732s versus a
  4-second deadline). Live files now read their header directly; missing-file
  cache fallback remains, with regression coverage proving live loads do not
  scan the full-data cache.
- [x] Historical pre-fix runs recorded 462 passed/4 skipped/1 failed at the
  header-loader path and a separate 463 passed/4 skipped run; those are no
  longer current blockers.
- [ ] Packaged visual QA, the existing strict pylint blocker, hosted
  build/tagged-release validation, and the full Graphify refresh remain open
  in `TODO.md`.
- [ ] Mypy is not a configured clean gate: the first UI pass had 187 errors
  without a baseline, and the targeted metadata pass had four import-resolution
  errors (`back.capability_evidence`, `model_cache`, `model_readers`,
  `.explorer_data`).

## 2026-09-20 — Review gates and final regression pass

### Completed implementation and review fixes

- [x] Gate 1: Advanced Viewer exposes full non-tensor values while retaining
  bounded compact tensor presentation.
- [x] Gate 2: supported loaded-model Inspect paths remain read-only and bypass
  destructive file addition or unnecessary reanalysis.
- [x] Explorer metadata recovers a locatable source path and presents full
  long/deep safetensors and GGUF arrays in the detail pane from headers only,
  while retaining the bounded compact table.
- [x] Gate 3: the single `Model: <path>` label uses middle elision and supports
  copying the file or folder path.
- [x] Gate 4: Open theme presentation uses theme rules rather than hardcoded ID
  colors.
- [x] The implementations were independently reviewed; the pylint `E` issue
  and all three post-baseline `C` findings were corrected.

### Validation and unresolved gate

- [x] Integrated suite: 448 passed, 4 skipped, compared with the 442 passed,
  4 skipped baseline. Targeted regressions in the existing Explorer, card,
  Advanced Viewer, and live-theme test files passed.
- [x] Pyright reached 0 errors after the initial 38-error result; `actionlint`
  passes.
- [ ] Gate 5 — **BLOCKED**, not a pass: strict pylint's independent final log
  records 486 findings (`C237`, `R158`, `W91`, `E0`) at 9.58, below the
  pre-existing strict 10 threshold. The baseline was 494 (`C241`, `R158`,
  `W94`, `E1`); remaining findings are pre-existing `C`/`R`/`W` debt. No
  rejected behavior is claimed or accepted by this lint status.
- [x] Gates 1-4 have headless evidence only; this does not claim manual
  real-world visual or behavioral QA.

## 2026-09-18 — Near-release bug bash

### Completed fixes and focused coverage

- [x] Advanced metadata actions provide bounded UI Inspect plus full-source
  Save/Extract where supported, with filename/full-path labels and an Advanced
  card tooltip; Inspect preserves the model list in replace mode.
- [x] Theme changes refresh existing cards and style `QToolButton` controls;
  Settings visibility controls are right-aligned.
- [x] Rescan Selected evicts the selected model, full, sidecar, and raw-cache
  artifacts while guarding active cache loads and other running operations.
- [x] Actual PTQ142/PTQ143 mappings are corrected, with real-example,
  header-only CLI smoke coverage for human-readable and JSON output.
- [x] Focused regression contracts cover PTQ precision, selected-model rescan,
  and release workflow/artifact wiring.

### Local validation

- [x] Full suite: 441 passed, 4 skipped before the final packaging/typed-attr
  corrections; affected final tests: 25 passed after those corrections.
- [x] Rebuilt wheel and sdist, isolated roundtrip, clean installed-wheel CLI/
  GUI help/assets/tiny-model/modelinfo smokes, source bounded GUI smoke, and
  source/wheel/sdist version `1.0.0` agreement all passed.
- [x] Actual PTQ header-only CLI smokes passed in human-readable and JSON modes.
- [ ] Hosted GitHub artifact/release validation and packaged visual/render QA
  remain pending; `actionlint` was unavailable locally.

## 2026-09-15 — Integration review and release hardening

Integration review of the release-readiness diff with targeted defect fixes,
plus the packaging/reporting milestone and a full-suite/type baseline.

### Cache location separation and safety

- [x] `--cache` selects the model cache only (`SMI_MODEL_CACHE_DIR`:
  `index.json`, `entries/`, `data/`), while `--cachedir` relocates the cache
  root (`SMI_CACHE_DIR`: the inspection cache plus sidecars, raw dumps, and
  directory scans). `app_paths.model_cache_dir()` falls back to the root, so
  an existing cache is never orphaned by a model-cache override.
- [x] The Settings cache-location control remembers a most-recently-used
  history and refuses to switch live while a scan/cache worker is running: it
  keeps the dialog open with a "Cache busy" warning instead of silently
  dropping the selection.
- [x] Clear Cache removes both the model cache and the cache root.

### Evidence-aware labels and conservative facts

- [x] Vision-language models classify as `VLM` and other-modality language
  models as `MLM`. Legacy `MLLM`/`MMLLLM`/`MMLM` aliases migrate evidence-aware
  (audio-multimodal facts map to `MLM`, not `VLM`), and a vision+audio model
  keeps its vision component instead of degrading to a checkpoint/backbone.
- [x] The estimator no longer fabricates `Tool Use`/`Thinking` capabilities
  from raw substring metadata; only evidence-backed capability facts surface.
- [x] GGUF block-rate quantization (Q4_K=4.5, Q5_K=5.5, ...) and complete
  inspected tensor byte counts drive the weight estimate, with mixed-quant and
  inspected-storage assumptions labelled.

### Explorer metadata and sort invariants

- [x] Explorer embedded metadata is bounded and read-only. Inspect shows the
  decoded text (real template newlines), Save writes a readable text/JSON
  artifact, and Extract writes exact source JSON bytes only for locatable
  safetensors/GGUF metadata; tensor payloads are never read. Raw extraction is
  unavailable for other formats or when the source file is missing.
- [x] Batch table inserts no longer re-sync card order per row; sort state is
  restored once per batch, and full-path toggles preserve the active sort.

### Reporting/packaging milestone

- [x] `modelinfo_diagnostics` projects header-only diagnostics into text and
  JSON `.modelinfo` output, with credential-key redaction that does not
  over-redact tokenizer metadata (`tokenizer.*`, `*_token_id`, `num_tokens`).
- [x] `reporting` forwards an already-inspected result and header into
  modelinfo writers, avoiding a duplicate header read on the dump path.
- [x] `pyproject.toml` declares Python 3.12-3.14 classifiers and the
  `assets`/`assets.themes` packages; `.github/workflows/build.yml` builds a
  universal wheel across a 3x3 OS/Python matrix plus the Windows executable.

### Validation (2026-09-15)

- [x] Full isolated pytest: 417 passed, 4 skipped (`PYTHONPATH=src`,
  `QT_QPA_PLATFORM=offscreen`, isolated SMI data/cache paths).
- [x] Pyright on `src`: 38 errors, 0 warnings — the existing dynamic-layout
  (`advanced_viewer*`) and optional-member (`filter_widgets`) baseline; no new
  cache-location diagnostics.
- [x] Headless offscreen source-GUI startup smoke (process alive ~5s; only the
  local PyQt font-directory warning on stderr); not visual QA.
- [x] Module ceiling audit: no source or test module exceeds 500 lines.

### Remote CI validation

- [x] Remote build run `35007857714` at
  `e3c5f2e23c50bed6dff51a37d722c437b9a403cb` completed successfully: all nine
  wheel jobs (Windows, macOS, and Ubuntu on Python 3.12-3.14) and the Windows
  PyInstaller job passed. This supersedes the initial `35006721326` Linux EGL
  and frozen-help-smoke failures.
- [x] The frozen `--help` smoke verifies that the onefile child process starts
  and remains alive before CI deliberately terminates only that launched process
  tree. It proves bounded process lifetime, not visual or render correctness.

## 2026-09-14 — Release-readiness bugbash

User-facing bug fixes and pre-release packaging from the day's bugbash. This
milestone records what was fixed and validated that day; it is not a guarantee
that the whole project is release-complete.

### GUI and Data fixes

- [x] Data-row context-menu `View Raw` respects the auto-load Raw setting and no
  longer double-loads a different model: it routes through the RAW dropdown and
  suppresses the refresh's own load.
- [x] Cache loading reads persisted summaries directly instead of recomputing an
  option-derived key, fixing an `allow_filename_alias_detection` cache-key
  mismatch that could miss valid persisted summaries.
- [x] Async cache load delivers bounded batches with backpressure, is
  cancel/close safe, and preserves existing filters and selection for both
  historic and refresh entries.
- [x] Settings close no longer rebuilds every loaded card, removing the
  multi-second freeze; only the changed projections are refreshed.
- [x] The Data selection column is always the first, visible column with no
  hide/reorder controls, and only its checkbox cells are centered. Canonical
  labels and default widths now live in `front/data_columns.py`; hidden columns
  retain their last valid width across smart masks and reloads.
- [x] Quantization keeps real metadata labels and only infers `f32`/`f16`/`bf16`
  for a uniform standard float dtype; mixed or unknown dtypes fall back to `-`.

### Pre-release packaging and startup

- [x] Settings is resizable and remembers its size, clamped to the current
  screen; the default remains 900x640.
- [x] Save/output dialogs default to `~/.local/share/ModelInspector` via
  `ensure_output_dir()` (`SMI_OUTPUT_DIR` override). The legacy
  `.model-inspector` settings/cache stay in place to avoid a destructive
  migration, and `--settings`/`-s` selects an explicit settings file for the CLI
  and GUI. Modelinfo dumps intentionally remain beside the source model.
- [x] The GUI accepts optional file/folder startup targets, queued safely after
  the window is shown; `--help` exits before Qt starts.
- [x] Setuptools flat-layout wheel with `modelinspector`/`modelinspector-gui`
  entry points and packaged assets that `app_paths` resolves in an installed
  layout; `pyproject.toml` declares the setuptools build backend.
- [x] `.github/workflows/build.yml` builds the wheel and a PyInstaller executable
  on Windows, installs the wheel into a clean venv, validates CLI/GUI help,
  assets, and a tiny safetensors inspection, and validates executable startup
  with timeouts so Qt cannot hang CI.

### Validation (2026-09-14)

- [x] Full local pytest: 378 passed, 4 skipped.
- [x] Wheel built locally and clean-installed: `--help`, imports, packaged
  assets, and a tiny safetensors CLI inspection all passed.
- [x] Windows PyInstaller 6.22.2 build passed; the windowed executable's
  `--help` exited 0 and a bare offscreen startup stayed alive about 10 seconds.
- [x] Manual visual QA of the packaged window was not performed (headless
  offscreen startup only).
- [ ] GitHub Actions was not run remotely (nothing pushed).
- [x] Pyright on all 21 changed production modules: 0 errors, 0 warnings.
- [x] Typing-targeted rerun (`test_startup_arguments.py`,
  `test_file_operations.py`): 21 passed, 1 skipped.

The 4 skips are the unavailable symlink fixtures on the temp drive.

## 2026-09-13 — Completed sidequests

### Inspection and metadata enrichment

Implemented and integrated; validation is complete:

- [x] Architecture coverage: SeedVR2, SANA Video, RCAN, Anima, and Krea 2 key
  signatures; explicit Mage Flow / Ideogram 4 trainer metadata; narrower Krea
  merge-recipe false positives; conservative ZImage handling.
- [x] GGUF same-parent bounded companion fallback for `config.json`,
  `tokenizer_config.json`, and `processor_config.json`, plus
  `chat_template.jinja` and `chat_template.json` only — ambiguous arbitrarily
  named templates are ignored.
- [x] Think/Tool structural evidence split into strong vs weak; the shared
  `capability_evidence` projection filters weak evidence out of the GUI,
  reports, and the estimator.
- [x] Conservative processor-backed VLM and explicit audio/omni MMLM detection
  with no mmproj filename guessing; GGUF reliable alias KV with labelled
  vision/MLA/asymmetric heuristics and the `estimator_metadata` helper.

Validation summary — Initial full run: 311 passed, 4 skipped, 4 failed. All
four failures were corrected; affected-module rerun: 34 passed. Full suite was
not rerun after those fixes:

- [x] Original full suite: 319 tests — 311 passed, 4 skipped, 4 failed. All four
  failures were stale assertions, since fixed: the current 900x640
  settings-dialog default, 30-row overflow fixtures, and the generated spec
  accepting the bundled directory; plus one new cache-sync-close regression
  test.
- [x] Final affected-module rerun: 34 passed. Earlier changed GUI/file-operation
  group: 45 passed.
- [x] Header-only real CLI smoke passed for SeedVR2 and EXAONE files, both
  human-readable and `--json` output.
- [x] Headless actual `py src/gui.py` startup smoke passed (no human visual
  inspection).
- [x] Lifecycle module `pyright` reports 0 errors.
- [x] The 4 skips are symlink fixtures unavailable on the temp drive.

### GUI startup, feedback, and file operations

- [x] Native splash painted from the existing asset before `MainWindow`
  construction; startup cache report computed once (not fully async); unknown
  summary caption/value hidden while retaining zero/False; all six selected
  actions give feedback; threaded modal move/dump with no-clobber failures
  retained and cooperative cancel between files. Copy Files remains clipboard
  file URLs — no actual disk copy.

## 2026-09-07 — Cache, Settings, Themes, and Smart Columns

### Cache actions and verification

- [x] Move `Load Cache`, `Load Cache All`, and `Load Cache Archived` from
  Settings to the main-window Open menu. Actions are shown only for a matching
  cache population and enabled only when the current model view is empty.
- [x] Define cache actions exactly: `Load Cache` loads active summaries only;
  `Load Cache All` loads active and Historic summaries; `Load Cache Archived`
  loads Historic summaries only. Loading Historic summaries never reads or
  inspects unavailable model files.
- [x] Refresh Total / Active / Historic cache counts immediately after Clear
  Cache, and provide an explicit `Verify Cached File Paths` control that is
  disabled when the cache is empty.
- [x] Surface verification progress and its concise outcome. Verification
  derives current classifications from filesystem identity (including shard and
  sidecar identity): missing entries are Historic and retained for viewing;
  changed or legacy active entries are scheduled for background refresh without
  inspecting missing Historic entries.
- [x] Product decision: Historic classification remains dynamically derived
  from verified filesystem identity. No separately persisted archive index is
  needed because it risks staleness; cached summaries remain preserved and
  viewable without their source files.

### Settings and themes

- [x] Remove the obsolete `Load default libraries on startup` setting and its
  dead startup-cache sorting path now that cache loading has explicit actions.
- [x] Place the compact current-theme dropdown in the General tab's
  bottom-right cell at roughly one third of the column width.
- [x] Export bundled themes to the user theme directory, enumerate user themes,
  and document the editable theme schema in `settings.jsonc`.
- [x] Show a user-facing error for a malformed requested external theme while
  retaining the validated default fallback.
- [x] Add a dedicated Theme tab with live editing and `Save`, `Save As`, and
  `Reset to Defaults` actions.
- [x] Load the read-only neutral default from the replaceable bundled
  `default.jsonc` asset. The New Theme action creates uniquely numbered,
  writable themes from that asset rather than from the selected theme.
- [x] Apply editable theme roles live, including muted status text, cached
  inline styles, and a distinct inactive-tab hover color with old-theme
  fallback. Friendly Theme-editor labels identify accent use by buttons,
  badges, inactive tabs, and headers.
- [x] Require explicit confirmation before Theme `Reset to Defaults`, then
  clear the user theme directory and re-extract bundled themes.
- [x] Complete the tooltip/content audit across existing controls, not only
  Explorer and settings additions.

### Data-table smart column groups

- [x] Add pinned `LLM`, `Diffusion`, and `Adapter` controls to the right of
  Select All and Show Full Path in the Data toolbar.
- [x] Keep groups runtime-only and initially off; automatically enable a group
  when loaded results genuinely use its family columns, while preserving a
  manual toggle for the rest of the session. Clear All resets only groups that
  were auto-enabled.
- [x] Define smart-column precedence: a user's manual group choice overrides
  later automatic enabling for that session, while persisted Settings > Data
  per-column visibility is the baseline and always wins. A checked group shows
  only baseline-visible columns; an unchecked group masks every column it owns.

## 2026-09-04 — File Readers, Model Formats, Sharding, and Sidecars

**Completed:** Added bounded metadata-only ONNX inspection; explicit metadata-safe
checkpoint handling that never deserializes pickle payloads; and a shared reader
registry abstraction. GGUF and safetensors shard sets retain aggregate and
original-order data, shard IDs, and byte sizes. Explorer and Advanced Viewer
support ordering, shard grouping, and size tooltips. Six sidecar roles are
discovered as separate records with compact primary identities and runtime paths.

### Additional model formats

- [x] Add bounded metadata-only `.onnx` inspection.
- [x] Add `.ckpt`, `.pt`, and `.pth` dispatch behind an explicit metadata-safety
  model; never deserialize pickle payloads.
- [x] Keep optional third-party reader libraries behind the shared reader
  abstraction when they improve safety or coverage.

### Sharded models and original ordering

- [x] Support sharded `.gguf` and `.safetensors` sets such as
  `*00001-of-00004*`.
- [x] Preserve original tensor/layer/block order in addition to the current sorted
  presentation.
- [x] Record the shard index for every tensor or block (`shard_id = 0` for
  non-sharded models).
- [x] In Explorer and Advanced Viewer, allow sorted versus original-order display
  and visually group original-order rows by shard.
- [x] Calculate tensor or block byte size for raw output and tooltips in Advanced
  Viewer.

### Sidecar discovery and association

- [x] Detect `mmproj`, `dflash`, `dspark`, `eagle`, `draft`, and MTP sidecars beside
  the primary model.
- [x] Store full sidecar inspection records separately while keeping enough
  identity metadata on the primary model to detect changes quickly.
- [x] Tag the primary model with discovered sidecar roles and include associated
  paths in copied runtime configurations.

## Discovery, Filtering, Progress, and Concurrency

- [x] Add separate file-format and architecture/type filters.
- [x] Sort filter values consistently and align Cards/Raw ordering with the
  Data table.
- [x] Report files, bytes, directory progress, cancellation, and partial
  results during scans.
- [x] Add bounded parallel analysis for independent files with per-file error
  reporting and configurable thread count.

## Cache Foundations and Integrity

- [x] Persist inspection summaries, raw/model data, directory scans, canonical
  identity, size, modification time, and format in an app-local cache.
- [x] Retain missing-file summaries rather than pruning them.
- [x] Add `Load Cache`, `Load Cache All`, and `Load Cache Archived` controls with
  conditional availability.
- [x] Display Total, Active, and Historic counts beside cache controls.
- [x] Classify missing files as Historic without inspecting them and keep their
  cached summaries viewable.
- [x] Detect changed or legacy active entries and queue background refresh while
  leaving unchanged active entries on the cached fast path.
- [x] Repair the cache identity handoff so unchanged active entries do not
  spuriously schedule analysis.
- [x] Retain an explicit confirmed Clear Cache action.

## Settings and Themes

- [x] Replace primary INI persistence with readable, commented
  `settings.jsonc` defaults.
- [x] Migrate legacy INI settings on first JSONC launch.
- [x] Use atomic settings replacement and back up malformed settings before
  falling back to defaults.
- [x] Externalize bundled Catppuccin, Cursor, GitHub, and Gruvbox theme data
  under `assets/themes/`.
- [x] Validate themes and keep a safe built-in fallback when loading fails.
- [x] Apply persisted themes at startup and apply settings changes immediately.

## Data Table Customization

- [x] Add settings for Data-column visibility, stable-key ordering, and width.
- [x] Add checkbox rows and drag handles for column reordering.
- [x] Persist table header moves and resized widths across settings reloads.
- [x] Fix the native drag/drop ownership crash by keeping durable column state
  outside Qt-owned cell widgets, deferring post-drop reconciliation, and
  rebuilding controls safely after each move.
- [x] Add deleted-widget and repeated queued-reorder regression coverage.
- [x] Preserve metadata-backed quantization labels in the Data viewer; otherwise
  show meaningful dtype/precision or a clear unknown fallback without labeling
  uniform unquantized files as quantized.

## Explorer and Raw Dump

- [x] Keep Explorer and Raw as coexisting views, with searchable metadata and
  tensor descriptors, a bounded header-only tensor-root summary, lazy
  host-request loading, and window-bounded scrolling filter controls.
- [x] Detect header-derived VAE, LoRA, text-encoder, and template candidates
  and expose explicit host-handled inspect/export/extract requests without
  loading tensor payloads.

## Advanced Viewer

- [x] Add a topmost modal Advanced Viewer dialog for the selected model.
- [x] Add architecture/layer/context/RoPE/MTP/expert fact extraction with safe
  handling for missing metadata.
- [x] Add domain tags and Tool Use, Thinking, and Vision capability badges.
- [x] Add interactive weight/context/KV-cache VRAM and RAM estimation.
- [x] Add plain-text configuration generation and clipboard copy support.
- [x] Fix Advanced Viewer Cards bottom spacing, long-card width/wrapping, and
  minimum short-card sizing, with focused geometry regression coverage. The
  accepted Advanced Viewer is the settled presentation direction.
- [x] Populate the accepted viewer with conservative facts, tensor descriptors,
  shard/order information, companion discovery, and evidence-conservative
  capability/domain badges.

## 2026-09-03 — Integrated Card and Advanced Viewer Pass

- [x] Consolidate the main Cards tab into one compact, viewport-bounded,
  top-aligned card mode; clicking a card body opens that exact model in
  Advanced Viewer.
- [x] Keep card checkboxes as the only card-selection control and add an exact
  model Advanced Viewer action to the Data-row context menu.
- [x] Remove the ambiguous standalone Advanced Viewer button and route openings
  through deterministic filepath-based helpers.
- [x] Re-layout Advanced Viewer into peer Overview, Card Details, Metadata,
  Tensors, and Embedded Content tabs while retaining Explorer's read-only
  request signals and detailed-card field preferences.
- [x] Scale conservative KV-cache fallback projections by the selected KV-cache
  bit precision from their 16-bit baseline, with estimator and dialog coverage.
- [x] Verify the integrated pass with focused UI/backend coverage, clean
  Pyright, and the full 94-test pytest suite.

## Developer tooling

- [x] Repair `.graphifyignore` ordering so frontend and backend source files are
  eligible for graph extraction. A full graph rebuild remains unverified and is
  deferred in `TODO.md`.

## 2026-08-24 — Immediate UI Glitches and Performance

- [x] Fix bottom-item Data-column reordering so the moved row remains visible,
  while retaining the earlier deleted-widget crash fix.
- [x] Remove the persistent blank row from the bottom of the Data-column
  settings scroller.
- [x] Improve Settings close performance for large loaded libraries by moving
  expensive work out of the dialog close path.
- [x] Load bundled themes correctly in packaged executables through extracted
  application assets.
- [x] Keep the Settings default at 900x640 with screen clamping; this fixed-size
  behavior was later superseded by the resizable, remembered-size work recorded
  in the 2026-09-14 milestone.
- [x] Keep the Advanced Viewer above its main window without forcing it above
  unrelated applications.
- [x] Propagate multimodal model classification as MLLM, including vision-tower
  detection, to cards and lists.
- [x] Give the Advanced Viewer ownership of Explorer search while keeping Raw
  as a single-purpose main tab.
- [x] Show Advanced Viewer’s current output information at the top of Raw for
  convenient copying.
- [x] Remove the unnecessary “top key prefixes” from the Raw view.

## Project Structure and Architecture

- [x] Move executable sources under `src/` and keep `src/gui.py` and
  `src/inspect_model.py` as thin compatibility/bootstrap wrappers.
- [x] Split GUI workflows into focused `src/front/` widgets/controllers and
  inspection logic into focused `src/back/` modules.
- [x] Keep bundled icons, splash assets, and themes under `assets/` and resolve
  them in development and packaged execution.
- [x] Update build/spec entry points for the current source layout.
- [x] Establish a hard 500-line source-module ceiling and verify the current
  `src/front` and `src/back` modules against it.
- [x] Add regression coverage for scan lifecycle, projection, inspection
  summaries, background tasks, integrated behavior, settings, themes, cache,
  Explorer, and Advanced Viewer components.

## Readers, Inspection, and Reporting

- [x] Add a shared extension reader abstraction for `.safetensors` and `.gguf`.
- [x] Implement read-only GGUF metadata, tensor descriptors, dtype summaries,
  architecture hints, and size reporting.
- [x] Inspect safetensors headers without loading tensor payloads.
- [x] Research pickle-backed checkpoint risks and require explicit opt-in for
  any future unsafe deserialization. Actual additional-format support remains
  in `TODO.md`.
- [x] Add stable, pretty-printed JSON `.modelinfo` output to CLI and GUI flows.
- [x] Preserve both user-provided and resolved file paths and keep default dump
  output beside the user-provided path.
- [x] Give FLUX LoRA header detection precedence over broad Qwen Edit heuristics
  for standard rank-64 adapters with 19 dual and 38 single blocks plus generic
  `add_k_proj`/`add_q_proj` markers; add header-only regression coverage without
  loading model payloads.
