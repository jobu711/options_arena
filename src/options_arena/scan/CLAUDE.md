# CLAUDE.md — Scan Pipeline Module (`scan/`)

## Purpose

Pipeline orchestration: ties together `services/`, `indicators/`, `scoring/`, and `data/` into
a testable, cancellable, progress-reporting 4-phase async pipeline. Replaces v3's monolithic
430-line `cli.py` scan function with a `ScanPipeline` class.

This is the most integration-heavy module in the project. Every type at every boundary was
verified against the actual source before writing this document.

## Files

| File | Purpose |
|------|---------|
| `progress.py` | `ScanPhase` enum, `CancellationToken`, `ProgressCallback` protocol |
| `indicators.py` | `InputShape` enum, `IndicatorSpec`, `INDICATOR_REGISTRY` (15 entries), `ohlcv_to_dataframe()`, `compute_indicators()` |
| `models.py` | Pipeline-internal typed models: `UniverseResult`, `ScoringResult`, `OptionsResult`, `ScanResult` |
| `pipeline.py` | `ScanPipeline` class with 4 async phases |
| `__init__.py` | Re-exports public API with `__all__` |

---

## Architecture Rules

- `scan/` orchestrates flow — it calls into other modules but contains no business logic
- All data crosses boundaries as **typed Pydantic models** — never raw dicts
- Service calls go through injected service instances — never import service internals
- Indicator computation goes through `compute_indicators()` — never call indicator functions directly from `pipeline.py`
- Scoring goes through `scoring/` public API — never replicate normalization or composite logic
- Persistence goes through `data/Repository` — never write raw SQL
- No `print()` — use `logging` module only
- All thresholds from `ScanConfig` / `PricingConfig` — no hardcoded magic numbers

---

## Critical Data Flow (All Types Verified)

### Phase 1: Universe + OHLCV
```text
UniverseService.fetch_optionable_tickers() → list[str]
UniverseService.fetch_sp500_constituents() → list[SP500Constituent]
  SP500Constituent.ticker: str, SP500Constituent.sector: str

MarketDataService.fetch_batch_ohlcv(tickers, period="1y") → BatchOHLCVResult
  BatchOHLCVResult.results: list[TickerOHLCVResult]
  TickerOHLCVResult.ticker: str
  TickerOHLCVResult.data: list[OHLCV] | None
  TickerOHLCVResult.ok: bool (property)
  BatchOHLCVResult.succeeded() → list[TickerOHLCVResult]  (data is not None)
  BatchOHLCVResult.failed() → list[TickerOHLCVResult]     (data is None)

Filter: len(result.data) >= config.ohlcv_min_bars (default 200)
Output: dict[str, list[OHLCV]] — ticker → OHLCV bars (only tickers with enough data)
```

### Phase 2: Indicators + Scoring + Direction
```text
For each ticker:
  ohlcv_to_dataframe(list[OHLCV]) → pd.DataFrame
    Columns: open, high, low, close, volume (float/int, NOT Decimal)
    Index: date

  compute_indicators(df, INDICATOR_REGISTRY) → IndicatorSignals
    15 fields populated, 4 options-specific fields left as None
    Values are RAW (not normalized)

Collect: raw_signals: dict[str, IndicatorSignals]

score_universe(raw_signals) → list[TickerScore]
  Internally: normalize → invert → composite score → sort descending
  TickerScore.signals contains NORMALIZED (0-100) values
  TickerScore.direction is NEUTRAL (placeholder — overwritten below)
  TickerScore.composite_score: float (0-100)

For each scored ticker:
  determine_direction(
      adx=raw_signals[ticker].adx,      # RAW value, NOT normalized
      rsi=raw_signals[ticker].rsi,       # RAW value, NOT normalized
      sma_alignment=raw_signals[ticker].sma_alignment,  # RAW value
      config=scan_config,
  ) → SignalDirection

Output: list[TickerScore] with direction set, raw_signals dict retained
```

### Phase 3: Liquidity Pre-filter + Options + Contracts
```text
Liquidity pre-filter (using OHLCV data from Phase 1):
  avg_dollar_volume = mean(close * volume) over full history
  latest_close = last OHLCV close price
  Keep if: avg_dollar_volume >= config.min_dollar_volume AND latest_close >= config.min_price

Top-N by composite_score (config.top_n, default 50)

FredService.fetch_risk_free_rate() → float  (called ONCE for entire scan, never raises)

For each top-N ticker:
  OptionsDataService.fetch_chain_all_expirations(ticker) → list[ExpirationChain]
    ExpirationChain.expiration: date
    ExpirationChain.contracts: list[OptionContract]
      OptionContract.greeks is ALWAYS None (yfinance provides no Greeks)

  MarketDataService.fetch_ticker_info(ticker) → TickerInfo
    TickerInfo.dividend_yield: float (guaranteed, never None, default 0.0)
    TickerInfo.current_price: Decimal

  All contracts across expirations: list[OptionContract]
  spot = float(ticker_info.current_price)

  recommend_contracts(
      contracts=all_contracts,
      direction=ticker_score.direction,
      spot=spot,
      risk_free_rate=risk_free_rate,  # from FredService (shared)
      dividend_yield=ticker_info.dividend_yield,
      config=pricing_config,
  ) → list[OptionContract]  # 0 or 1 contracts with greeks populated

Output: dict[str, list[OptionContract]] — ticker → recommended contracts
```

