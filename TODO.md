# TODO: Active Product Roadmap

This is a prioritized plan, not a list of release gates. Completed work is in
`DONE.md`; rejected or superseded proposals are in `REJECT.md`.

## Pre-release checklist

Completed items are recorded in `DONE.md`; only open verification is tracked in
the follow-up list below.

- [x] **1. Settings** — resizable and remembers its size, clamped to the current
  screen; the release default remains 900x640.
- [x] **2. Output paths** — GUI save/output dialogs default to
  `~/.local/ModelInspector` via `app_paths.ensure_output_dir()` (override
  `SMI_OUTPUT_DIR`). Existing `.model-inspector` settings/cache stay in place to
  avoid a destructive migration, and `--settings <path>` / `-s <path>` selects
  an explicit settings file for both CLI and GUI. Modelinfo dumps intentionally
  remain beside the source model and are not relocated by this change.
- [x] **3. Startup argument** — the GUI accepts an optional file or folder and
  queues a safe scan after the window is ready; `--help` exits before any Qt
  application is created.
- [x] **4. Packaging and CI** — setuptools builds a working top-level wheel with
  `modelinspector` / `modelinspector-gui` console scripts and packaged, resolved
  assets; the Windows GitHub Actions workflow builds the wheel and executable
  with clean-install/package validation and timeouts.

### Remaining pre-release verification

- [ ] Rerun `.github/workflows/build.yml` remotely after the pending CI fixes.
  The first remote run (`35006721326`) had six passing wheel jobs (all Windows
  and macOS), while all three Ubuntu wheel jobs failed importing PyQt6 without
  `libEGL.so.1`. The Windows PyInstaller build passed, but its frozen `--help`
  smoke incorrectly required the intentional help dialog to exit. Both fixes
  are pending rerun; this is not a green remote-validation result.
- [ ] Manually launch and visually inspect the packaged windowed executable.
  The source GUI was visually audited (commit abd1ed4), but packaged-exe QA is
  limited to a headless offscreen startup (process alive ~10s), not visual QA.

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

- Keep target-specific context-menu View Raw behavior and Raw label refinement
  under review; the Data selection column is now a locked first/always-visible
  column, so selection-column pinning is no longer an open question.
- Implement host-side extraction only for genuinely supported embedded tensors;
  Explorer currently emits host-handled requests only.
- Consider safe text/template extraction, template validation and
  supported-kwargs reporting, and a selected-model metadata re-scan that
  preserves cached-first behavior.

### Advanced Viewer refinements — non-release

- Add only evidence-backed architecture, sampling, RoPE, MTP, sidecar, and
  template facts that are not already available through the accepted viewer.
- Consider comparison projections across common contexts and quantizations, and
  complete runtime copy details only when path/source semantics remain exact.

### CLI, packaging, and developer maintenance

- Keep legacy `-cli` executable passthrough optional and deferred; it is
  distinct from the GUI positional startup target in the pre-release checklist.
- Wheel release metadata and artifact validation are implemented and validated
  locally; a remote GitHub Actions run and release upload remain optional
  follow-on work.
- Treat publishing and GitHub-release upload as optional follow-on work, not a
  prerequisite for the initial artifact-validation workflow.
- Run a full Graphify rebuild and verify frontend/backend nodes and edges after
  the repaired ignore ordering; use incremental updates after later structure
  changes.
