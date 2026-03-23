# CLAUDE.md -- Scan Pipeline Module (`scan/`)

## Purpose

Pipeline orchestration: ties together `services/`, `indicators/`, `scoring/`, and `data/`
into a testable, cancellable, progress-reporting 4-phase async pipeline.

The pipeline is decomposed into a thin `ScanPipeline` orchestrator (~352 LOC) that delegates
to four standalone phase functions. Each phase is a module-level async function with explicit
parameters -- no class state, independently testable. Cross-phase concerns (cancellation,
direction filter, earnings propagation) remain in the orchestrator.

This is the most integration-heavy module in the project. Use Glob to discover files.

---

## Architecture Rules

- `scan/` orchestrates flow -- it calls into other modules but contains no business logic
- All data crosses boundaries as **typed Pydantic models** -- never raw dicts
- Service calls go through injected service instances -- never import service internals
- Indicator computation goes through `compute_indicators()` -- never call indicator functions directly
- Scoring goes through `scoring/` public API -- never replicate normalization or composite logic
- Persistence goes through `data/Repository` -- never write raw SQL
- No `print()` -- use `logging` module only
- All thresholds from `ScanConfig` / `PricingConfig` -- no hardcoded magic numbers

### Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (all models, enums, config) | Business logic from other modules |
| `services/` (public service classes, BatchOHLCVResult) | Service internals (`helpers.py`) |
| `scoring/` (score_universe, determine_direction, recommend_contracts) | Scoring internals |
| `indicators/` (function references for registry) | Indicator internals (`_validation.py`) |
| `data/` (Database, Repository) | Raw SQL, aiosqlite |
| `asyncio`, `logging`, `math`, `pandas` | `print()`, `httpx`, `yfinance` |

---

## Critical Data Flow

### Phase 1: Universe + OHLCV
`UniverseService` -> tickers + S&P 500 constituents. `MarketDataService.fetch_batch_ohlcv()`
-> `BatchOHLCVResult`. Filter: `len(data) >= config.ohlcv_min_bars` (default 200).
Output: `dict[str, list[OHLCV]]`.

### Phase 2: Indicators + Scoring + Direction
`ohlcv_to_dataframe()` -> DataFrame (open/high/low/close as float, volume as int, DatetimeIndex ascending).
`compute_indicators(df, INDICATOR_REGISTRY)` -> `IndicatorSignals` (15 fields, RAW values).
`score_universe(raw_signals)` -> `list[TickerScore]` (signals NORMALIZED 0-100).
`determine_direction(adx=RAW, rsi=RAW, sma_alignment=RAW, config)` -> `SignalDirection`.

### Phase 3: Liquidity Pre-filter + Options
Liquidity pre-filter (OHLCV from Phase 1): avg dollar volume + min price check.
Top-N by composite_score. `FredService.fetch_risk_free_rate()` called ONCE (never raises).
Per top-N ticker: fetch chains, fetch ticker_info, `recommend_contracts()` -> contracts with greeks.

### Phase 4: Persist
`Repository.save_scan_run()` -> `int` ID. `Repository.save_ticker_scores()` batch insert.

---

## IndicatorSpec Registry -- 15 Entries (NOT 19)

The 4 options-specific indicators (`iv_rank`, `iv_percentile`, `put_call_ratio`,
`max_pain_distance`) require option chain data unavailable in Phase 2. They are left as
`None` on `IndicatorSignals`. The scoring module's `get_active_indicators()` detects
universally-missing indicators and renormalizes weights automatically.

### InputShape Enum

5 variants: `CLOSE`, `HLC`, `CLOSE_VOLUME`, `HLCV`, `VOLUME`.
Column dispatch via `match` statement in `compute_indicators()`.

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

### Function Name != Field Name Mapping

| Function Name | IndicatorSignals Field | Why Different |
|---------------|----------------------|---------------|
| `stoch_rsi` | `stochastic_rsi` | Full name preferred |
| `atr_percent` | `atr_pct` | Shortened |
| `obv_trend` | `obv` | Simplified |
| `ad_trend` | `ad` | Simplified |

Remaining 11 have matching names.

---

## Raw vs Normalized Signals -- CRITICAL

`score_universe()` returns `TickerScore` objects where `signals` contains **percentile-ranked
(0-100) normalized** values. But `determine_direction()` needs **raw indicator values**.

