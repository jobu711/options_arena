---
name: volatility-intelligence
description: Put-call parity IV smoothing and fitted volatility surface with mispricing detection for alpha-generative contract scoring
status: planned
created: 2026-03-11T02:36:56Z
---

# PRD: volatility-intelligence

## Executive Summary

Cherry-pick two techniques from QuantConnect/Lean's volatility infrastructure into Options Arena's pricing and scoring pipeline: (1) put-call parity IV smoothing — pairing call and put IVs at the same strike to cancel bid-ask noise before Greeks computation, and (2) a fitted implied volatility surface with per-contract mispricing scores. Together these form a compounding volatility intelligence stack: cleaner IVs → better surface fit → accurate mispricing detection → higher-alpha contract selection. Both use existing scipy — zero new dependencies.

**Relationship to other PRDs**: The `native-quant` PRD creates `indicators/vol_surface.py` with a tiered architecture — standalone indicators (Tier 2) and a fitted surface framework (Tier 1). This PRD completes the Tier 1 fitted surface implementation and adds mispricing detection. `native-quant` is a **hard dependency** for Issue 3 (vol surface extension). Issues 1-2 (IV smoothing) are independent. See Cross-PRD Coordination section for the full contract.

## Problem Statement

### 1. Noisy IVs poison everything downstream

yfinance reports `impliedVolatility` per contract, derived from each option's individual market price. For illiquid strikes, wide bid-ask spreads (often 20-50% of mid) distort the IV. This noise propagates through the entire pipeline:

- **Greeks are wrong** — `compute_greeks()` uses the noisy IV as `sigma` input to BAW/BSM. Delta, gamma, vega, theta are all functions of sigma. Noisy sigma → noisy Greeks.
- **Delta targeting is wrong** — `select_by_delta()` picks the contract closest to target delta (0.35). If the IV is 5 vol points too high, delta is systematically biased, and the "closest to 0.35 delta" contract may not actually be closest.
- **IV indicators are wrong** — `iv_rank`, `iv_percentile`, `iv_hv_spread` all use the per-contract IV. Noise in individual strikes propagates into aggregate metrics.

Put-call parity provides a free noise reduction: at the same strike and expiration, the call and put must have the same IV (in theory). Averaging them cancels much of the bid-ask noise. QuantConnect/Lean does exactly this with its `mirror_option` parameter.

### 2. IVs are treated as independent points, not a surface

Options Arena computes `put_skew_index` and `call_skew_index` from two data points (25-delta put and ATM). It computes `iv_term_slope` from two expirations (30d and 60d). These are point estimates on a 2D surface.

The full option chain contains dozens of (strike, expiration, IV) triples. A fitted surface through these points reveals:

- **Mispriced contracts** — individual IVs that deviate significantly from the fitted surface are statistical outliers. An IV 2+ standard deviations above the surface means the market is overpricing that specific contract's volatility. An IV 2+ standard deviations below means it's underpriced. This is not opinion — it's the market disagreeing with itself.
- **Better ATM IV estimates** — interpolating ATM IV from the surface is cleaner than picking the single nearest-to-ATM contract.
- **Richer skew/curvature** — the full surface derivative captures smile shape across all strikes, not just at 25-delta.

**Why now**: The chain data is already fetched (Phase 3 calls `chain_all_expirations()`). The contracts are already iterated for Greeks computation. The infrastructure to consume new indicator fields exists (Phase 3 merge + normalize). This is a pure computation insertion — no new data sources, no new API calls.

## User Stories

### US-1: Analyst wants accurate Greeks on recommended contracts
**As** a trader evaluating a debate recommendation, **I want** the Greeks computed from smoothed IVs rather than raw yfinance IVs **so that** the delta, theta, and vega I see reflect the option's true exposure, not bid-ask noise.

**Acceptance criteria:**
- When both call and put exist at the same strike/expiration, IV is smoothed via put-call parity before Greeks computation
- When only one side exists (call or put), raw IV is used (graceful fallback)
- `GreeksSource` enum gains `SMOOTHED` variant to distinguish from `COMPUTED` and `MARKET`
- Smoothed IV is persisted on `OptionContract.smoothed_iv: float | None` for audit trail
- All existing Greeks tests pass — smoothing is additive, never replaces working computation

### US-2: Analyst wants to know if a contract's IV is cheap or expensive relative to the surface
**As** a trader, **I want** a mispricing score on each contract showing how far its IV deviates from the fitted volatility surface **so that** I can identify statistical outliers — contracts where the market is pricing vol too high or too low.

