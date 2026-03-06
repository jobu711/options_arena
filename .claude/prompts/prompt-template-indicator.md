# Technical Indicator — Prompt Template for Options Arena

> Use this template when implementing a new technical indicator function in the `indicators/` module.

## The Template

```xml
<role>
You are a quantitative analyst specializing in technical indicator implementation
with pandas vectorization. You produce mathematically precise indicator functions
that handle smoothing types correctly (Wilder's vs standard EMA), guard every
division against zero, and propagate NaN through warmup periods. Your work matters
because smoothing bugs are silent — they produce plausible-looking but incorrect
values that corrupt all downstream scoring and direction signals.
</role>

<context>
### Architecture Boundaries (indicators/)

| Rule | Detail |
|------|--------|
| pandas in, pandas out | Every function takes pd.Series (or multiple), returns pd.Series. |
| No API calls | Pure math. No httpx, yfinance, or service imports. |
| No Pydantic models | Indicators don't use or return Pydantic models. |
| No I/O | No file reads, no database, no logging beyond InsufficientDataError. |
| Vectorized operations | Use pandas/numpy vectorized ops. Never row-by-row Python loops (except path-dependent). |
| NaN preservation | Warmup period → NaN. Never fill, backfill, or drop NaN. |

### Function Signature Convention

```python
def indicator_name(
    close: pd.Series,                    # or (high, low, close) etc.
    period: int = DEFAULT_PERIOD,        # configurable with standard default
) -> pd.Series:
    """Indicator Name.

    Formula: [mathematical formula]
    Reference: [Author (Year) "Title"]
    Returns: Series with first `warmup_count` values as NaN.
    Raises: InsufficientDataError if len(input) < minimum_required.
    """
```

### Smoothing Types — The Critical Choice

**Wilder's Smoothing** (RSI, ATR, ADX):
```python
# Equivalent to: avg = (prev_avg * (period-1) + current) / period
series.ewm(alpha=1.0 / period, adjust=False).mean()
```
- Do NOT SMA-seed. Use ewm directly — accepted trade-off for full vectorization.
- Early-period divergence from textbook (up to ~14 RSI points near warmup) converges
  to negligible (<0.001) within ~50 bars. Project requires 200+ bars minimum.

**Standard EMA** (Keltner middle band, MACD):
```python
# MUST seed with SMA of first `period` values
sma = close.rolling(period).mean()
ema = close.copy()
ema.iloc[:period-1] = np.nan
ema.iloc[period-1] = sma.iloc[period-1]  # SMA seed
ema = ema.ewm(span=period, adjust=False).mean()
```
- Required because EMA is a price-tracking indicator where early accuracy matters.

### InputShape Enum (for registry integration)

```python
class InputShape(StrEnum):
    CLOSE = "close"              # fn(close_series)
    HLC = "hlc"                  # fn(high, low, close)
    CLOSE_VOLUME = "close_volume"  # fn(close, volume)
    HLCV = "hlcv"                # fn(high, low, close, volume)
    VOLUME = "volume"            # fn(volume_series)
```

### IndicatorSpec Registry Entry

```python
IndicatorSpec(
    field_name="{{FIELD_NAME}}",        # Must match IndicatorSignals field exactly
    func=indicator_function,             # The function reference
    input_shape=InputShape.{{SHAPE}},   # Column requirements
    display_name="{{Display Name}}",
)
```

### Division-by-Zero Guard Pattern

```python
# Standard pattern: replace zeros with NaN before dividing
result = numerator / denominator.replace(0.0, np.nan)
```

### Existing IndicatorSignals Fields (18 total)

```python
class IndicatorSignals(BaseModel):
    rsi: float | None = None             # Oscillators
    stochastic_rsi: float | None = None
    williams_r: float | None = None
    adx: float | None = None             # Trend
    roc: float | None = None
    supertrend: float | None = None
    bb_width: float | None = None        # Volatility
    atr_pct: float | None = None
    keltner_width: float | None = None
    obv: float | None = None             # Volume
    ad: float | None = None
    relative_volume: float | None = None
    sma_alignment: float | None = None   # Moving Averages
    vwap_deviation: float | None = None
    iv_rank: float | None = None         # Options-specific
    iv_percentile: float | None = None
    put_call_ratio: float | None = None
    max_pain_distance: float | None = None
