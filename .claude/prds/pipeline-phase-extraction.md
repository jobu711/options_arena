---
name: pipeline-phase-extraction
description: Extract ScanPipeline's 4 monolithic phase methods into standalone async functions in separate modules
status: planned
created: 2026-03-09T18:44:10Z
---

# PRD: pipeline-phase-extraction

## Executive Summary

Extract the 4 phase methods from `ScanPipeline` (1,362 LOC god-class) into standalone async
functions in dedicated modules. The orchestrator shrinks to ~150 LOC. Each phase becomes
independently testable, profilable, and developable without touching unrelated code.

## Problem Statement

### What problem are we solving?

`scan/pipeline.py` is a 1,362 LOC file containing a single `ScanPipeline` class with 4 async
phase methods, a per-ticker helper, a cancelled-result builder, 5 module-level helper functions,
and a constant tuple. This mirrors the god-function anti-pattern previously fixed in the debate
orchestrator. The monolithic structure makes it hard to:
- Test individual phases without mocking the entire class
- Profile per-phase performance
- Navigate the file (must scroll through ~1,300 lines)
- Develop one phase without merge conflicts in unrelated phases

### Why is this important now?

The pipeline is stable after 26 epics and ~297 tests. All 4 phases have well-defined boundaries
with typed result models already in `scan/models.py` (`UniverseResult`, `ScoringResult`,
`OptionsResult`, `ScanResult`). The phase boundaries are clear — this is the ideal time to
formalize them before the next round of feature work adds more complexity.

## User Stories

1. **As a developer**, I want each pipeline phase in its own file so I can navigate directly
   to the phase I'm working on without scrolling through 1,300 lines.
2. **As a developer**, I want to test a single phase function by passing explicit parameters,
   without constructing a full `ScanPipeline` instance.
3. **As a developer**, I want to profile Phase 3 (options) independently since it's the slowest
   phase (~345 LOC with concurrent API calls).

## Architecture & Design

### Chosen Approach: Phase Functions (Approach B)

Extract each `_phase_*` method into a standalone `async def` in its own module. Functions take
explicit parameters (services, config, progress callback) rather than `self`. No classes, no
protocols, no new abstractions — just functions.

**Why functions over classes**: The phases are stateless — they take inputs, call services, return
a result model. A class adds constructor boilerplate without benefit. Functions with explicit
parameters are simpler, more composable, and easier to test.

### Module Changes

**New files**:
| File | Contents | ~LOC |
|------|----------|------|
| `scan/phase_universe.py` | `run_universe_phase()` | ~230 |
| `scan/phase_scoring.py` | `run_scoring_phase()` | ~110 |
| `scan/phase_options.py` | `run_options_phase()`, `process_ticker_options()`, `_extract_mp_strike()`, `_merge_signals()`, `_normalize_phase3_signals()`, `_recompute_composite_scores()`, `_recompute_dimensional_scores()`, `_PHASE3_FIELDS`, `_REGIME_*` constants | ~550 |
| `scan/phase_persist.py` | `run_persist_phase()` | ~170 |

**Modified files**:
| File | Change |
|------|--------|
| `scan/pipeline.py` | Shrink to ~150 LOC orchestrator: `__init__`, `run()`, `_make_cancelled_result()` |
| `scan/__init__.py` | No change — public API is `ScanPipeline`, `ScanResult`, `CancellationToken`, `ProgressCallback`, `ScanPhase` (none of the phase functions are public) |

**Unchanged files**: `scan/models.py`, `scan/progress.py`, `scan/indicators.py`

### Function Signatures

```python
# phase_universe.py
async def run_universe_phase(
    preset: ScanPreset,
    progress: ProgressCallback,
    *,
    universe: UniverseService,
    market_data: MarketDataService,
    repository: Repository,
    scan_config: ScanConfig,
) -> UniverseResult: ...

# phase_scoring.py
async def run_scoring_phase(
    universe_result: UniverseResult,
    progress: ProgressCallback,
    *,
    scan_config: ScanConfig,
) -> ScoringResult: ...

# phase_options.py
async def run_options_phase(
    scoring_result: ScoringResult,
    universe_result: UniverseResult,
    progress: ProgressCallback,
    *,
    fred: FredService,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    repository: Repository,
    scan_config: ScanConfig,
    pricing_config: PricingConfig,
) -> OptionsResult: ...

# phase_persist.py
async def run_persist_phase(
    *,
    started_at: datetime,
    preset: ScanPreset,
    source: ScanSource,
    universe_result: UniverseResult,
    scoring_result: ScoringResult,
    options_result: OptionsResult,
    progress: ProgressCallback,
    repository: Repository,
) -> ScanResult: ...
```

Key design decisions:
- Positional args for primary data flow (result models, preset, progress)
- Keyword-only args (after `*`) for injected dependencies (services, config)
- Config slices (`ScanConfig`, `PricingConfig`) instead of full `AppSettings` — each phase gets only what it needs
- `_make_cancelled_result` stays on `ScanPipeline` (it uses `self._settings.pricing.risk_free_rate_fallback`)

