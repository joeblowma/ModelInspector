# Goal: Refactor Model Inspector for Responsive, Memory-Bounded Scans

## 0. Execution Directive

Mode: `deep`.

Status: `awaiting_human_review`. This file is a draft execution contract, not implementation authorization. Human review gate: do not create subagents, edit application code, or begin benchmarks until the user starts a separate execution request (Codex: `/goal`) or explicitly approves this generated goal after review.

After approval, the root coordinator must remain the sole integrator and use exactly two implementation subagents requested as GPT-5.6 Luna. Keep their context packets narrow, their file ownership disjoint, and their handoffs concise. If that exact model is unavailable, stop and ask whether substitution is acceptable; do not silently use another model.

## 1. Objective

Refactor Model Inspector so recursive discovery and model analysis remain responsive at library scale, scan orchestration has bounded in-flight memory, and GUI memory retains compact display state rather than unnecessary full inspection payloads. Preserve model-detection correctness, CLI behavior, cache integrity, cancellation, filtering, cards, table, and raw-detail workflows.

Success must be demonstrated with repeatable before/after measurements, focused automated tests, CLI smoke checks, and a GUI responsiveness validation. The implementation should reduce the responsibilities and cross-community coupling of `MainWindow`, not merely insert additional `processEvents()` calls.

## 2. Background and Context

The existing Graphify report contains 325 nodes and 786 edges. It identifies `MainWindow` as the dominant god node (102 edges) and `AnalysisWorker` as a bridge among background tasks, the main window, filters, and model cards. The graph is stale relative to the current commit, so every graph-derived hypothesis must be verified against source before editing.

Current-source preflight found four concrete hotspots:

1. Recursive folder discovery runs inside `MainWindow._discover_model_paths()` on the UI thread and periodically calls `QApplication.processEvents()`.
2. `AnalysisWorker._run_parallel()` submits all file futures at once, so queued futures and their references scale with total scan size rather than worker count.
3. Every result triggers immediate creation of two cards and a full table row, plus global filtering/order/raw-selector work, producing repeated whole-view work during a scan.
4. GUI `_results` and startup cache snapshots may retain metadata and nested inspection data that cards and tables do not need; two card instances per model and eager table items further amplify retained memory.

These are measured hypotheses, not permission to make an unbounded redesign. Phase 0 determines the baseline and freezes the interface between the two subagents.

## 3. Inputs and Important Paths

- Repository: `C:\Users\Joseph\Desktop\ModelInspector`
- Coordination ledger: `generated-goals/20260719-184021-responsive-memory-bounded-scans/STATE.md`
- Architecture report: `graphify-out/GRAPH_REPORT.md`
- Graph data: `graphify-out/graph.json`
- Primary GUI: `src/gui.py`
- Existing worker: `src/background_tasks.py`
- Inspection pipeline: `src/inspect_model.py`
- Read-only model readers: `src/model_readers.py`
- Cache: `src/model_cache.py`
- GUI helpers: `src/front/`
- Backend helpers: `src/back/`
- Runtime/build metadata: `requirements.txt`, `requirements-dev.txt`, `pyproject.toml`
- Tests to add: narrowly scoped files under `tests/` using `pytest`; do not migrate unrelated test material.
- User-owned dirty files observed at refinement time: `profile.svg`, `pyproject.toml`

## 4. Assumptions

- Assumption A1: Exactly two GPT-5.6 Luna subagents will perform bounded implementation work; the root coordinator will inspect, integrate, and validate their outputs.
- Assumption A2: The product must remain usable on Windows with PyQt6 and Python 3.11+.
- Assumption A3: No representative private model files may be copied, uploaded, committed, or modified. Synthetic fixtures or user-local paths may be used read-only.
- Assumption A4: The final design will use background discovery, bounded analysis scheduling, compact GUI summaries, and batched/time-sliced UI projection unless Phase 0 evidence disproves one of those approaches.
- Assumption A5: Raw metadata/details may be loaded on demand from the existing cache or model file; cards and table rows do not require the full payload resident in every GUI result.
- Assumption A6: Numeric responsiveness and memory comparisons will use the same workload and environment before and after. Required structural bounds are absolute; measured percentage improvements are relative to the captured baseline.
- Assumption A7: Existing user changes are authoritative. Agents must inspect diffs before touching an overlapping file and stop if safe preservation is unclear.
- Assumption A8: No public API, cache-format migration, visual redesign, or new runtime dependency is required unless Phase 0 proves it necessary and the user approves the expansion.

