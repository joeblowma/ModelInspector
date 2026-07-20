# Agent A Packet: Scan Pipeline and Memory

Requested model: GPT-5.6 Luna. Do not silently substitute another model.

## Objective

Implement the backend half of `GOAL.md` against `PHASE0_INTERFACE.md`: asynchronous cancellable discovery, bounded analysis scheduling and event backpressure, and compact GUI summaries while preserving full CLI/cache behavior.

## Exclusive Editable Ownership

- `src/background_tasks.py`
- `src/inspect_model.py`
- `src/model_readers.py`
- `src/model_cache.py`
- New helpers under `src/back/`
- Uniquely named backend tests such as `tests/test_background_tasks.py` and `tests/test_inspection_summary.py`
- Uniquely named backend benchmark helpers if needed

Everything else is read-only. In particular, do not edit `src/gui.py`, `src/front/`, `GOAL.md`, `STATE.md`, `pyproject.toml`, `profile.svg`, generated/build outputs, or Agent B tests.

## Required Context

Read repository `AGENTS.md`, `GOAL.md`, `PHASE0_BASELINE.md`, `PHASE0_INTERFACE.md`, current owned files, and the relevant read-only GUI methods: `_discover_model_paths`, `_browse_folder_recursive`, `_start_analysis`, `_on_result`, `_on_error`, `_on_all_done`, `_load_default_libraries_from_cache_on_startup`, and raw-detail methods.

## Required Work

1. Provide `DiscoveryWorker` with throttled progress, cooperative cancellation, terminal paths, and no widget access.
2. Replace submit-all futures with the frozen sliding-window bound.
3. Bound successful/error event delivery with acknowledgement-based backpressure.
4. Preserve completion-order semantics, per-file errors, cancellation, and `all_done` behavior.
5. Provide the pure compact-summary function exactly matching the allowed/forbidden field contract.
6. Keep `inspect_file()` CLI/full-cache semantics unchanged.
7. Add focused pytest coverage for bounds, cancellation while backpressured, errors, discovery, compact-copy isolation, and resource release.
8. Run packet-specific tests and relevant CLI smoke checks.

## Stop Conditions

Stop and report without editing cross-owned files if the frozen interface is insufficient, GUI changes are required, cache schema would change, a runtime dependency is needed, or user dirty work overlaps an owned file.

## Handoff (maximum 500 words)

Return only: outcome, changed files, interface implemented/deviations, tests/commands and numeric results, risks, and exact next integration action. Do not paste full diffs and do not edit coordinator state files.

