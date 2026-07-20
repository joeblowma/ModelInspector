# Phase 0 Baseline Report

## Environment

- Captured: 2026-07-19, America/Edmonton
- Commit: `fe177819c9380c4d2f4c8b6d5d874e28ec8418fb`
- OS: Microsoft Windows NT `10.0.26200.0`, PowerShell `7.6.3`
- Project Python: `3.11.15`
- PyQt: `6.11.0`; Qt: `6.11.0`
- Graphify report source commit: `537de1b1` (stale; navigation only)
- Pre-existing user changes preserved: `profile.svg` added, `pyproject.toml` modified

## Workload and Method

The reproducible probe is `baseline_probe.py` in this folder. It uses only synthetic data beneath `R:\codexTemp`, isolates Model Inspector settings/cache, and never reads or modifies user model files.

- Discovery: real directory trees with one header-only `.safetensors` and one ignored file per leaf.
- Inspection: valid header-only `.safetensors` with 64 or 128 tensor descriptors.
- Worker bound: instrumented `ThreadPoolExecutor` with two workers and 2 ms synthetic inspections.
- GUI: realistic summary dictionaries with 64 bounded synthetic metadata fields; offscreen Qt; 10 ms heartbeat; `tracemalloc`; Windows working set through `GetProcessMemoryInfo`.
- Cancellation/error: 101 synthetic jobs, one malformed job, two threads, cancellation after 45 ms.

Exact rerun shape:

```powershell
.\.venv\Scripts\python.exe generated-goals\20260719-184021-responsive-memory-bounded-scans\baseline_probe.py <mode> --size <small|large>
```

Modes are `discovery`, `gui`, `analysis`, `worker`, and `cancel_error`.

## Measurements

| Area | Small baseline | Large baseline | Finding |
|---|---:|---:|---|
| Discovery workload | 100 directories/files | 1,000 directories/files | Current traversal is synchronous inside `MainWindow` |
| Discovery elapsed | 24.21 ms | 233.93 ms | Time scales with directory count |
| Discovery max heartbeat gap | 11.64 ms | 11.83 ms | Nested `QApplication.processEvents()` masks blocking in this synthetic tree |
| Analysis workload | 10 files × 64 tensors | 100 files × 128 tensors | Header-only, cold isolated cache |
| Analysis throughput | 101.25 files/s | 59.04 files/s | Parsing itself is not the dominant GUI stall |
| Analysis result deep size | 37,615 B | 348,861 B | Full results scale with retained fields |
| Worker workload | 25 paths, 2 threads | 500 paths, 2 threads | Existing parallel path submits every job immediately |
| Worker max pending | 25 (12.5× threads) | 500 (250× threads) | Pending work is proportional to library size, not concurrency |
| GUI workload | 25 results | 250 results | Each result currently produces two cards and one table row |
| GUI ingestion time | 346.35 ms | 8,524.58 ms | Super-linear repeated whole-view work is visible |
| GUI max heartbeat gap | 354.00 ms | 8,526.71 ms | Both violate the reviewed 250 ms target |
| GUI result payload | 1,077,062 B | 10,757,147 B | Synthetic full dictionaries before projection |
| GUI retained result state | 1,079,679 B | 10,784,289 B | Nearly the entire payload remains resident |
| GUI objects created | 50 cards + 25 rows | 500 cards + 250 rows | Both card modes are eagerly materialized |
| Working set before | 48,410,624 B | 64,589,824 B | Fresh process, offscreen Qt |
| Working set after ingest | 74,227,712 B | 307,539,968 B | Large case adds about 243 MB |
| Working set after clear | 59,174,912 B | 129,200,128 B | Large case remains about 64.6 MB above pre-ingest |
| Tracemalloc retained after ingest | 1,856,572 B | 17,806,678 B | Includes Python payloads/wrappers, not all Qt native memory |
| Tracemalloc retained after clear | 273,043 B | 1,717,191 B | Python retention improves; Qt/process RSS remains elevated |

Cancellation/error baseline:

- One malformed input produced one per-file error.
- Cancellation after 45 ms left seven successful results.
- Cancel-to-terminal latency was 17.01 ms.
- Worker stopped cleanly and reported `was_cancelled=True`.

## Independent Evidence

The user-owned `profile.svg` flame graph independently identifies the same hot path: `_on_result`, `_apply_arch_filter`, `_sync_order_from_table`, and `_refresh_raw_combo_filtered` dominate the sampled GUI work. Graphify also identifies `MainWindow` as the 102-edge god node and `AnalysisWorker` as the background-task bridge.

## Baseline Conclusions

1. The responsiveness symptom is reproduced strongly and exceeds the contractual threshold by more than 34× in the large GUI workload.
2. The current executor has an absolute submit-all defect: peak pending work equals total input paths.
3. Inspection parsing throughput is not the principal freeze; projection and repeated whole-view reconciliation dominate.
4. GUI state retains full result payloads and eagerly creates both card variants, contributing to Python and native Qt memory growth.
5. Discovery should still move to a worker despite the synthetic heartbeat result: it currently relies on nested event processing and keeps filesystem orchestration inside `MainWindow`.

## Final Targets (Frozen)

- Maximum large-workload Qt heartbeat gap: `<= 250 ms`.
- Analysis in-flight futures: `<= max(2, 2 × threads)`.
- Undrained analysis events across worker signals and GUI buffer: `<= max(8, 2 × threads)`.
- Resident GUI summary contains no `metadata`, tensor descriptor map, `arch_details`, or full dtype/tensor-shape collections.
- Large-workload retained Python allocation improvement: at least 30% against 17,806,678 B.
- Throughput regression: no more than 10% against 59.04 files/s for the large inspection workload.

