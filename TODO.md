# TODO: Active Product Roadmap

This is a prioritized plan, not a list of release gates. Completed work is in
`DONE.md`; rejected or superseded proposals are in `REJECT.md`.

## Pre-release checklist

Completed items are recorded in `DONE.md`; only open verification is tracked in
the follow-up list below.

- [x] **1. Settings** — resizable and remembers its size, clamped to the current
  screen; the release default remains 900x640.
- [x] **2. Output paths** — GUI save/output dialogs default to
  `~/.local/share/ModelInspector` via `app_paths.ensure_output_dir()` (override
  `SMI_OUTPUT_DIR`). Existing `.model-inspector` settings/cache stay in place to
  avoid a destructive migration, and `--settings <path>` / `-s <path>` selects
  an explicit settings file for both CLI and GUI. Modelinfo dumps intentionally
  remain beside the source model and are not relocated by this change.
- [x] **3. Startup argument** — the GUI accepts an optional file or folder and
  queues a safe scan after the window is ready; `--help` exits before any Qt
  application is created.
- [x] **4. Packaging and CI foundation** — setuptools builds a working top-level wheel with
  `modelinspector` / `modelinspector-gui` console scripts and packaged, resolved
  assets; the Windows GitHub Actions workflow builds the wheel and executable
  with clean-install/package validation and timeouts.

### Remaining pre-release verification

- [ ] Manually launch and visually inspect the packaged windowed executable.
  The source GUI was visually audited (commit abd1ed4), but packaged-exe visual
  and render QA remains pending; the current frozen-help check is headless.
- [ ] Exercise the packaged build manually with 420+ representative real model
  files. Independent review approved the backend/GUI safety boundary; a live
  420-model `MainWindow` filter run reached one visible result in 38 ms with a
  5.57 ms maximum observed stall. The completed native 1,080-model profile
  verifies bounded event delivery and layout restoration, not packaged visual
  or real-new-scan/move QA. Synthetic coverage cannot close this live-model/
  render QA.

### Review gates

- [x] Gates 1-4 have headless evidence: Advanced shows full non-tensor values;
  Inspect does not destructively add files; a single `Model: <path>` label
  middle-elides and supports copying; and Open uses the active theme rules.
  This records automated/headless evidence only, not a manual real-world QA
  claim.
- [ ] Gate 5 — **BLOCKED**, not a pass: independent strict pylint records 486
  findings (`C237`, `R158`, `W91`, `E0`) at 9.58, below the pre-existing 10
  threshold. The 494-finding baseline (`C241`, `R158`, `W94`, `E1`) had three
  introduced `C` findings, now removed; remaining `C`/`R`/`W` debt is
  pre-existing. No rejected behavior is claimed or accepted by this lint
  status; the recommended follow-up is scoped cleanup to the configured gate.

### Release validation

- [x] Current canonical integration run: **528 passed, 4 skipped in 102.77
  seconds** (exit 0) on system Python 3.14.8. Command:
  `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen'; python -m pytest
  tests --capture=tee-sys`. Log:
  `R:\Temp\opencode\modelinspector-cache-load-canonical-2026-10-04.log`.
  The shared autouse fixture isolates `SMI_CACHE_DIR`, `SMI_MODEL_CACHE_DIR`,
  and legacy `SMI_CACHE_PATH` for every test; this supersedes the prior 527/4
  canonical run.
- [x] Historical pre-isolation integration run: **512 passed, 4 skipped, 6
  failed in 85.37 seconds** (exit 1). Its cache-root environment leakage is
  superseded by the current canonical pass. Log:
  `R:\Temp\opencode\modelinspector-qodo-followup-2026-10-03.log`.
- [x] Canonical suite before the subsequent GGUF fallback fix: 502 passed, 4
  skipped in 56.03 seconds, exit 0. Command: `$env:PYTHONPATH='src';
  $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests`. Log:
  `R:\Temp\opencode\modelinspector-qodo-2026-10-03.log`. The follow-up's
  affected command, `$env:PYTHONPATH='src'; $env:QT_QPA_PLATFORM='offscreen';
  python -m pytest tests/test_model_readers_bounds.py tests/test_ptq_precision.py`,
  passed 16 tests; the full suite was not rerun per validation cadence.
- [x] Prior canonical suite: 484 passed, 4 skipped in 105.54 seconds, exit 0;
  its original milestone evidence remains recorded in `DONE.md`.
- [x] Focused Explorer/metadata/Advanced regression: 55 passed. Real-header
  Qwen smokes passed
  in human-readable and JSON modes; the generic Qwen Image2.1 false positive
  is guarded, unsupported diffusion projects a null domain and empty
  capabilities, and Qwen35 prompt enhancers remain LLM with thinking/tools.
- [ ] Verify the hosted Windows executable workflow end to end with the native
  seven-character SHA artifact naming (the third-party SHA action was removed).
- [ ] Validate the tagged GitHub release end to end: tag/source/wheel version
  agreement and both release asset types.
- [ ] Mypy is not a configured clean gate: the current unbaselined run reports
  211 errors. Do not treat it as a release pass until a scoped baseline exists.

