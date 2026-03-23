# CLAUDE.md -- Technical Indicators

## Purpose

All technical indicator calculations. Each function takes pandas Series/DataFrames in,
returns pandas Series/DataFrames out. No API calls. No Pydantic models. Pure math.

## Function Convention

Every function: docstring with formula + reference, configurable params with standard defaults,
`InsufficientDataError` on bad input, NaN for warmup period. Raises `ValueError` for
structurally invalid inputs (mismatched lengths).

## Mathematical Correctness -- The Rules That Matter

### Smoothing

- **Wilder's smoothing** (RSI, ATR, ADX): `ewm(alpha=1/period, adjust=False)`.
  Do NOT SMA-seed -- use `ewm` directly. Early-period divergence from textbook is accepted
  because 200-bar OHLCV minimum + NaN warmup masking make it negligible.
- **Standard EMA** (Keltner middle band): `ewm(span=period, adjust=False)`.
  MUST be seeded with SMA of first `period` values (set earlier values to NaN, place SMA at
  index `period-1`). Required because Keltner is price-tracking where early accuracy matters.
- Get these wrong and every downstream value is silently incorrect.

### Specific Indicators

| Indicator | Critical rule | Common bug |
|---|---|---|
| RSI | Wilder's smoothing via `ewm(alpha=1/period)` | Using simple average instead of recursive |
| MACD Signal | EMA of **MACD line**, not of price | Computing signal from price series |
| Bollinger Bands | Population std dev (`ddof=0`) | Using sample std dev (`ddof=1`) |
| ATR | Wilder's smoothed True Range, needs OHLC | Missing prev_close in True Range calc |
| Stochastic | %K denominator can be zero (flat range) | Division by zero when high == low |
| RSI | avg_loss can be zero (all gains) | Division by zero -> RSI should be 100 |

### Options-Specific Indicators

| Indicator | Key rule |
|---|---|
| IV Rank | `(current - low) / (high - low) * 100` -- NOT the same as IV Percentile |
| IV Percentile | Count-based (% of days IV was lower). Drop NaN before counting |
| Put/Call Ratio | Specify which (volume vs OI) in function name |
| Max Pain | Sum ITM call + put value at each strike. Use `np.nansum` for NaN-safe computation |
| GEX (Gamma Exposure) | Net gamma * OI * 100 * spot^2 * 0.01 |

### Division-by-Zero Guards

Every division must be guarded:
```python
result = numerator / denominator.replace(0.0, np.nan)
```
Applies to: RSI (avg_loss), Stochastic (range), Williams %R, ADX (TR, DI_sum),
ROC (prev_close), ATR% (close), BB width (middle), A/D (hl_range), relative volume
(avg_vol), SMA alignment (sma_long), VWAP deviation (cum_vol, vwap).

### Input Validation

- All multi-Series functions must call `validate_aligned(*series)` before computation
- `InsufficientDataError` for too-short inputs
- `ValueError` for mismatched lengths

### Vectorization

- Use pandas/numpy vectorized ops. Never row-by-row Python loops for math.
- **Exception**: Path-dependent indicators (Supertrend) require iterative state --
  extract to numpy via `.to_numpy()` and loop over numpy, never pandas.
- Never `.apply(lambda ...)` for math numpy can do natively.

### NaN Rules

- Warmup period -> NaN. Never fill, backfill, or drop.
- `ewm(adjust=False)` absorbs NaN by carrying forward last value -- accepted pandas behavior.
- IV Percentile and Max Pain must handle NaN in inputs explicitly (drop NaN / use `nansum`).

## What Claude Gets Wrong Here

- Don't use simple averages where Wilder's smoothing is required (RSI, ATR)
- Don't compute MACD Signal from price instead of MACD Line
- Don't use `ddof=1` for Bollinger Bands -- use `ddof=0`
- Don't try to SMA-seed Wilder's smoothing -- use `ewm(alpha=1/period, adjust=False)` directly
- Don't seed standard EMA with first price -- seed with SMA of first `period` values
- Don't fill NaN warmup values
- Don't confuse IV Rank with IV Percentile
- Don't forget division-by-zero guards
- Don't forget `validate_aligned()` on multi-Series functions
- Don't use `np.sum` on NaN-containing data -- use `np.nansum` or drop NaN first
