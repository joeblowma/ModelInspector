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

### Release validation still open

- [x] Final canonical suite at `2026-09-21T10:57:10.5414636-06:00`: 466
  passed, 4 skipped in 172.61 seconds, exit 0. Command:
  `$env:PYTHONPATH='src';
  $env:QT_QPA_PLATFORM='offscreen'; python -m pytest tests`. Log:
  `R:\Temp\opencode\modelinspector-metadata-full-20260921.log`.
- [x] Focused metadata regression: 12 passed. Real-header Qwen smokes passed
  in human-readable and JSON modes; the generic Qwen Image2.1 false positive
  is guarded, unsupported diffusion projects a null domain and empty
  capabilities, and Qwen35 prompt enhancers remain LLM with thinking/tools.
- [ ] Verify hosted CI Windows executable checks and actual revision-named
  artifacts.
- [ ] Validate the tagged GitHub release: tag/source/wheel version agreement
  and both release asset types.
- [ ] Mypy is not a configured clean gate: the first UI pass reported 187
  errors without a baseline, and the targeted metadata pass reported four
  import-resolution errors (`back.capability_evidence`, `model_cache`,
  `model_readers`, `.explorer_data`).

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
  stored-preview reuse work is recorded in `DONE.md`; the remaining raw/metadata
  work is intentionally limited to the items below.
- Implement host-side extraction only for genuinely supported embedded tensors;
  Explorer currently emits host-handled requests only.
- Consider safe text/template extraction, template validation and
  supported-kwargs reporting, and a selected-model metadata re-scan that
  preserves cached-first behavior.

### Test and evidence follow-up

- [x] Metadata UI live-file header loading now bypasses full-data cache scans;
  missing-file cache fallback and the capability/domain boundary are covered
  by regression tests. Keep the `test_ui_release_gates.py` catalog current.

### Advanced Viewer refinements — non-release

- Add only evidence-backed architecture, sampling, RoPE, MTP, sidecar, and
  template facts that are not already available through the accepted viewer.
- Consider comparison projections across common contexts and quantizations, and
  complete runtime copy details only when path/source semantics remain exact.

### CLI, packaging, and developer maintenance

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
