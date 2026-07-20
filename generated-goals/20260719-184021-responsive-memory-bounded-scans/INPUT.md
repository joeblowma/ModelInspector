# Input

## Original request (verbatim)

> $goal-refiner this project needs refactoring, memory bloat and too much work occuring in GUI making it non-responsive during scans. $subagent-coordination-goal
> plan to use two GPT-5.6 luna subagents to do the work to keep the noise out of your context. Graphify is available for easier identification of god nodes and hotspots.

## Selected generation mode

`deep`

Reason: this is a cross-module performance refactor involving concurrency, GUI responsiveness, memory behavior, cache boundaries, coordinated edits, and resumable validation.

## Review language

English.

## Clarifying questions and answers

No clarification round was required. The repository path, desired coordination shape, primary symptoms, and safety context were discoverable. Missing numeric performance targets are handled through explicit conservative assumptions and a baseline-first phase.

## Assumptions used

- Exactly two implementation subagents are desired, both requested as GPT-5.6 Luna.
- The current visible behavior and CLI/report semantics should remain compatible unless a measured performance fix requires a narrowly documented adjustment.
- Model files remain read-only.
- Performance work must be evidence-led: capture repeatable responsiveness and memory baselines before choosing final internal boundaries.
- The existing Graphify graph is useful for navigation but stale: it was built from commit `537de1b1`, while preflight observed `fe177819c9380c4d2f4c8b6d5d874e28ec8418fb`.
- Existing uncommitted changes (`profile.svg` added and `pyproject.toml` modified) belong to the user and must not be overwritten or folded into this refactor without explicit approval.
- The repository currently uses `test/` rather than a committed `tests/` suite; the executor may create narrowly scoped pytest files under `tests/` if that is the cleanest route, while avoiding unrelated test migration.

## Evidence gathered for refinement

- `MainWindow` is the graph god node with 102 edges; `AnalysisWorker` bridges background tasks and several GUI communities.
- Recursive discovery is currently executed synchronously by `MainWindow._discover_model_paths()` and manually calls `QApplication.processEvents()`.
- `MainWindow._on_result()` creates two `ModelCard` widgets and a table row per result, then reapplies filters and refreshes the raw selector.
- `_apply_arch_filter()` walks all results, synchronizes table/card order, refreshes layout geometry, and updates selection state.
- `AnalysisWorker._run_parallel()` submits one future for every path up front.
- GUI-held inspection dictionaries can include full metadata and nested analysis details even when only compact summary fields are needed for cards and tables.

