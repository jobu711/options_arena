# Research: pipeline-phase-extraction

## PRD Summary

Extract `ScanPipeline`'s 4 monolithic phase methods (1,362 LOC god-class) into standalone async
functions in dedicated modules (`phase_universe.py`, `phase_scoring.py`, `phase_options.py`,
`phase_persist.py`). The orchestrator shrinks to ~150 LOC. Zero behavior change — identical scan
results, all ~312 existing scan tests pass, public API unchanged.

## Relevant Existing Modules

- `scan/pipeline.py` (1,362 LOC) — The god-class being decomposed. Contains `ScanPipeline` with 4 `_phase_*` methods, `_process_ticker_options` helper, `_make_cancelled_result`, 5 module-level helpers, and `_PHASE3_FIELDS` constant.
- `scan/models.py` (117 LOC) — Result types: `UniverseResult`, `ScoringResult`, `OptionsResult`, `ScanResult`. No changes needed.
- `scan/progress.py` (60 LOC) — `ScanPhase` enum, `CancellationToken`, `ProgressCallback` protocol. No changes needed.
- `scan/indicators.py` (822 LOC) — Indicator registry, dispatch, options/Phase 3 indicators. No changes needed.
- `scan/__init__.py` (13 LOC) — Re-exports `ScanPipeline`, `ScanResult`, `CancellationToken`, `ProgressCallback`, `ScanPhase`. No changes needed (phase functions are not public).
- `models/config.py` — `ScanConfig` (25+ fields) and `PricingConfig` (14 fields) used as config slices.
- `services/` — 5 service types injected: `UniverseService`, `MarketDataService`, `OptionsDataService`, `FredService`, `Repository`.
- `scoring/` — Phase 2+3 import: `score_universe`, `determine_direction`, `composite_score`, `recommend_contracts`, `percentile_rank_normalize`, etc.

## Existing Patterns to Reuse

- **Explicit-parameter async functions**: The PRD proposes standalone `async def` functions with positional args for data flow and keyword-only args (after `*`) for injected dependencies. This mirrors the existing pattern in `scoring/` where functions take explicit typed parameters.
- **Config slices over full AppSettings**: Each phase receives only `ScanConfig` and/or `PricingConfig`, not the full `AppSettings` — aligning with the DI pattern in CLAUDE.md.
- **Re-export pattern**: Phase functions are internal to `scan/` — `__init__.py` does NOT re-export them. Only `ScanPipeline` and result types are public.
- **Module-level helpers colocated with their caller**: `_extract_mp_strike()`, `_merge_signals()`, etc. move to `phase_options.py` alongside `process_ticker_options()`.

## Existing Code to Extend

### `scan/pipeline.py` — Line Ranges for Extraction

| Target Module | Method/Helper | Current Lines | ~LOC |
|---------------|---------------|---------------|------|
| `phase_universe.py` | `_phase_universe()` | 204-433 | 230 |
| `phase_scoring.py` | `_phase_scoring()` | 435-543 | 109 |
| `phase_options.py` | `_phase_options()` | 545-720 | 176 |
| `phase_options.py` | `_process_ticker_options()` | 722-889 | 168 |
| `phase_options.py` | `_PHASE3_FIELDS` | 1122-1170 | 49 |
| `phase_options.py` | `_extract_mp_strike()` | 1173-1210 | 38 |
| `phase_options.py` | `_merge_signals()` | 1213-1225 | 13 |
| `phase_options.py` | `_normalize_phase3_signals()` | 1228-1281 | 54 |
| `phase_options.py` | `_recompute_composite_scores()` | 1284-1314 | 31 |
| `phase_options.py` | `_REGIME_*` constants | 1319-1321 | 3 |
| `phase_options.py` | `_recompute_dimensional_scores()` | 1324-1362 | 39 |
| `phase_persist.py` | `_phase_persist()` | 891-1056 | 166 |
| stays in `pipeline.py` | `__init__`, `run()`, `_make_cancelled_result()` | 96-202, 1058-1116 | ~150 |