### Phase 4: Persist
```text
ScanRun(
    started_at=start_time,   # UTC datetime, captured at pipeline start
    completed_at=now_utc,    # UTC datetime
    preset=preset,           # ScanPreset enum
    tickers_scanned=universe_count,
    tickers_scored=scored_count,
    recommendations=recommendation_count,
)

Repository.save_scan_run(scan_run) → int  (DB-assigned ID)
Repository.save_ticker_scores(scan_id, scores) → None  (batch insert)
```

---

## IndicatorSpec Registry — 14 Entries (NOT 18)

### Why 15, Not 19?
The 4 options-specific indicators (`iv_rank`, `iv_percentile`, `put_call_ratio`,
`max_pain_distance`) require option chain data that isn't available during Phase 2.
They are intentionally left as `None` on `IndicatorSignals`. The scoring module's
`get_active_indicators()` detects universally-missing indicators and renormalizes
weights automatically.

### InputShape Enum
```python
class InputShape(StrEnum):
    CLOSE = "close"              # fn(close_series)
    HLC = "hlc"                  # fn(high, low, close)
    CLOSE_VOLUME = "close_volume"  # fn(close, volume)
    HLCV = "hlcv"                # fn(high, low, close, volume)
    VOLUME = "volume"            # fn(volume_series)
```

### Column Dispatch (match statement in compute_indicators)
```python
match spec.input_shape:
    case InputShape.CLOSE:
        result = spec.func(df["close"])
    case InputShape.HLC:
        result = spec.func(df["high"], df["low"], df["close"])
    case InputShape.CLOSE_VOLUME:
        result = spec.func(df["close"], df["volume"])
    case InputShape.HLCV:
        result = spec.func(df["high"], df["low"], df["close"], df["volume"])
    case InputShape.VOLUME:
        result = spec.func(df["volume"])
```

### Complete Registry (15 entries)

| # | `field_name` | Function | `InputShape` | Category |
|---|-------------|----------|-------------|----------|
| 1 | `rsi` | `rsi` | `CLOSE` | Oscillators |
| 2 | `stochastic_rsi` | `stoch_rsi` | `CLOSE` | Oscillators |
| 3 | `williams_r` | `williams_r` | `HLC` | Oscillators |
| 4 | `adx` | `adx` | `HLC` | Trend |
| 5 | `roc` | `roc` | `CLOSE` | Trend |
| 6 | `supertrend` | `supertrend` | `HLC` | Trend |
| 7 | `macd` | `macd` | `CLOSE` | Trend |
| 8 | `bb_width` | `bb_width` | `CLOSE` | Volatility |
| 9 | `atr_pct` | `atr_percent` | `HLC` | Volatility |
| 10 | `keltner_width` | `keltner_width` | `HLC` | Volatility |
| 11 | `obv` | `obv_trend` | `CLOSE_VOLUME` | Volume |
| 12 | `relative_volume` | `relative_volume` | `VOLUME` | Volume |
| 13 | `ad` | `ad_trend` | `HLCV` | Volume |
| 14 | `sma_alignment` | `sma_alignment` | `CLOSE` | Moving Avg |
| 15 | `vwap_deviation` | `vwap_deviation` | `CLOSE_VOLUME` | Moving Avg |

### Function Name ≠ Field Name Mapping

| Function Name | IndicatorSignals Field | Why Different |
|---------------|----------------------|---------------|
| `stoch_rsi` | `stochastic_rsi` | Full name preferred |
| `atr_percent` | `atr_pct` | Shortened |
| `obv_trend` | `obv` | Simplified |
| `ad_trend` | `ad` | Simplified |

The remaining 10 indicators have matching function and field names.

---

## OHLCV → DataFrame Conversion

The `ohlcv_to_dataframe()` function converts `list[OHLCV]` to a pandas DataFrame:

```python
def ohlcv_to_dataframe(ohlcv: list[OHLCV]) -> pd.DataFrame:
    """Convert OHLCV Pydantic models to DataFrame for indicator computation.

    Critical conversions:
    - Decimal → float (prices): indicators use float math, not Decimal
    - date → DatetimeIndex: standard pandas time series convention
    - Sorted ascending by date: indicators assume chronological order
    """
```

