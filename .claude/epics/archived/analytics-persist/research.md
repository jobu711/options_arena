# Research: analytics-persist

## PRD Summary

Persist contract recommendations, track outcomes, capture normalization metadata, and expose analytics queries via API. Closes the feedback loop: "Did the BULLISH signal on AAPL from scan #42 actually make money?" Five waves: contract persistence, outcome tracking, normalization metadata, analytics queries, API endpoints.

## Critical Finding: Migration Numbering

**The PRD assumes migration 010 is available — it is NOT.** Migration `010_intelligence_tables.sql` already exists (from the market-recon epic). The correct starting migration numbers are:

| PRD Planned | Actual Available | Table |
|-------------|-----------------|-------|
| 010 | **011** | `recommended_contracts` |
| 011 | **012** | `contract_outcomes` |
| 012 | **013** | `normalization_metadata` |

## Relevant Existing Modules

- `data/repository.py` — 20+ methods following `save_*()` / `get_*()` pattern with `_row_to_*()` converters. All return typed models, use parameterized queries, commit after every write.
- `data/database.py` — Connection lifecycle, WAL mode, sequential migration runner. Migrations auto-discovered from `data/migrations/` sorted by filename.
- `scan/pipeline.py` — Phase 3 (`_process_ticker_options`) produces `OptionsResult` with recommendations dict. Phase 4 (`_phase_persist`) saves `ScanRun` + `TickerScore` only. **Contracts are discarded.**
- `scan/models.py` — `OptionsResult` has `recommendations: dict[str, list[OptionContract]]`, `risk_free_rate: float`, `earnings_dates: dict[str, date]`. No entry prices captured.
- `models/options.py` — `OptionContract` (frozen) with Decimal fields (strike, bid, ask, last), field_serializer for JSON, computed mid/spread/dte. Greeks via `OptionGreeks | None`.
- `models/config.py` — `AppSettings(BaseSettings)` root with 8 nested `BaseModel` sub-configs. Pattern: add `AnalyticsConfig(BaseModel)` + wire to `AppSettings.analytics`.
- `models/enums.py` — 19 StrEnums. Will need `OutcomeCollectionMethod` StrEnum.
- `scoring/normalization.py` — `percentile_rank_normalize()` processes `dict[str, IndicatorSignals]`. Stats (min/max/percentiles) computed internally but discarded. `get_active_indicators()` available.
- `services/market_data.py` — `fetch_quote(ticker) -> Quote` for outcome collection (current stock price).
- `api/app.py` — App factory with `@asynccontextmanager` lifespan, services on `app.state`, routers via `app.include_router()`.
- `api/deps.py` — `Depends()` providers reading from `request.app.state`.
- `api/routes/` — 6 route files. Pattern: `router = APIRouter(prefix="/api", tags=[...])`.
- `cli/app.py` — Typer app with subcommand groups. Sync commands + `asyncio.run()`.

## Existing Patterns to Reuse

### 1. Repository save/get pattern
```python
async def save_recommended_contracts(self, scan_id: int, contracts: list[RecommendedContract]) -> None:
    # executemany() for batch insert, await conn.commit()

async def get_contracts_for_scan(self, scan_id: int) -> list[RecommendedContract]:
    # SELECT with parameterized query, _row_to_recommended_contract() converter
```

### 2. Decimal-as-TEXT serialization
Store via `str(decimal_value)`, reconstruct via `Decimal(row["column"])`. Field serializer on model for JSON output.

### 3. Frozen snapshot models
`OptionContract`, `OptionGreeks`, `Quote` all use `ConfigDict(frozen=True)`. Analytics models should too.

### 4. NaN/Inf defense
Every float validator must call `math.isfinite()` before range checks. Every Decimal validator must call `v.is_finite()`.

### 5. UTC datetime validator
```python
if v.tzinfo is None or v.utcoffset() != timedelta(0):
    raise ValueError("must be UTC")
```

### 6. Config injection
`AppSettings` → nested `BaseModel` sub-config → passed to service constructor. Env override: `ARENA_ANALYTICS__ENABLED=false`.

### 7. API route registration
Module-level `router = APIRouter(prefix="/api", tags=["analytics"])`. Lazy import in `create_app()`. `Depends(get_analytics_service)` for DI.

### 8. CLI subcommand group
```python
outcomes_app = typer.Typer(help="Outcome tracking.")
app.add_typer(outcomes_app, name="outcomes")
```

## Existing Code to Extend

| File | What Exists | What Needs Changing |
|------|-------------|---------------------|
| `scan/models.py` | `OptionsResult` with recommendations | Add `entry_prices: dict[str, Decimal]` field |
| `scan/pipeline.py` | Phase 3 fetches spot price, Phase 4 persists run+scores | Capture spot in Phase 3, persist contracts in Phase 4 |
| `data/repository.py` | 20+ typed methods | Add ~12 new methods (save/get contracts, outcomes, analytics queries) |
| `models/__init__.py` | Re-exports 70+ symbols | Add analytics model re-exports |
| `models/enums.py` | 19 StrEnums | Add `OutcomeCollectionMethod` |
| `models/config.py` | 8 sub-configs on AppSettings | Add `AnalyticsConfig` |
| `scoring/normalization.py` | `percentile_rank_normalize()` | Add `compute_normalization_stats()` returning typed model |
| `api/app.py` | 6 routers registered | Register analytics router |
| `api/deps.py` | 8 dependency providers | Add `get_outcome_collector()` or similar |
| `cli/app.py` | 6 command groups | Add `outcomes` command group |

