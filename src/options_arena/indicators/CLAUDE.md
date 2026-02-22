# CLAUDE.md — Technical Indicators

## Purpose
All technical indicator calculations. Each function takes pandas Series/DataFrames in,
returns pandas Series/DataFrames out. No API calls. No Pydantic models. Pure math.

## Files

## Function Signature Convention
```python
def rsi(prices: pd.Series, period: int = 14, *, smoothing: str = "wilder") -> pd.Series:
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
- **Wilder's smoothing** (RSI, ATR): `avg = (prev_avg * (period - 1) + current) / period`. First value is simple mean.
- **EMA**: multiplier = `2 / (period + 1)`. Seed with SMA of first `period` values, NOT the first price.
- Get these wrong and every downstream value is silently incorrect.

### Specific Indicators
| Indicator | Critical rule | Common bug |
|---|---|---|
| RSI | Wilder's smoothing, not SMA of gains/losses | Using simple average instead of recursive |
| MACD Signal | EMA of **MACD line**, not of price | Computing signal from price series |
| Bollinger Bands | Population std dev (`ddof=0`) | Using sample std dev (`ddof=1`) |
| ATR | Wilder's smoothed True Range, needs OHLC | Missing prev_close in True Range calc |
| Stochastic | %K denominator can be zero (flat range) | Division by zero when high == low |
| RSI | avg_loss can be zero (all gains) | Division by zero → RSI should be 100 |

### Options-Specific Indicators
| Indicator | What it measures | Key rule |
|---|---|---|
| IV Rank | Where current IV sits in 52-week range | `(current - low) / (high - low) * 100` |
| IV Percentile | % of days in past year IV was lower | Count-based, NOT the same as IV Rank |
| Put/Call Ratio | Sentiment via volume or OI | Specify which (volume vs OI) in function name |
| Max Pain | Strike where options expire worthless most | Sum of ITM call + put value at each strike |
| Volatility Skew | IV difference across strikes | OTM put IV vs OTM call IV at same delta |
| Term Structure | IV across expirations | Compare ATM IV at different DTEs |
| GEX (Gamma Exposure) | Dealer hedging pressure | Net gamma * OI * 100 * spot^2 * 0.01 |

### Vectorization
- Use pandas/numpy vectorized ops. Never row-by-row Python loops.
- Wilder's smoothing: `pd.Series.ewm(alpha=1/period, adjust=False)` — this IS vectorized.
- Never `.apply(lambda ...)` for math numpy can do natively.

### NaN Rules
- Warmup period → NaN. Never fill, backfill, or drop.
- Internal NaN in input → propagate. Don't interpolate silently.
- Document expected NaN count in docstring.

## Testing (see also `tests/CLAUDE.md`)
Every indicator needs: known-value test (cite source), minimum-data test, insufficient-data test
(`InsufficientDataError`), NaN-count test, edge cases (flat data, monotonic, single spike).
Use `pytest.approx(rel=1e-6)`.

## What Claude Gets Wrong Here (Fix These)
- Don't use simple averages where Wilder's smoothing is required (RSI, ATR).
- Don't compute MACD Signal from price instead of MACD Line.
- Don't use `ddof=1` for Bollinger Bands — use `ddof=0`.
- Don't seed EMA with first price — seed with SMA of first `period` values.
- Don't fill NaN warmup values.
- Don't confuse IV Rank with IV Percentile.
- Don't forget division-by-zero guards (RSI when avg_loss=0, Stochastic when range=0).