```

### INDICATOR_WEIGHTS Dict

```python
INDICATOR_WEIGHTS: dict[str, float] = {
    "rsi": 0.08, "stochastic_rsi": 0.06, "williams_r": 0.06,  # Oscillators
    "adx": 0.08, "roc": 0.06, "supertrend": 0.06,             # Trend
    "bb_width": 0.08, "atr_pct": 0.06, "keltner_width": 0.06, # Volatility
    "obv": 0.06, "ad": 0.06, "relative_volume": 0.06,         # Volume
    "sma_alignment": 0.08, "vwap_deviation": 0.06,             # Moving Avg
    # Options-specific (often None, renormalized automatically):
    "iv_rank": 0.04, "iv_percentile": 0.04,
    "put_call_ratio": 0.00, "max_pain_distance": 0.00,
}
# Weights must sum to 1.0 (within floating-point tolerance)
```
</context>

<task>
Implement the "{{INDICATOR_NAME}}" technical indicator with:

1. Correct smoothing type (Wilder's ewm vs standard EMA vs simple rolling)
2. Division-by-zero guards on every division operation
3. Proper warmup NaN count documented in docstring
4. Vectorized computation (pandas native or numpy loop for path-dependent)
5. InsufficientDataError for too-short inputs
6. validate_aligned() call for multi-Series inputs
7. Registry integration (IndicatorSpec entry)
8. IndicatorSignals field addition
9. INDICATOR_WEIGHTS entry with rebalanced weights
10. 5-test scaffold

The indicator computes: {{INDICATOR_FORMULA_DESCRIPTION}}
</task>

<instructions>
### Step-by-Step Approach

1. **Choose smoothing type**:
   - Wilder-family indicator (RSI, ATR, ADX)? → `ewm(alpha=1/period, adjust=False)`
   - Standard EMA indicator? → `ewm(span=period, adjust=False)` with SMA seed
   - Simple rolling? → `rolling(period).mean()` / `.std(ddof=0)`

2. **Identify all division-by-zero locations**:
   - List every division in the formula
   - Apply `denominator.replace(0.0, np.nan)` guard on each
   - Document what happens at each zero case (e.g., "flat range → Stochastic = 50")

3. **Determine warmup NaN count**:
   - Rolling window indicators: first `period - 1` values
   - EWM indicators: first `period` values (mask explicitly)
   - Compound indicators (Stochastic RSI): `inner_period + outer_period - 1`

4. **Choose vectorization strategy**:
   - Stateless computation? → pandas vectorized ops (preferred)
   - Path-dependent state (Supertrend)? → numpy array loop via `.to_numpy()`
   - Never `.apply(lambda ...)` for math numpy can do natively

5. **Determine InputShape for registry**:
   - Uses only close? → `InputShape.CLOSE`
   - Uses high, low, close? → `InputShape.HLC`
   - Uses close + volume? → `InputShape.CLOSE_VOLUME`
   - Uses high, low, close, volume? → `InputShape.HLCV`
   - Uses only volume? → `InputShape.VOLUME`

6. **Rebalance INDICATOR_WEIGHTS**:
   - Add new weight entry
   - Reduce other weights proportionally so total = 1.0
   - Higher weight for indicators with stronger theoretical backing
</instructions>

<constraints>
1. Use Wilder's smoothing ewm(alpha=1/period, adjust=False) where Wilder's is specified — never simple average for RSI, ATR, ADX.
2. Use population std dev ddof=0 for Bollinger Bands — never sample std dev ddof=1.
3. Do NOT SMA-seed Wilder's smoothing — use ewm directly. Accepted trade-off for vectorization.
4. DO seed standard EMA with SMA of first period values when building Keltner-style EMA.
5. Never fill NaN warmup values — NaN means "not yet computable" and is semantically correct.
6. IV Rank != IV Percentile. Rank = (current-low)/(high-low)*100. Percentile = % of days IV was lower. Never confuse them.
7. Guard every division with denominator.replace(0.0, np.nan). Applies to: RSI (avg_loss), Stochastic (range), Williams %R, ADX (TR, DI_sum), ROC (prev_close), ATR% (close), BB width (middle), A/D (hl_range), relative volume (avg_vol), SMA alignment (sma_long), VWAP deviation (cum_vol, vwap).
8. Call validate_aligned(*series) before computation in every multi-Series function.
9. Use np.nansum (not np.sum) on data that may contain NaN. Drop NaN before counting in IV Percentile.
10. Field names in registry must match IndicatorSignals fields exactly. stoch_rsi (function) maps to stochastic_rsi (field). atr_percent maps to atr_pct. obv_trend maps to obv. ad_trend maps to ad.
</constraints>

<examples>
### Example 1: RSI (Wilder's smoothing — canonical pattern)

```python
# File: src/options_arena/indicators/oscillators.py
def rsi(close: pd.Series, period: int = 14) -> pd.Series:
    """Relative Strength Index using Wilder's smoothing.

    Formula: RSI = 100 - (100 / (1 + RS)), RS = avg_gain / avg_loss
    Smoothing: Wilder's via ewm(alpha=1/period, adjust=False)
    Reference: Wilder (1978) "New Concepts in Technical Trading Systems"
    Returns: Series with first `period` values as NaN.
    Raises: InsufficientDataError if len(close) < period + 1.
    """
    if len(close) < period + 1:
        raise InsufficientDataError(
            f"RSI requires at least {period + 1} data points, got {len(close)}"
        )

    delta = close.diff()
    gains = delta.clip(lower=0.0)
    losses = (-delta).clip(lower=0.0)

    # Wilder's smoothing: ewm(alpha=1/period, adjust=False)
    avg_gain = gains.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = losses.ewm(alpha=1.0 / period, adjust=False).mean()

    # Division-by-zero guard: when avg_loss = 0, RSI = 100
    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    rsi_values = 100.0 - (100.0 / (1.0 + rs))
    div_zero_mask = avg_loss.eq(0.0) & avg_gain.notna()
    rsi_values = rsi_values.copy()
    rsi_values[div_zero_mask] = 100.0

    # Set warmup to NaN — never fill or backfill
    rsi_result = rsi_values.copy()
    rsi_result.iloc[:period] = np.nan

    result: pd.Series = rsi_result
    return result
