---
name: pipeline-phase-extraction
status: active
created: 2026-03-09T19:02:47Z
updated: 2026-03-09T19:11:03Z
progress: 0%
prd: .claude/prds/pipeline-phase-extraction.md
github: https://github.com/jobu711/options_arena/issues/423
---

# Epic: pipeline-phase-extraction

## Overview

Pure mechanical refactoring: extract `ScanPipeline`'s 4 phase methods (1,362 LOC) into standalone
async functions in 4 dedicated modules. The orchestrator shrinks to ~170 LOC with thin delegation
wrappers preserving backward compatibility for ~110+ existing test calls. Zero behavior change.

## Architecture Decisions

1. **Standalone async functions, not classes** — phases are stateless; functions with explicit
   parameters are simpler, more composable, and directly testable without constructing `ScanPipeline`.

2. **Thin delegation wrappers on ScanPipeline** — 13 test files make ~110+ direct calls to
   `pipeline._phase_*()` methods. Keeping 1-line wrappers on the class avoids mass test rewriting.
   The `run()` method calls standalone functions directly (bypasses wrappers).

3. **Config slices over full AppSettings** — each phase receives only `ScanConfig` and/or
   `PricingConfig`, not the full `AppSettings`. Aligns with DI pattern in CLAUDE.md.

4. **Helpers colocated with their caller** — `_PHASE3_FIELDS`, `_extract_mp_strike()`,
   `_merge_signals()`, `_normalize_phase3_signals()`, `_recompute_composite_scores()`,
   `_recompute_dimensional_scores()`, and `_REGIME_*` constants all move to `phase_options.py`.

5. **`_make_cancelled_result()` stays on ScanPipeline** — it needs `self._settings.pricing.risk_free_rate_fallback`.

6. **Cross-phase concerns stay in `run()`** — direction filter, earnings date propagation,
   cancellation checks are orchestrator responsibilities, not phase responsibilities.

## Technical Approach

### New Files

| File | Public Function | ~LOC | Extracted From |
|------|----------------|------|----------------|
| `scan/phase_universe.py` | `run_universe_phase()` | ~240 | `_phase_universe` (lines 204-433) |
| `scan/phase_scoring.py` | `run_scoring_phase()` | ~120 | `_phase_scoring` (lines 435-543) |
| `scan/phase_options.py` | `run_options_phase()`, `process_ticker_options()` + 5 helpers + constants | ~560 | `_phase_options` (545-720), `_process_ticker_options` (722-889), helpers (1122-1362) |
| `scan/phase_persist.py` | `run_persist_phase()` | ~180 | `_phase_persist` (lines 891-1056) |

### Modified Files

| File | Change |
|------|--------|
| `scan/pipeline.py` | Shrink from 1,362 → ~170 LOC: `__init__`, `run()`, `_make_cancelled_result()`, 5 thin wrappers |
| `tests/unit/scan/test_phase3_fields.py` | 1 import change: `_PHASE3_FIELDS` from `phase_options` instead of `pipeline` |

### Unchanged Files

`scan/__init__.py`, `scan/models.py`, `scan/progress.py`, `scan/indicators.py`, all other test files.

### Function Signature Pattern

```python
async def run_universe_phase(
    preset: ScanPreset,           # positional: primary data
    progress: ProgressCallback,   # positional: callback
    *,
    universe: UniverseService,    # keyword-only: injected deps
    market_data: MarketDataService,
    repository: Repository,
    scan_config: ScanConfig,
) -> UniverseResult: ...
```

### Thin Wrapper Pattern

```python
# In ScanPipeline (preserves test backward compat)
async def _phase_universe(self, preset: ScanPreset, progress: ProgressCallback) -> UniverseResult:
    return await run_universe_phase(
        preset, progress,
        universe=self._universe, market_data=self._market_data,
        repository=self._repository, scan_config=self._settings.scan,
    )
```

## Implementation Strategy

Sequential extraction — each task creates a new phase file, adds the thin wrapper to
`pipeline.py`, and verifies scan tests still pass before proceeding. Phase 3 (options) is
isolated as its own task due to size (~560 LOC, 7 helpers). Final task slims the orchestrator
and runs full verification.

### Risk Mitigation

- **mypy --strict** catches any missed `self._*` → explicit parameter conversions
- **Thin wrappers** ensure 0 test modifications (except 1 import)
- **Per-task test runs** catch regressions immediately, not at the end
- **No logic changes** — pure code relocation with parameter substitution

## Task Breakdown Preview

- [ ] Task 1: Extract `phase_universe.py` and `phase_scoring.py` (simpler phases, ~360 LOC combined)
- [ ] Task 2: Extract `phase_options.py` with all helpers and constants (~560 LOC, largest extraction)
- [ ] Task 3: Extract `phase_persist.py` (~180 LOC)
- [ ] Task 4: Slim `pipeline.py` to orchestrator — update `run()`, remove dead code, add thin wrappers
- [ ] Task 5: Fix `_PHASE3_FIELDS` test import, run full verification (ruff + mypy + all tests), update `scan/CLAUDE.md`

Tasks 1-3 create the new files. Task 4 transforms pipeline.py. Task 5 is the quality gate.

## Tasks Created

- [ ] #424 - Extract phase_universe.py and phase_scoring.py (parallel: false)
- [ ] #425 - Extract phase_options.py with helpers and constants (parallel: false, depends: #424)
- [ ] #426 - Extract phase_persist.py (parallel: true, depends: #424)
- [ ] #427 - Slim pipeline.py to orchestrator with thin wrappers (parallel: false, depends: #424, #425, #426)
- [ ] #428 - Fix test import, full verification, update scan/CLAUDE.md (parallel: false, depends: #427)

Total tasks: 5
Parallel tasks: 1 (003 can run alongside 002)
Sequential tasks: 4
Estimated total effort: 10-14 hours

## Test Coverage Plan

Total test files planned: 1 (import fix in test_phase3_fields.py)
Total test cases planned: 0 new (312+ existing scan tests serve as regression suite)

## Dependencies

- **No external dependencies** — only existing imports redistributed across files
- **Internal**: `scan/models.py` (result types), `scan/progress.py` (ScanPhase, callbacks), `scan/indicators.py` (compute functions), `scoring/` (6+ functions), `services/` (5 service types), `data/` (Repository)
- **Blocking**: None — all prerequisite code is stable

## Success Criteria (Technical)

- `pipeline.py` < 200 LOC
- 4 new phase files, each containing one public async function
- All ~312 scan tests pass unchanged (except 1 import fix)
- `mypy --strict` clean on all `scan/` files
- `ruff check` + `ruff format` clean
- Full test suite passes (`uv run pytest tests/ -n auto -q`)
- No behavior change in scan output

## Estimated Effort

- **Size**: Medium (M)
- **LOC moved**: ~1,200 across 4 new files
- **LOC modified**: ~170 in pipeline.py (slim down) + 1 line in test
- **Risk**: Low — mechanical extraction, no logic changes, mypy catches parameter misses
- **Critical path**: Task 2 (Phase 3 extraction) is the largest single unit