**Acceptance criteria:**
- `iv_surface_residual` z-score computed for every contract with a valid IV
- Positive residual = IV above surface (overpriced vol, favor selling premium)
- Negative residual = IV below surface (underpriced vol, favor buying premium)
- Score is NaN/None when surface can't be fitted (too few data points)
- Value flows into `MarketContext` for debate agent consumption

### US-3: Analyst wants surface-derived ATM IV instead of single-contract ATM IV
**As** a trader, **I want** ATM IV interpolated from the fitted surface rather than taken from the single nearest-ATM contract **so that** a single illiquid strike doesn't distort my view of at-the-money volatility.

**Acceptance criteria:**
- Surface-interpolated ATM IV computed at moneyness=1.0 for each DTE, populating the existing `atm_iv_30d` field (no new field — replaces nearest-contract extraction)
- Used as primary ATM IV in `iv_hv_spread` when available (fallback to existing extraction)
- `VolSurfaceResult` includes `r_squared` to indicate data quality

### US-4: Debate agents can reference mispricing in analysis
**As** a debate agent (Volatility, Risk, Contrarian), **I want** to see whether the recommended contract's IV is cheap/fair/expensive relative to the surface **so that** my trade thesis accounts for relative vol mispricing.

**Acceptance criteria:**
- `MarketContext` gains `iv_surface_residual`, `surface_fit_r2`, `surface_is_1d` fields
- Volatility Agent prompt references residual: "The recommended contract's IV is X std devs [above|below] the fitted surface"
- Risk Agent uses residual sign in risk assessment: overpriced vol = headwind for long premium
- Fields are `float | None` with `math.isfinite()` validators

### US-5: Surface gracefully handles sparse chains
**As** a user scanning mid-cap or low-liquidity tickers, **I want** the surface to degrade gracefully when there aren't enough strikes **so that** the system never errors and always produces a result.

**Acceptance criteria:**
- Minimum threshold for 2D surface: `(kx+1)*(ky+1)` contracts (16 for cubic, 4 for bilinear) across at least 2 expirations. Degree adapts to data: `kx = min(3, n_unique_moneyness - 1)`, `ky = min(3, n_unique_dte - 1)`. Absolute floor: 4 contracts with valid IV.
- Below threshold: all surface-derived fields are None, pipeline continues with raw IVs
- Single-expiration chains: 1D interpolation (strike-only smile) instead of 2D surface. Input sorted by log-moneyness (UnivariateSpline requires strictly increasing x).
- `surface_fit_r2 < 0.5`: log warning, still populate fields but mark low-confidence

## Requirements

### Functional Requirements

#### FR-V1: Put-Call Parity IV Smoothing

Implement in `pricing/iv_smoothing.py`:

```python
def smooth_iv_parity(
    call_iv: float,
    put_iv: float,
    call_bid: float,
    call_ask: float,
    put_bid: float,
    put_ask: float,
) -> float:
    """Smooth IV using put-call parity with liquidity weighting.

    Weight each side by inverse of relative spread — tighter spread = more trust.
    Falls back to simple average when both spreads are zero or non-finite.
    """
```

**Algorithm**:
1. Validate both IVs are finite and positive. If only one valid, return it.
2. Compute relative spread for each side: `spread_pct = (ask - bid) / mid` where `mid = (ask + bid) / 2`.
3. If both spreads are zero or non-finite, return simple average `(call_iv + put_iv) / 2`.
4. Compute weights as inverse spread: `w_call = 1 / max(spread_pct_call, 0.001)`, same for put.
5. Normalize: `w_call_norm = w_call / (w_call + w_put)`.
6. Return `w_call_norm * call_iv + (1 - w_call_norm) * put_iv`.

**Integration point**: `scoring/contracts.py` `compute_greeks()`:
1. Group contracts by `(strike, expiration)`.
2. For each group, find the call and put (if both exist).
3. Call `smooth_iv_parity()` to get smoothed IV.
4. Store smoothed IV on contract via `model_copy(update={"smoothed_iv": smoothed})`.
5. Use smoothed IV as `sigma` input to `option_greeks()`.
6. Set `greeks_source=GreeksSource.SMOOTHED` to distinguish from `COMPUTED`.

**Edge cases**:
- Strike has only call or only put → use raw IV (no smoothing possible)
- One side has IV = 0 or NaN → use the valid side's IV
- Both IVs valid but wildly different (ratio > 2.0) → log warning, still average (arbitrage may be present)
- Zero-bid contracts → use ask-based spread estimate, weight accordingly