## 5. Scope

### In Scope

- Measure UI event-loop delay, scan throughput, pending-work count, Python allocations, and process RSS on repeatable synthetic workloads.
- Move recursive discovery off the GUI thread with progress and cooperative cancellation.
- Replace submit-all scheduling with a bounded producer/consumer or bounded-futures design.
- Define a small scan event/result-summary contract independent of Qt widgets.
- Separate scan orchestration and result projection from `MainWindow` where practical.
- Batch or time-slice result ingestion so filters, layouts, sorting, and raw-selector updates are coalesced.
- Reduce GUI-retained result payloads and avoid eager duplicate heavyweight presentation where evidence supports it.
- Preserve on-demand raw details, cache behavior, CLI output, filters, selections, cancellation, errors, and progress reporting.
- Add focused pytest coverage and a reproducible performance harness that does not require committing real model files.
- Refresh Graphify after code edits and compare god nodes/hotspots.

### Out of Scope

- Changing architecture-detection heuristics, quantization interpretation, or tensor-analysis semantics except for a proven regression fix directly caused by this refactor.
- Loading tensor payloads or modifying model files.
- A broad visual redesign or replacement of PyQt6.
- Cache deletion or an incompatible cache-format migration.
- Editing generated packaging artifacts: `ModelInspector.spec`, `version.txt`, `build/`, or `dist/`.
- Modifying, removing, or committing the user's unrelated `profile.svg` and `pyproject.toml` changes.
- Git push, pull request creation, publishing, or release work.
- Spawning more than two implementation subagents without explicit approval.

## 6. Safety Boundaries and Do-Not Rules

- Treat every model file as read-only; never rewrite, rename, move, upload, or delete it during benchmarking or validation.
- Never commit private model paths, metadata, filenames, or binary fixtures.
- Do not use `QApplication.processEvents()` as the primary responsiveness architecture.
- Do not create an unbounded task queue, future map, signal backlog, result list, widget population loop, or cache read into memory.
- Do not let both subagents edit the same file. If ownership must change, both agents stop; the coordinator records and approves the handoff in `STATE.md` before either continues.
- Do not let a subagent modify files outside its packet. Cross-packet changes must be proposed in the handoff, not applied.
- Do not overwrite or normalize unrelated dirty work. Check `git status --short` and targeted diffs before and after every merge point.
- Do not add runtime dependencies solely for benchmarking. Prefer `tracemalloc`, Qt timers, and OS RSS sampling in development-only tooling.
- Do not change cache schema or delete caches without a separate user approval gate and a compatibility/migration plan.
- Do not run remote, paid, publishing, or destructive operations.
- After modifying code files, run `graphify update .` as required by repository instructions.

## 7. Required Deliverables

1. A committed-to-worktree refactor that moves discovery and scan orchestration out of GUI-thread responsibilities and bounds analysis scheduling.
2. A compact, documented data contract for discovery events, analysis results, progress, errors, and cancellation.
3. Batched/time-sliced GUI projection with coalesced filtering, sorting, layout, selection, and raw-selector refreshes.
4. A memory policy documenting which inspection fields remain resident in the GUI and how raw detail is loaded on demand.
5. Focused automated tests for bounded scheduling, cancellation, error delivery, compact summaries, result batching, and compatibility.
6. A reproducible benchmark/profile harness and before/after report containing workload, environment, event-loop delay, pending-work bound, throughput, Python allocations, and process RSS.
7. Updated `graphify-out/` outputs and a before/after hotspot comparison.
8. Updated `STATE.md` after every phase and every subagent handoff.
9. A concise final report in the format defined in Section 13.

## 8. Execution Phases

### Phase 0: Preflight and Baseline Capture

