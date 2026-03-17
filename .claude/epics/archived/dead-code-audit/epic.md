---
name: dead-code-audit
status: completed
created: 2026-03-16T22:16:47Z
updated: 2026-03-17T02:30:00Z
completed: 2026-03-17T02:30:00Z
progress: 100%
prd: .claude/prds/dead-code-audit.md
github: https://github.com/jobu711/options_arena/issues/557
---

# Epic: dead-code-audit

## Overview

Remove ~1,720 lines of dead code across 17 modules, wire 10+ never-connected indicator functions into the scan pipeline, and modernize the `DebatePhase` enum to match the 6-agent protocol. Waves 1-3 are pure subtraction (zero behavioral change). Wave 4 is additive — connecting existing indicator code and fixing WebSocket progress reporting.

## Research Corrections Applied

Research (`.claude/epics/dead-code-audit/research.md`) identified 5 critical PRD corrections incorporated into this plan:

1. **`spread_analysis` and `constraint_warnings` are LIVE** — must NOT be removed from `DebateDeps`
2. **`DebateResult` backward-compat shims** (`bull_response`, `bear_response`, `bull_rebuttal`, `vol_response`) are serialized to SQLite — only remove `DebateDeps` counterparts (`opponent_argument`, `bear_counter_argument`), leave `DebateResult` fields intact
3. **Function name is `hurst_exponent()`** not `compute_hurst_exponent()` — use correct name
4. **`BatchOHLCVResult`/`TickerOHLCVResult` re-exports are used** by `scan/phase_universe.py` — do NOT remove
5. **`RateLimitExceededError`** has a registered FastAPI handler — remove both together

## Architecture Decisions

- **Sequential waves, not parallel**: Despite Waves 1-3 being logically independent, execute sequentially to avoid merge conflicts in overlapping `__init__.py` files
- **Groups A/B deferred**: VIX/cross-asset indicators (Group A) and sector ETF indicators (Group B) require new data plumbing in services — deferred to a future epic. Only Groups C/D (data already available in Phase 3) are wired here
- **Clustering deleted, not moved**: `scoring/clustering.py` deleted outright per PRD preference — if needed later, re-implement with pipeline-aware design
- **DebateResult fields preserved**: Keep `bull_response`/`bear_response` field names on `DebateResult` for DB backward compatibility — only clean `DebateDeps`
- **`put_call_ratio_oi` kept in exports**: Wave 3 skips removing this export since Wave 4 wires it into the pipeline

## Technical Approach

### Deletion Safety Protocol (Waves 1-3)
For each deletion:
1. Grep all references in `src/` (non-test) — verify zero callers
2. Grep all references in `tests/` — identify test code to co-delete
3. Delete source + update `__init__.py` re-exports
4. Delete corresponding tests
5. Run `ruff check`, `mypy --strict`, `pytest -m critical`

### Indicator Wiring Pattern (Wave 4)
- **Phase 2 indicators**: Add `IndicatorSpec` entry to `INDICATOR_REGISTRY` in `scan/indicators.py`
- **Phase 3 indicators**: Add calls in `compute_phase3_indicators()` in `scan/phase_options.py`
- Each wired indicator: computation call → guard None → set `IndicatorSignals` field
- Verify DOMAIN_BOUNDS entry exists in `scoring/normalization.py`
- Verify INDICATOR_WEIGHTS entry exists in `scoring/composite.py` (if weight desired)

### DebatePhase Modernization (Wave 4)
- Replace 5-member enum with 6 members: TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN
- Wire `_progress` callback invocation before each agent run in `_run_debate_pipeline()`
- Update WebSocket message types in `api/ws.py`

## Implementation Strategy

### Risk Mitigation
- Each wave is an atomic commit with all tests green
- Research corrections prevent removing live code (`spread_analysis`, `constraint_warnings`)
- DebateResult DB fields preserved to avoid migration burden
- Groups A/B deferred to avoid scope creep from data plumbing

### Testing Approach
- **Delete tests for deleted code** (~1,100 lines across test_bull.py, test_bear.py, test_clustering.py, and others)
- **Update tests** for modified interfaces (DebateDeps field removal, SpreadType member count, DebatePhase members)
- **Add tests** for newly wired indicators and DebatePhase progress events (~200 lines)
- **Verification after each task**: `ruff check`, `mypy --strict`, `pytest -m "not exhaustive" -n auto -q`

