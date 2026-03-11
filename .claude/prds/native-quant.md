---
name: native-quant
description: Native reimplementation of 3 quantitative finance algorithms — HV estimators, vol surface, higher-order Greeks
status: researched
created: 2026-03-11T01:46:14Z
---

# PRD: native-quant

## Executive Summary

Integrate three quantitative finance capabilities into Options Arena through native reimplementation (no new dependencies). These fill gaps identified through competitive landscape research against 40+ open source options tools: (1) Yang-Zhang/Parkinson/Rogers-Satchell historical volatility estimators replace the naive close-to-close std dev, (2) implied volatility surface analytics extract skew, curvature, and probability-of-profit from option chains, and (3) second-order Greeks (vanna, charm, vomma) enable professional-grade hedging exposure analysis. All three use existing numpy/scipy/pandas — zero new runtime dependencies. Multi-leg strategy building is covered separately in the `multi-leg-strategies` PRD.

## Problem Statement

Options Arena currently has three quantitative blind spots that limit the quality of AI debate analysis and contract recommendations:

1. **HV estimation is naive** — `compute_hv_20d()` uses simple log-return standard deviation, which is statistically inefficient. Yang-Zhang (2000) achieves ~7x better efficiency by incorporating OHLC data already available in the pipeline. This directly impacts IV-HV spread quality, a key signal for the Volatility Agent.

2. **Vol surface is invisible** — The system computes `iv_rank`, `iv_percentile`, and `iv_term_slope` as scalar indicators but never constructs the full IV surface across strikes and expirations. Skew (put-call IV differential), smile curvature, and implied probability distributions are absent. The Volatility Agent debates without seeing the shape of the market's expectations.

3. **Only first-order Greeks** — `OptionGreeks` has delta/gamma/theta/vega/rho. Professional options traders also monitor vanna (delta sensitivity to vol changes), charm (delta decay over time), and vomma (vega convexity). `MarketContext` already has placeholder fields (`target_vanna`, `target_charm`, `target_vomma`) that are never populated. The Risk Agent cannot assess second-order exposure.

**Why now**: The competitive research showed no open source tool combines AI debate with options-specific quant analytics. These three integrations deepen Options Arena's moat in an area where competitors (TradingAgents, OpenBB, optopsy) are weakest.

## User Stories

### US-1: Analyst wants better volatility signals
**As** a trader using the scan pipeline, **I want** the IV-HV spread computed from a statistically efficient HV estimator **so that** I can trust the "cheap IV" or "expensive IV" signal rather than relying on noisy close-to-close volatility.

**Acceptance criteria:**
- Yang-Zhang HV appears in debate context alongside existing HV-20d
- IV-HV spread uses Yang-Zhang as primary (fallback to close-to-close)
- `MarketContext.hv_yang_zhang` is populated for debate agents

### US-2: Analyst wants to understand vol surface shape
**As** a trader evaluating an options position, **I want** to see the IV skew, smile curvature, and implied probability of profit **so that** I can assess whether the market is pricing tail risk asymmetrically.

**Acceptance criteria:**
- `skew_25d`, `smile_curvature`, `prob_above_current` computed from chain data
- Values appear in debate context for Volatility and Risk agents
- Graceful degradation to None when chain data is too sparse

### US-3: Analyst wants second-order Greek exposure
**As** a risk-conscious trader, **I want** to see vanna, charm, and vomma for recommended contracts **so that** I can understand how my position behaves under vol shifts and time decay.

**Acceptance criteria:**
- `OptionGreeks` model includes vanna, charm, vomma (optional, backward-compatible)
- BSM: analytical closed-form computation
- BAW: finite-difference cross-bump computation
- Values flow through to `MarketContext.target_vanna/charm/vomma`
- Risk Agent prompt references second-order Greeks

## Requirements

### Functional Requirements

#### FR-Q1: Historical Volatility Estimators
- Implement Parkinson (1980), Rogers-Satchell (1991), Yang-Zhang (2000) in `indicators/hv_estimators.py`
- Signatures: `compute_hv_*(pd.Series args, period=20) -> float | None`
- All annualized with `sqrt(252)`, `math.isfinite()` guards, None for insufficient data
- Yang-Zhang formula: `σ²_yz = σ²_overnight + k·σ²_close + (1-k)·σ²_rs` where `k = 0.34 / (1.34 + (n+1)/(n-1))`

#### FR-Q2: Second-Order Greeks
- Extend `OptionGreeks` with `vanna: float | None`, `charm: float | None`, `vomma: float | None`
- BSM analytical: Vanna = `-e^(-qT)·n(d1)·d2/σ`, Charm per Merton 1973 extension, Vomma = `Vega·d1·d2/σ`
- BAW finite-difference: cross-bump `(S,σ)` for vanna, `(S,T)` for charm, double-bump `σ` for vomma
- Dispatch via `option_second_order_greeks()` in `pricing/dispatch.py`