## Potential Conflicts

### 1. Migration 010 collision (CRITICAL)
PRD specifies migration 010 but it's taken by `intelligence_tables.sql`. **Renumber to 011/012/013.**

### 2. OptionsResult is not frozen
`OptionsResult` allows mutation. Adding `entry_prices` field is safe — no `frozen=True` constraint to worry about.

### 3. Phase 3 spot price availability
The PRD assumes spot price is available in Phase 3. Research confirms `_process_ticker_options` fetches `ticker_info` which contains `current_price`. This is available but not currently captured into `OptionsResult`. Need to propagate it.

### 4. Repository method count
Repository already has 20+ methods. Adding 12 more is significant. Consider whether a separate `AnalyticsRepository` class is warranted, or keep in single `Repository` with clear method grouping.

## Open Questions

1. **Separate AnalyticsRepository?** The PRD adds all methods to `Repository`. With 30+ methods total, should we split into `Repository` (scan/score CRUD) and `AnalyticsRepository` (contracts/outcomes/analytics)? Both share the same `Database` instance.

2. **Outcome collection trigger**: The PRD proposes a CLI command `options-arena outcomes`. Should this also be triggerable via API endpoint (for web UI)? The PRD's Wave 5 includes `POST /api/analytics/collect-outcomes` suggesting yes.

3. **Holding period windows**: PRD says T+1, T+5, T+10, T+20, at-expiry. Are these configurable via `AnalyticsConfig` or hardcoded?

4. **Expired contract handling**: For outcome collection on expired options, how do we get the settlement price? yfinance may not have historical option prices. May need to compute intrinsic value from stock price at expiry.

## Recommended Architecture

### Models (`models/analytics.py`)
- `RecommendedContract` (frozen) — mirrors DB schema, Decimal fields with serializers
- `ContractOutcome` (frozen) — P&L tracking, holding period, collection method
- `NormalizationStats` (frozen) — per-indicator distribution metadata
- `WinRateResult`, `ScoreCalibrationBucket`, `HoldingPeriodResult`, `DeltaPerformanceResult`, `PerformanceSummary` (frozen) — analytics query results
- `OutcomeCollectionMethod` StrEnum in `enums.py`
- `AnalyticsConfig(BaseModel)` in `config.py`

### Data Layer
- Migrations 011, 012, 013 (renumbered from PRD)
- Repository methods grouped with `# --- Analytics ---` comment block
- All save methods use `executemany()` for batch inserts
- All get methods return typed models via `_row_to_*()` converters
- Analytics queries use JOINs on `recommended_contracts` + `contract_outcomes`

### Service Layer (`services/outcome_collector.py`)
- `OutcomeCollector` class with config + repository + market_data DI
- `collect_outcomes(holding_days: int) -> list[ContractOutcome]`
- Fetches current quotes, computes P&L, handles expired contracts
- Never raises — returns partial results with logging

### Pipeline Integration
- Phase 3: Capture `spot_price` from `ticker_info.current_price` into new `entry_prices` dict on `OptionsResult`
- Phase 4: Build `RecommendedContract` list, call `repo.save_recommended_contracts()`
- Phase 2: Call `compute_normalization_stats()`, persist in Phase 4

### API (`api/routes/analytics.py`)
- 8 GET endpoints + 1 POST (collect-outcomes)
- All return typed Pydantic models
- DI via `Depends(get_repository)` (reuse existing) or `Depends(get_outcome_collector)`

### CLI (`cli/app.py`)
- `options-arena outcomes collect [--holding-days 5]`
- `options-arena outcomes summary [--lookback-days 30]`

## Test Strategy Preview

### Existing patterns
- `tests/unit/data/test_repository.py` — in-memory SQLite, migration runner, typed assertions
- `tests/unit/scan/test_pipeline.py` — mocked services, phase-by-phase assertions
- `tests/unit/models/` — model construction, validation, serialization round-trips
- `tests/unit/services/` — mocked httpx/yfinance, typed return assertions
- `tests/unit/api/` — FastAPI TestClient, mocked deps

### Test file locations
- `tests/unit/models/test_analytics.py` — model construction, validators, serialization
- `tests/unit/data/test_analytics_repository.py` — save/get round-trips, analytics queries
- `tests/unit/services/test_outcome_collector.py` — P&L computation, expired handling
- `tests/unit/scan/test_contract_persistence.py` — pipeline Phase 4 contract persist
- `tests/unit/scoring/test_normalization_stats.py` — stats computation
- `tests/unit/api/test_analytics_routes.py` — endpoint responses, error cases

### Mocking strategies
- `aiosqlite` in-memory DB with migration runner for repository tests
- `unittest.mock.AsyncMock` for service methods
- `TestClient` with overridden `Depends()` for API tests
- Factory functions for test model construction

## Estimated Complexity

**L (Large)** — 5 waves, 3 new migrations, 3 new files, ~12 edited files, ~145 new tests. Each wave is independently mergeable but has sequential dependencies (Wave 2 depends on Wave 1 tables). Estimated 5 implementation sessions.
