# Frozen Scan and GUI Interface Contract

This contract is immutable during the two-agent implementation phase. Any required change stops both workstreams and returns control to the coordinator.

## Ownership-Neutral Lifecycle

- A scan has one monotonically increasing GUI generation identifier.
- Events from an older/cancelled generation must never mutate a replacement or cleared view.
- Discovery and analysis are mutually exclusive operations in the existing action slot.
- All filesystem traversal and inspection execute outside the GUI thread.
- All widget creation/mutation executes on the GUI thread.
- Completion means the worker is terminal and the GUI buffer has been fully projected.

## Discovery Contract

Agent A provides a `DiscoveryWorker` in its owned backend/worker files.

- Input: root path and supported extension tuple captured before thread start.
- Progress object: root, discovered file count, scanned directory count, current directory.
- Terminal object: root, deduplicated path tuple/list, scanned directory count, cancelled flag, elapsed seconds.
- Error: root/path context plus displayable message; errors do not expose private metadata.
- Progress emission is throttled to at most 10 updates per second plus a final update.
- File results are returned in one terminal collection rather than an unbounded queued signal stream.
- Cancellation is cooperative and checked at least once per directory and file iteration.
- The worker never touches widgets, settings, or `MainWindow` state.

Agent B owns connection, generation checks, progress display, cache storage after successful completion, queueing paths, and optional auto-analysis.

## Analysis Contract

Agent A retains the public `AnalysisWorker` signal names for compatibility:

- `result_ready(dict)`: one compact GUI summary.
- `error_occurred(str, str)`: filepath and displayable error.
- `all_done()`: worker terminal signal.

Required additions/semantics:

- Completion-order delivery remains the policy; input ordering is not guaranteed when `threads > 1`, matching current behavior.
- In-flight futures are a sliding window bounded by `max(2, 2 × threads)` and replenished only as futures complete.
- Successful and error events share backpressure bounded by `max(8, 2 × threads)`.
- The worker acquires one event slot before emission. Agent B acknowledges slots only after corresponding events are projected or deliberately discarded for a stale generation.
- Acknowledgement is thread-safe and may be called from the GUI thread.
- Cancellation interrupts scheduling, cancels not-started futures, remains responsive while waiting for event capacity, and never emits work from a later generation.
- Worker diagnostics expose or allow tests to observe peak in-flight work and peak outstanding events without adding a runtime dependency.

Agent B buffers the existing signals, associates them with the active generation, and defers terminal UI state until `all_done()` has arrived and its local queue is empty.

## Compact GUI Summary Contract

Agent A provides one pure, independently tested compaction function used for live results and startup cache snapshots. It returns a fresh dictionary and does not mutate the full inspection result.

Allowed resident keys:

- Identity/display: `filepath`, `resolved_filepath`, `filename`, `format`
- Counts/sizes: `file_size`, `file_size_friendly`, `tensor_count`, `total_params`, `total_params_friendly`
- Classification: `architecture`, `model_type`, `adapter_type`, `quantization`
- Presentation: `components`, `named_text_encoders`, `lora_rank`, `is_moe`, `expert_count`, `expert_used_count`
- Precision: `precision_summary`, `component_precision_summary`, `component_precisions`, `precision_display`
- Bounded display metadata: `training_meta`, `extra`, `warnings`, `cache_status`, `modelinfo_outputs`

Explicitly forbidden from resident GUI summaries:

- `metadata`
- tensor descriptor maps such as `tensor_info`
- per-tensor shapes or keys
- `arch_details`
- full dtype/tensor detail collections not consumed by cards/table/raw summary
- any newly introduced unbounded nested field

Bounded display dictionaries/lists must be shallow-copied so GUI mutation cannot alter cached/full inspection data. Full CLI `inspect_file()` behavior and cache compatibility remain unchanged.

Raw summary uses the compact fields. Full raw dump continues to load on demand through the existing raw-dump cache or read-only model inspection path.

## GUI Projection Contract

Agent B owns a GUI-thread buffer/controller under `src/front/` or private `MainWindow` helpers.

- Use a FIFO `deque` for result/error events.
- Drain at most eight events or 12 ms of work per Qt tick, whichever comes first.
- If one widget projection exceeds 12 ms, yield immediately after that item.
- Disable table sorting once at scan start and restore it once after the final flush, preserving the selected sort column/order.
- Do not run whole-result filtering, card reordering, layout adjustment, raw-combo rebuilding, or selection synchronization per item.
- Coalesce global reconciliation to bounded ticks and always run one final reconciliation before marking the scan complete.
- Acknowledge worker event capacity after projection/discard, not merely after signal receipt.
- Final completion/error counts and byte totals reflect projected events and match terminal worker state.
- Clear, cancel, replacement, and window close invalidate the generation and safely discard/acknowledge stale buffered events.

## Card Materialization Policy

- Do not eagerly retain both detailed and simple `ModelCard` instances for every result.
- Materialize only the active card mode.
- Switching modes may rebuild the card view from compact summaries in time-sliced batches, while the inactive map/layout contains no model cards.
- The table remains available and behavior-compatible; replacing it with a custom model is not required for this goal.

## Integration Invariants

- `MainWindow` imports and consumes Agent A's public worker/compaction API but Agent B does not edit Agent A-owned modules.
- Agent A validates its API using backend tests without editing `gui.py`.
- Agent B may use test doubles conforming to this contract while Agent A works.
- `STATE.md`, `GOAL.md`, and integration decisions remain coordinator-owned. Agents return concise handoffs; they do not edit shared coordination files.