#### FR-Q3: Volatility Surface Analytics
- Implement in `indicators/vol_surface.py` — pure numpy/scipy, no Pydantic models (indicators module rule)
- **Shared file**: This file is jointly owned with the `volatility-intelligence` epic. native-quant creates it; volatility-intelligence extends it.
- Single public entry point: `compute_vol_surface(contracts, spot, ...) -> VolSurfaceResult`
- Tiered computation:
  - **Tier 1 (fitted surface)**: `_fit_surface()` via `scipy.interpolate.SmoothBivariateSpline` when ≥6 contracts across ≥2 expirations. Derives `skew_25d`, `smile_curvature`, `atm_iv_30d/60d` from spline derivatives. Also produces per-contract residuals and z-scores for mispricing detection.
  - **Tier 2 (standalone fallback)**: `_standalone_skew_25d()`, `_standalone_smile_curvature()`, `_standalone_atm_iv()`, `_standalone_implied_move()` when chain is too sparse for fitting. Finite-difference curvature, raw 25-delta extraction, nearest-ATM contract.
  - `VolSurfaceResult.is_standalone_fallback` indicates which tier ran.
- `compute_surface_indicators(vol_result, contracts, spot)` — maps per-contract z-scores from fitted surface. Stub in this epic (returns empty dict); completed by `volatility-intelligence`.
- Breeden-Litzenberger (1978) implied PDF → `prob_above_current`

**VolSurfaceResult NamedTuple**:
```python
class VolSurfaceResult(NamedTuple):
    skew_25d: float | None
    smile_curvature: float | None
    prob_above_current: float | None
    atm_iv_30d: float | None
    atm_iv_60d: float | None
    fitted_ivs: np.ndarray | None       # None on standalone fallback
    residuals: np.ndarray | None        # None on standalone fallback
    z_scores: np.ndarray | None         # None on standalone fallback
    r_squared: float | None             # None on standalone fallback
    is_1d_fallback: bool
    is_standalone_fallback: bool
```

#### FR-Q4: Pipeline Integration
- Vol surface computation occurs in `phase_options.py` `process_ticker_options()`, BEFORE `compute_phase3_indicators()`
- `compute_phase3_indicators()` gains optional `vol_result: VolSurfaceResult | None = None` parameter
- When `vol_result` is provided, `vol_result.atm_iv_30d/60d` replaces the existing `_extract_atm_iv_by_dte()` call — surface-interpolated ATM IV is cleaner than nearest-contract extraction
- Phase 3 also computes Yang-Zhang HV and second-order Greeks (unchanged)
- Values populate `IndicatorSignals` → `MarketContext` via existing orchestrator mapping
- Composite scoring: add `skew_25d` (weight 0.02) and `smile_curvature` (weight 0.01) to `INDICATOR_WEIGHTS`. Redistribute: `put_call_ratio` 0.04→0.03, `max_pain_distance` 0.04→0.03, `chain_spread_pct` 0.04→0.03. Sum stays 1.0.

#### FR-Q5: Agent Prompt Enrichment
- Volatility Agent: `render_volatility_context()` gains a vol surface block rendering `SKEW 25D`, `SMILE CURVATURE`, `PROB ABOVE`, `HV YANG-ZHANG`. The `volatility-intelligence` epic later appends `IV VS SURFACE` and `SURFACE R²` to this same block.
- Risk Agent: receives second-order Greeks and HV estimates (unchanged)
- Rendering uses existing `_render_optional(label, value, fmt)` pattern

### Non-Functional Requirements

#### NFR-Q1: No New Dependencies
All implementations use existing numpy, scipy, pandas. No new `uv add` required.

#### NFR-Q2: Backward Compatibility
- `OptionGreeks` new fields default to None — existing constructors unaffected
- Pipeline produces same output for existing fields; new fields are additive
- All existing ~4,400 tests must continue passing

#### NFR-Q3: Performance
- BAW cross-bumps: 12 additional `american_price()` calls per contract for 3 second-order Greeks
- On top-50 scan (~50 contracts each): ~2,400 extra BAW calls, estimated +2-3 seconds
- Vol surface computation: lightweight numpy operations, <100ms per ticker

#### NFR-Q4: Graceful Degradation
- All new functions return None on insufficient/invalid data — never raise
- First-order Greeks still returned if second-order computation fails
- Vol surface returns None for sparse chains (<3 strikes at target DTE)

## Success Criteria

| Metric | Target |
|--------|--------|
| Yang-Zhang HV populated in MarketContext | >95% of debate tickers |
| Second-order Greeks populated on recommended contracts | >90% of contracts with first-order Greeks |
| Vol surface metrics (skew_25d) populated | >60% of debate tickers (chain-dependent) |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~125 tests across 4 new test files |
| BSM-vs-BAW cross-verification | Second-order Greeks agree within rel=1e-3 |

