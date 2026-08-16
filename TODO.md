# TODO: Active Product Roadmap

This file contains only outstanding or partially completed work. Completed,
rejected, and superseded items belong in `DONE.md`.

The legacy Raw Dump view remains useful and should be retained alongside the
read-only Explorer. The Explorer is an expansion of model inspection, not a
replacement for access to the raw generated dump.

## 0. Immediate UI Glitches and Performance

- Fix Data-column ordering when the bottom item is moved: the row currently
  disappears even though the earlier deleted-widget crash is fixed.
- Remove the persistent blank row/line at the bottom of the Data-column
  settings scroller.
- Profile closing Settings with a large loaded library (observed 3-5 seconds
  with roughly 600 models). Move expensive table reprojection, settings writes,
  cache verification, or filter rebuilding out of the dialog close path and
  avoid making the main window appear hung.

## 1. File Readers, Model Formats, Sharding, and Sidecars

### Additional model formats

- Add `.onnx` metadata inspection.
- Add `.ckpt`, `.pt`, and `.pth` dispatch only behind an explicit safety model.
  Prefer metadata-only paths and never silently enable pickle deserialization.
- Keep optional third-party reader libraries behind the shared reader
  abstraction and add them only when they improve safety or coverage.

### Sharded models and original ordering

- Support sharded `.gguf` and `.safetensors` sets such as
  `*00001-of-00004*`.
- Preserve original tensor/layer/block order in addition to the current sorted
  presentation.
- Record the shard index for every tensor or block (`shard_id = 0` for
  non-sharded models).
- In Explorer and Advanced Viewer, allow sorted versus original-order display
  and visually group original-order rows by shard.

### Sidecar discovery and association

- Detect `mmproj`, `dflash`, `eagle`, `draft`, and MTP sidecars beside the
  primary model.
- Store full sidecar inspection records separately while keeping enough
  identity metadata on the primary model to detect changes quickly.
- Tag the primary model with discovered sidecar roles and include associated
  paths in copied runtime configurations.

## 2. Library Linking and Path Resolution

- Add symbolic-link creation alongside existing move-file actions.
- Support editable destination templates such as
  `.\models\<type>\<model name>\<file>`.
- Provide presets for ComfyUI, LM Studio, Fooocus, and A1111 layouts.
- Canonicalize source and destination paths so symlinks, junctions, hardlinks,
  and original paths do not create duplicate model records.
- Show resolved source and planned destination paths before bulk operations.
- Detect existing destinations and offer Skip, Overwrite, or Open Location.

## 3. Cache Follow-ups

- Move `Load Cache`, `Load Cache All`, and `Load Cache Archived` out of Settings
  into a menu attached to the main-window Open button.
- Only show cache-load menu actions when their corresponding cache population
  makes them meaningful, and enable loading only when the current model view is
  empty (normally startup or immediately after Clear).
- Define the actions consistently: active-only, active plus Historic, and
  Historic-only; loading Historic summaries must never inspect missing files.
- Refresh Total / Active / Historic counts immediately after Clear Cache rather
  than requiring Settings to be closed and reopened.
- Add an explicit `Verify Cached File Paths` action beside the cache controls;
  disable it when the cache is empty.
- Decide whether the current dynamically derived Historic classification needs
  a separately persisted archive index. Preserve cached summaries either way.
- Surface verification progress and a concise result summary when a manual
  verification archives missing entries or schedules changed entries.

## 4. Settings, Themes, and General UI Refinement

- Remove the obsolete `Load default libraries on startup` setting and its
  startup-cache path now that cache loading has explicit actions.
- Move the current theme dropdown to the General tab, in the bottom-right cell,
  using roughly one third of that column's width.
- Export bundled themes into a user theme directory, enumerate user themes,
  and document the editable theme schema in `settings.jsonc`.
- Show a user-facing popup when a requested external theme is malformed; retain
  the current validated default fallback.
- Later add a dedicated Theme tab with live color editing applied to the real
  window or a representative preview, plus `Save`, `Save As`, and
  `Reset to Defaults` actions.
