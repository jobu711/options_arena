# Algorithms Reference

## BSM Pricing (European Options)

- `bsm.py` -- Merton 1973 with continuous dividend yield `q`. Uses `scipy.stats.norm.cdf` for N(d1)/N(d2), `norm.pdf` for vega
- BSM IV solver: Newton-Raphson with analytical vega as fprime (quadratic convergence, ~5-8 iterations). Bounded [1e-6, 5.0]. Bracket pre-check rejects out-of-range market prices before iteration
- Guard `T=0`: `sigma * sqrt(T)` in denominators; use `math.log/sqrt/exp` for scalars, not numpy

## BAW Pricing (American Options)

- `american.py` -- Barone-Adesi-Whaley 1987 analytical approximation. Early exercise premium added to BSM base price. Critical price found via Newton-Raphson on boundary condition
- BAW IV solver: `scipy.optimize.brentq` (NOT Newton-Raphson -- BAW has no analytical vega w.r.t. IV). Bracket [1e-6, 5.0], ~15-40 function evaluations
- BAW Greeks: finite-difference bump-and-reprice (11 BAW evaluations per call). Bumps: dS=1%, dT=1/365, dSigma=0.001, dR=0.001. Sigma clamp prevents negative sigma in vega bump
- Dispatch: `dispatch.py` routes by `ExerciseStyle` via `match`. AMERICAN->BAW, EUROPEAN->BSM. Three functions: `option_price`, `option_greeks`, `option_iv`
- Shared helpers: `_common.py` -- `validate_positive_inputs(S, K)`, `intrinsic_value`, `is_itm`, `boundary_greeks`

## Scoring Pipeline

- **Normalization**: `percentile_rank_normalize()` converts raw values to 0-100 percentile ranks with tie averaging. Single ticker -> 50.0. `invert_indicators()` flips bb_width, atr_pct, relative_volume, keltner_width, chain_spread_pct (higher raw = worse). `get_active_indicators()` detects missing indicators for weight renormalization
- **Composite scoring**: Weighted geometric mean: `exp(sum(w_i * ln(max(x_i, 0.5))) / sum(w_i))`. 27 indicators, weights sum to 1.0. Floor 0.5 prevents log(0). Output clamped [0, 100]
- **Direction classification**: `determine_direction(adx, rsi, sma_alignment, config)` returns `SignalDirection`. ADX gate (< 15 -> NEUTRAL), RSI scoring (strong +=2, mild +=1), SMA scoring (+=1 for >0.5 or <-0.5), SMA tiebreaker
- **Contract selection**: `recommend_contracts()` pipeline: `filter_contracts()` (direction, OI, volume, spread <=30% with zero-bid exemption) -> `select_expiration()` (DTE [30,365], closest to midpoint 197.5) -> `compute_greeks()` (via `pricing/dispatch.py`, IV re-solve for suspect market_iv) -> `select_by_delta()` (primary [0.20,0.50] + fallback [0.10,0.80], target 0.35)
- **Critical**: `score_universe()` returns percentile-ranked signals. `determine_direction()` requires RAW indicator values -- callers must retain raw `IndicatorSignals` separately

## Filter Architecture (Two Layers)

- **Service layer** (`options_data.py`): Basic liquidity -- OI >= 100, volume >= 1. Rejects contracts where both bid AND ask are zero. No spread or delta filtering
- **Analysis layer** (`contracts.py`): OI/volume (defense in depth), spread filtering with zero-bid exemption (bid=0/ask>0 skips spread check), delta targeting (0.20-0.50) with fallback (0.10-0.80). Greeks via `pricing/dispatch.py`
- Separation ensures zero-bid contracts reach analysis layer for pricing computation

## Indicator Conventions

- Input/output: `pd.Series` or `pd.DataFrame`
- Warmup period returns `NaN` -- never fill, backfill, or drop
- `InsufficientDataError` if input too short
- Vectorized operations only (no Python loops for math)
- Wilder's smoothing: `ewm(alpha=1/period, adjust=False)` -- do NOT SMA-seed
- Standard EMA (Keltner): MUST seed with SMA of first `period` values
- Bollinger Bands: population std dev `ddof=0`, not sample `ddof=1`
- Division-by-zero: `denominator.replace(0.0, np.nan)` before every division
- IV Rank != IV Percentile (range-based vs count-based)

## Dividend Yield Waterfall

- BAW requires continuous dividend yield `q`. yfinance returns `None` for ~40% of tickers
- 3-tier waterfall: (1) `info["dividendYield"]` (forward), (2) `info["trailingAnnualDividendYield"]` (trailing), (3) `get_dividends(period="1y")` sum/price (computed), (4) 0.0 fallback
- Fall-through on `value is None`, NOT falsy -- `0.0` is valid for non-dividend stocks
- `DividendSource` enum tracks provenance