#### FR-V2: Volatility Surface Construction

Extend `indicators/vol_surface.py` (created by the `native-quant` epic — shared file):

- Complete the fitted surface tier inside the existing `compute_vol_surface()`:
  - `_fit_surface_2d()` — `scipy.interpolate.SmoothBivariateSpline(log_moneyness, dte, iv, s=adaptive)`
  - `_fit_surface_1d()` — `scipy.interpolate.UnivariateSpline(log_moneyness, iv, s=smoothing)` for single-DTE chains
- Reuse the existing `VolSurfaceResult` NamedTuple (defined in native-quant) — no new return type
- `smile_curvature` field: surface-derived `∂²IV/∂m²` at ATM replaces the standalone finite-diff value when surface fit succeeds (same field, better computation)
- `atm_iv_30d/60d` fields: surface-interpolated at `m=0` replaces standalone nearest-ATM extraction (same field, better value)

**Algorithm** (SVI-lite — Stochastic Volatility Inspired parameterization):
1. Convert strikes to log-moneyness: `m = ln(K / spot)`.
2. Filter out contracts with non-finite IV, IV <= 0, or IV > 3.0.
3. If fewer than `min_contracts` valid points, return None.
4. If only one unique DTE, fall back to 1D fit: sort `(m, iv)` pairs by `m` (required — `UnivariateSpline` demands strictly increasing `x`), then `scipy.interpolate.UnivariateSpline(m_sorted, iv_sorted, s=smoothing)`.
5. For 2D: compute adaptive degree `kx = min(3, n_unique_moneyness - 1)`, `ky = min(3, n_unique_dte - 1)`. Guard that total points >= `(kx + 1) * (ky + 1)` — if not, reduce degree further or fall back to 1D. Then `scipy.interpolate.SmoothBivariateSpline(m, dte, iv, kx=kx, ky=ky, s=smoothing)`.
6. Compute fitted IV at each data point: **`iv_fitted = surface.ev(m_array, dte_array)`** (CRITICAL: `__call__` defaults to `grid=True` which returns a 2D Cartesian product — must use `.ev()` or `__call__(grid=False)` for per-point evaluation).
7. Compute residuals: `residual_i = (iv_i - iv_fitted_i) / iv_fitted_i` (relative residual).
8. Compute z-scores: `z_i = (residual_i - mean(residuals)) / std(residuals)`.
9. Compute R²: `1 - SS_res / SS_tot`.
10. Extract ATM IV: `surface.ev(np.array([0.0]), np.array([target_dte]))[0]` for each target DTE (using `.ev()` for consistency).
11. Compute smile curvature: `∂²IV/∂m²` at m=0 (second derivative via finite difference on surface).

**Smoothing factor selection**:
- `s = len(data) * median_iv_variance` — scales with data size and IV noise level. Floor at `s = max(s, 1.0)` to prevent near-interpolation when IV variance is near zero.
- Scipy guidance: good `s` values are in the range `m ± sqrt(2m)` where m = number of data points. Validate computed `s` falls in this range; clamp if outside.
- Quality gate is R² after fitting, NOT exception catching — FITPACK convergence failures emit `warnings.warn()`, not exceptions. The `ValueError` from scipy only fires when data count < `(kx+1)*(ky+1)`.
- If R² < 0.3 with initial `s`, retry with `s * 2.0` (more smoothing)
- If retry still yields R² < 0.3, return None

#### FR-V3: Mispricing Score Integration

Complete `compute_surface_indicators()` in `indicators/vol_surface.py` (stubbed by native-quant):

```python
def compute_surface_indicators(
    vol_result: VolSurfaceResult,
    contract_keys: list[tuple[float, int]],  # (strike, dte) per contract
) -> dict[tuple[float, int], SurfaceIndicators]:
    """Map per-contract z-scores from the fitted surface result.
    Returns empty dict when vol_result.is_standalone_fallback is True.
    """
```

Integration into Phase 3 (`scan/phase_options.py`):
1. `compute_vol_surface()` is already called before `compute_phase3_indicators()` (established by native-quant)
2. After contract recommendation, call `compute_surface_indicators(vol_result, [(strike, dte)])` to get the recommended contract's z-score
3. Store `iv_surface_residual` on `IndicatorSignals`
4. Store `surface_fit_r2` on `IndicatorSignals`

#### FR-V4: ~~VolatilitySurface Model~~ — REMOVED

