# Agent B Packet: GUI Projection and Responsiveness

Requested model: GPT-5.6 Luna. Do not silently substitute another model.

## Objective

Implement the GUI half of `GOAL.md` against `PHASE0_INTERFACE.md`: consume background discovery, time-slice result/error projection with final-flush semantics, coalesce whole-view work, and avoid duplicate card materialization.

## Exclusive Editable Ownership

- `src/gui.py`
- New helpers under `src/front/`
- Uniquely named GUI tests such as `tests/test_gui_projection.py` and `tests/test_gui_scan_lifecycle.py`
- Uniquely named GUI benchmark helpers if needed

Everything else is read-only. In particular, do not edit `src/background_tasks.py`, `src/inspect_model.py`, `src/model_readers.py`, `src/model_cache.py`, `src/back/`, `GOAL.md`, `STATE.md`, `pyproject.toml`, `profile.svg`, generated/build outputs, or Agent A tests.

## Required Context

Read repository `AGENTS.md`, `GOAL.md`, `PHASE0_BASELINE.md`, `PHASE0_INTERFACE.md`, current `src/gui.py`, and Agent A's frozen public API contract. The user-owned flame graph identifies `_on_result`, `_apply_arch_filter`, `_sync_order_from_table`, and `_refresh_raw_combo_filtered` as hot paths.

## Required Work

1. Replace synchronous recursive discovery with lifecycle-managed `DiscoveryWorker` integration.
2. Add generation-safe FIFO buffering for result/error events and the frozen eight-item/12 ms drain policy.
3. Acknowledge Agent A worker capacity only after projection or stale-event discard.
4. Defer terminal UI state until the worker is done and the queue has received a final flush.
5. Disable sorting once per scan and coalesce filtering, card ordering, layout geometry, raw selector, and selection refreshes.
6. Materialize only the active detailed/simple card mode and time-slice rebuilding when switching.
7. Apply Agent A's compact-summary function to live and startup-cache results.
8. Preserve progress, bytes/errors, replace/additive behavior, cancellation, filters, sorting, selection, cards, table, and raw views.
9. Add focused offscreen Qt pytest coverage, using contract-compatible test doubles if Agent A's implementation is not yet present.
10. Run packet-specific tests and the GUI portion of the baseline probe where possible.

## Stop Conditions

Stop and report without editing cross-owned files if the frozen interface is insufficient, backend changes are required, behavior requires a redesign outside scope, a runtime dependency is needed, or user dirty work overlaps an owned file.

## Handoff (maximum 500 words)

Return only: outcome, changed files, interface implemented/deviations, tests/commands and numeric results, risks, and exact next integration action. Do not paste full diffs and do not edit coordinator state files.

