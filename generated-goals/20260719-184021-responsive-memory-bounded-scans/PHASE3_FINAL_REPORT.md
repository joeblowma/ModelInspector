# Phase 3 Final Performance and Validation Report

## Environment and workload

- Captured: 2026-07-19, America/Edmonton
- Commit under test: `fe177819c9380c4d2f4c8b6d5d874e28ec8418fb` plus the reviewed working-tree changes
- Runtime: project Python 3.11.15, PyQt 6.11.0 / Qt 6.11.0, offscreen Qt
- Workload: the same synthetic sizes and shapes documented in `PHASE0_BASELINE.md`; all files and caches were disposable under `R:\codexTemp`
- The final GUI probe releases the workload driver's full-detail input list immediately after enqueue. This makes the settled sample reflect what the application actually retains; the pre-refactor window retained those same full objects in `_results`, while the refactored window retains compact copies.

## Before/after measurements

| Metric | Large baseline | Large final | Change / gate |
|---|---:|---:|---|
| GUI maximum heartbeat gap | 8,526.71 ms | 123.80 ms | 98.5% lower; pass (`<= 250 ms`) |
| GUI ingestion/projection | 8,524.58 ms synchronous | 8.72 ms enqueue; 1,960.39 ms time-sliced projection | pass; GUI remains schedulable |
| Retained GUI result deep size | 10,784,289 B | 563,756 B | 94.8% lower |
| Settled Python allocations | 17,806,678 B | 4,993,006 B | 72.0% lower; pass (`>= 30%`) |
| Peak Python allocations | not separately frozen | 14,008,714 B | reported |
| RSS before / after / after clear | 64,589,824 / 307,539,968 / 129,200,128 B | 66,605,056 / 187,895,808 / 94,961,664 B | retained RSS materially lower |
| Cards / table rows | 500 / 250 | 250 / 250 | inactive card mode not materialized |
| Worker peak pending, 2 threads | 500 | 4 | pass (`2 x threads`) |
| Analysis throughput | 59.04 files/s | 58.42 files/s | 1.1% regression; pass (`<= 10%`) |
| Discovery maximum heartbeat gap | 11.83 ms with nested event pumping | 10.84 ms from background worker | pass; traversal off GUI thread |
| Cancellation to terminal | 17.01 ms | 13.44 ms | pass; thread stopped, one error preserved |

Small final measurements were: GUI gap 24.99 ms, projection 201.08 ms, retained results 58,646 B, settled Python allocations 577,088 B, worker peak four, discovery gap 10.87 ms, and analysis throughput 92.80 files/s (8.3% below the small baseline and within tolerance).

## Functional and regression validation

- `python -m pytest -q -p no:cacheprovider tests`: 30 passed.
- `py_compile` for all changed/new application modules: passed.
- CLI `--help`: passed.
- Synthetic single-file human-readable CLI inspection: passed.
- Synthetic recursive JSON CLI inspection: passed.
- Integrated real worker-to-GUI projection validates errors, compact residency, filters, sorting restoration, selection, raw summary/full cached dump, and final flush.
- Dedicated tests validate discovery completion/cancellation/errors, analysis cancellation and success/error backpressure, cache full/compact APIs, startup cache cancellation, replace/additive modes, stale-generation discard, bounded projection, active-card-only materialization, and deferred close.
- `git diff --check`: passed; only benign Git LF-to-CRLF notices were emitted.
- Manual visible GUI interaction was not available through this headless agent environment. Automated Qt construction, event-loop heartbeat, lifecycle, and workflow coverage were maximized instead.

## Graphify comparison

`graphify update .` rebuilt the graph at 545 nodes, 1,197 edges, and 30 communities with no import cycles. Absolute `MainWindow` degree rose from 102 to 135 because the refreshed corpus now includes the new tests and generated goal/benchmark documents, so it is not a like-for-like coupling metric. Source inspection and graph traversal confirm that directory walking now belongs to `DiscoveryWorker`, bounded scheduling/backpressure to `AnalysisWorker`, event time-slicing/generation handling to `ScanProjectionBuffer`, and retained-field policy to `compact_inspection_summary`. `MainWindow` remains the presentation coordinator and therefore remains the top GUI hub; the expensive scan mechanics are now distinct source nodes and communities.

## Regression notes

- Result/error delivery requires acknowledgement after GUI projection or deliberate discard; cancellation wakes a worker blocked on this capacity.
- Cooperative cancellation cannot interrupt an individual model-header read already executing, but at most the bounded in-flight window remains.
- Native Qt RSS remains higher than Python retention after a large clear, although both settled RSS and Python allocations improved substantially.