Objective: verify repository state, reproduce both symptoms, freeze success metrics, and define a collision-free two-agent interface before any delegation.

Checklist:

- [ ] Confirm human approval of this goal and set `STATE.md` to `approved_preflight`.
- [ ] Record current commit, Python/PyQt versions, OS, graph freshness, and complete `git status --short`; preserve `profile.svg` and `pyproject.toml` changes.
- [ ] Read current `AGENTS.md`, `graphify-out/GRAPH_REPORT.md`, and the exact source paths cited in Section 2.
- [ ] Create a deterministic synthetic directory tree and small header-only model fixtures under `R:\codexTemp` or a test temp directory; do not use or copy private models.
- [ ] Build a repeatable baseline harness measuring idle/event-loop timer gaps, recursive discovery latency, analysis throughput, peak pending futures/tasks, `tracemalloc` peak/retained allocations, and OS process RSS.
- [ ] Capture at least small and large workloads, including cancellation and per-file errors.
- [ ] Specify immutable interface contracts for discovery events, bounded analysis scheduling, compact result summaries, and batched GUI delivery.
- [ ] Assign exclusive ownership packets exactly as listed below and record them in `STATE.md`.
- [ ] Stop for explicit user approval before spawning the two GPT-5.6 Luna subagents.

Agent A packet — Scan Pipeline and Memory:

- Exclusive editable ownership: `src/background_tasks.py`, `src/inspect_model.py`, `src/model_readers.py`, `src/model_cache.py`, new helpers under `src/back/`, and uniquely named backend tests/benchmarks.
- Read-only context: relevant `src/gui.py` methods and the frozen interface contract.
- Output contract: bounded discovery/analysis pipeline, compact summary/detail boundary, tests, measurements, changed-file list, validation results, risks, and an integration note of at most 500 words.

Agent B packet — GUI Projection and Responsiveness:

- Exclusive editable ownership: `src/gui.py`, new helpers under `src/front/`, and uniquely named GUI tests/benchmarks.
- Read-only context: the frozen interface contract and Agent A-owned modules.
- Output contract: non-blocking GUI integration, batch/time-budgeted result projection, coalesced global view updates, reduced eager presentation cost, tests, measurements, changed-file list, validation results, risks, and an integration note of at most 500 words.

Expected artifacts: baseline report, benchmark harness, frozen interface/ownership entry in `STATE.md`, and two final context packets.

Validation checks: baseline reproduces a measurable event-loop delay and records memory behavior; interface covers progress, cancellation, errors, completion, ordering expectations, cache hit/miss behavior, and detail loading; editable ownership sets do not overlap.

Checkpoint update: record commands, workload sizes, raw baseline values, dirty files, interface decisions, ownership, and the approval gate result.

Stop conditions: exact subagent model unavailable; symptom cannot be reproduced; private data would be exposed; dirty-file overlap is unsafe; ownership or integration criteria remain unclear; user has not approved subagent creation.

### Phase 1: Two-Agent Parallel Implementation

Objective: have exactly two approved GPT-5.6 Luna subagents implement their isolated packets concurrently against the frozen interface.

Checklist:

- [ ] Spawn both subagents only after the Phase 0 approval gate, using the final packets recorded in `STATE.md`.
- [ ] Tell both agents that the shared filesystem is live, ownership is exclusive, and cross-owned files are read-only.
- [ ] Agent A implements asynchronous cancellable discovery and bounded analysis scheduling without submit-all retention.
- [ ] Agent A implements or exposes compact GUI summaries and on-demand detail access while preserving full CLI inspection semantics.
- [ ] Agent A tests bounds, cancellation, errors, cache hits, ordering policy, and resource release.
- [ ] Agent B removes synchronous recursive discovery from `MainWindow` and consumes the frozen scan event API.
- [ ] Agent B queues result events and drains them in bounded batches or by a per-tick time budget.
- [ ] Agent B coalesces filter/order/layout/raw-selector/selection refreshes and avoids enabling table sorting per inserted row.
- [ ] Agent B evaluates lazy creation, single-view creation, or virtualization for duplicate card widgets; adopt the smallest behavior-compatible option supported by measurements.
- [ ] Agent B tests GUI-thread responsiveness, cancellation, filter correctness, selection, result visibility, and final flush.
- [ ] Each agent checks only its own diff, runs packet-specific validation, updates its assigned `STATE.md` subsection, and returns the required concise handoff.

