# Research: native-quant

## PRD Summary

Add three quantitative finance capabilities to Options Arena using only existing numpy/scipy/pandas (zero new dependencies):

1. **HV Estimators** — Yang-Zhang, Parkinson, Rogers-Satchell in `indicators/hv_estimators.py`. Replace naive close-to-close HV as primary IV-HV spread signal.
2. **Second-Order Greeks** — Vanna, charm, vomma on `OptionGreeks`. BSM analytical closed-form + BAW finite-difference cross-bumps in `pricing/`. Dispatch via `option_second_order_greeks()`.
3. **Vol Surface Analytics** — Skew (25-delta risk reversal), smile curvature, ATM term structure, Breeden-Litzenberger implied PDF in `indicators/vol_surface.py`.

Integration into scan pipeline Phase 3, MarketContext, and debate agent prompts (Volatility + Risk agents).

## Relevant Existing Modules

| Module | Relevance |
|--------|-----------|
| `indicators/` | New files: `hv_estimators.py`, `vol_surface.py`. Existing: `iv_analytics.py` has `compute_hv_20d()`, skew, term slope |
| `pricing/` | Extend `bsm.py` (analytical 2nd-order), `american.py` (finite-diff cross-bumps), `dispatch.py` (new dispatcher) |
| `models/` | Extend `OptionGreeks` (options.py), `IndicatorSignals` (scan.py), `MarketContext` (analysis.py), `RecommendedContract` (analytics.py) |
| `scoring/` | `contracts.py` calls `option_greeks()` — will also call `option_second_order_greeks()` |
| `scan/` | `indicators.py` (Phase 3 computation), `phase_options.py` (merge/normalize, `_PHASE3_FIELDS`) |
| `agents/` | `_parsing.py` (context rendering), `orchestrator.py` (signals→MarketContext mapping), `prompts/volatility.py`, `prompts/risk.py` |
| `data/` | New migration 031 for `recommended_contracts` vanna/charm/vomma columns |
| `api/` | `schemas.py` DebateResultDetail — add new MarketContext fields |

## Existing Patterns to Reuse

### Indicator Function Pattern (from `iv_analytics.py`)
```python
def compute_hv_20d(close_series: pd.Series) -> float | None:
    if len(close_series) < 21:
        return None
    # ... math with np.log(), .std(ddof=1) * sqrt(252) ...
    return result if math.isfinite(result) else None
```
All new HV estimators and vol surface functions follow this exact pattern: pandas in, `float | None` out, `math.isfinite()` guard, None for insufficient data.

### Pricing Function Pattern (from `bsm.py`)
```python
def bsm_greeks(S, K, T, r, q, sigma, option_type) -> OptionGreeks:
    validate_positive_inputs(S, K, T, r)
    # ... scalar math with math.log/sqrt/exp (NOT numpy) ...
    return OptionGreeks(delta=..., pricing_model=PricingModel.BSM)
```
New `bsm_second_order_greeks()` reuses `_d1_d2()` helper (line 41) and returns a tuple or extended OptionGreeks.

### BAW Finite-Difference Pattern (from `american.py`)
Existing bump constants: `_DS_FRACTION=0.01`, `_DT=1/365`, `_DSIGMA=0.001`, `_DR=0.001`. Cross-bumps for second-order Greeks use the same sizes. Guard `T - dT <= 0` for charm (same as theta forward-diff guard).

### Dispatch Pattern (from `dispatch.py`)
```python
def option_greeks(exercise_style, S, K, T, r, q, sigma, option_type) -> OptionGreeks:
    match exercise_style:
        case ExerciseStyle.AMERICAN: return american_greeks(...)
        case ExerciseStyle.EUROPEAN: return bsm_greeks(...)
```
New `option_second_order_greeks()` follows identical match-dispatch routing.

### Phase 3 Indicator Wiring Pattern (from `scan/indicators.py`)
```python
try:
    result = compute_function(inputs)
    if result is not None and math.isfinite(result):
        signals.field_name = result
except Exception:
    logger.warning("Indicator field_name failed; setting to None", exc_info=True)
```
Every new indicator call uses isolated try/except — one failure never crashes the pipeline.

### MarketContext Mapping Pattern (from `agents/orchestrator.py`)
```python
target_vanna=signals.vanna,
target_charm=signals.charm,
```
New fields (`hv_yang_zhang`, `skew_25d`, `smile_curvature`) follow this same signals→context mapping.