### Core Logic

No logic changes. Each function is a direct extraction of the corresponding `self._phase_*` method
with `self._*` references replaced by explicit parameters.

The `run()` orchestrator becomes:

```python
async def run(self, preset, token, progress, source=ScanSource.MANUAL) -> ScanResult:
    started_at = datetime.now(UTC)

    universe_result = await run_universe_phase(
        preset, progress,
        universe=self._universe, market_data=self._market_data,
        repository=self._repository, scan_config=self._settings.scan,
    )
    if token.is_cancelled:
        return self._make_cancelled_result(...)

    scoring_result = await run_scoring_phase(
        universe_result, progress, scan_config=self._settings.scan,
    )
    if token.is_cancelled:
        return self._make_cancelled_result(...)

    # direction filter (stays in orchestrator — cross-phase concern)
    ...

    options_result = await run_options_phase(
        scoring_result, universe_result, progress,
        fred=self._fred, market_data=self._market_data,
        options_data=self._options_data, repository=self._repository,
        scan_config=self._settings.scan, pricing_config=self._settings.pricing,
    )
    # earnings date propagation (stays in orchestrator — cross-phase concern)
    ...
    if token.is_cancelled:
        return self._make_cancelled_result(...)

    return await run_persist_phase(
        started_at=started_at, preset=preset, source=source,
        universe_result=universe_result, scoring_result=scoring_result,
        options_result=options_result, progress=progress,
        repository=self._repository,
    )
```

Cross-phase concerns that stay in the orchestrator's `run()`:
- Direction filter (between Phase 2 and 3)
- Earnings date propagation from Phase 3 results to Phase 2 scores
- Cancellation checks between phases

### Helper Colocations

| Helper | Colocates with | Reason |
|--------|---------------|--------|
| `_extract_mp_strike()` | `phase_options.py` | Called by `process_ticker_options()` |
| `_merge_signals()` | `phase_options.py` | Called by `process_ticker_options()` |
| `_normalize_phase3_signals()` | `phase_options.py` | Called at end of options phase |
| `_recompute_composite_scores()` | `phase_options.py` | Called at end of options phase |
| `_recompute_dimensional_scores()` | `phase_options.py` | Called at end of options phase |
| `_PHASE3_FIELDS` | `phase_options.py` | Used by all Phase 3 helpers |
| `_REGIME_*` constants | `phase_options.py` | Used by `_recompute_dimensional_scores()` |

## Requirements

### Functional Requirements
- All 4 phases extracted into standalone async functions
- `pipeline.py` reduced to orchestrator-only (~150 LOC)
- Zero behavior change — identical scan results for any input
- All ~297 existing scan tests pass without modification
- Public API unchanged: `ScanPipeline`, `ScanResult`, `CancellationToken`, `ProgressCallback`, `ScanPhase`

### Non-Functional Requirements
- No performance regression — same async patterns, same concurrency model
- No new dependencies — uses only existing imports redistributed across files
- `mypy --strict` passes on all new files
- `ruff` clean on all new files

## API / CLI Surface

No changes. `ScanPipeline` constructor and `run()` signatures are identical. CLI and API
callers see no difference.

## Testing Strategy

### Phase 1: No test changes
The refactor should NOT require modifying any existing tests. Tests call `pipeline._phase_*`
methods which still exist as thin wrappers delegating to the extracted functions. If any test
breaks, it indicates a behavior change (bug in the extraction).

### Phase 2: New unit tests for extracted functions (optional, future)
Once extracted, the standalone functions can be tested without constructing a `ScanPipeline`:
```python
result = await run_scoring_phase(universe_result, noop_progress, scan_config=ScanConfig())
```
This is a follow-up task, not part of this epic.

### Verification
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/unit/scan/ -n auto -q
uv run pytest tests/integration/scan/ -n auto -q
uv run pytest tests/ -n auto -q          # full suite
uv run mypy src/options_arena/scan/ --strict
```

## Success Criteria

- `pipeline.py` < 200 LOC
- 4 new phase files, each containing one public async function
- All ~297 scan tests pass unchanged
- `mypy --strict` clean
- No behavior change in scan output

## Constraints & Assumptions

- Tests call `pipeline._phase_*` (private methods) directly — the orchestrator must preserve these as thin delegation wrappers, OR tests must be updated to import the standalone functions
- `_make_cancelled_result` references `self._settings` — stays on the class
- Phase 3 is the largest extraction (~550 LOC) because `_process_ticker_options` and all 5 helpers belong to it

## Out of Scope

- Protocol/interface abstractions for phases
- Parallel phase execution
- New tests for extracted functions (follow-up)
- Changes to `scan/models.py`, `scan/progress.py`, or `scan/indicators.py`
- Any behavior changes to the pipeline logic

## Dependencies

- No external dependencies
- Internal: `scan/models.py` (result types), `scan/progress.py` (ScanPhase, callbacks), `scan/indicators.py` (compute functions)
