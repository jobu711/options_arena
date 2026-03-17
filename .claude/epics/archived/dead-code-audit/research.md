# Research: dead-code-audit

## PRD Summary

Remove ~1,720 lines of dead code across 17 modules in 4 waves: legacy bull/bear debate removal (Wave 1), dead function deletion (Wave 2), re-export cleanup (Wave 3), and indicator wiring + DebatePhase modernization (Wave 4). Waves 1-3 are pure subtraction; Wave 4 is additive.

## Critical PRD Corrections

Research uncovered several items the PRD marks as dead that are **actually live**:

### 1. DebateDeps Fields — Mixed Dead/Live Status

The PRD claims 8 `DebateDeps` fields are dead: `opponent_argument`, `bear_counter_argument`, `bull_response`, `bear_response`, `bull_rebuttal`, `vol_response`, `spread_analysis`, `constraint_warnings`.

**Actually dead on DebateDeps** (set only for legacy bull/bear agents that are being deleted):
- `opponent_argument` — passed to bear agent only
- `bear_counter_argument` — passed to bull rebuttal only

**Repurposed as backward-compat shims** (used by `DebateResult`, serialized to DB, rendered in CLI/API):
- `bull_response` — `DebateResult.bull_response` holds trend agent output (backward-compat shim)
- `bear_response` — `DebateResult.bear_response` is a static fallback
- `bull_rebuttal` — `DebateResult.bull_rebuttal` set to `None` in 6-agent path
- `vol_response` — `DebateResult.vol_response` duplicates `volatility_thesis`

**Actively used** (NOT dead):
- `spread_analysis` — set by orchestrator (lines 1440, 1514-1520, 1623), read in phase_options
- `constraint_warnings` — set via `render_constraint_warnings()`, injected into all agent prompts

**Recommendation**: Only remove `opponent_argument` and `bear_counter_argument` from `DebateDeps` in Wave 1. The `bull_response`/`bear_response`/`bull_rebuttal`/`vol_response` fields on `DebateResult` need a migration plan (DB backward compat). `spread_analysis` and `constraint_warnings` must NOT be removed.

### 2. RateLimitExceededError — NOT Dead

Registered as FastAPI exception handler in `api/app.py` (lines 288, 312-313). Never raised currently, but the handler is a valid consumer. Removing it requires removing the handler too — but the PRD already plans this.

### 3. compute_hurst_exponent — Function Name Mismatch

`compute_hurst_exponent` does not exist as a callable. The actual function is `hurst_exponent()` in `indicators/hurst.py`, exported from `indicators/__init__.py`. The field on `IndicatorSignals` is `hurst_exponent`. The composite weight (0.01) exists. Only the wiring call in `scan/indicators.py` is missing.

### 4. BatchOHLCVResult/TickerOHLCVResult Re-exports — NOT Safe to Remove

The PRD's Wave 3 proposes removing these from `services/__init__.py`, but `scan/phase_universe.py` imports them from the package. Verify import path before removing.

## Relevant Existing Modules

| Module | Relevance | Files Affected |
|--------|-----------|----------------|
| `agents/` | Wave 1: delete bull.py, bear.py, prompts/bull.py, prompts/bear.py; clean DebateDeps, orchestrator, volatility, flow, fundamental agents | 10+ files |
| `scoring/` | Wave 2: delete clustering.py; clean dimensional.py, __init__.py | 3 files |
| `services/` | Wave 2: delete helpers.py::fetch_with_retry, market_data dead functions; Wave 3: clean __init__.py | 3 files |
| `pricing/` | Wave 2: delete neural_surface.py::predict_iv | 1 file |
| `models/` | Wave 1: clean config.py, analysis.py, openbb.py, enums.py | 4 files |
| `data/` | Wave 2: delete 6 repository methods across 4 mixin files | 4 files |
| `api/` | Wave 1: clean deps.py, schemas.py, app.py | 3 files |
| `indicators/` | Wave 3: clean __init__.py; Wave 4: wire 16 functions | 2 files |
| `scan/` | Wave 4: wire indicators in phase_scoring.py and phase_options.py | 2 files |
| `reporting/` | Wave 3: extract shared sentinel constant | 1 file |
| `utils/` | Wave 2: delete RateLimitExceededError | 1 file |
| `analysis/` | Wave 3: clean __init__.py re-exports | 1 file |