## Constraints & Assumptions

### Constraints
- Indicators module: pure math only — pandas/numpy in, float/Series out. No Pydantic models, no API calls.
- Pricing module: scalar float in/out. No pandas. Returns `OptionGreeks` model or float.
- Scoring imports `pricing/dispatch` only — never `pricing/bsm` or `pricing/american` directly.
- All models with Decimal fields need `field_serializer`. All float fields need `math.isfinite()` validators.
- Frozen models use `model_copy(update=...)` for field updates.

### Assumptions
- yfinance chains provide sufficient strikes per expiration for vol surface (~5+ strikes typical for liquid names)
- BAW finite-difference bump sizes (`_DS_FRACTION=0.01`, `_DSIGMA=0.001`) are appropriate for second-order Greeks
- 25-delta approximation for skew is acceptable (vs. interpolating exact delta from surface)
## Out of Scope

- **Multi-leg strategy builder** — covered separately in `multi-leg-strategies` PRD
- **Volatility surface 3D visualization** — frontend chart component deferred to future UI epic
- **Real-time streaming Greeks** — updating Greeks on live quotes (would require broker integration)
- **Exotic option pricing** — barrier, Asian, lookback options beyond vanilla American/European
- **GARCH/stochastic vol models** — vol forecasting beyond HV estimators
- **Portfolio-level Greek aggregation** — aggregating across multiple tickers/positions
- **Broker execution** — placing multi-leg orders via IBKR or other APIs

## Cross-PRD Coordination: volatility-intelligence

This PRD shares `indicators/vol_surface.py` with the `volatility-intelligence` PRD. Coordination contract:

| Aspect | native-quant (this PRD) | volatility-intelligence |
|--------|------------------------|------------------------|
| File | Creates `vol_surface.py` with tiered architecture | Extends with `_fit_surface_2d/_1d()` and `compute_surface_indicators()` |
| NamedTuple | Defines `VolSurfaceResult` | Uses it (no changes) |
| `smile_curvature` | Defines field on `IndicatorSignals` + `MarketContext` | Populates via surface derivative (upgrades standalone value) |
| `atm_iv_30d` | Surface-derived replaces `_extract_atm_iv_by_dte()` | Same — no new field |
| Rendering | Creates vol surface block in `render_volatility_context()` | Appends 2 lines (`IV VS SURFACE`, `SURFACE R²`) |
| Weights | `+skew_25d(0.02) +smile_curvature(0.01)`, redistributed | `iv_surface_residual` as tiebreaker only — no weight change |
| Fields owned | `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current` | `iv_surface_residual`, `surface_fit_r2`, `surface_is_1d`, `smoothed_iv` |

## Dependencies

### Internal
- `OptionGreeks` model extension (Wave 1) is prerequisite for Greeks integration (Wave 2)
- `IndicatorSignals` and `MarketContext` field additions (Wave 2) are prerequisite for agent prompt enrichment (Wave 3)
- Vol surface functions (Wave 2) need chain data available in Phase 3 pipeline
- `multi-leg-strategies` PRD has a soft dependency on this epic's `OptionGreeks` extension (second-order Greeks used in spread aggregation when available)

### External
- No external dependencies. All algorithms implemented with existing numpy/scipy/pandas stack.

## Delivery Waves

| Wave | Focus | Issues | New Files | Modified Files | Est. Tests |
|------|-------|--------|-----------|----------------|------------|
| 1 | Foundation (pure math) | 2 | 2 | 5 | ~70 |
| 2 | Pipeline integration | 3 | 1 (shared) | 8 | ~40 |
| 3 | Agent + API + UI | 2 | 0 | 6 | ~15 |
| **Total** | | **7** | **3** | **19** | **~125** |

**Wave 1** issues (HV estimators + second-order Greeks) are independent and can be implemented in parallel. **Wave 2** creates `indicators/vol_surface.py` — the shared vol surface file also extended by `volatility-intelligence`. **Wave 3** requires Waves 1-2 complete.

## References

- Yang & Zhang (2000) "Drift Independent Volatility Estimation Based on High, Low, Open, and Close Prices"
- Parkinson (1980) "The Extreme Value Method for Estimating the Variance of the Rate of Return"
- Rogers & Satchell (1991) "Estimating Variance From High, Low and Closing Prices"
- Breeden & Litzenberger (1978) "Prices of State-Contingent Claims Implicit in Option Prices"
- Hull (2018) "Options, Futures, and Other Derivatives", Ch. 15 (HV) and Ch. 19 (Higher-Order Greeks)
- Barone-Adesi & Whaley (1987) "Efficient Analytic Approximation of American Option Values"
- Sinclair (2013) "Volatility Trading", 2nd Edition — HV estimator implementations