- Make Theme `Reset to Defaults` require an explicit warning/confirmation, then
  clear the user theme directory and re-extract the bundled themes.
- Perform a complete tooltip/content audit across existing controls, not only
  controls added during the Explorer/settings work.

### Data table smart column groups

- Add pinned `LLM`, `Diffusion`, and `Adapter` checkboxes on the right of the
  same toolbar row as Select All and Show Full Path.
- Each checkbox controls the columns used only by that model family. Smart
  groups default off, automatically enable when loaded data needs their
  columns, and remain user-toggleable so those columns can be hidden entirely.
- Keep smart-group behavior distinct from the persisted per-column visibility
  settings and define which preference wins after an automatic enable.

## 5. Explorer and Raw Dump Refinement

- Keep both Explorer and Raw Dump views available in the current shared tab.
- In Raw model labels, hide the file extension unless Show Full Path is enabled.
- Keep the Raw selection-checkbox column permanently visible and pinned on the
  left; remove it from user-configurable column visibility/order.
- Implement safe host-side extraction for genuinely extractable embedded
  tensors such as VAE, encoder/decoder, and LoRA content. The current Explorer
  intentionally exposes header-derived candidates and requests only.
- Support extraction of useful text fields such as Jinja templates and training
  configuration without implying that tensor payloads were loaded.
- Add template type detection, validation, and supported-kwargs reporting.
- Add a selected-model action to force a metadata re-scan while preserving
  cached-first UI behavior.

## 6. Advanced Model Viewer Redesign and Completion

- Revisit the Advanced Viewer layout and interaction model against the supplied
  reference screenshot; treat the current dialog as a functional foundation,
  not the final design.
- Follow the reference's file-inspector information architecture: a persistent
  model path/header, dense use of the available window, and separate Metadata
  and Tensors work areas rather than making summary cards the primary content.
- Keep the at-a-glance facts and memory estimator as a compact header, sidebar,
  or secondary tab supporting the inspector rather than dominating the window.
- Show metadata as typed Key / Type / Value rows and tensors as an equivalently
  dense sortable table. Replace the reference editor's mutating actions with
  read-only actions such as Copy, Inspect, and safe Export/Extract where the
  underlying format actually supports them.
- Retain a topmost/modal relationship with the main window while improving the
  density and hierarchy of model facts.
- Add sorted/original block and layer views, visually grouped by shard.
- Present memory projections as useful comparisons across common context sizes,
  weight quantizations, and KV-cache precisions rather than only a single
  selected estimate.
- Expand the at-a-glance section, when values are available or safely
  inferable, with:
  - architecture, layers, parameter size, and file size;
  - total/active experts;
  - trained/max context, top-p, top-k, and temperature;
  - RoPE type, original context, scale, and multiplier;
  - MTP/speculative-decoding details;
  - embedded-template presence, type, validation, and supported kwargs;
  - associated `mmproj` and draft model facts.
- Refine capability badges so Tool Use, Thinking, and Vision distinguish
  metadata-backed facts from weaker heuristics.
- Generate the full human-readable runtime configuration format, including
  primary model, sidecars, comments, context, sampling, RoPE, and speculative
  decoding arguments. Keep copy icons consistent between Explorer/Raw and the
  Advanced Viewer.

## 7. CLI, Packaging, and CI/CD

- Accept files/folders passed to the packaged executable and queue them after
  the GUI is ready, as if dropped onto the window.
- Add `modelinspector.exe -cli <commands>` pass-through and mirror the behavior
  when launched from Python.
- Finish wheel packaging.
- Add GitHub Actions for supported wheel builds, Windows executable packaging,
  optional publishing, and GitHub releases.

## 8. Developer Tooling and Architecture Graph

- Repair `.graphifyignore` ordering so `src/back/*.py` and `src/front/*.py`
  remain unignored after the broad `src/*` rule; the current incremental graph
  sees root `src/*.py` and tests but omits both application subpackages.
- Run a full Graphify rebuild after fixing the ignore rules, verify current
  frontend/backend nodes and edges are present, and use incremental
  `graphify update .` after later structural changes.
