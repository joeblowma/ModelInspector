# TODO: Active Product Roadmap

This is a prioritized plan, not a list of release gates. Completed work is in
`DONE.md`; rejected or superseded proposals are in `REJECT.md`.

## Pre-release checklist

1. Make Settings resizable and remember its size, clamped to the current screen.
   Start from the current fixed 900x640 default; do not change that default as
   part of planning alone.
2. Make GUI save/output default under a user-home subfolder, with a CLI override.
   Default to `~/.local/ModelInspector`.
   Override with `--cache <path>`.
3. Accept an optional GUI file or folder startup argument and queue a safe scan
   after the window is ready.
4. Add GitHub Actions that produce a Windows executable package and wheels,
   including packaging validation.

## Completed sidequests

### Inspection and metadata enrichment

Implemented and integrated; validation is complete:

- Architecture coverage: SeedVR2, SANA Video, RCAN, Anima, and Krea 2 key
  signatures; explicit Mage Flow / Ideogram 4 trainer metadata; narrower Krea
  merge-recipe false positives; conservative ZImage handling.
- GGUF same-parent bounded companion fallback for `config.json`,
  `tokenizer_config.json`, and `processor_config.json`, plus
  `chat_template.jinja` and `chat_template.json` only — ambiguous arbitrarily
  named templates are ignored.
- Think/Tool structural evidence split into strong vs weak; the shared
  `capability_evidence` projection filters weak evidence out of the GUI,
  reports, and the estimator.
- Conservative processor-backed VLM and explicit audio/omni MMLM detection
  with no mmproj filename guessing; GGUF reliable alias KV with labelled
  vision/MLA/asymmetric heuristics and the `estimator_metadata` helper.

Validation summary — Initial full run: 311 passed, 4 skipped, 4 failed. All
four failures were corrected; affected-module rerun: 34 passed. Full suite was
not rerun after those fixes:

- Original full suite: 319 tests — 311 passed, 4 skipped, 4 failed. All four
  failures were stale assertions, since fixed: the current 900x640
  settings-dialog default, 30-row overflow fixtures, and the generated spec
  accepting the bundled directory; plus one new cache-sync-close regression
  test.
- Final affected-module rerun: 34 passed. Earlier changed GUI/file-operation
  group: 45 passed.
- Header-only real CLI smoke passed for SeedVR2 and EXAONE files, both
  human-readable and `--json` output.
- Headless actual `py src/gui.py` startup smoke passed (no human visual
  inspection).
- Lifecycle module `pyright` reports 0 errors.
- The 4 skips are symlink fixtures unavailable on the temp drive.

### GUI startup, feedback, and file operations

- Native splash painted from the existing asset before `MainWindow`
  construction; startup cache report computed once (not fully async); unknown
  summary caption/value hidden while retaining zero/False; all six selected
  actions give feedback; threaded modal move/dump with no-clobber failures
  retained and cooperative cancel between files. Copy Files remains clipboard
  file URLs — no actual disk copy.

## Deferred product work

### Inspection and metadata enrichment — evidence-gated followups

- Ambiguous Mage Flow vs Qwen files with identical headers remain structural
  Qwen; explicit trainer metadata is the only disambiguator, and ambiguous
  arbitrarily named Jinja templates stay excluded.
- No real ZImage LoRA was available, so ZImage coverage is synthetic only.
- Review conservative LLM, VLM, and MMLM card-family presentation labels as
  architecture coverage improves.
- Wider runtime-configuration arguments and comparable memory projections
  stay postponed until their metadata inputs are reliable; broader runtime
  coverage remains unreliable.
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

- Keep target-specific context-menu View Raw behavior, Raw label refinement, and
  selection-column pinning under review.
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
- Verify wheel release metadata and artifact validation as part of the CI work.
- Treat publishing and GitHub-release upload as optional follow-on work, not a
  prerequisite for the initial artifact-validation workflow.
- Run a full Graphify rebuild and verify frontend/backend nodes and edges after
  the repaired ignore ordering; use incremental updates after later structure
  changes.
