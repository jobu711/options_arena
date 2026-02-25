# System Patterns — Detailed Reference

Module-specific implementation details. Loaded on demand, not auto-loaded.
For core patterns, see `system-patterns.md`.

## Analysis & Scoring Algorithm Details

- **BSM pricing**: `bsm.py` — Merton 1973 with continuous dividend yield `q`. `scipy.stats.norm.cdf` for N(d1)/N(d2), `norm.pdf` for vega. BSM IV solver: Newton-Raphson (analytical vega as fprime, quadratic convergence, ~5-8 iterations). Bounded search [1e-6, 5.0]. Bracket pre-check rejects out-of-range market prices before iteration.
- **BAW pricing**: `american.py` — Barone-Adesi-Whaley 1987 analytical approximation. Early exercise premium added to BSM base price. Critical price found via Newton-Raphson on boundary condition. BAW IV solver: `scipy.optimize.brentq` (NOT Newton-Raphson — BAW has no analytical vega w.r.t. IV). Bracket [1e-6, 5.0], ~15-40 function evaluations typical.
- **BAW Greeks**: finite-difference bump-and-reprice (11 BAW evaluations per Greeks call). Bump sizes: `dS=1%`, `dT=1/365`, `dSigma=0.001`, `dR=0.001`. Sigma clamp prevents negative sigma in vega bump.
- **Dispatch**: `dispatch.py` — `ExerciseStyle`-based routing via `match`. AMERICAN→BAW, EUROPEAN→BSM. Three functions: `option_price`, `option_greeks`, `option_iv`.
- **Shared helpers**: `_common.py` — `validate_positive_inputs(S, K)`, `intrinsic_value`, `is_itm`, `boundary_greeks`. Input validation at all entry points.

## Scoring Pipeline Details

- **Normalization**: `percentile_rank_normalize()` converts raw indicator values to 0–100 percentile ranks with tie averaging. Single ticker → 50.0. `invert_indicators()` flips bb_width, atr_pct, relative_volume, keltner_width (higher raw = worse). `get_active_indicators()` detects universally-missing indicators for weight renormalization.
- **Composite scoring**: `composite_score()` computes weighted geometric mean: `exp(sum(w_i * ln(max(x_i, 1.0))) / sum(w_i))`. 18 indicators, 6 categories, weights sum to 1.0. Floor value 1.0 prevents log(0). Output clamped [0, 100].
- **Direction classification**: `determine_direction(adx, rsi, sma_alignment, config)` returns `SignalDirection`. ADX gate (< 15 → NEUTRAL), RSI scoring (strong +=2, mild +=1), SMA scoring (+=1 for >0.5 or <-0.5), SMA tiebreaker.
- **Contract selection**: `recommend_contracts()` pipeline: `filter_contracts()` (direction, OI, volume, spread ≤30% with zero-bid exemption) → `select_expiration()` (DTE [30,365], closest to midpoint 197.5) → `compute_greeks()` (via `pricing/dispatch.py`, IV re-solve for suspect market_iv with `math.isfinite` guard) → `select_by_delta()` (primary [0.20,0.50] + fallback [0.10,0.80], target 0.35).
- **Critical**: `score_universe()` returns percentile-ranked signals on `TickerScore.signals`. `determine_direction()` requires **raw** indicator values — callers must retain raw `IndicatorSignals` separately.

## S&P 500 Universe Fetch Details

- **Source**: `https://en.wikipedia.org/wiki/List_of_S%26P_500_companies`
- **Page structure**: 2 tables — constituents (`id="constituents"`, table 0) and historical changes (table 1)
- **Call**: `pd.read_html(url, attrs={"id": "constituents"})` — targets by HTML id, not positional index
- **Columns returned**: `Symbol`, `Security`, `GICS Sector`, `GICS Sub-Industry`, `Headquarters Location`, `Date added`, `CIK`, `Founded`
- **Columns needed**: `Symbol` (ticker), `GICS Sector` (sector classification)
- **Ticker translation**: Wikipedia uses `.` separator (`BRK.B`), yfinance uses `-` (`BRK-B`) — `symbol.replace(".", "-")`
- **Validation**: check `{"Symbol", "GICS Sector"} <= set(df.columns)` at parse time to catch schema drift
- **Caching**: cache result to SQLite; S&P 500 membership changes ~25 times/year, day-old data is acceptable

## Dividend Yield Waterfall Details

- **Purpose**: BAW American options pricing requires continuous dividend yield `q` as input
- **Problem**: yfinance `Ticker.info` uses camelCase keys (`dividendYield`, not `dividend_yield`) and returns `None` or omits the key entirely for ~40% of optionable tickers
- **yfinance fields confirmed** (Context7-verified):
  - `info["dividendYield"]` — forward annual yield as **decimal fraction** (0.005 = 0.5%), `float | None`
  - `info["trailingAnnualDividendYield"]` — trailing 12-month yield as decimal fraction, `float | None`
  - `info["dividendRate"]` — forward annual dividend in **dollars**, `float | None` (audit/cross-validation)
  - `info["trailingAnnualDividendRate"]` — trailing annual dividend in dollars, `float | None` (audit)
  - `Ticker.get_dividends(period="1y")` — `pd.Series` of per-payment dollar amounts, date-indexed
- **Solution**: 3-tier waterfall in service layer, guaranteed `float` output (never `None`):
  1. `info.get("dividendYield")` — if not `None`, accept (including `0.0` for growth stocks), source = `FORWARD`
  2. `info.get("trailingAnnualDividendYield")` — same `None` guard, source = `TRAILING`
  3. `Ticker.get_dividends(period="1y")` — sum payments / current price, source = `COMPUTED`
  4. `0.0` — source = `NONE`
- **Critical**: fall-through condition is `value is None`, NOT falsy — `0.0` is valid data for non-dividend stocks
- **Provenance**: `DividendSource` enum on `TickerInfo` tracks which tier produced the value
- **Cross-validation**: when yield and dollar-rate are both available, warn if >20% divergence

## yfinance Option Chain Columns (Context7-Verified)

- `option_chain(date)` returns `.calls` and `.puts` DataFrames with exactly these columns:
  `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`, `change`,
  `percentChange`, `volume`, `openInterest`, `impliedVolatility`, `inTheMoney`,
  `contractSize`, `currency`
- **No Greeks**: delta, gamma, theta, vega, rho are NOT provided by yfinance — never have been
- **`impliedVolatility`**: Yahoo-computed IV. Useful as IV solver seed and sanity-check against locally computed BAW IV
- **Implication**: `pricing/dispatch.py` is the sole source of Greeks for the entire pipeline

## Filter Architecture (Service vs Analysis Layer)

- **Service layer** (`options_data.py`): Basic liquidity filters — OI >= 100, volume >= 1. Rejects contracts where both bid AND ask are zero (truly dead). No spread or delta filtering.
- **Analysis layer** (`contracts.py`): OI/volume (defense in depth), spread filtering with zero-bid exemption (bid=0/ask>0 skips spread check), delta targeting (0.20-0.50) with closest-to-target fallback (0.10-0.80). Greeks computed via `pricing/dispatch.py`.
- This separation ensures zero-bid contracts reach the analysis layer for pricing computation.

## Indicator Convention

- Input: `pd.Series` or `pd.DataFrame`
- Output: `pd.Series` or `pd.DataFrame`
- Warmup period returns `NaN` — never fill, backfill, or drop
- `InsufficientDataError` if input too short
- Vectorized operations only (no Python loops for math)
