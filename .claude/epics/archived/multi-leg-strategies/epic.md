---
name: multi-leg-strategies
status: backlog
created: 2026-03-15T13:55:55Z
progress: 0%
prd: .claude/prds/multi-leg-strategies.md
github: https://github.com/jobu711/options_arena/issues/515
---

# Epic: multi-leg-strategies

## Overview

Add multi-leg option strategy construction, P&L analytics, and IV-regime-based selection to Options Arena. The existing `SpreadLeg`, `OptionSpread`, and `SpreadType` models are defined but unused. This epic builds the engine that constructs, prices, and selects strategies (vertical spreads, iron condors, straddles, strangles), then integrates them into the scan pipeline, debate agents, persistence layer, and presentation stack.

Zero new dependencies. Two new files (`pricing/spreads.py`, `scoring/spreads.py`). ~65 new tests.

## Architecture Decisions

- **`SpreadAnalysis` model** in `models/options.py` — frozen Pydantic model with Decimal prices, float Greeks/ratios, validators. Sits alongside existing `SpreadLeg`/`OptionSpread`.
- **`SpreadConfig` model** in `models/config.py` — new `BaseModel` nested under `AppSettings` for spread width/delta parameters. Env-overridable via `ARENA_SPREAD__*`.
- **`pricing/spreads.py`** — pure Greeks aggregation only. Imports `models/` only.
- **`scoring/spreads.py`** — construction functions + selection engine. Imports `models/` + `pricing/dispatch` only (never `bsm`/`american` directly).
- **Algorithmic > LLM precedence** — the algorithmic engine's recommendation takes priority over the Volatility Agent's LLM-generated `recommended_strategy` since it has actual constructed legs. LLM output becomes secondary agreement signal.
- **Persistence** — migration 033 adds `spread_recommendations` + `spread_legs` tables. Enables outcome tracking matching single-leg pattern.
- **Graceful fallback** — every construction function returns `None` when insufficient contracts. Pipeline falls back to single-contract seamlessly.

## Technical Approach

### Data Flow

```
Phase 3 (phase_options.py)
  └─ _recommend() → single OptionContract (existing, unchanged)
  └─ select_strategy() [NEW] → SpreadAnalysis | None
       ├─ classify_vol_regime(iv_rank) → VolRegime (existing)
       ├─ direction + confidence → strategy type decision tree
       ├─ build_vertical / build_iron_condor / build_straddle / build_strangle
       │    └─ reuse filter_contracts() for candidate leg pools
       │    └─ aggregate_spread_greeks() from pricing/spreads.py
       │    └─ compute P&L, breakevens, PoP (BSM N(d2))
       └─ return SpreadAnalysis or None (fallback to single contract)

Phase 4 (phase_persist.py)
  └─ persist SpreadAnalysis via migration 033 tables

Debate (orchestrator.py)
  └─ SpreadAnalysis passed via DebateDeps
  └─ Flat spread fields on MarketContext → agent prompts
  └─ TradeThesis.recommended_strategy set from algorithmic result
```

### Module Boundaries (Verified Against CLAUDE.md)

| New Code | Imports | Cannot Import |
|----------|---------|---------------|
| `pricing/spreads.py` | `models/` | services, pandas, scoring, bsm, american |
| `scoring/spreads.py` | `models/`, `pricing/dispatch` | services, bsm, american directly |
| `scan/phase_options.py` (modified) | `scoring/spreads` | `pricing/` directly |
| `agents/` (modified) | receives pre-computed `SpreadAnalysis` | pricing, scoring |

### Strategy Selection Decision Tree (FR-S4)

| IV Rank | Direction | Confidence | Strategy |
|---------|-----------|------------|----------|
| >50 | NEUTRAL | any | Iron Condor |
| >50 | BULLISH/BEARISH | any | Vertical Credit Spread |
| <25 | BULLISH/BEARISH | any | Vertical Debit Spread |
| >50 | any | <0.4 | Strangle |
| 25-50 or None | any | any | None (single contract) |

Falls through in priority order — if iron condor can't be built, try vertical, etc.

## Implementation Strategy

Six tasks in dependency order. Tasks 1-2 are foundation (parallel). Task 3 depends on 1-2. Tasks 4-5 depend on 3. Task 6 depends on 4-5.

