---
name: native-quant
status: completed
created: 2026-03-13T18:57:46Z
completed: 2026-03-13T23:45:00Z
progress: 100%
prd: .claude/prds/native-quant.md
github: https://github.com/jobu711/options_arena/issues/485
---

# Epic: native-quant

## Overview

Native reimplementation of three quantitative finance capabilities using existing numpy/scipy/pandas — zero new dependencies. Adds Yang-Zhang/Parkinson/Rogers-Satchell HV estimators, second-order Greeks (vanna/charm/vomma) via BSM analytical + BAW finite-difference, and volatility surface analytics (skew, curvature, implied probability). All integrate into the scan pipeline, debate agent prompts, and API.

## Architecture Decisions

- **HV estimators in `indicators/hv_estimators.py`**: Pure math following existing indicator pattern — pandas in, `float | None` out, `math.isfinite()` guard. Only `hv_yang_zhang` flows to `IndicatorSignals`/`MarketContext`; Parkinson/RS are library functions.
- **Second-order Greeks extend existing pricing pattern**: BSM gets analytical closed-form formulas reusing `_d1_d2()` helper. BAW gets finite-difference cross-bumps using existing bump constants. New `option_second_order_greeks()` in dispatch follows identical match-routing pattern.
- **`OptionGreeks` extension is additive**: `vanna/charm/vomma: float | None = None` with `isfinite` validators. Frozen model unchanged — existing constructors unaffected.
- **Vol surface in `indicators/vol_surface.py`**: Returns `VolSurfaceResult` NamedTuple (not Pydantic — indicators module rule). Tiered: fitted surface (≥6 contracts, ≥2 expirations) → standalone fallback. **Shared file with `volatility-intelligence` epic** — we create it, they extend it.
- **Single-shot Greeks construction in `scoring/contracts.py`**: Compute both first-order and second-order Greeks, construct one `OptionGreeks(delta=..., vanna=..., ...)` — no two-step `model_copy()`.
- **Context-only HV estimators, not composite weights**: HV estimators enrich debate context but don't enter `INDICATOR_WEIGHTS`. Vol surface metrics (`skew_25d` +0.02, `smile_curvature` +0.01) are added with weight redistribution from `put_call_ratio`, `max_pain_distance`, `chain_spread_pct` (each -0.01).
- **Vol surface computed in Phase 3 before `compute_phase3_indicators()`**: Surface-interpolated `atm_iv_30d/60d` replaces existing `_extract_atm_iv_by_dte()` extraction.

## Technical Approach

### New Files

| File | Purpose | ~Lines |
|------|---------|--------|
| `indicators/hv_estimators.py` | Parkinson, Rogers-Satchell, Yang-Zhang HV | ~120 |
| `indicators/vol_surface.py` | Skew, curvature, ATM term structure, Breeden-Litzenberger PDF | ~180 |
| `data/migrations/032_second_order_greeks.sql` | ALTER TABLE recommended_contracts ADD vanna/charm/vomma | ~5 |
| `tests/unit/indicators/test_hv_estimators.py` | 3 estimators × mandatory tests | ~200 |
| `tests/unit/indicators/test_vol_surface.py` | 4 surface functions + degradation | ~200 |
| `tests/unit/pricing/test_second_order_greeks.py` | BSM analytical + BAW finite-diff + cross-verification | ~300 |

### Modified Files (~19)

| File | Changes |
|------|---------|
| `models/options.py` | Add `vanna/charm/vomma: float \| None = None` to `OptionGreeks` with `isfinite` validators |
| `models/scan.py` | Add `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current` to `IndicatorSignals` |
| `models/analysis.py` | Add same fields to `MarketContext` |
| `models/analytics.py` | Add flat `vanna/charm/vomma` columns to `RecommendedContract` |
| `pricing/bsm.py` | Add `bsm_second_order_greeks()` — analytical vanna, charm, vomma using `_d1_d2()` |
| `pricing/american.py` | Add `american_second_order_greeks()` — 12 cross-bump `american_price()` calls |
| `pricing/dispatch.py` | Add `option_second_order_greeks()` match-dispatch |
| `pricing/__init__.py` | Re-export `option_second_order_greeks` |
| `scoring/contracts.py` | Call `option_second_order_greeks()` after `option_greeks()`, single OptionGreeks construction |
| `scoring/normalization.py` | Add `skew_25d`, `smile_curvature` to `INDICATOR_WEIGHTS` with redistribution |
| `scan/indicators.py` | Wire HV estimators + vol surface into `compute_phase3_indicators()` |
| `scan/phase_options.py` | Add new field names to `_PHASE3_FIELDS`; call vol surface before Phase 3 indicators |
| `indicators/__init__.py` | Re-export new functions |
| `agents/orchestrator.py` | Map `signals.hv_yang_zhang/skew_25d/smile_curvature` → `MarketContext` |
| `agents/_parsing.py` | Add vol surface + HV blocks in `render_volatility_context()` |
| `agents/prompts/volatility.py` | Expand prompt with vol surface interpretation guidance |
| `agents/prompts/risk.py` | Expand prompt with second-order Greeks analysis guidance |
| `api/schemas.py` | Add new MarketContext fields to `DebateResultDetail` |
| `data/repository.py` | Handle new vanna/charm/vomma columns in persistence |