### `self._*` Attribute References Per Phase (Become Explicit Parameters)

**Phase 1** — `self._universe`, `self._market_data`, `self._repository`, `self._settings.scan`
**Phase 2** — `self._settings.scan` (only for `determine_direction()`)
**Phase 3** — `self._fred`, `self._market_data`, `self._options_data`, `self._repository`, `self._settings.scan`, `self._settings.pricing`
**Phase 4** — `self._repository`

### Cross-Phase Data Flows

```
Phase 1 (universe) → UniverseResult {tickers, ohlcv_map, sp500_sectors, sector_map, industry_group_map}
    ↓
Phase 2 (scoring) → ScoringResult {scores, raw_signals, normalization_stats}
    ↓ (orchestrator applies direction filter)
Phase 3 (options) → OptionsResult {recommendations, risk_free_rate, earnings_dates, entry_prices}
    Side effects: mutates ScoringResult.scores (merges Phase 3 fields, recomputes composites)
    ↓ (orchestrator propagates earnings dates)
Phase 4 (persist) → ScanResult {scan_run, scores, recommendations, risk_free_rate, earnings_dates}
```

Cross-phase concerns staying in orchestrator's `run()`:
- Direction filter (between Phase 2 and 3)
- Earnings date propagation (Phase 3 → Phase 2 scores)
- Cancellation checks between phases

## Potential Conflicts

### 1. Test Backward Compatibility (HIGH RISK)

**~110+ direct calls** to `pipeline._phase_*()` methods across **13 test files**. Two sub-patterns:

**A) Direct invocation** (~103 calls):
```python
result = await pipeline._phase_universe(preset, progress)
```
Tests construct a `ScanPipeline` and call private methods directly for phase-level isolation.

**B) Monkey-patching for cancellation** (5 instances across 4 files):
```python
original = pipeline._phase_scoring
async def _scoring_then_cancel(universe_result, progress):
    result = await original(universe_result, progress)
    token.cancel()
    return result
pipeline._phase_scoring = _scoring_then_cancel
```

**Mitigation**: Keep thin delegation wrappers on `ScanPipeline`:
```python
async def _phase_universe(self, preset, progress):
    return await run_universe_phase(preset, progress, universe=self._universe, ...)
```
This preserves all existing test patterns with zero test changes. The wrappers add ~20 LOC to pipeline.py but avoid rewriting ~110+ test call sites.

### 2. `_PHASE3_FIELDS` Import (LOW RISK)

`test_phase3_fields.py` imports `from options_arena.scan.pipeline import _PHASE3_FIELDS`. After extraction, this moves to `phase_options.py`. Fix: update the single import, or re-export from pipeline.py.

### 3. `_process_ticker_options` Monkey-Patch (MEDIUM RISK)

`test_pipeline_metadata.py` and `test_audit_hardening.py` monkey-patch `pipeline._process_ticker_options`. The thin wrapper approach handles this — keep `_process_ticker_options` as a wrapper on `ScanPipeline` delegating to `phase_options.process_ticker_options()`.

### 4. 12 Independent `_make_pipeline()` Factory Helpers (LOW RISK)

Each test file has its own `_make_pipeline()` helper. The `ScanPipeline` constructor signature does NOT change, so these are unaffected.

## Open Questions

1. **Wrapper approach vs test rewrite?** PRD suggests thin wrappers OR test updates. Research strongly recommends wrappers — 110+ call sites make mass rewrite risky and noisy. The ~20 LOC overhead is trivial vs the diff churn.

2. **Should `_PHASE3_FIELDS` be re-exported from pipeline.py?** One test imports it from there. Cleanest to update the single import in `test_phase3_fields.py` to `from options_arena.scan.phase_options import _PHASE3_FIELDS`.