**Input**: `list[OHLCV]` where each `OHLCV` has:
- `date: datetime.date`
- `open, high, low, close, adjusted_close: Decimal`
- `volume: int`

**Output**: `pd.DataFrame` with columns:
- `open`, `high`, `low`, `close`: `float` (from `Decimal`)
- `volume`: `int`
- Index: `DatetimeIndex` from `OHLCV.date`

**Rules**:
- Sort by date ascending (never assume input order)
- Convert `Decimal` to `float` via `float()` — precision loss is acceptable for indicators
- Do NOT include `adjusted_close` or `ticker` — indicators don't use them

---

## Raw vs Normalized Signals — CRITICAL

`score_universe()` returns `TickerScore` objects where `signals` contains **percentile-ranked
(0–100) normalized** values. But `determine_direction()` needs **raw indicator values**:

```text
determine_direction(adx=RAW_adx, rsi=RAW_rsi, sma_alignment=RAW_sma_alignment)
```

**The pipeline MUST retain `raw_signals: dict[str, IndicatorSignals]` separately** from the
normalized signals on `TickerScore.signals`. Do NOT pass `TickerScore.signals.adx` (normalized)
to `determine_direction()` — this would compare percentile ranks (e.g., 75.0) against absolute
thresholds (e.g., ADX < 15.0 → NEUTRAL), producing wrong results.

### Correct Pattern
```python
raw_signals: dict[str, IndicatorSignals] = {}
for ticker, ohlcv_list in ohlcv_map.items():
    df = ohlcv_to_dataframe(ohlcv_list)
    raw_signals[ticker] = compute_indicators(df, INDICATOR_REGISTRY)

scored = score_universe(raw_signals)  # signals are now NORMALIZED

for ts in scored:
    raw = raw_signals[ts.ticker]
    ts.direction = determine_direction(
        adx=raw.adx or 0.0,
        rsi=raw.rsi or 50.0,
        sma_alignment=raw.sma_alignment or 0.0,
        config=scan_config,
    )
```

### Fallback Values for Missing Raw Indicators
When a raw indicator is `None` (computation failed), use neutral defaults:
- `adx` → `0.0` (below any threshold → NEUTRAL)
- `rsi` → `50.0` (midpoint, contributes nothing)
- `sma_alignment` → `0.0` (neutral)

---

## Liquidity Pre-Filter (Phase 3)

Applied BEFORE fetching option chains (expensive API call). Uses OHLCV data from Phase 1:

```python
avg_dollar_volume = float(
    sum(float(o.close) * o.volume for o in ohlcv_list) / len(ohlcv_list)
)
latest_close = float(ohlcv_list[-1].close)  # assumes sorted ascending

keep = (
    avg_dollar_volume >= config.min_dollar_volume  # default $10M
    and latest_close >= config.min_price           # default $10
)
```

This pre-filter runs on ALL scored tickers (not just top-N) before the top-N cutoff.

---

## Error Handling by Phase

### Phase 1: Universe + OHLCV
- Universe fetch fails → **fatal** (DataSourceUnavailableError propagates up)
- Individual OHLCV fetch fails → **skip ticker** (BatchOHLCVResult isolates failures)
- Insufficient data (< `ohlcv_min_bars`) → **skip ticker**, log at INFO

### Phase 2: Indicators + Scoring
- Individual indicator fails → **set to None**, log at WARNING, continue with other indicators
- All indicators fail for a ticker → all `None` signals → low composite score → naturally filtered
- `score_universe()` → shouldn't fail on valid `IndicatorSignals` input
- `determine_direction()` → pure math, shouldn't fail

### Phase 3: Options + Contracts
- Options chain fetch fails → **skip ticker**, log at WARNING
- `fetch_ticker_info()` fails → **skip ticker**, log at WARNING
- No contracts pass filter → empty recommendation (0 contracts), ticker still in results
- Greeks computation fails for a contract → contract excluded (logged at WARNING by `scoring/contracts.py`)
- FredService → **never raises** (falls back to `PricingConfig.risk_free_rate_fallback`)

### Phase 4: Persist
- DB save fails → **propagate** (RuntimeError if not connected, sqlite3 errors)
- This is the only phase where failure is not recoverable

### Cancellation
- Token checked BETWEEN phases (not within phases)
- If cancelled, return partial `ScanResult` with `cancelled=True` and `phases_completed` count

---

## CancellationToken Design

Instance-scoped (not global). Replaces v3's `_scan_cancelled` global variable.

```python
class CancellationToken:
    """Thread-safe, instance-scoped cancellation for scan pipeline."""

    def cancel(self) -> None: ...
    @property
    def is_cancelled(self) -> bool: ...
```