### Dependency Graph

```
[1] Models + Config ──┐
                      ├──→ [3] Construction + Selection ──→ [4] Pipeline + Persistence ──→ [6] Presentation
[2] Greeks Aggregation┘                                  → [5] Agent Integration ─────────┘
```

### Testing Approach

- Extend `tests/factories.py` with `make_spread_leg()` and `make_spread_analysis()` helpers
- Greeks aggregation: sign correctness, second-order handling, missing-Greeks skip
- Construction: P&L formula verification per strategy type, breakeven math, PoP bounds
- Selection: IV regime → strategy type mapping, fallback cascade, None for mid-IV
- Edge cases: insufficient contracts, zero-width, missing Greeks, None iv_rank
- Integration: pipeline produces spreads alongside single contracts, persistence round-trip

## Task Breakdown Preview

- [ ] Task 1: `SpreadAnalysis` model + `SpreadConfig` + re-exports + model tests
- [ ] Task 2: `pricing/spreads.py` — `aggregate_spread_greeks()` + tests
- [ ] Task 3: `scoring/spreads.py` — 4 construction functions + `select_strategy()` + P&L + PoP + tests
- [ ] Task 4: Pipeline integration + persistence (phase_options hook, migration 033, repository, phase_persist)
- [ ] Task 5: Agent integration (DebateDeps, MarketContext fields, prompt enrichment for Vol + Risk agents)
- [ ] Task 6: Presentation (API schemas, CLI rendering, debate export, frontend spread display)

## Dependencies

### Internal (all satisfied)
- `SpreadLeg`, `OptionSpread`, `SpreadType`, `PositionSide` — exist in `models/`
- `OptionGreeks` with second-order (vanna, charm, vomma) — exist from native-quant epic
- `filter_contracts()`, `compute_greeks()`, `select_by_delta()` — exist in `scoring/contracts.py`
- `classify_vol_regime()` — exists in `indicators/iv_analytics.py`
- `pricing/dispatch.option_greeks()` — exists

### External
- None. All algorithms use existing numpy/scipy/Decimal stack.

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| P&L formulas correct | 100% of 5 strategy types verified by tests |
| Greeks aggregation signs | Cross-checked against manual calculation |
| PoP estimates | Within [0, 1], BSM-consistent |
| Graceful fallback | 100% — never errors on insufficient data |
| Existing test suite | 0 regressions |
| New tests | ~65 across 3 test files |
| Strategy produced | >50% of tickers with liquid chains |
| Construction time | <50ms per ticker |

## Tasks Created
- [ ] #516 - SpreadAnalysis Model + SpreadConfig + Re-exports (parallel: true)
- [ ] #518 - Greeks Aggregation Module (parallel: true)
- [ ] #520 - Strategy Construction + Selection Engine (parallel: false)
- [ ] #517 - Pipeline Integration + Persistence (parallel: false)
- [ ] #519 - Agent Integration (parallel: true)
- [ ] #521 - Presentation Layer (parallel: false)

Total tasks: 6
Parallel tasks: 3 (#516, #518, #519)
Sequential tasks: 3 (#520, #517, #521)
Estimated total effort: 32-40 hours

## Test Coverage Plan
Total test files planned: 7
Total test cases planned: ~75

| Task | Test File | Est. Tests |
|------|-----------|------------|
| 001 | tests/unit/models/test_spread_analysis.py | ~10 |
| 002 | tests/unit/pricing/test_spreads.py | ~15 |
| 003 | tests/unit/scoring/test_spreads.py | ~35 |
| 004 | tests/unit/scan/test_spread_pipeline.py, tests/unit/data/test_spread_persistence.py | ~10 |
| 005 | tests/unit/agents/test_spread_integration.py | ~10 |
| 006 | tests/unit/api/test_spread_schemas.py, tests/unit/cli/test_spread_rendering.py | ~8 |

## Estimated Effort

- **Size**: L (Large) — 6 tasks, 2 new files, ~11 modified files, ~75 new tests
- **Critical path**: Task 1 → Task 3 → Task 4 → Task 6
- **Risk**: Low — straightforward arithmetic on pre-computed data, no new external dependencies, existing infrastructure is 80% ready
- **Comparable**: Similar scope to native-quant epic (also L)