Expected artifacts: two disjoint patches, packet-specific tests, packet-specific before/after measurements, and two concise handoffs.

Validation checks: no file is edited by both agents; pending analysis work is structurally bounded by a documented function of thread count; no recursive traversal occurs on the GUI thread; result delivery cannot grow an unbounded GUI signal backlog; full inspection dictionaries are not retained solely for cards/table; packet tests pass independently.

Checkpoint update: record each agent ID/model, owned files, start/end commit state, changed files, commands, results, interface deviations, and handoff summary.

Stop conditions: an agent needs to edit the other packet; the frozen interface is insufficient; a test exposes a behavior decision not covered by the goal; memory or responsiveness regresses; either agent attempts destructive or out-of-scope work.

### Phase 2: Coordinator Review and Merge Point

Objective: independently review both outputs, resolve integration centrally, and reject changes that hide work rather than remove it.

Checklist:

- [ ] Stop both agents before integration edits begin.
- [ ] Review every changed file and compare it with the ownership ledger and initial dirty state.
- [ ] Verify Agent A's queue bound mathematically and with instrumentation; verify cancellation does not wait for the entire original queue.
- [ ] Verify Agent B's UI drain has a strict item/time budget and guarantees a final flush before completion state.
- [ ] Verify detail loading preserves raw-view behavior without keeping full metadata resident for every result.
- [ ] Verify errors, progress counts, bytes scanned, cache options, result ordering policy, and partial cancellation semantics.
- [ ] Make only minimal coordinator-owned integration edits. If substantial rework is needed, return it to the owning agent with a narrow follow-up packet rather than editing across ownership silently.
- [ ] Run focused tests after integration and inspect retained objects/Qt widgets after clear, replacement scan, cancellation, and window close.

Expected artifacts: integrated worktree, coordinator review notes, resolved interface deviations, and updated ownership ledger.

Validation checks: no duplicate event delivery, stale signal connection, orphan worker/thread, late result after clear, lost final batch, cache regression, or UI update from a non-GUI thread.

Checkpoint update: record accepted/rejected portions, integration edits, test results, and remaining risks.

Stop conditions: source ownership violation cannot be safely disentangled; full-data compatibility is unclear; stale workers can mutate cleared/replaced views; integration requires a cache migration or new dependency not approved in scope.

### Phase 3: Performance, Functional, and Regression Validation

Objective: prove the refactor improves the reported symptoms without changing inspection correctness.

Checklist:

- [ ] Re-run the exact Phase 0 small and large workloads in the same environment.
- [ ] Compare idle and active event-loop gaps, peak/retained Python allocations, process RSS, throughput, cancellation latency, pending-work peak, and resident GUI result size.
- [ ] Require discovery to remain off the GUI thread and the scan heartbeat maximum gap to remain at or below 250 ms on the baseline machine for the synthetic large workload.
- [ ] Require pending analysis tasks/futures to stay within the documented constant multiple of configured worker threads, independent of library size.
- [ ] Require the GUI summary representation to exclude raw tensor descriptors and unbounded metadata fields; load those details on demand.
- [ ] Require at least a 30% reduction in peak retained Python allocations attributable to orchestration/result state on the large synthetic workload, or stop and present evidence plus a revised target for user approval.
- [ ] Require no more than a 10% throughput regression; any larger regression needs a documented responsiveness tradeoff and user approval.
- [ ] Exercise discovery cancel, analysis cancel, malformed file errors, empty folder, cache hit, cache miss, replace mode, additive mode, filters, selections, card/simple-card switch, table sorting, raw summary, and raw full detail.
- [ ] Run `py src/inspect_model.py --help` and representative human-readable and `--json` CLI smoke checks with synthetic/read-only fixtures.
- [ ] Launch the GUI for a manual smoke test when the environment supports it; otherwise record the headless limitation and maximize automated Qt coverage.

