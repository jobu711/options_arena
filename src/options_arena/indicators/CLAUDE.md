# CLAUDE.md — Technical Indicators

## Purpose
All technical indicator calculations. Each function takes pandas Series/DataFrames in,
returns pandas Series/DataFrames out. No API calls. No Pydantic models. Pure math.

## Files
- `_validation.py` — Shared input validation helpers (`validate_aligned`)
- `oscillators.py` — RSI, Stochastic RSI, Williams %R
- `trend.py` — Rate of Change, ADX, Supertrend
- `volatility.py` — Bollinger Band Width, ATR%, Keltner Channel Width
- `volume.py` — OBV Trend, Relative Volume, A/D Line Trend
- `moving_averages.py` — SMA Alignment, VWAP Deviation
- `options_specific.py` — IV Rank, IV Percentile, Put/Call Ratios, Max Pain

## Function Signature Convention
```python
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index.
    Formula: RSI = 100 - (100 / (1 + RS)), RS = avg_gain / avg_loss (Wilder's smoothing).
    Reference: Wilder (1978) "New Concepts in Technical Trading Systems"
    Returns: Series with first `period` values as NaN.
    Raises: InsufficientDataError if len(prices) < period + 1.
    """
```
Every function: docstring with formula + reference, configurable params with standard defaults,
`InsufficientDataError` on bad input, NaN for warmup period.

## Mathematical Correctness — The Rules That Matter

### Smoothing
- **Wilder's smoothing** (RSI, ATR, ADX): `pd.Series.ewm(alpha=1/period, adjust=False)`.
  This is the vectorized equivalent of `avg = (prev_avg * (period - 1) + current) / period`.
  Note: `ewm` seeds from the first input value, not from the SMA of the first `period` values.
  This causes early-period divergence from textbook Wilder (up to ~14 RSI points near warmup),
  but converges to negligible difference (<0.001) within ~50 bars. Since the project's OHLCV
  minimum is 200 bars and the warmup period is masked as NaN, this is an accepted trade-off
  for full vectorization. Do NOT attempt to SMA-seed Wilder's smoothing — use `ewm` directly.
- **Standard EMA** (Keltner middle band): `pd.Series.ewm(span=period, adjust=False)`.
  Must be seeded with SMA of first `period` values (set earlier values to NaN, place SMA at
  index `period-1`). This is required because Keltner's EMA is a price-tracking indicator
  where early accuracy matters more than for smoothed averages.
- Get these wrong and every downstream value is silently incorrect.

### Specific Indicators
| Indicator | Critical rule | Common bug |
|---|---|---|
| RSI | Wilder's smoothing via `ewm(alpha=1/period)` | Using simple average instead of recursive |
| MACD Signal | EMA of **MACD line**, not of price | Computing signal from price series |
| Bollinger Bands | Population std dev (`ddof=0`) | Using sample std dev (`ddof=1`) |
| ATR | Wilder's smoothed True Range, needs OHLC | Missing prev_close in True Range calc |
| Stochastic | %K denominator can be zero (flat range) | Division by zero when high == low |
| RSI | avg_loss can be zero (all gains) | Division by zero → RSI should be 100 |
| ROC | prev_close can be zero | Division by zero → guard with `.replace(0.0, np.nan)` |
| ATR% | close can be zero | Division by zero → guard with `.replace(0.0, np.nan)` |

### Options-Specific Indicators
| Indicator | What it measures | Key rule |
|---|---|---|
| IV Rank | Where current IV sits in 52-week range | `(current - low) / (high - low) * 100` |
| IV Percentile | % of days in past year IV was lower | Count-based, NOT the same as IV Rank. Drop NaN before counting. |
| Put/Call Ratio | Sentiment via volume or OI | Specify which (volume vs OI) in function name |
| Max Pain | Strike where options expire worthless most | Sum of ITM call + put value at each strike. Use `np.nansum` for NaN-safe computation. |
| Volatility Skew | IV difference across strikes | OTM put IV vs OTM call IV at same delta |
| Term Structure | IV across expirations | Compare ATM IV at different DTEs |
| GEX (Gamma Exposure) | Dealer hedging pressure | Net gamma * OI * 100 * spot^2 * 0.01 |

### Input Validation
- All multi-Series functions must call `validate_aligned(*series)` before any computation.
  This catches mismatched-length inputs that would silently produce NaN via pandas index alignment.
- `InsufficientDataError` for too-short inputs.
- `ValueError` for structurally invalid inputs (mismatched lengths).

### Division-by-Zero Guards
Every division must be guarded. The standard pattern is:
```python
# Replace zeros with NaN before dividing, then fill back specific cases
result = numerator / denominator.replace(0.0, np.nan)
```
This applies to: RSI (avg_loss), Stochastic (range), Williams %R (hl_range), ADX (TR, DI_sum),
ROC (prev_close), ATR% (close), BB width (middle), A/D (hl_range), relative volume (avg_vol),
SMA alignment (sma_long), VWAP deviation (cum_vol, vwap).

### Vectorization
- Use pandas/numpy vectorized ops. Never row-by-row Python loops for math.
- **Exception**: Path-dependent indicators (Supertrend final bands) require iterative state.
  In these cases, extract to numpy arrays via `.to_numpy()` and loop over numpy — never pandas.
- Wilder's smoothing: `pd.Series.ewm(alpha=1/period, adjust=False)` — this IS vectorized.
- Never `.apply(lambda ...)` for math numpy can do natively.

### NaN Rules
- Warmup period → NaN. Never fill, backfill, or drop.
- Internal NaN in input → propagate where possible. Note: `ewm(adjust=False)` absorbs NaN
  by carrying forward the last computed value — this is inherent to the pandas API and accepted.
- IV Percentile and Max Pain must handle NaN in inputs explicitly (drop NaN / use `nansum`).
- Document expected NaN count in docstring.

## Testing (see also `tests/CLAUDE.md`)
Every indicator needs: known-value test (cite source), minimum-data test, insufficient-data test
(`InsufficientDataError`), NaN-count test, edge cases (flat data, monotonic, single spike).
Use `pytest.approx(rel=1e-6)`.

Additionally, test:
- NaN-in-input for iv_percentile and max_pain
- Division-by-zero for ROC (prev_close=0) and ATR% (close=0)
- Mismatched-length inputs for all multi-Series functions

## What Claude Gets Wrong Here (Fix These)
- Don't use simple averages where Wilder's smoothing is required (RSI, ATR).
- Don't compute MACD Signal from price instead of MACD Line.
- Don't use `ddof=1` for Bollinger Bands — use `ddof=0`.
- Don't try to SMA-seed Wilder's smoothing — use `ewm(alpha=1/period, adjust=False)` directly.
- Don't seed standard EMA with first price — seed with SMA of first `period` values.
- Don't fill NaN warmup values.
- Don't confuse IV Rank with IV Percentile.
- Don't forget division-by-zero guards (RSI, Stochastic, ROC, ATR%, BB width, etc.).
- Don't forget `validate_aligned()` on multi-Series functions.
- Don't use `np.sum` on data that may contain NaN — use `np.nansum` or drop NaN first.
- Don't count NaN entries when computing IV Percentile — drop them first.
