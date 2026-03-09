# Research: backtesting-engine

## PRD Summary

Performance measurement engine analyzing actual recommendation track records. Adds:
auto-scheduled daily outcome collection (asyncio loop), basic Greeks P&L decomposition
(delta vs residual using entry Greeks), 9 new repository queries, ~10 new API endpoints
under `/api/analytics/backtest/`, 3 CLI subcommands, and a Vue dashboard with 5 tabs
(overview/equity curve, agent accuracy, segments, Greeks, holding periods). Full analytics
suite with Chart.js visualizations.

## Relevant Existing Modules

| Module | Relevance | Key Files | CLAUDE.md Rules |
|--------|-----------|-----------|----------------|
| `data/` | **Largest change** — 9 new query methods | `repository.py` (lines 997-1339+) | Typed returns only, parameterized SQL, `await db.commit()` for writes |
| `models/` | ~10 new frozen result models | `analytics.py` (350+ lines), `config.py` (AnalyticsConfig) | `frozen=True`, `math.isfinite()` first, UTC validators, `X \| None` not Optional |
| `services/` | Scheduler loop in OutcomeCollector | `outcome_collector.py` (448 lines) | Never-raises contract, batch isolation, DI via `__init__` |
| `api/` | ~10 new GET endpoints | `routes/analytics.py` (146 lines) | `Depends()` injection, rate limiting, no manual `model_dump()` |
| `cli/` | 3 new subcommands | `outcomes.py` (240 lines) | Sync Typer + `asyncio.run()`, Rich tables, try/finally lifecycle |
| `web/` | New dashboard page + store + 6 components | Views, stores, router | Composition API, Pinia setup syntax, PrimeVue dark theme |
| `tests/` | ~150+ new tests | `tests/unit/data/`, `tests/unit/models/`, `tests/unit/api/` | Never real APIs, `pytest.approx()` for floats, mock dates |

## Existing Patterns to Reuse

### 1. Analytics Query Pattern (repository.py)
6 existing methods follow identical structure: parameterized SQL → `fetchall()` → list comprehension → frozen Pydantic model. New queries copy this exactly.
- Example: `get_win_rate_by_direction()` (lines 997-1028) — GROUP BY + CASE WHEN aggregation
- Example: `get_indicator_attribution()` (lines 1071-1144) — `json_extract()` + numpy correlation in Python
- Median computed in Python via `statistics.median()` (SQLite lacks built-in median)

### 2. API Endpoint Pattern (routes/analytics.py)
All endpoints: `@router.get()` → `Depends(get_repo)` → return typed model (FastAPI auto-serializes). Rate limited `60/minute`. New endpoints copy this exactly.

### 3. Pinia Store Pattern (stores/*.ts)
Setup function syntax with `ref()` state, `computed()` getters, async action functions. `useApi` composable for typed fetch. Existing stores: scan, debate, health, heatmap.

### 4. OutcomeCollector Never-Raises Pattern (outcome_collector.py)
Per-contract error isolation, `return_exceptions=True` for batch, partial results on failure. Scheduler must preserve this contract.

### 5. Config DI Pattern (config.py → services)
`AnalyticsConfig(BaseModel)` nested in `AppSettings(BaseSettings)`. Env override: `ARENA_ANALYTICS__AUTO_COLLECT_ENABLED=true`. Service receives config slice via `__init__`.

### 6. FastAPI Lifespan Pattern (app.py)
Services created in `lifespan()`, stored on `app.state`, cleaned up in finally. Scheduler task: `asyncio.create_task()` before `yield`, `task.cancel()` after `yield`.

### 7. CLI Outcomes Pattern (outcomes.py)
Sync Typer commands → `asyncio.run(_async())`. Service lifecycle in try/finally. Rich `Table()` for output. `--holding-days` and `--lookback-days` options.

## Existing Code to Extend

### `src/options_arena/models/analytics.py` — Add ~10 new models
Existing: `RecommendedContract`, `ContractOutcome`, `NormalizationStats`, `WinRateResult`, `ScoreCalibrationBucket`, `IndicatorAttributionResult`, `HoldingPeriodResult`, `DeltaPerformanceResult`, `PerformanceSummary` (9 models, ~647 lines).