Expected artifacts: before/after performance report, full validation transcript, regression notes, and any approved target deviation.

Validation checks: all acceptance thresholds and functional cases pass using identical workloads; test and benchmark processes exit cleanly without live worker threads.

Checkpoint update: store exact commands, workload identity, raw numbers, comparisons, failures/retries, and manual-test status.

Stop conditions: responsiveness threshold fails; retained-allocation target fails; throughput regresses beyond tolerance; CLI output changes unexpectedly; model correctness differs; cancellation or shutdown leaks work.

### Phase N: Final Validation and Review

Objective: refresh architecture evidence, confirm repository hygiene, and produce a reviewable completion report.

Checklist:

- [ ] Run the complete focused pytest suite and all smoke checks from Phase 3.
- [ ] Run `graphify update .` after all code edits.
- [ ] Read the refreshed `graphify-out/GRAPH_REPORT.md` and compare `MainWindow`, worker, cache, and inspection god-node/cross-community relationships with the baseline.
- [ ] Confirm no generated/build artifacts, private fixtures, caches, absolute private paths, or unrelated dirty changes were added.
- [ ] Review `git diff --check`, `git status --short`, and the final diff without reverting user work.
- [ ] Update `STATE.md` to `complete` only if every acceptance criterion is satisfied; otherwise leave it `blocked_for_review` with exact evidence.
- [ ] Produce the Section 13 completion report.

Expected artifacts: refreshed Graphify outputs, clean validation transcript, final diff inventory, completed checkpoint ledger, and concise completion report.

Validation checks: graph refresh succeeds; tests and smoke checks pass; final diff matches scope; user-owned dirty files remain intact; all acceptance criteria have evidence.

Checkpoint update: record final commit/worktree state, graph summary, all command results, remaining risks, and completion status.

Stop conditions: graph update fails; required test or smoke check fails; unrelated changes cannot be separated; any acceptance criterion lacks evidence.

## 9. Validation Matrix

| Area | Validation Method | Required Result | Evidence Location |
|---|---|---|---|
| GUI responsiveness | Qt timer/heartbeat during identical large synthetic discovery and result ingestion | Maximum active gap `<= 250 ms` on baseline machine | Before/after performance report |
| Discovery threading | Thread-affinity assertions and integration test | Filesystem walk is not executed on GUI thread; widget updates are | Focused test transcript |
| Queue memory bound | Instrument pending futures/tasks across small and large queues | Peak is a documented constant multiple of threads, not file count | Benchmark report and unit test |
| Result memory | `tracemalloc`, OS RSS, and field/size inspection | At least 30% lower retained Python allocations for orchestration/result state | Before/after performance report |
| Payload policy | Unit tests for compact summary/detail loader | No tensor descriptor map or unbounded metadata in resident display summary | Summary-schema tests |
| Throughput | Same fixtures, thread count, cache state, and machine | No more than 10% regression without approved exception | Before/after performance report |
| Cancellation | Discovery and analysis cancellation at multiple points | Prompt stop, consistent partial results, no late mutation or leaked worker | Focused test transcript |
| Errors | Malformed/missing fixtures | Per-file error visible; remaining scan completes | Focused test transcript |
| Cache | Hit/miss, startup summary load, raw-detail retrieval | Existing cache remains readable; no destructive migration | Cache test transcript |
| GUI behavior | Qt tests/manual smoke | Existing cards, table, filters, sorting, selection, and raw workflows preserved | GUI validation notes |
| CLI behavior | `--help`, human output, `--json` smoke tests | No unintended semantic/output regression | CLI transcript |
| Architecture | `graphify update .` and refreshed report | `MainWindow` scan responsibilities/coupling reduced or explicitly justified | Final Graphify comparison |
| Repository hygiene | `git diff --check`, status, private-path scan | No unrelated overwrite, private fixture, generated build output, or secret | Final diff inventory |

## 10. Acceptance Criteria