The `VolatilitySurface` Pydantic model is unnecessary. The `VolSurfaceResult` NamedTuple (defined in native-quant's `vol_surface.py`) carries all surface data through the pipeline. Fields flow into `MarketContext` directly via the existing signals → context mapping. No separate persistence model needed.

#### FR-V5: MarketContext Enrichment

Add fields to `MarketContext` in `models/analysis.py` (the vol surface fields `skew_25d`, `smile_curvature`, `prob_above_current`, `hv_yang_zhang` are already added by `native-quant`):

```python
# Volatility Surface Intelligence (this epic)
iv_surface_residual: float | None = None   # z-score: contract IV vs fitted surface
surface_fit_r2: float | None = None        # surface fit quality [0, 1]
surface_is_1d: bool | None = None          # True if single-DTE fallback
```

All `float | None` fields with `math.isfinite()` validators. `surface_fit_r2` additionally constrained to `[0.0, 1.0]`.

~~`atm_iv_interpolated`~~ — eliminated. Surface-derived ATM IV populates the existing `atm_iv_30d` field.
~~`smile_curvature_30d`~~ — eliminated. Unified as `smile_curvature` (defined by native-quant).

#### FR-V6: Agent Prompt Enrichment

Create `render_volatility_context()` in `agents/_parsing.py`. Note: this function does NOT yet exist — native-quant added the `MarketContext` fields (`skew_25d`, `smile_curvature`, `prob_above_current`, `hv_yang_zhang`) but did not create a dedicated rendering function. This epic creates `render_volatility_context()` which renders all vol surface fields (both native-quant and this epic's additions) into a single context block for debate agents:

```
--- VOLATILITY SURFACE ---
SKEW 25D: {skew_25d:.4f}
SMILE CURVATURE: {smile_curvature:.4f}
PROB ABOVE CURRENT: {prob_above_current:.1%}
HV YANG-ZHANG: {hv_yang_zhang:.1%}
IV VS SURFACE: {iv_surface_residual:+.2f} std devs ({overpriced|underpriced|fair})
SURFACE R²: {surface_fit_r2:.2f}
```

Classification: `|z| < 0.5` → fair, `z > 0.5` → overpriced, `z < -0.5` → underpriced, `|z| > 2.0` → significantly over/underpriced.

#### FR-V7: Scoring Integration

`iv_surface_residual` is NOT added to `INDICATOR_WEIGHTS` — it is direction-dependent (overpriced vol is bad for buyers, good for sellers) and therefore unsuitable as a universal composite score component.

Instead, use as a **contract-level tiebreaker** in `scoring/contracts.py` `select_by_delta()`: when two contracts have similar delta distance (within 0.02), prefer the one with lower residual for BULLISH (underpriced vol is better to buy) and higher residual for BEARISH (overpriced vol is better to sell).

Weight redistribution for `skew_25d` and `smile_curvature` is handled by the `native-quant` epic (see Cross-PRD Coordination).

#### FR-V8: GreeksSource Extension

Extend `GreeksSource` enum in `models/enums.py`:

```python
class GreeksSource(StrEnum):
    MARKET = "market"      # from CBOE or broker
    COMPUTED = "computed"   # computed locally from raw IV
    SMOOTHED = "smoothed"  # computed locally from parity-smoothed IV
```

#### FR-V9: OptionContract Extension

Add optional field to `OptionContract` in `models/options.py`:

```python
smoothed_iv: float | None = None   # parity-smoothed IV (when call+put pair exists)
```

Validator: `math.isfinite()` and `v > 0` when not None.

### Non-Functional Requirements

#### NFR-V1: No New Dependencies
All implementations use existing scipy (SmoothBivariateSpline, UnivariateSpline), numpy, math. No new `uv add` required.

#### NFR-V2: Backward Compatibility
- IV smoothing is opt-in via `PricingConfig.use_parity_smoothing: bool = True`
- Surface fitting is opt-in via `ScanConfig.fit_vol_surface: bool = True`
- When disabled, pipeline behavior is identical to current (raw IVs, no surface indicators)
- All new model fields are `Optional` with `None` defaults
- All ~4,522 existing tests pass without modification

#### NFR-V3: Performance
- IV smoothing: O(n) grouping + O(1) per pair = negligible overhead
- Surface fitting: `SmoothBivariateSpline` is O(n log n) — <100ms for typical chains (200-500 contracts)
- Total per-ticker overhead: <150ms (well within Phase 3's existing ~2s budget per ticker)

#### NFR-V4: Numerical Stability
- Log-moneyness transform avoids large strike values dominating the fit
- Smoothing factor `s` adaptive to data density — prevents overfitting on sparse data
- Residuals computed as relative (not absolute) to handle different IV scales
- All outputs guarded with `math.isfinite()` before storage

#### NFR-V5: Graceful Degradation
| Condition | Behavior |
|-----------|----------|
| <4 contracts with valid IV | Surface = None, use raw IVs |
| 4-15 contracts, 2+ DTEs | Reduced-degree 2D fit (`kx`/`ky` adapted to data). Guard `n >= (kx+1)*(ky+1)` |
| 16+ contracts, 2+ DTEs | Full cubic 2D fit (`kx=3, ky=3`) |
| Single expiration | 1D smile fit (strike-only, sorted by log-moneyness), `is_1d_fallback=True` |
| Surface fit R² < 0.5 | Populate fields but log warning, `surface_fit_r2` visible to agents |
| Surface fit R² < 0.3 | Retry with `s * 2.0`. If still < 0.3, return None |
| FITPACK convergence warning | Not an exception — detected via R² quality gate after fitting |
| `ValueError` from scipy | Data count < `(kx+1)*(ky+1)` — reduce degree or fall back to 1D |
| All IVs at a strike are NaN | Skip that strike in surface fit |
| Strike has only call or only put | No parity smoothing, use raw IV |

## Success Criteria

| Metric | Target |
|--------|--------|
| Parity smoothing applied | >60% of contracts at expirations with both calls and puts |
| IV noise reduction (std dev of residuals) | >30% reduction vs raw IV residuals |
| Surface fit R² on liquid chains (top 20 S&P 500) | >0.85 mean |
| Surface fit R² on mid-cap chains | >0.60 mean |
| `iv_surface_residual` populated | >50% of debate tickers |
| Mispricing detection: residuals outside ±2σ | 5-15% of contracts (expected for well-fitted surface) |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~80 tests across 3 new test files |

## Constraints & Assumptions

### Constraints
- `indicators/vol_surface.py` (shared with native-quant): pure numpy/scipy — no Pydantic models (indicators module convention). Use NamedTuple for structured returns.
- `pricing/iv_smoothing.py`: scalar float in/out — no pandas, no API calls (pricing module convention).
- `scoring/contracts.py` modification: imports `pricing/dispatch` only — smoothing function imported from `pricing/iv_smoothing`.
- All new model fields need `math.isfinite()` validators. `MarketContext.surface_fit_r2` needs `[0, 1]` range check. New float fields must be added to `MarketContext.validate_optional_finite` field list (currently 45+ fields) or they'll silently pass NaN/Inf.
- Frozen models use `model_copy(update=...)` — never mutate in place.

### Assumptions
- yfinance chains provide `impliedVolatility` on most contracts (confirmed: present for >95% of liquid chains)
- Most liquid equities have both calls and puts at each strike (parity smoothing applicable)
- `SmoothBivariateSpline` is appropriate for IV surfaces (well-established in quant literature)
- Log-moneyness is a better fitting coordinate than raw strike (standard in vol surface literature)
- A 2σ threshold for "mispricing" is a reasonable starting point (tunable via config)

### scipy API Constraints (Context7-verified, scipy v1.17.0)
- `SmoothBivariateSpline.__call__` defaults to `grid=True` (Cartesian product output). Per-point evaluation requires `.ev()` or `__call__(grid=False)`. **All evaluation calls must use `.ev()`**.
- `SmoothBivariateSpline` minimum data: `(kx+1)*(ky+1)` points. Cubic (kx=ky=3) needs 16 points. Degree must adapt to data size.
- `UnivariateSpline` requires strictly increasing `x`. Log-moneyness arrays must be sorted before fitting.
- FITPACK convergence issues emit `warnings.warn()`, not exceptions. `ValueError` only fires on data-count violations. Quality must be assessed via R² after fitting.
- `IndicatorSignals` currently has 65 fields (native-quant added 4 to the original 61).

## Out of Scope

- **Local volatility surface** (Dupire) — requires solving a PDE, far more complex
- **Stochastic volatility models** (Heston, SABR) — parametric surface fits are a separate effort
- **Surface 3D visualization** — frontend chart deferred to future UI epic
- **Real-time surface updates** — would require streaming data
- **Cross-ticker surface comparison** — comparing vol surfaces between correlated tickers
- **Surface-based hedging recommendations** — using the surface for delta-hedge ratios
- **Historical surface persistence** — storing fitted surfaces over time for backtesting

## Cross-PRD Coordination: native-quant

This PRD shares `indicators/vol_surface.py` with the `native-quant` PRD. native-quant is **complete** (Epic 31, merged 2026-03-13). The `vol_surface.py` file exists with `VolSurfaceResult` (11 fields including `r_squared`, `residuals`, `z_scores`, `is_1d_fallback`), tiered `compute_vol_surface()` (400+ LOC), and `compute_surface_indicators()` stub.

| Aspect | native-quant (COMPLETE) | volatility-intelligence (this PRD) |
|--------|-------------|-----------------------------------|
| File | Created `vol_surface.py` with `VolSurfaceResult`, standalone tier, fitted surface tier, `compute_surface_indicators()` stub | Completes fitted surface implementation and `compute_surface_indicators()` |
| MarketContext fields | `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current` (lines 172-176) | `iv_surface_residual`, `surface_fit_r2`, `surface_is_1d` |
| `atm_iv_30d` | Surface-derived replaces `_extract_atm_iv_by_dte()` | Same mechanism — no new field |
| `smile_curvature` | Standalone finite-diff (Tier 2) | Surface derivative (Tier 1) — same field, better value |
| Rendering | Added MarketContext fields but NO `render_volatility_context()` function | Creates `render_volatility_context()` rendering ALL vol surface fields (both epics) |
| Weights | `+skew_25d(0.02) +smile_curvature(0.01)` | None (tiebreaker only) |

## Dependencies

### Internal
- `OptionContract`, `OptionGreeks`, `GreeksSource` models exist — extensions only (new fields)
- `compute_greeks()` in `scoring/contracts.py` — modification point for IV smoothing
- `scan/phase_options.py` — modification point for surface fitting insertion
- `MarketContext` in `models/analysis.py` — new fields for surface data
- `agents/_parsing.py` — new rendering block for surface context
- **`native-quant` dependency SATISFIED** (Epic 31, merged 2026-03-13): `vol_surface.py` exists with `VolSurfaceResult` NamedTuple (11 fields), tiered `compute_vol_surface()`, and `compute_surface_indicators()` stub. All 5 issues are now unblocked.

### External
- No external dependencies. scipy (`SmoothBivariateSpline`, `UnivariateSpline`) already in dependency tree.

## Delivery Issues

| Issue | Description | New Files | Modified Files | Est. Tests |
|-------|-------------|-----------|----------------|------------|
| 1 | IV smoothing function + GreeksSource extension | 1 (`pricing/iv_smoothing.py`) | 2 (`models/enums.py`, `models/options.py`) | ~20 |
| 2 | Smoothing integration into `compute_greeks()` | 0 | 1 (`scoring/contracts.py`) | ~15 |
| 3 | Vol surface fitting + mispricing indicators | 0 (extends `indicators/vol_surface.py`) | 0 | ~25 |
| 4 | Pipeline integration + MarketContext fields | 0 | 2 (`models/analysis.py`, `models/scan.py`) | ~10 |
| 5 | Agent prompt enrichment (create `render_volatility_context()`) + scoring integration | 0 | 3 (`agents/_parsing.py`, `scoring/composite.py`, `scoring/contracts.py`) | ~10 |
| **Total** | | **1** | **9** | **~80** |

Issues 1 and 3 can be implemented in parallel (both unblocked — native-quant merged). Issue 2 depends on 1. Issue 4 depends on 2 and 3. Issue 5 depends on 4.

```
Issue 1 (IV smoothing) ──→ Issue 2 (scoring integration) ──┐
                                                             ├──→ Issue 4 (pipeline) ──→ Issue 5 (agents + scoring)
Issue 3 (extend vol_surface.py) ───────────────────────────┘
```

## References

- Gatheral (2006) "The Volatility Surface: A Practitioner's Guide" — SVI parameterization, surface fitting methodology
- Hull (2018) "Options, Futures, and Other Derivatives", Ch. 20 — volatility smiles and surfaces
- QuantConnect/Lean `ImpliedVolatility` indicator — mirror_option smoothing pattern, `set_smoothing_function()` API
- QuantConnect/Lean `QLOptionPriceModel.cs` — QuantLib surface-based pricing
- Stoll (1969) "The Relationship Between Put and Call Option Prices" — put-call parity foundation
- De Boor (1978) "A Practical Guide to Splines" — mathematical basis for scipy spline interpolation