## Existing Patterns to Reuse

### 1. Indicator Wiring Pattern (scan/indicators.py)
```python
INDICATOR_REGISTRY: list[IndicatorSpec] = [
    IndicatorSpec("rsi", rsi, InputShape.CLOSE),
    # ... 15 entries
]
```
To wire `hurst_exponent`: add `IndicatorSpec("hurst_exponent", hurst_exponent, InputShape.CLOSE)` to registry. For Phase 3 indicators: add calls in `compute_phase3_indicators()` in `scan/phase_options.py`.

### 2. Phase 3 Indicator Pattern (scan/phase_options.py)
Phase 3 indicators that need chain data follow the `compute_phase3_indicators()` pattern — receives contracts, spot, close_series, and other Phase 3 context. Results merged by copying non-None fields to `IndicatorSignals`.

### 3. Module Re-export Pattern (__init__.py)
Each package `__init__.py` re-exports public API. When deleting a function, must update both the source file and the `__init__.py` re-export.

### 4. Repository Mixin Pattern (data/)
Dead repository methods live in mixin files (`_scan.py`, `_analytics.py`, `_metadata.py`, `_spreads.py`). Delete methods individually; no need to touch `Repository` class composition.

## Existing Code to Extend

### scan/indicators.py — INDICATOR_REGISTRY
Currently 15 entries. Wave 4a adds `hurst_exponent` (trivial — field, weight, bounds all exist).

### scan/phase_options.py — compute_phase3_indicators()
Wave 4b Group C/D indicators wire here. Pattern: call indicator function, guard None, `setattr(signals, field_name, value)`.

### scoring/composite.py — INDICATOR_WEIGHTS
Currently 27 entries summing to 1.0. New indicators need weights added and sum rebalanced. Import-time guard enforces `sum == 1.0`.

### scoring/normalization.py — DOMAIN_BOUNDS
Per-indicator normalization bounds. New indicators need entries.

### agents/orchestrator.py — DebatePhase enum + progress callback
`DebatePhase` at line 96 (5 members). `DebateProgressCallback` type alias at line 106. `run_debate()` accepts `progress` param but never invokes it. Wave 4c adds 6 correct members and wires invocations.

## Potential Conflicts

### 1. DebateResult DB Backward Compatibility
`DebateResult.bull_response` (trend output shim) and `DebateResult.bear_response` (static fallback) are serialized to SQLite. Old debate results in the DB reference these field names. Renaming/removing requires either: (a) migration to rename columns, or (b) keeping field names as-is and only removing the DebateDeps counterparts.

### 2. Wave 3 Re-export Removal vs Wave 4 Wiring Order
`put_call_ratio_oi` is exported from `indicators/__init__.py`. Wave 3 wants to remove the export. Wave 4 wants to wire it into the pipeline. If Wave 3 runs first and removes the export, Wave 4 must re-add it. **Recommendation**: Skip removing `put_call_ratio_oi` export in Wave 3; let Wave 4 wire it.

### 3. Composite Weight Rebalancing
Wiring `hurst_exponent` (weight 0.01, currently silently redistributed) will change composite scores by up to 0.01. Tests asserting exact composite scores may need tolerance adjustment.

### 4. SpreadType Member Count Assertion
`tests/unit/models/test_enums.py` asserts exact `SpreadType` member count (6). Removing `CALENDAR` and `BUTTERFLY` changes count to 4. Test must be updated in same commit.

### 5. CLAUDE.md Staleness
Multiple module CLAUDE.md files are stale:
- `agents/CLAUDE.md` lists 8 agents (includes bull/bear)
- `models/CLAUDE.md` says 18 IndicatorSignals fields (actual: 73)
- `data/CLAUDE.md` shows simplified Repository
- `reporting/CLAUDE.md` describes files that don't match reality
These should be updated as part of each wave.

## Open Questions