## Implementation Strategy

### Wave 1 — Foundation (Pure Math, Parallelizable)

Two independent streams — can be implemented in parallel:

**Stream A**: HV Estimators (Task 1)
**Stream B**: Second-Order Greeks (Tasks 2)

### Wave 2 — Pipeline Integration (Sequential, depends on Wave 1)

Tasks 3-5: Model extensions → vol surface → pipeline wiring + persistence

### Wave 3 — Agent + API (depends on Wave 2)

Tasks 6-7: Prompt enrichment, composite weights, API schema

### Risk Mitigation

- **BAW charm cross-bump T-dT guard**: Same forward-diff pattern as existing BAW theta — use `T+dT` only when `T <= dT`
- **Sparse chain degradation**: Vol surface returns None gracefully for <3 strikes
- **Weight redistribution**: Import-time `sum==1.0` guard catches any arithmetic drift
- **Cross-verification**: BSM vs BAW second-order Greeks agree within rel=1e-3 for European inputs

## Task Breakdown Preview

- [ ] Task 1: HV Estimators — Create `indicators/hv_estimators.py` with Parkinson, Rogers-Satchell, Yang-Zhang + tests
- [ ] Task 2: Second-Order Greeks — Extend `OptionGreeks` model + BSM analytical + BAW finite-diff + dispatch + cross-verification tests
- [ ] Task 3: Vol Surface Analytics — Create `indicators/vol_surface.py` with tiered computation + VolSurfaceResult + tests
- [ ] Task 4: Model Field Extensions — Add fields to `IndicatorSignals`, `MarketContext`, `RecommendedContract` + migration 032
- [ ] Task 5: Pipeline Integration — Wire HV/Greeks/vol-surface into scan phases + scoring + orchestrator mapping
- [ ] Task 6: Agent Prompt Enrichment + Composite Weights — Context rendering + weight redistribution + prompt updates
- [ ] Task 7: API Schema + Final Validation — Update `DebateResultDetail` + regression suite

## Dependencies

### Internal (task ordering)
- Tasks 1-2 are independent (Wave 1, parallelizable)
- Task 3 depends on nothing (vol surface is standalone math)
- Task 4 depends on Tasks 1-2 (model fields reference new Greek types)
- Task 5 depends on Tasks 1-4 (wires everything into pipeline)
- Task 6 depends on Task 5 (needs populated fields for rendering)
- Task 7 depends on Task 6 (API exposes enriched data)

### External
- None. All algorithms use existing numpy/scipy/pandas.

### Cross-PRD
- **`volatility-intelligence`**: Shares `indicators/vol_surface.py`. We create the file and `VolSurfaceResult`; they extend with `_fit_surface_2d/_1d()` and `compute_surface_indicators()`.
- **`multi-leg-strategies`**: Soft dependency on `OptionGreeks` extension (second-order Greeks used in spread aggregation when available).

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Yang-Zhang HV populated in MarketContext | >95% of debate tickers |
| Second-order Greeks on recommended contracts | >90% of contracts with first-order Greeks |
| Vol surface metrics (skew_25d) populated | >60% of debate tickers (chain-dependent) |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~125 tests across 3 new test files + integration |
| BSM-vs-BAW cross-verification | Second-order Greeks agree within rel=1e-3 |
| Composite weight sum | Exactly 1.0 (import-time guard) |

## Estimated Effort

- **Size**: Large (L)
- **Tasks**: 7 across 3 waves
- **New files**: 3 source + 3 test + 1 migration
- **Modified files**: ~19
- **New tests**: ~125
- **Critical path**: Wave 1 (parallel) → Wave 2 (sequential) → Wave 3 (sequential)
- **Parallelism**: Tasks 1-2 can run simultaneously; Task 3 can overlap with late Wave 1

## Tasks Created
- [ ] #487 - HV Estimators (parallel: true) — M, 6-8h
- [ ] #489 - Second-Order Greeks (parallel: true) — L, 10-12h
- [ ] #490 - Vol Surface Analytics (parallel: true) — M, 8-10h
- [ ] #491 - Model Field Extensions + Migration (parallel: false, depends: #487, #489) — S, 3-4h
- [ ] #486 - Pipeline Integration (parallel: false, depends: #487-#491) — L, 10-14h
- [ ] #488 - Agent Prompt Enrichment (parallel: false, depends: #486) — S, 3-5h
- [ ] #492 - API Schema + Final Validation (parallel: false, depends: #488) — S, 2-4h

Total tasks: 7
Parallel tasks: 3 (Wave 1: #487, #489, #490)
Sequential tasks: 4 (Wave 2-3: #491, #486, #488, #492)
Estimated total effort: 42-57 hours

## Test Coverage Plan
Total test files planned: 6 (3 unit + 2 integration + 1 model)
Total test cases planned: ~125
