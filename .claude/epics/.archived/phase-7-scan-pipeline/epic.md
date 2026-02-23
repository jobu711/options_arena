---
name: phase-7-scan-pipeline
status: completed
created: 2026-02-22T08:50:13Z
updated: 2026-02-23T15:25:27Z
completed: 2026-02-23T15:25:27Z
progress: 100%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: https://github.com/jobu711/options_arena/issues/46
---

# Epic 7: Scan Pipeline

## Overview

Build the `scan/` package: the core orchestration module that ties services, indicators,
scoring, and persistence into a testable, cancellable, progress-reporting `ScanPipeline`
class with 4 async phases. Replaces the monolithic 430-line `cli.py` scan function from v3.

This epic is the most integration-heavy in the project. All types at every module boundary
have been verified against actual source code before writing this specification.

## Scope

### PRD Requirements Covered
FR-SP1, FR-SP2, FR-SP3, FR-SP4, FR-SP5

### Deliverables

**`src/options_arena/scan/`:**

- `progress.py`:
  - `ScanPhase` — `StrEnum` with 4 members: `UNIVERSE`, `SCORING`, `OPTIONS`, `PERSIST`
  - `CancellationToken` — instance-scoped cancellation (replaces v3's global `_scan_cancelled`).
    `cancel()` method, `is_cancelled` property. Thread-safe via `threading.Event`. Checked between phases.
  - `ProgressCallback` — `Protocol` class: `__call__(phase: ScanPhase, current: int, total: int) -> None`.
    Framework-agnostic (CLI uses Rich, tests use recording/no-op callback).

- `indicators.py`:
  - `InputShape` — `StrEnum` with 5 members encoding OHLCV column requirements:
    `CLOSE`, `HLC`, `CLOSE_VOLUME`, `HLCV`, `VOLUME`
  - `IndicatorSpec` — `NamedTuple(field_name: str, func: Callable[..., pd.Series], input_shape: InputShape)`
    where `field_name` matches the `IndicatorSignals` field name exactly (NOT the function name)
  - `INDICATOR_REGISTRY: list[IndicatorSpec]` — **14 entries** (NOT 18; options-specific indicators
    excluded — they need chain data, not OHLCV). Full registry:

    | # | `field_name` | Function | `InputShape` |
    |---|-------------|----------|-------------|
    | 1 | `rsi` | `rsi` | `CLOSE` |
    | 2 | `stochastic_rsi` | `stoch_rsi` | `CLOSE` |
    | 3 | `williams_r` | `williams_r` | `HLC` |
    | 4 | `adx` | `adx` | `HLC` |
    | 5 | `roc` | `roc` | `CLOSE` |
    | 6 | `supertrend` | `supertrend` | `HLC` |
    | 7 | `bb_width` | `bb_width` | `CLOSE` |
    | 8 | `atr_pct` | `atr_percent` | `HLC` |
    | 9 | `keltner_width` | `keltner_width` | `HLC` |
    | 10 | `obv` | `obv_trend` | `CLOSE_VOLUME` |
    | 11 | `relative_volume` | `relative_volume` | `VOLUME` |
    | 12 | `ad` | `ad_trend` | `HLCV` |
    | 13 | `sma_alignment` | `sma_alignment` | `CLOSE` |
    | 14 | `vwap_deviation` | `vwap_deviation` | `CLOSE_VOLUME` |

    Note: 4 field names differ from function names:
    `stoch_rsi` → `stochastic_rsi`, `atr_percent` → `atr_pct`,
    `obv_trend` → `obv`, `ad_trend` → `ad`

  - `ohlcv_to_dataframe(ohlcv: list[OHLCV]) -> pd.DataFrame` — converts `list[OHLCV]` (Decimal
    prices) to DataFrame with `float` columns `[open, high, low, close, volume]`, date index,
    sorted ascending. Decimal→float conversion is intentional (indicators use float math).

  - `compute_indicators(df: pd.DataFrame, registry: list[IndicatorSpec]) -> IndicatorSignals` —
    generic dispatch loop. For each spec: extract columns via `match spec.input_shape`,
    call `spec.func(...)`, take `series.iloc[-1]` as the scalar value (NaN → `None`).
    Isolated per-indicator `try/except` — one failure logs WARNING, sets field to `None`,
    continues with remaining indicators.

- `models.py` — Pipeline-internal typed models (NOT in `models/` package):
  - `UniverseResult(BaseModel)`:
    - `tickers: list[str]` — full universe list
    - `ohlcv_map: dict[str, list[OHLCV]]` — ticker → bars (successful fetches only)
    - `sp500_sectors: dict[str, str]` — ticker → GICS sector
    - `failed_count: int` — tickers that failed OHLCV fetch
    - `filtered_count: int` — tickers filtered for insufficient bars

  - `ScoringResult(BaseModel)`:
    - `scores: list[TickerScore]` — sorted descending by composite_score, direction set
    - `raw_signals: dict[str, IndicatorSignals]` — RAW values (NOT normalized) for direction

  - `OptionsResult(BaseModel)`:
    - `recommendations: dict[str, list[OptionContract]]` — ticker → 0 or 1 contracts
    - `risk_free_rate: float` — rate used for the entire scan

  - `ScanResult(BaseModel)`:
    - `scan_run: ScanRun` — metadata (id populated after persist)
    - `scores: list[TickerScore]` — all scored tickers with direction
    - `recommendations: dict[str, list[OptionContract]]` — contracts per ticker
    - `risk_free_rate: float` — FRED rate or fallback
    - `cancelled: bool = False` — True if pipeline was cancelled
    - `phases_completed: int = 0` — 0–4, how far the pipeline got

- `pipeline.py` — `ScanPipeline`:
  - Constructor (dependency injection — never creates services):
    ```python
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
  - `async def run(self, preset: ScanPreset, token: CancellationToken, progress: ProgressCallback) -> ScanResult`

  - **Phase 1 — Universe + OHLCV** (`_phase_universe`):
    1. `universe.fetch_optionable_tickers()` → `list[str]` (~5,296 tickers)
    2. If `preset == SP500`: filter to S&P 500 only via `universe.fetch_sp500_constituents()`
    3. `market_data.fetch_batch_ohlcv(tickers)` → `BatchOHLCVResult`
    4. Filter: `len(result.data) >= settings.scan.ohlcv_min_bars` (default 200)
    5. Report progress: `progress(ScanPhase.UNIVERSE, ...)`
    6. Return `UniverseResult`

  - **Phase 2 — Indicators + Scoring + Direction** (`_phase_scoring`):
    1. For each ticker in `ohlcv_map`:
       - `ohlcv_to_dataframe(ohlcv_list)` → `pd.DataFrame`
       - `compute_indicators(df, INDICATOR_REGISTRY)` → `IndicatorSignals` (raw values)
       - Store in `raw_signals[ticker] = signals`
    2. `score_universe(raw_signals)` → `list[TickerScore]` (signals are now NORMALIZED)
    3. For each `TickerScore`:
       - `raw = raw_signals[ticker]` ← **RAW values, NOT normalized**
       - `determine_direction(adx=raw.adx or 0.0, rsi=raw.rsi or 50.0, sma_alignment=raw.sma_alignment or 0.0, config=settings.scan)`
       - Set `ticker_score.direction = direction`
    4. Report progress: `progress(ScanPhase.SCORING, ...)`
    5. Return `ScoringResult`

  - **Phase 3 — Liquidity Pre-filter + Options + Contracts** (`_phase_options`):
    1. **Liquidity pre-filter** (uses OHLCV data from Phase 1):
       - `avg_dollar_volume = mean(close * volume)` over full history
       - `latest_close = last OHLCV close`
       - Keep if `avg_dollar_volume >= settings.scan.min_dollar_volume` AND `latest_close >= settings.scan.min_price`
    2. Top-N by `composite_score` (`settings.scan.top_n`, default 50)
    3. `fred.fetch_risk_free_rate()` → `float` (called ONCE, never raises)
    4. For each top-N ticker (concurrent via `asyncio.gather`):
       - `options_data.fetch_chain_all_expirations(ticker)` → `list[ExpirationChain]`
       - `market_data.fetch_ticker_info(ticker)` → `TickerInfo`
       - Flatten all contracts: `list[OptionContract]` (greeks=None from yfinance)
       - `recommend_contracts(contracts, direction, spot=float(ticker_info.current_price), risk_free_rate, dividend_yield=ticker_info.dividend_yield, config=settings.pricing)` → 0 or 1 contracts
    5. Report progress: `progress(ScanPhase.OPTIONS, ...)`
    6. Return `OptionsResult`

  - **Phase 4 — Persist** (`_phase_persist`):
    1. Build `ScanRun(started_at=..., completed_at=now_utc, preset=..., tickers_scanned=..., tickers_scored=..., recommendations=...)`
    2. `repository.save_scan_run(scan_run)` → `int` (DB ID)
    3. `repository.save_ticker_scores(scan_id, scores)` → batch insert
    4. Report progress: `progress(ScanPhase.PERSIST, 1, 1)`
    5. Return updated `ScanResult` with `scan_run.id` set

  - **Cancellation**: check `token.is_cancelled` between each phase. If cancelled, return
    partial `ScanResult` with `cancelled=True` and `phases_completed` count.

- `__init__.py` — Re-export public API:
  ```python
  from options_arena.scan.models import ScanResult
  from options_arena.scan.pipeline import ScanPipeline
  from options_arena.scan.progress import CancellationToken, ProgressCallback, ScanPhase

  __all__ = ["CancellationToken", "ProgressCallback", "ScanPhase", "ScanPipeline", "ScanResult"]
  ```

---

## Issue Decomposition (6 Issues)

### Issue 1: Module setup — `progress.py`
**Deliverables**: `scan/CLAUDE.md` (already created), `progress.py` with `ScanPhase`, `CancellationToken`, `ProgressCallback`
**Tests** (~10): ScanPhase exhaustive members, CancellationToken cancel/is_cancelled, thread-safety, ProgressCallback protocol conformance, recording callback helper for tests
**Why first**: These are the contracts that all other scan files depend on

### Issue 2: Pipeline-internal models — `models.py`
**Deliverables**: `UniverseResult`, `ScoringResult`, `OptionsResult`, `ScanResult`
**Tests** (~12): Construction with valid data, default values, serialization round-trip, partial results (cancelled pipeline)
**Dependencies**: Issue 1 (uses `ScanPhase` for `phases_completed` context)

### Issue 3: Indicator dispatch — `indicators.py`
**Deliverables**: `InputShape` enum, `IndicatorSpec` NamedTuple, `INDICATOR_REGISTRY` (14 entries), `ohlcv_to_dataframe()`, `compute_indicators()`
**Tests** (~25):
- Registry: all 14 entries present, correct function references, field names match `IndicatorSignals`
- InputShape: exhaustive enum, column dispatch match
- `ohlcv_to_dataframe`: Decimal→float conversion, date index, column names, sort order
- `compute_indicators`: happy path (all 14 indicators), isolated failure (one bad indicator), NaN→None, empty DataFrame, InsufficientDataError handling
**Dependencies**: None (only references `indicators/` and `models/scan.py`)

### Issue 4: Pipeline Phase 1 + Phase 2
**Deliverables**: `ScanPipeline.__init__`, `run()` skeleton, `_phase_universe()`, `_phase_scoring()`
**Tests** (~20):
- Phase 1: mock services return BatchOHLCVResult, verify ohlcv_map filtering, min_bars enforcement, SP500 preset filtering, progress callback invocation
- Phase 2: mock compute_indicators, verify raw_signals retention, direction from RAW values (NOT normalized), score_universe integration, None fallback values for missing indicators
- Cancellation between Phase 1 and Phase 2
**Dependencies**: Issues 1, 2, 3

### Issue 5: Pipeline Phase 3 + Phase 4
**Deliverables**: `_phase_options()`, `_phase_persist()`, `__init__.py` re-exports
**Tests** (~20):
- Phase 3: liquidity pre-filter ($10M/`$10), top-N selection, mock FredService (once call), mock chains, recommend_contracts integration, per-ticker error isolation, progress reporting
- Phase 4: ScanRun construction with UTC timestamps, Repository.save_scan_run/save_ticker_scores integration, scan_run.id populated after save
- Cancellation between Phase 3 and Phase 4
- Full run with all 4 phases (mock services)
**Dependencies**: Issues 1, 2, 3, 4