- [ ] Recursive discovery and model inspection never perform filesystem traversal or parsing on the GUI thread.
- [ ] UI updates are delivered in bounded batches/time slices, with a guaranteed final flush and no unbounded signal backlog.
- [ ] Analysis scheduling has a verified pending-work bound based on configured concurrency, not total file count.
- [ ] GUI resident summaries exclude raw tensor maps and unbounded metadata; raw details remain correct through on-demand loading.
- [ ] The large synthetic workload meets the 250 ms maximum event-loop gap target.
- [ ] Retained Python allocations attributable to scan orchestration/result state improve by at least 30% on the identical large workload.
- [ ] Throughput regression is no greater than 10%, unless the user explicitly approves a documented responsiveness tradeoff.
- [ ] Discovery and analysis cancellation, errors, cache hit/miss, replace/additive modes, filters, sorting, selections, cards, table, and raw detail all pass validation.
- [ ] CLI human-readable and JSON inspection semantics remain compatible.
- [ ] Exactly two GPT-5.6 Luna implementation subagents were used, with disjoint ownership and concise handoffs, unless execution stopped at the model-availability gate.
- [ ] User-owned `profile.svg` and `pyproject.toml` changes remain intact and unrelated.
- [ ] `graphify update .` completes and the final report explains the before/after hotspot changes.
- [ ] `STATE.md` contains enough commands, decisions, measurements, ownership, and results to resume or audit the work.

## 11. Checkpoint and Resume Protocol

- `STATE.md` is the single shared ledger. Update it before delegation, after every agent handoff, after integration, after each validation phase, and before stopping.
- Only the coordinator edits global status, interface decisions, ownership, merge decisions, and final acceptance. Each subagent may edit only its clearly labeled packet subsection or return text for the coordinator to copy.
- Every checkpoint records: timestamp, current commit, `git status --short`, active phase, completed checklist items, exact commands/results, measured values, files changed, decisions, blockers, next action, and safe resume command/context.
- Subagent handoffs are limited to: outcome, changed files, tests/benchmarks run, numeric results, interface deviations, known risks, and next integration action. Maximum 500 words each.
- On resume, read `GOAL.md`, `STATE.md`, current `AGENTS.md`, `git status --short`, and diffs for all dirty owned files before acting.
- Never repeat a completed benchmark unless the workload/environment changed, a result is suspect, or the relevant code changed; record the reason.

## 12. Failure Gates and Approval Gates

- Human review gate: no execution occurs until the user approves this `GOAL.md` in a separate request.
- Subagent gate: after Phase 0, stop for explicit approval before creating exactly two GPT-5.6 Luna subagents.
- Model gate: if GPT-5.6 Luna is unavailable, stop and request approval for a named substitute.
- Ownership gate: if file ownership or integration criteria are ambiguous, stop; do not allow concurrent edits to the same file.
- Dirty-work gate: if a required edit overlaps unexplained user changes, stop and request direction.
- Metrics gate: if the baseline cannot reproduce the issue or cannot measure event-loop delay/memory consistently, stop and revise the harness before implementation.
- Scope gate: cache-format migration, new runtime dependency, public API break, visual redesign, third subagent, private fixture use, or destructive action requires separate approval.
- Performance gate: missing the 250 ms responsiveness target, 30% allocation reduction, or 10% throughput tolerance stops completion and requires an evidence-backed user decision.
- Correctness gate: any model-detection, CLI, cache, raw-detail, cancellation, or selection/filter regression stops completion.
- External-action gate: git push, PR, release, upload, or publishing is prohibited unless separately requested and approved.

## 13. Final Completion Report Format

The coordinator must report:

1. Outcome and whether every acceptance criterion passed.
2. Architecture changes, organized by scan pipeline, memory policy, and GUI projection.
3. Two subagent handoff summaries and confirmation of disjoint ownership.
4. Before/after table for event-loop delay, pending-work peak, allocations, RSS, throughput, and cancellation latency.
5. Functional and CLI validation commands with pass/fail results.
6. Graphify before/after god-node and bridge comparison.
7. Exact changed-file inventory, explicitly separating pre-existing user changes.
8. Remaining risks, limitations, and any approved deviations.
9. Safe next step, without pushing, publishing, or deleting anything.