## Deferred product work

### Inspection and metadata enrichment — evidence-gated followups

- Ambiguous Mage Flow vs Qwen files with identical headers remain structural
  Qwen; explicit trainer metadata is the only disambiguator, and ambiguous
  arbitrarily named Jinja templates stay excluded.
- No real ZImage LoRA was available, so ZImage coverage is synthetic only.
- Review conservative LLM, VLM, and MLM card-family presentation labels as
  architecture coverage improves.
- Wider runtime-configuration arguments and comparable memory projections
  stay postponed until their metadata inputs are reliable; broader runtime
  coverage remains unreliable. Runtime VRAM/RAM estimates remain heuristics
  (8%/12% activation/allocator overhead, 12% KV fallback), not calibrated
  measurements.
- Move/dump progress has no byte-level progress; per-file progress is
  indeterminate; cancellation between files; the native splash is not a fully
  asynchronous cache load.

### Library linking and paths — non-release

- Defer optional symlink creation, editable destination templates, application
  presets, and canonical-path duplicate handling.
- Any future linking workflow must be non-destructive: preview resolved source
  and destination paths; collisions must not overwrite, delete, or move source
  or target files as a side effect. Valid symlinks are not rejected.

### Explorer and Raw Dump

- Completed bounded preview, readable-content, exact source extraction, and
  stored-preview reuse work is recorded in `DONE.md`, including stable sorted
  row previews and requested/resolved live-source recovery from cache previews;
  the remaining raw/metadata work is intentionally limited to the items below.
- Implement host-side extraction only for genuinely supported embedded tensors;
  Explorer currently emits host-handled requests only.
- Consider safe text/template extraction, template validation and
  supported-kwargs reporting, and a selected-model metadata re-scan that
  preserves cached-first behavior.

### Test and evidence follow-up

- [ ] Profile residual native cache-load cost and RSS. The 1,080-summary Cards
  geometry correction reduced the usable custom-replay baseline from
  29.77/30.00 s (including 500 ms settle) to 15.71/15.93 s; the earlier ~38 s
  `QApplication.notify` instrumentation result is not a usable baseline. Real
  `CacheLoadWorker` first/repeat projection was 14.644/15.370 s before settle,
  with 378.2/364.0 MB RSS growth and 357.9/286.0 ms maximum heartbeat gaps.
  Do not claim universal responsiveness improvement: the controlled geometry
  flow (160/168 ms versus 291/313 ms) differs, and real-worker first-run stall
  is worse. Only 1,080 selected entries plus index (241,037,326 bytes) were
  read from a 397 MB/2,201-file cache; no SQLite migration or low-RAM design is
  justified by storage I/O alone. Verifier/source-sync were stubbed in that
  native harness, so they remain outside its end-to-end evidence.
- [x] Metadata UI live-file header loading now bypasses full-data cache scans;
  missing-file cache fallback and the capability/domain boundary are covered
  by regression tests. Keep the `test_ui_release_gates.py` catalog current.
- [x] Persisted cache records no longer let stale header-path/completeness flags
  suppress an Advanced Viewer live-header reload after Clear Cache or restart.
  The controller records its local read provenance and selects the first existing
  requested, filepath, or resolved path; regression coverage round-trips three
  models through two windows and verifies full metadata detail.
- [x] Card-surface drag relaying dispatches only exact DragEnter, DragMove, and
  Drop event types. Move accepts URL drags without queueing work; release alone
  queues files or starts folder discovery across the Cards tab, scroll, viewport,
  card container, and main window.

### Advanced Viewer refinements — non-release

- Add only evidence-backed architecture, sampling, RoPE, MTP, sidecar, and
  template facts that are not already available through the accepted viewer.
- Consider comparison projections across common contexts and quantizations, and
  complete runtime copy details only when path/source semantics remain exact.

### CLI, packaging, and developer maintenance

- [x] Checkpoint ZIP central-directory preflight now supports the legacy
  Python 3.12 and current ZIP64 end-record positions without constructing
  `ZipFile` before its 2 MiB bounds check; Python 3.12.15 and 3.14.8 full suites
  each passed 534 tests with 4 skipped. The legacy layout is simulated coverage,
  not a claim for every installed Python 3.12 version.
- [ ] Revalidate the bounded private-`zipfile._EndRecData` compatibility boundary
  on future Python minors and with real SFX/ZIP64 edge archives; Python 3.13 has
  not been validated.
- Keep legacy `-cli` executable passthrough optional and deferred; it is
  distinct from the GUI positional startup target in the pre-release checklist.
- Wheel release metadata and artifact validation are under repair; local,
  hosted, and release-upload validation remain open in the checklist above.
- Treat publishing and GitHub-release upload as optional follow-on work, not a
  prerequisite for the initial artifact-validation workflow.
- Run a full Graphify rebuild and verify frontend/backend nodes and edges after
  the repaired ignore ordering; use incremental updates after later structure
  changes.
- Resolve the remaining baseline strict-pylint `C`/`R`/`W` findings in a scoped
  maintenance follow-up; do not close Gate 5 until an independent final count
  passes the configured threshold.