### Issue 6: Integration tests + verification gate
**Deliverables**: Integration tests, verification gate pass (ruff + pytest + mypy --strict)
**Tests** (~8):
- Full pipeline end-to-end with mock services (all phases, happy path)
- Cancelled mid-pipeline returns partial ScanResult
- ScanResult.phases_completed reflects actual progress
- Empty universe (0 tickers) → graceful empty result
- All tickers fail OHLCV → graceful empty result
- ProgressCallback invocation order: UNIVERSE → SCORING → OPTIONS → PERSIST
- Re-export verification: all public names importable from `options_arena.scan`
**Dependencies**: Issues 1–5

---

## Verified Design Decisions

### Why 14 registry entries, not 18
The 4 options-specific indicators (`iv_rank`, `iv_percentile`, `put_call_ratio`, `max_pain_distance`)
require option chain data that isn't available during Phase 2. They are left as `None` on
`IndicatorSignals`. The scoring module's `get_active_indicators()` detects universally-missing
indicators and renormalizes composite score weights automatically. This is the same behavior
as v3 (documented in progress.md under "Scan Pipeline Logic Fix").

### Why InputShape enum instead of "series"/"dataframe"
The 14 indicators use 5 distinct column combinations. `"series"` vs `"dataframe"` tells you
nothing about WHICH columns to extract. `InputShape.HLC` means "pass high, low, close" —
unambiguous dispatch via `match` statement.