## Task Breakdown Preview

- [ ] Task 1: Legacy debate removal (Wave 1) — delete bull/bear agents, clean DebateDeps, remove dead agent blocks
- [ ] Task 2: Dead function removal (Wave 2) — delete clustering.py, dead repo methods, dead helpers, predict_iv, dead config fields
- [ ] Task 3: Re-export cleanup (Wave 3) — clean __init__.py exports, extract sentinel constant, deduplicate classify_market_cap
- [ ] Task 4: Wire Phase 2 indicators — add hurst_exponent to INDICATOR_REGISTRY
- [ ] Task 5: Wire Phase 3 indicators (Groups C/D) — pop, optimal_dte, spread_quality, max_loss_ratio, flow_anomalies, short_interest, put_skew, call_skew, skew_ratio, put_call_ratio_oi
- [ ] Task 6: Modernize DebatePhase enum — 6 members matching protocol, wire progress callback, update WebSocket types

## Dependencies

- **complexity-reduction PRD**: Items covered there (OpenBB removal, EGARCH, HV estimators, classify_market_regime) are excluded from scope. No ordering dependency — can run independently.
- **No external dependencies**: No new packages. All indicator functions already exist. All model fields already exist.

## Deferred to Future Work

- **Group A indicators** (VIX term structure, risk-on/off, VIX correlation) — need VIX/HYG/LQD data fetching
- **Group B indicators** (sector momentum) — need sector ETF price fetching
- **DebateResult field rename** (`bull_response` → `trend_response`) — needs DB migration
- **CLAUDE.md updates** for affected modules — should be done as part of each task but is not a blocking concern
- **Adding composite weights** for newly-wired indicators — separate evaluation after data collection

## Success Criteria (Technical)

1. All tests pass after each task
2. `mypy --strict` clean after each task
3. No function exported from any `__init__.py` has zero pipeline/API call sites (verified by grep)
4. `bull.py`, `bear.py`, `prompts/bull.py`, `prompts/bear.py` do not exist
5. `scoring/clustering.py` does not exist
6. `DebateDeps` has only `opponent_argument` and `bear_counter_argument` removed (not `spread_analysis` or `constraint_warnings`)
7. `hurst_exponent` and Group C/D indicators produce values during scans
8. `DebatePhase` has exactly 6 members: TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN
9. WebSocket debate progress reports per-agent phase names

## Tasks Created

- [ ] #558 - Legacy debate removal (Wave 1) (parallel: false)
- [ ] #559 - Dead function removal (Wave 2) (parallel: false, depends: #558)
- [ ] #560 - Re-export cleanup and deduplication (Wave 3) (parallel: false, depends: #558, #559)
- [ ] #561 - Wire hurst_exponent into Phase 2 (parallel: true, depends: #558-#560)
- [ ] #562 - Wire Phase 3 indicators, Groups C/D (parallel: true, depends: #558-#560)
- [ ] #563 - Modernize DebatePhase enum + progress callback (parallel: true, depends: #558-#560)

Total tasks: 6
Sequential tasks: 3 (Waves 1-3)
Parallel tasks: 3 (Wave 4a/4b/4c — can run concurrently after Waves 1-3)
Estimated total effort: 14-22 hours

## Test Coverage Plan

Total test files planned: ~30 (delete 3, modify ~24, add ~3)
Total test cases planned: ~15 new tests across tasks 4-6
Test lines deleted: ~1,900 (across deleted files and removed blocks)

## Estimated Effort

- **Wave 1**: Medium — 10+ files touched, but all deletions with clear grep verification
- **Wave 2**: Medium — similar scope, independent deletions
- **Wave 3**: Small — minor cleanup across __init__.py files
- **Wave 4 (tasks 4-6)**: Medium — indicator wiring follows established patterns, DebatePhase is straightforward enum change
- **Total**: 6 tasks, estimated 2-3 sessions
- **Critical path**: Waves 1-3 → Wave 4 (Waves 1-3 must complete before Wave 4 starts)