1. **DebateResult backward compat**: Should `bull_response`/`bear_response` fields on `DebateResult` be renamed to `trend_response`/`static_fallback` with a DB migration, or kept as-is with only `DebateDeps` cleaned up?

2. **Wave 4b data plumbing scope**: Group A indicators (VIX term structure, risk-on/off, VIX correlation) require fetching VIX/HYG/LQD data in services. Group B (sector momentum) needs sector ETF prices. Is data plumbing in scope, or should these be deferred to a separate epic?

3. **Clustering module fate**: PRD prefers deletion over move-to-analysis. Confirm no future plans to revive clustering-based contract selection?

4. **RateLimitExceededError**: Remove the exception AND its FastAPI handler together (as PRD plans), or keep both as defensive infrastructure?

5. **DebatePhase progress events**: The callback type exists but is never invoked. Should Wave 4c wire real progress events into the orchestrator pipeline, or just modernize the enum members?

## Recommended Architecture

### Wave Execution Strategy
- **Waves 1-3**: Execute sequentially (not parallel) despite PRD saying they're independent. Reason: overlapping `__init__.py` edits in scoring/ and services/ could cause merge conflicts.
- **Wave 4a**: Quick win after Waves 1-3 — single `IndicatorSpec` addition.
- **Wave 4b**: Decompose by data dependency group (C/D first since data is available, A/B deferred if data plumbing is out of scope).
- **Wave 4c**: Independent of 4a/4b, can run in parallel.

### Deletion Safety Protocol
For each deletion:
1. Grep for all references in `src/` (non-test)
2. Grep for all references in `tests/`
3. Delete source code + update `__init__.py` exports
4. Delete corresponding test code
5. Run `ruff check`, `mypy --strict`, `pytest -m critical`

## Test Strategy Preview

### Existing Patterns
- Unit tests in `tests/unit/{module}/test_{file}.py`
- Audit tests in `tests/audit/{type}/test_{module}_{type}.py`
- Conftest fixtures build `DebateDeps`, `IndicatorSignals`, etc. — must be updated when fields change
- `pytest.mark.critical` for pre-commit gate tests

### Tests to Delete (Waves 1-2, ~1,100 lines estimated)
- `tests/unit/agents/test_bull.py` (203 lines)
- `tests/unit/agents/test_bear.py` (186 lines)
- `tests/unit/scoring/test_clustering.py` (370 lines)
- Tests for `build_cleaned_trade_thesis` in `test_prompt_enhancements.py`
- Tests for `_opposite_direction` (none found — untested)
- Tests for `fetch_with_retry` in `test_helpers.py`
- Tests for `predict_iv` in `test_neural_surface.py`
- Tests for 6 dead repository methods across `test_repository_*.py` files
- Tests for `SectorInfo` in `test_schemas.py`
- Tests for `OpenBBHealthStatus` in `test_openbb_models.py`
- Tests for dead `MarketContext` methods
- Tests for `IntelligencePackage.intelligence_completeness()`

### Tests to Update
- `test_parsing.py` lines 720-728 (DebatePhase member assertions)
- `test_enums.py` (SpreadType member count)
- Agent conftest fixtures (DebateDeps field removal)
- `test_orchestrator_v2.py`, `test_orchestrator_wiring.py` (DebateDeps changes)

### Tests to Add (Wave 4, ~200 lines estimated)
- Integration: `hurst_exponent` populated during scan
- Integration: each Group C/D indicator produces non-None output
- Unit: `DebatePhase` has exactly 6 members
- Integration: WebSocket debate progress emits all 6 phase events

## Estimated Complexity

**XL** — Justified by:
- 17 modules touched across 30+ source files
- ~1,100 lines of test deletion + ~200 lines of test addition
- DB backward compatibility concern for DebateResult fields
- Composite weight rebalancing with sum-to-1.0 constraint
- 16 indicator wiring with 4 different data dependency groups
- Multiple CLAUDE.md files need updating
- High risk of cascading failures if deletion order is wrong

Recommend decomposing into 6 GitHub issues (one per wave, Wave 4 split into 4a/4b/4c).