### Why retain raw_signals separately
`score_universe()` returns `TickerScore.signals` with percentile-ranked (0–100) values.
`determine_direction()` compares ADX/RSI against absolute thresholds (ADX < 15.0 → NEUTRAL).
Passing normalized values (where 15.0 means "15th percentile") to absolute thresholds produces
incorrect classifications.

### Why FredService is called once
The 10-year Treasury rate doesn't change between tickers in a single scan. Calling it once
saves ~50 API calls. `FredService.fetch_risk_free_rate()` never raises — always returns a float.

### Why DI for services
`ScanPipeline` receives pre-built services via constructor. This enables:
- Tests inject mocks without monkey-patching
- CLI shares service instances across commands
- Service lifecycle managed by caller (not pipeline)

### Why pipeline-internal models live in `scan/models.py`
These are orchestration artifacts (`UniverseResult`, `ScoringResult`, etc.), not domain models.
They exist to type the boundaries between pipeline phases for testability and documentation.
They don't belong in `models/` which is for domain-wide data shapes.

---

## Dependencies
- **Blocked by**: Epic 1 (models), Epic 2 (pricing), Epic 3 (indicators), Epic 4 (scoring), Epic 5 (services), Epic 6 (data) — ALL COMPLETE
- **Blocks**: Epic 8 (CLI integration)

## Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .   # lint + format
uv run pytest tests/ -v                              # all tests (~95 new + 905 existing)
uv run mypy src/ --strict                            # type checking
```

## Estimated Tests: ~95

## Tasks Created
- [ ] #48 - Module setup — progress.py (parallel: false)
- [ ] #49 - Pipeline-internal models — models.py (parallel: false, depends: #48)
- [ ] #52 - Indicator dispatch — indicators.py (parallel: true)
- [ ] #47 - Pipeline Phase 1 + Phase 2 (parallel: false, depends: #48, #49, #52)
- [ ] #50 - Pipeline Phase 3 + Phase 4 (parallel: false, depends: #48-#52, #47)
- [ ] #51 - Integration tests + verification gate (parallel: false, depends: all)

Total tasks: 6
Parallel tasks: 1 (#52 can run alongside #48/#49)
Sequential tasks: 5
Estimated total effort: 24-34 hours
