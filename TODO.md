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

## Deferred product work

### Inspection and metadata enrichment

- Extend architecture coverage to reduce Unknown results.
- Review conservative LLM, VLM, and MMLM card-family presentation labels as
  architecture coverage improves.
- Deepen chat-template parsing for Think/Tool facts when safe metadata provides
  a template, and distinguish evidence-backed badges from weaker heuristics.
- Expand safe companion metadata fallbacks (`config.json`,
  `tokenizer_config.json`, `processor_config.json`, and Jinja details) without
  claiming validation against the nonexistent `./test` symlink fixtures.
- Consider more complete runtime-configuration arguments and comparable memory
  projections only when their metadata inputs are reliable.

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