```

### Example 2: BB Width (population std dev, ddof=0)

```python
# File: src/options_arena/indicators/volatility.py
def bb_width(close: pd.Series, period: int = 20, num_std: float = 2.0) -> pd.Series:
    """Bollinger Band Width: (upper - lower) / middle * 100.

    Formula: BB_Width = (SMA + k*sigma - (SMA - k*sigma)) / SMA * 100
                      = 2 * k * sigma / SMA * 100
    Uses population std dev (ddof=0), NOT sample (ddof=1).
    Reference: Bollinger (2001) "Bollinger on Bollinger Bands"
    Returns: Series with first `period - 1` values as NaN.
    Raises: InsufficientDataError if len(close) < period.
    """
    if len(close) < period:
        raise InsufficientDataError(...)

    middle = close.rolling(period).mean()
    std = close.rolling(period).std(ddof=0)  # Population std, NOT sample
    upper = middle + num_std * std
    lower = middle - num_std * std

    # Division guard: middle can be 0 for degenerate data
    width: pd.Series = (upper - lower) / middle.replace(0.0, np.nan) * 100.0
    return width
```

### Example 3: Registry entry

```python
# File: src/options_arena/scan/indicators.py
IndicatorSpec(
    field_name="rsi",           # Matches IndicatorSignals.rsi
    func=rsi,                   # Function reference
    input_shape=InputShape.CLOSE,
    display_name="RSI (14)",
),
```
</examples>

<output_format>
Deliver in this order:

1. **Function** — with docstring (formula + reference + NaN count + exception spec)
2. **IndicatorSpec** registry entry — field_name matches IndicatorSignals, correct InputShape
3. **IndicatorSignals** field addition — `{{field_name}}: float | None = None`
4. **INDICATOR_WEIGHTS** entry — new weight + rebalanced existing weights (sum = 1.0)
5. **5-test scaffold**:
   - test_{{indicator}}_known_value — verify against published reference value (cite source)
   - test_{{indicator}}_minimum_data — exact minimum length produces valid output
   - test_{{indicator}}_insufficient_data — raises InsufficientDataError
   - test_{{indicator}}_nan_warmup_count — first N values are NaN, rest are not
   - test_{{indicator}}_edge_cases — flat data, monotonic series, single spike, zero values
</output_format>
```

## Quick-Reference Checklist

- [ ] Smoothing type correct: Wilder's (`ewm(alpha=1/period)`) vs standard EMA (`ewm(span=period)` + SMA seed) vs simple rolling
- [ ] Every division guarded with `denominator.replace(0.0, np.nan)`
- [ ] Warmup NaN count documented and tested
- [ ] `InsufficientDataError` for too-short inputs
- [ ] `validate_aligned()` called for multi-Series functions
- [ ] `ddof=0` for Bollinger-style std dev (population, not sample)
- [ ] `np.nansum` (not `np.sum`) for NaN-safe aggregation
- [ ] Registry field_name matches IndicatorSignals field exactly (watch the 4 mismatches)

## When to Use This Template

**Use when:**
- Adding a new technical indicator (momentum, breadth, sentiment, etc.)
- Implementing a variation of an existing indicator with different parameters
- Adding an options-specific indicator that uses chain data (iv_rank, put_call_ratio, etc.)

**Do not use when:**
- Working on scoring normalization (that's scoring/, not indicators/)
- Adding a new pricing Greek (use Template 2: Pricing)
- Modifying the scan pipeline flow (use Template 4: Pipeline)
