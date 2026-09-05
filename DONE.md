# DONE: Completed, Rejected, and Superseded Work

This file records implemented foundations and explicit product decisions. A
completed foundation does not imply that every refinement in `TODO.md` is done.

## 2026-08-24 — Immediate UI Glitches and Performance

- [x] Fix bottom-item Data-column reordering so the moved row remains visible,
  while retaining the earlier deleted-widget crash fix.
- [x] Remove the persistent blank row from the bottom of the Data-column
  settings scroller.
- [x] Improve Settings close performance for large loaded libraries by moving
  expensive work out of the dialog close path.
- [x] Load bundled themes correctly in packaged executables through extracted
  application assets.
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
- [x] Evaluate the official `safetensors` package for metadata-only use. The
  custom header reader remains the preferred lightweight path; adding the
  dependency merely for parity was rejected.
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

- [x] Add a read-only Explorer with searchable metadata key/value rows.
- [x] Add a sortable/filterable tensor descriptor table with Name, Shape,
  Dtype, Component Bucket, and Parameter Count.
- [x] Detect header-derived VAE, LoRA, text-encoder, and template candidates and
  expose explicit host-handled inspect/export/extract requests.
- [x] Keep the legacy Raw Dump navigator beside Explorer.
- [x] Reject the earlier requirement to replace/remove Raw; retaining both views
  is the accepted product direction.

## Advanced Viewer Foundation

- [x] Add a topmost modal Advanced Viewer dialog for the selected model.
- [x] Add architecture/layer/context/RoPE/MTP/expert fact extraction with safe
  handling for missing metadata.
- [x] Add domain tags and Tool Use, Thinking, and Vision capability badges.
- [x] Add interactive weight/context/KV-cache VRAM and RAM estimation.
- [x] Add plain-text configuration generation and clipboard copy support.
- [x] Fix Advanced Viewer Cards bottom spacing, long-card width/wrapping, and
  minimum short-card sizing, with focused geometry regression coverage. The
  broader Advanced Viewer redesign remains open in `TODO.md`.
- [x] Keep richer layout, shard visualization, sidecar integration, template
  validation, and screenshot-aligned redesign work explicitly open in
  `TODO.md`.

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