New models needed:
- `EquityCurvePoint(date, cumulative_return_pct, trade_count)`
- `DrawdownPoint(date, drawdown_pct, peak_value)`
- `AgentAccuracyResult(agent_name, total, correct, accuracy_pct, avg_confidence, overconfidence_ratio)`
- `ConfidenceCalibrationBucket(confidence_min, confidence_max, predicted_win_rate, actual_win_rate, count)`
- `SectorPerformanceResult(sector, total, win_rate_pct, avg_return_pct)`
- `DTEBucketResult(dte_min, dte_max, total, win_rate_pct, avg_return_pct)`
- `IVRankBucketResult(iv_min, iv_max, total, win_rate_pct, avg_return_pct)`
- `GreeksDecompositionResult(group_key, delta_pnl, residual_pnl, total_pnl, count)`
- `HoldingPeriodComparison(holding_days, direction, avg_return, median_return, win_rate, sharpe_like, max_loss, count)`
- `OutcomeCollectionResult` — already exists (count wrapper)

### `src/options_arena/data/repository.py` — Add 9 new query methods
Lines 997-1339+ contain existing analytics methods. New methods follow same pattern.

New queries:
1. `get_equity_curve(direction?, period?)` — cumulative return by date using SQL ORDER BY + Python running sum
2. `get_drawdown_series(period?)` — peak-to-trough from equity curve
3. `get_agent_accuracy()` — JOIN `agent_predictions` → `contract_outcomes`, GROUP BY agent_name
4. `get_agent_confidence_calibration(bucket_size?)` — confidence bucket vs actual win rate
5. `get_win_rate_by_sector(holding_days?)` — JOIN `recommended_contracts` → `ticker_metadata`
6. `get_win_rate_by_dte_bucket(holding_days?)` — compute DTE from expiration-created_at, bucket
7. `get_win_rate_by_iv_rank(holding_days?)` — bucket by market_iv percentile
8. `get_greeks_decomposition(holding_days?, groupby?)` — delta_pnl = stock_return × delta, residual = total - delta
9. `get_holding_period_comparison()` — enhanced version of `get_optimal_holding_period` with Sharpe-like ratio

### `src/options_arena/models/config.py` — Extend AnalyticsConfig
Add: `auto_collect_enabled: bool = False`, `auto_collect_hour_utc: int = 6`

### `src/options_arena/services/outcome_collector.py` — Add scheduler method
Add: `async def run_scheduler(self) -> None:` — asyncio.sleep loop, runs daily at configured hour

### `src/options_arena/api/routes/analytics.py` — Add ~10 endpoints
New routes under `/api/analytics/backtest/` prefix. Same rate limiting pattern.

### `src/options_arena/api/app.py` — Start scheduler in lifespan
Add `asyncio.create_task(scheduler)` before `yield`, cancel after `yield`.

### `src/options_arena/cli/outcomes.py` — Add 3 subcommands
`outcomes backtest`, `outcomes agents`, `outcomes equity-curve`

### `web/src/router/index.ts` — Add `/analytics` route
### `web/src/stores/backtest.ts` — New Pinia store (NEW FILE)
### `web/src/views/AnalyticsView.vue` — New page with 5 tabs (NEW FILE)
### `web/src/components/analytics/` — 5-6 chart components (NEW FILES)

## Database Schema — No Migration Needed for Tables

All 9 new queries use **existing tables only**: `recommended_contracts`, `contract_outcomes`,
`agent_predictions`, `ticker_metadata`, `ticker_scores`. No new tables needed.

### New Indexes Needed (Migration 026)

```sql
-- Optimize backtesting queries
CREATE INDEX IF NOT EXISTS idx_co_holding_days ON contract_outcomes(holding_days);
CREATE INDEX IF NOT EXISTS idx_co_collected_at ON contract_outcomes(collected_at);
CREATE INDEX IF NOT EXISTS idx_ap_agent_direction ON agent_predictions(agent_name, direction);
CREATE INDEX IF NOT EXISTS idx_rc_market_iv ON recommended_contracts(market_iv);
CREATE INDEX IF NOT EXISTS idx_rc_direction_created ON recommended_contracts(direction, created_at);
```

## Potential Conflicts

### 1. Chart.js Dependency — NEEDS VERIFICATION
PrimeVue Chart component wraps Chart.js but may not be installed. Check `web/package.json`
for `chart.js`. If absent, add via `npm install chart.js` (PrimeVue Chart requires it).

### 2. Analytics Router Namespace
Existing endpoints under `/api/analytics/`. New endpoints under `/api/analytics/backtest/`
to avoid collision. No breaking changes to existing endpoints.

### 3. Operation Lock Scope
Auto-scheduler must NOT acquire the operation mutex. Outcome collection is read-heavy
(fetch quotes) + write-light (save outcomes) — doesn't conflict with scans/debates.
Verify OutcomeCollector doesn't use the lock internally.