### Context Rendering Pattern (from `agents/_parsing.py`)
```python
_render_optional("HV YANG-ZHANG", ctx.hv_yang_zhang, ".1%"),
```
Uses existing `_render_optional(label, value, fmt)` for all nullable float fields.

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|--------------|
| `models/options.py` | `OptionGreeks` with delta/gamma/theta/vega/rho (frozen) | Add `vanna/charm/vomma: float \| None = None` with `isfinite` validators |
| `models/scan.py` | `IndicatorSignals` already has `vanna/charm/vomma` fields (lines 97-99, never populated) | Add `hv_yang_zhang`, `skew_25d`, `smile_curvature` fields |
| `models/analysis.py` | `MarketContext` already has `target_vanna/charm/vomma` (lines 165-167, always None) | Add `hv_yang_zhang`, `skew_25d`, `smile_curvature` fields |
| `pricing/bsm.py` | `bsm_greeks()` computes first-order via `_d1_d2()` helper | Add `bsm_second_order_greeks()` reusing d1/d2 |
| `pricing/american.py` | BAW greeks via finite-diff, bump constants defined | Add `american_second_order_greeks()` with cross-bumps |
| `pricing/dispatch.py` | `option_greeks()` with match dispatch | Add `option_second_order_greeks()` parallel dispatcher |
| `scoring/contracts.py` | `recommend_contracts()` calls `option_greeks()` | Also call `option_second_order_greeks()`, populate on OptionGreeks |
| `scan/indicators.py` | `compute_phase3_indicators()` — calls `compute_hv_20d()` at line 461 | Add HV estimator calls + vol surface calls |
| `scan/phase_options.py` | `_PHASE3_FIELDS` includes `vanna/charm/vomma` (lines 116-118) | Add `hv_yang_zhang`, `skew_25d`, `smile_curvature` to tuple |
| `agents/orchestrator.py` | Maps `signals.vanna → target_vanna` (line 344) | Add mapping for `hv_yang_zhang`, `skew_25d`, `smile_curvature` |
| `agents/_parsing.py` | Already renders Second-Order Greeks section (lines 966-976) | Add HV estimator + vol surface rendering in `render_volatility_context()` |
| `indicators/__init__.py` | Re-exports all indicator functions | Add re-exports for new files |
| `models/analytics.py` | `RecommendedContract` has flat delta/gamma/theta/vega/rho columns | Add flat `vanna/charm/vomma` columns |

## New Files to Create

| File | Purpose | Est. Lines |
|------|---------|------------|
| `src/options_arena/indicators/hv_estimators.py` | Parkinson, Rogers-Satchell, Yang-Zhang HV estimators | ~120 |
| `src/options_arena/indicators/vol_surface.py` | ATM term structure, skew_25d, smile curvature, Breeden-Litzenberger | ~180 |
| `data/migrations/031_second_order_greeks.sql` | ALTER TABLE recommended_contracts ADD vanna/charm/vomma | ~5 |
| `tests/unit/indicators/test_hv_estimators.py` | Tests for 3 HV estimators | ~200 |
| `tests/unit/indicators/test_vol_surface.py` | Tests for 4 vol surface functions | ~200 |
| `tests/unit/pricing/test_second_order_greeks.py` | BSM analytical + BAW finite-diff + cross-verification | ~300 |

## Potential Conflicts

### 1. `INDICATOR_WEIGHTS` sum==1.0 guard
**Risk**: Adding new indicators to the composite score weights requires redistributing from existing entries.
**Mitigation**: HV estimators and vol surface metrics are context enrichment for debate agents, NOT composite score components. Do not add to `INDICATOR_WEIGHTS`. They flow through `IndicatorSignals` → `MarketContext` → agent prompts only.

### 2. `OptionGreeks` is frozen — mutation via `model_copy()`
**Risk**: `scoring/contracts.py` builds OptionGreeks in one shot from `option_greeks()`. Adding second-order Greeks after the fact requires `model_copy(update=...)`.
**Mitigation**: Compute second-order Greeks immediately after first-order in `contracts.py`, then construct a single `OptionGreeks(delta=..., vanna=..., ...)` — avoid two-step mutation.

### 3. Yang-Zhang needs `open` prices — different input shape
**Risk**: Existing indicators use `close` or `(high, low, close)`. Yang-Zhang needs `(open, high, low, close)`.
**Mitigation**: `scan/indicators.py` already has the full OHLCV DataFrame from Phase 1. Extract `open_series = df["Open"]` alongside existing `close_series = df["Close"]`.

### 4. `compute_skew_25d()` vs existing `compute_put_skew()` / `compute_call_skew()`
**Risk**: Name/concept overlap. Existing skew functions use raw IV values; skew_25d is a 25-delta risk reversal.
**Mitigation**: Different computation, different field name (`skew_25d` vs `put_skew_index`/`call_skew_index`). Both coexist. Document distinction in docstrings.

### 5. BAW charm cross-bump: T-dT can go negative
**Risk**: When `T < 1/365`, charm cross-bump `T-dT` becomes negative/zero, invalid for BAW pricing.
**Mitigation**: Same forward-diff guard as BAW theta — use `T+dT` only (forward difference) when `T <= dT`. Already established pattern in `american.py`.

### 6. Second-order Greeks timing in pipeline
**Risk**: `compute_phase3_indicators()` runs BEFORE `recommend_contracts()`. Second-order Greeks need a specific contract.
**Mitigation**: Second-order Greeks computed inside `scoring/contracts.py` (alongside first-order), then extracted by `phase_options.py` into `signals.vanna/charm/vomma`. The plumbing already exists in `_PHASE3_FIELDS` — just need the computation.

## Open Questions