- Created per `run()` invocation
- CLI hooks `Ctrl+C` signal handler to call `token.cancel()`
- Checked after each phase completes (not mid-phase)
- Not async — just a bool flag protected by `threading.Event` or simple `bool`

---

## ProgressCallback Protocol

```python
class ProgressCallback(Protocol):
    def __call__(self, phase: ScanPhase, current: int, total: int) -> None: ...
```

- `ScanPhase` is a `StrEnum`: `UNIVERSE`, `SCORING`, `OPTIONS`, `PERSIST`
- `current` and `total` are phase-specific counts
- Called at phase start (`current=0`), during phase (incremental), and phase end (`current=total`)
- Framework-agnostic: CLI uses Rich progress bar, tests use no-op or recording callback

---

## Service Lifecycle

The pipeline does NOT create services. Services are injected via constructor (DI pattern):

```python
class ScanPipeline:
    def __init__(
        self,
        settings: AppSettings,
        market_data: MarketDataService,
        options_data: OptionsDataService,
        fred: FredService,
        universe: UniverseService,
        repository: Repository,
    ) -> None: ...
```

**Responsibility boundary**:
- `cli.py` creates `AppSettings`, services, `Database`, `Repository`
- `cli.py` creates `ScanPipeline` with injected dependencies
- `cli.py` calls `await pipeline.run(...)` and handles the `ScanResult`
- `cli.py` closes services in a `finally` block
- `ScanPipeline` never creates or closes services

---

## Integration Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | Business logic from other modules |
| `services/` (public service classes, BatchOHLCVResult, etc.) | Service internals (`helpers.py`) |
| `scoring/` (score_universe, determine_direction, recommend_contracts) | Scoring internals |
| `indicators/` (function references for registry) | Indicator internals (`_validation.py`) |
| `data/` (Database, Repository) | Raw SQL, aiosqlite |
| `asyncio`, `logging`, `math`, `pandas` | `print()`, `httpx`, `yfinance` |

---

## What Claude Gets Wrong — Scan-Specific (Fix These)

1. **Using `input_shape="series"` or `"dataframe"`** — Use `InputShape` enum with 5 specific variants
   (`CLOSE`, `HLC`, `CLOSE_VOLUME`, `HLCV`, `VOLUME`). "Series vs DataFrame" doesn't tell you
   which columns to extract.

2. **Putting 19 entries in the registry** — Only 15 OHLCV-based indicators go in `INDICATOR_REGISTRY`.
   The 4 options-specific indicators need chain data, not OHLCV.

3. **Passing normalized signals to `determine_direction()`** — Direction uses RAW ADX/RSI/SMA values.
   Normalized values (0–100 percentile ranks) compared against absolute thresholds (ADX < 15.0)
   produce meaningless results. Retain `raw_signals` dict separately.

4. **Using function names as field names** — `stoch_rsi` (function) ≠ `stochastic_rsi` (field).
   `atr_percent` ≠ `atr_pct`. `obv_trend` ≠ `obv`. `ad_trend` ≠ `ad`. The `IndicatorSpec.field_name`
   must match `IndicatorSignals` fields exactly.

5. **Forgetting to convert Decimal → float** — `OHLCV` prices are `Decimal`. Indicator functions
   expect `float`/`pd.Series[float]`. `ohlcv_to_dataframe()` must do this conversion.

6. **Creating services inside the pipeline** — Services are injected via constructor. Pipeline
   never creates, configures, or closes services.

7. **Fetching risk-free rate per ticker** — `FredService.fetch_risk_free_rate()` is called ONCE
   for the entire scan. The rate doesn't change between tickers.

8. **Fetching options chains for ALL scored tickers** — Chains are fetched only for the top-N
   tickers that pass the liquidity pre-filter. Not for the entire universe.

9. **Forgetting that `OptionContract.greeks` is always None from services** — Greeks are computed
   by `recommend_contracts()` via `pricing/dispatch.py`. Never assume greeks are populated
   on contracts returned by `OptionsDataService`.

10. **Using `Optional[X]`** — Use `X | None`. Never import from `typing`.

11. **Using raw strings for ScanPhase** — Use `ScanPhase` StrEnum, per project convention.

12. **Making CancellationToken global** — It's instance-scoped, passed to `run()`. Multiple
    concurrent scans each get their own token.

13. **Skipping the liquidity pre-filter** — Without it, the pipeline fetches expensive option
    chains for illiquid penny stocks. The pre-filter uses OHLCV data already available from Phase 1.

14. **Forgetting `TickerScore` is NOT frozen** — Unlike most models, `TickerScore` is mutable.
    Direction can be updated after scoring. `IndicatorSignals` is also mutable (populated
    incrementally).