3. **Phase 3 mutations**: `run_options_phase()` mutates `ScoringResult.scores` in-place (merges Phase 3 fields, recomputes composites). This is existing behavior but makes the function impure. Should we document this more prominently? (Answer: yes, in docstring, but don't change behavior.)

## Recommended Architecture

### Extraction Strategy: Copy-Delegate-Verify

1. **Create 4 new phase files** with standalone async functions extracted from pipeline.py
2. **Replace `self._*` references** with explicit parameters (services + config slices)
3. **Thin wrappers on ScanPipeline** — `_phase_universe()`, `_phase_scoring()`, `_phase_options()`, `_phase_persist()`, `_process_ticker_options()` become 1-line delegations to the extracted functions
4. **Update `run()` method** to call extracted functions directly (bypassing wrappers)
5. **Move `_PHASE3_FIELDS` and helpers** to `phase_options.py`, update 1 test import
6. **`_make_cancelled_result()` stays on `ScanPipeline`** — needs `self._settings.pricing.risk_free_rate_fallback`

### Import Structure for New Modules

| Module | Stdlib | Third-party | Local |
|--------|--------|-------------|-------|
| `phase_universe.py` | `asyncio`, `logging` | — | `models` (enums, config), `services` (Universe, MarketData), `data` (Repository), `scan.models`, `scan.progress`, `scan.indicators`, `services.universe` |
| `phase_scoring.py` | `logging` | — | `models` (config), `scoring` (6 functions), `scan.models`, `scan.progress`, `scan.indicators` |
| `phase_options.py` | `asyncio`, `logging`, `math`, `datetime`, `decimal`, `zoneinfo` | `numpy`, `pandas` | `models` (many), `services` (Fred, MarketData, Options, universe helper), `data` (Repository), `scoring` (5 functions), `indicators.options_specific`, `scan.models`, `scan.progress`, `scan.indicators` |
| `phase_persist.py` | `logging`, `datetime`, `decimal` | — | `models` (many), `data` (Repository), `scan.models`, `scan.progress` |

### Estimated File Sizes

| File | After Extraction |
|------|-----------------|
| `pipeline.py` | ~170 LOC (class + run + wrappers + cancelled) |
| `phase_universe.py` | ~240 LOC |
| `phase_scoring.py` | ~120 LOC |
| `phase_options.py` | ~560 LOC |
| `phase_persist.py` | ~180 LOC |

## Test Strategy Preview

### Existing Test Patterns
- 312 scan tests across 22 files (21 unit + 1 integration)
- `_make_pipeline()` factory in each test file — constructs `ScanPipeline` with 5 `AsyncMock` services
- Direct `pipeline._phase_*()` calls for phase-level testing
- Monkey-patching for cancellation injection
- Full `pipeline.run()` for integration-level testing

### What Changes
- **0 test file modifications** with the thin wrapper approach
- **1 import change**: `test_phase3_fields.py` updates import path for `_PHASE3_FIELDS`

### Verification Commands
```bash
uv run ruff check src/options_arena/scan/ --fix && uv run ruff format src/options_arena/scan/
uv run mypy src/options_arena/scan/ --strict
uv run pytest tests/unit/scan/ -n auto -q          # 290+ unit tests
uv run pytest tests/integration/scan/ -n auto -q   # integration tests
uv run pytest tests/ -n auto -q                    # full suite
```

## Estimated Complexity

**Medium (M)** — Pure mechanical extraction with no logic changes. The complexity comes from:
- Volume: ~1,200 LOC to relocate across 4 new files
- Import surgery: each phase needs its own import block from 5+ modules
- Thin wrappers: 5 delegation methods to maintain backward compat
- Phase 3 is the largest single extraction (~560 LOC) with the most helpers
- Risk of subtle `self._*` reference misses (mitigated by mypy --strict)

No new abstractions, no behavior changes, no new dependencies. Mypy --strict will catch any missed parameter conversions.