1. **Should HV estimators be added to the composite score weights?** The PRD says they populate `MarketContext` for agent context. Adding to weights requires weight redistribution. Recommendation: context only, not weights (can be promoted later).

2. **`RecommendedContract` migration**: Should vanna/charm/vomma be persisted as flat columns on `recommended_contracts`? This enables backtesting queries with second-order Greeks. The PRD doesn't explicitly require persistence. Recommendation: yes, add migration 031 for future analytics.

3. **Vol surface input format**: `compute_skew_25d()` and `compute_smile_curvature()` need chain data (strikes, IVs, option types). The `indicators/` module rule says "pandas in, float out". Should these accept a DataFrame of chain data, or separate Series? Recommendation: accept `strikes: pd.Series, ivs: pd.Series, spot: float` — consistent with indicators module pattern.

4. **Should `hv_parkinson` and `hv_rogers_satchell` also go on `IndicatorSignals` / `MarketContext`?** The PRD says Yang-Zhang is primary (others are intermediate/fallback). Recommendation: compute all 3 in `hv_estimators.py`, but only `hv_yang_zhang` goes on `IndicatorSignals`/`MarketContext`. Parkinson/RS are available as library functions.

## Recommended Architecture

### Wave 1 — Foundation (Pure Math, Parallelizable)
Two independent work streams:

**Stream A: HV Estimators**
- Create `indicators/hv_estimators.py` with 3 functions
- Unit tests in `tests/unit/indicators/test_hv_estimators.py`
- No model changes, no pipeline changes

**Stream B: Second-Order Greeks**
- Extend `OptionGreeks` model with 3 optional fields + validators
- Add `bsm_second_order_greeks()` in `pricing/bsm.py` (analytical closed-form using d1/d2)
- Add `american_second_order_greeks()` in `pricing/american.py` (12 cross-bump `american_price()` calls)
- Add `option_second_order_greeks()` in `pricing/dispatch.py`
- Unit tests in `tests/unit/pricing/test_second_order_greeks.py`
- Cross-verification: BSM vs BAW should agree within rel=1e-3 for European-exercise-style inputs

### Wave 2 — Pipeline Integration (Sequential, depends on Wave 1)
- Add `hv_yang_zhang`, `skew_25d`, `smile_curvature` to `IndicatorSignals` and `MarketContext`
- Create `indicators/vol_surface.py` with 4 functions
- Wire HV estimators into `compute_phase3_indicators()` in `scan/indicators.py`
- Wire vol surface into `compute_phase3_indicators()` (needs chain data access)
- Call `option_second_order_greeks()` in `scoring/contracts.py` after `option_greeks()`
- Add field names to `_PHASE3_FIELDS` in `phase_options.py`
- Map new signals to MarketContext in `orchestrator.py`
- Migration 031 for `recommended_contracts` table
- Update `RecommendedContract` model and persistence
- Unit tests for vol surface + integration tests

### Wave 3 — Agent Enrichment + API (depends on Wave 2)
- Add vol surface rendering in `agents/_parsing.py` `render_volatility_context()`
- Add HV estimator rendering in `render_volatility_context()` and `render_context_block()`
- Expand `volatility.py` prompt with vol surface interpretation guidance
- Expand `risk.py` prompt with second-order Greeks analysis guidance
- Update `DebateResultDetail` API schema with new fields
- Integration/smoke tests

## Test Strategy Preview

### Existing Test Patterns
- **Indicators**: Class-based, 5 mandatory tests per function (known-value, minimum-data, insufficient-data, NaN-warmup, edge-cases). Float comparisons via `pytest.approx(rel=1e-4)`. Source citations in docstrings.
- **Pricing**: Class-based, standard params (`STD_S=100`, `STD_K=100`, etc.). Parametrize across `OptionType.CALL/PUT`. No mocking for pure math.
- **Pipeline**: `asyncio` fixtures, `:memory:` SQLite, mocked external services.

### New Test Files
| File | Est. Tests | Focus |
|------|-----------|-------|
| `tests/unit/indicators/test_hv_estimators.py` | ~35 | 3 estimators × 5 mandatory tests + Yang-Zhang vs close-to-close comparison |
| `tests/unit/indicators/test_vol_surface.py` | ~35 | 4 functions × 5 tests + sparse chain degradation |
| `tests/unit/pricing/test_second_order_greeks.py` | ~40 | BSM analytical (3 Greeks × CALL/PUT), BAW finite-diff (3 × 2), cross-verification (3) |
| Integration tests in existing pipeline test files | ~15 | End-to-end flow, MarketContext population, agent context rendering |

### Cross-Verification Strategy
BSM and BAW second-order Greeks should agree within `rel=1e-3` when exercise_style=EUROPEAN (BAW degenerates to BSM). This is the same cross-verification used for first-order Greeks.

## Estimated Complexity

**Large (L)** — 7 issues across 3 waves, ~19 modified files + 3 new source files + 3 new test files + 1 migration, ~125 new tests. Pure math is well-defined (academic formulas), but integration touches models, scan pipeline, scoring, agents, persistence, and API. Wave 1 streams are parallelizable; Waves 2-3 are sequential.