**The pipeline MUST retain `raw_signals: dict[str, IndicatorSignals]` separately** from the
normalized signals on `TickerScore.signals`. Do NOT pass `TickerScore.signals.adx` (normalized)
to `determine_direction()` -- this would compare percentile ranks (e.g., 75.0) against absolute
thresholds (e.g., ADX < 15.0 -> NEUTRAL), producing wrong results.

### Fallback Values for Missing Raw Indicators

When a raw indicator is `None` (computation failed), use neutral defaults:
- `adx` -> `0.0` (below any threshold -> NEUTRAL)
- `rsi` -> `50.0` (midpoint, contributes nothing)
- `sma_alignment` -> `0.0` (neutral)

---

## Liquidity Pre-Filter (Phase 3)

Applied BEFORE fetching option chains (expensive API call). Uses OHLCV data from Phase 1:
- `avg_dollar_volume = mean(close * volume)` over full history
- `latest_close = last OHLCV close price`
- Keep if: both thresholds met

This runs on ALL scored tickers (not just top-N) before the top-N cutoff.

---

## Error Handling by Phase

### Phase 1: Universe + OHLCV
- Universe fetch fails -> **fatal** (propagates up)
- Individual OHLCV fails -> **skip ticker** (BatchOHLCVResult isolates)
- Insufficient data (< bars) -> **skip ticker**, log INFO

### Phase 2: Indicators + Scoring
- Individual indicator fails -> **set to None**, log WARNING, continue
- All indicators fail -> low composite score -> naturally filtered
- `score_universe()` / `determine_direction()` -> pure math, shouldn't fail

### Phase 3: Options + Contracts
- Chain/ticker_info fetch fails -> **skip ticker**, log WARNING
- No contracts pass filter -> empty recommendation (0 contracts)
- Greeks computation fails -> contract excluded
- FredService -> **never raises** (fallback rate)

### Phase 4: Persist
- DB save fails -> **propagate** (not recoverable)

### Cancellation
- Token checked BETWEEN phases (not within)
- Returns partial `ScanResult` with `cancelled=True` and `phases_completed` count

---

## CancellationToken Design

Instance-scoped (not global). Created per `run()` invocation.
- CLI hooks SIGINT handler to `token.cancel()`
- Checked after each phase (not mid-phase)
- Not async -- simple bool flag

---

## ProgressCallback Protocol

`__call__(phase: ScanPhase, current: int, total: int) -> None`
- `ScanPhase` StrEnum: `UNIVERSE`, `SCORING`, `OPTIONS`, `PERSIST`
- Called at phase start, during (incremental), and end
- Framework-agnostic: CLI uses Rich, tests use no-op or recorder

---

## Service Lifecycle

Pipeline does NOT create services. Injected via constructor (DI):
- `cli/` creates AppSettings, services, Database, Repository
- `cli/` creates ScanPipeline with injected dependencies
- `cli/` calls `await pipeline.run(...)` and handles ScanResult
- `cli/` closes services in `finally`
- ScanPipeline never creates or closes services

---

## What Claude Gets Wrong -- Scan-Specific (Fix These)

1. **19 entries in registry** -- Only 15. Options-specific indicators need chain data.

2. **Passing normalized signals to `determine_direction()`** -- Needs RAW ADX/RSI/SMA values.
   Normalized percentile ranks compared against absolute thresholds produce wrong results.

3. **Function names as field names** -- `stoch_rsi` != `stochastic_rsi`, `atr_percent` != `atr_pct`,
   `obv_trend` != `obv`, `ad_trend` != `ad`. `IndicatorSpec.field_name` must match exactly.

4. **Forgetting Decimal -> float** -- OHLCV prices are Decimal. Indicators expect float.
   `ohlcv_to_dataframe()` must convert.

5. **Creating services inside pipeline** -- Injected via constructor. Never created.

6. **Fetching risk-free rate per ticker** -- Called ONCE for entire scan.

7. **Chains for ALL scored tickers** -- Only top-N after liquidity pre-filter.

8. **Assuming `greeks` populated** -- Always `None` from services. Computed by `recommend_contracts()`.

9. **Global `CancellationToken`** -- Instance-scoped per `run()`. Multiple scans each get own token.

10. **Skipping liquidity pre-filter** -- Without it, expensive chains fetched for penny stocks.

11. **`TickerScore` is NOT frozen** -- Mutable. Direction updated after scoring.