### 4. Lifespan Complexity
Adding scheduler task to `lifespan()` increases shutdown complexity. Must handle
`CancelledError` gracefully and ensure partial collections are committed before exit.

## Open Questions

1. **Agent-to-contract linkage**: `agent_predictions.recommended_contract_id` is nullable.
   How reliably is this populated? If sparse, agent accuracy queries may have limited data.
   → Need to verify with actual DB data or check `extract_agent_predictions()` call sites.

2. **Sector data availability**: `get_win_rate_by_sector()` requires `ticker_metadata.sector`.
   How complete is the metadata index? If coverage is <80%, results may be misleading.
   → `MetadataStats` tracks coverage; query should filter NULL sectors.

3. **Chart.js vs alternatives**: PrimeVue Chart wraps Chart.js but requires separate install.
   Is Chart.js already in `package.json`? If not, confirm it's the right choice vs ECharts.
   → Check `web/package.json` during Phase 4 implementation.

4. **Scheduler persistence**: If the server restarts mid-collection, are partial outcomes saved?
   → OutcomeCollector saves outcomes per-contract (not batch-commit), so partial saves are safe.

## Recommended Architecture

### Phase 1: Models + Queries (Backend foundation)
1. Define ~10 new frozen result models in `models/analytics.py`
2. Implement 9 new repository methods in `data/repository.py`
3. Add migration 026 for performance indexes
4. Unit tests for all models (validation) and queries (SQL correctness)

### Phase 2: Scheduler + CLI (Backend services)
1. Add `auto_collect_enabled`/`auto_collect_hour_utc` to `AnalyticsConfig`
2. Implement `async def run_scheduler()` in `OutcomeCollector`
3. Wire scheduler into `api/app.py` lifespan + `cli/serve.py`
4. Add CLI subcommands: `outcomes backtest`, `outcomes agents`, `outcomes equity-curve`
5. Tests: scheduler (mock time), CLI integration

### Phase 3: API Endpoints (REST layer)
1. Create `routes/backtest.py` with ~10 new endpoints
2. Register router in `app.py` with `/api/analytics/backtest` prefix
3. Rate limiting consistent with existing analytics (60/min)
4. Tests: endpoint integration tests

### Phase 4: Vue Dashboard (Frontend)
1. Install Chart.js if needed
2. Create `AnalyticsView.vue` with PrimeVue TabView (5 tabs)
3. Create `useBacktestStore` Pinia store
4. Build chart components (equity curve, heatmap, bars, scatter, stacked bar)
5. Add route + navigation link
6. E2E tests with Playwright

## Test Strategy Preview

### Existing Test Patterns
- **Database fixtures**: In-memory SQLite via `pytest_asyncio.fixture`, fresh per test
- **Model tests**: Validation (valid/invalid), JSON roundtrip, `frozen=True` immutability
- **Repository tests**: 4-5 tests per query method (empty DB, single result, multiple, edge cases)
- **API tests**: `httpx.AsyncClient` with test app, status codes + response shape
- **CLI tests**: Typer `CliRunner` with mocked services
- **Float comparisons**: Always `pytest.approx(rel=1e-4)` for returns, `abs=0.01` for percentages

### Test File Locations
- `tests/unit/models/test_analytics.py` — extend with new model tests
- `tests/unit/data/test_repository_analytics.py` — new file for 9 query tests
- `tests/unit/api/test_analytics_backtest.py` — new file for endpoint tests
- `tests/unit/services/test_outcome_scheduler.py` — new file for scheduler tests
- `tests/unit/cli/test_outcomes.py` — extend with new subcommand tests
- `tests/e2e/` — analytics dashboard E2E tests

### Mocking Strategies
- `OutcomeCollector`: Mock `MarketDataService.fetch_quote()` and `OptionsDataService`
- Scheduler: Mock `asyncio.sleep()` and `datetime.now()` to advance time
- Repository: Use real in-memory SQLite (fast, no mocking needed)
- API: Test app factory with injected test database

## Estimated Complexity

**XL (10-13 days)** — justified by:
- 4 implementation phases across full stack (models → queries → API → frontend)
- ~10 new Pydantic models with validators
- 9 new SQL queries (some with window functions, GROUP BY, JOINs across 3 tables)
- ~10 new API endpoints with rate limiting
- 3 new CLI subcommands
- Vue dashboard with 5 tabs and 6+ chart types (largest single component)
- Auto-scheduler with lifespan integration
- ~150+ new tests across unit/integration/E2E
- Migration for performance indexes
- **~2,300 lines of new code** (1,500 Python + 800 TypeScript/Vue)

All changes are additive — no breaking changes to existing code.
