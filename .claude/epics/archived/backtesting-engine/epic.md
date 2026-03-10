---
name: backtesting-engine
status: planned
created: 2026-03-08T23:37:36Z
updated: 2026-03-10T00:25:28Z
progress: 0%
prd: .claude/prds/backtesting-engine.md
github: https://github.com/jobu711/options_arena/issues/429
---

# Epic: backtesting-engine

## Overview

Extend the existing analytics infrastructure into a complete performance measurement
platform. Adds 7 new AnalyticsMixin queries (equity curves, drawdowns, sector/DTE/IV
segmentation, Greeks decomposition, holding period comparison), auto-scheduled outcome
collection, 7 REST endpoints under `/api/analytics/backtest/`, 2 CLI subcommands, and
a Vue dashboard with 5 tabs.

All changes are additive — no breaking changes, no new tables, only a migration (029)
for performance indexes. Agent accuracy and calibration queries already exist in
`_debate.py` (DebateMixin) and are reused, not duplicated.

### What Already Exists (Not Duplicated)

- `get_agent_accuracy()` in `_debate.py` (DebateMixin)
- `get_agent_confidence_calibration()` in `_debate.py` (DebateMixin)
- `/api/analytics/agent-accuracy` endpoint
- `/api/analytics/agent-calibration` endpoint
- `/api/analytics/agent-weights` endpoint
- `outcomes agent-accuracy`, `outcomes calibration`, `outcomes agent-weights` CLI commands
- `auto_tune_weights` migration (028)

## Architecture Decisions

1. **New router file `api/routes/backtest.py`** — cleaner separation from existing
   `routes/analytics.py`. Registered under `/api/analytics/backtest/` prefix.

2. **All new queries in `_analytics.py` (AnalyticsMixin)** — follows the repository
   mixin decomposition pattern. Agent queries stay in `_debate.py`.

3. **Migration 029** — indexes only, no schema changes. All queries use existing tables:
   `recommended_contracts`, `contract_outcomes`, `agent_predictions`, `ticker_metadata`.

4. **asyncio.sleep() scheduler** — simple daily loop in OutcomeCollector, started in
   FastAPI `lifespan()`. No external scheduler dependency.

5. **Greeks decomposition uses entry Greeks only** — `delta_pnl = stock_return * delta`
   (negated for puts), `residual = total - delta`. Approximate but zero new data fetching.

6. **Chart.js via npm install** — PrimeVue Chart component wraps it. Must be added to
   `web/package.json` (not currently present).

## Task Breakdown

### Task 1: Analytics result models + migration 029
**Status**: pending
**Files**:
- `src/options_arena/models/analytics.py` — ~7 new frozen result models
- `data/migrations/029_backtest_indexes.sql` — performance indexes
- `tests/unit/models/test_analytics.py` — model validation tests (extend)

**Details**:
New models (all `frozen=True`, `math.isfinite()` validators, UTC datetime enforcement):
- `EquityCurvePoint(date, cumulative_return_pct, trade_count)`
- `DrawdownPoint(date, drawdown_pct, peak_value)`
- `SectorPerformanceResult(sector, total, win_rate_pct, avg_return_pct)`
- `DTEBucketResult(dte_min, dte_max, total, win_rate_pct, avg_return_pct)`
- `IVRankBucketResult(iv_min, iv_max, total, win_rate_pct, avg_return_pct)`
- `GreeksDecompositionResult(group_key, delta_pnl, residual_pnl, total_pnl, count)`
- `HoldingPeriodComparison(holding_days, direction, avg_return, median_return, win_rate, sharpe_like, max_loss, count)`

Migration 029 indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_co_holding_days ON contract_outcomes(holding_days);
CREATE INDEX IF NOT EXISTS idx_co_collected_at ON contract_outcomes(collected_at);
CREATE INDEX IF NOT EXISTS idx_ap_agent_direction ON agent_predictions(agent_name, direction);
CREATE INDEX IF NOT EXISTS idx_rc_market_iv ON recommended_contracts(market_iv);
CREATE INDEX IF NOT EXISTS idx_rc_direction_created ON recommended_contracts(direction, created_at);
```

**Depends on**: nothing

---

### Task 2: 7 AnalyticsMixin queries + Greeks decomposition
**Status**: pending
**Files**:
- `src/options_arena/data/_analytics.py` — 7 new query methods in AnalyticsMixin
- `tests/unit/data/test_repository_analytics.py` — new file, 4-5 tests per query

**Details**:
New methods in `_analytics.py` (AnalyticsMixin), all return frozen Pydantic models:
1. `get_equity_curve(direction?, period?)` → `list[EquityCurvePoint]`
2. `get_drawdown_series(period?)` → `list[DrawdownPoint]`
3. `get_win_rate_by_sector(holding_days?)` → `list[SectorPerformanceResult]`
4. `get_win_rate_by_dte_bucket(holding_days?)` → `list[DTEBucketResult]`
5. `get_win_rate_by_iv_rank(holding_days?)` → `list[IVRankBucketResult]`
6. `get_greeks_decomposition(holding_days?, groupby?)` → `list[GreeksDecompositionResult]`
7. `get_holding_period_comparison()` → `list[HoldingPeriodComparison]`

Pattern: parameterized SQL → `_fetchall()` → list comprehension → frozen model.
Median/Sharpe computed in Python (SQLite lacks built-ins).
Greeks: `delta_pnl = stock_return_pct * entry_delta` (negated for puts).

**Depends on**: Task 1

---

### Task 3: Auto-scheduler + config
**Status**: pending
**Files**:
- `src/options_arena/models/config.py` — extend `AnalyticsConfig` with scheduler fields
- `src/options_arena/services/outcome_collector.py` — add `run_scheduler()` method
- `src/options_arena/api/app.py` — start scheduler in `lifespan()`
- `tests/unit/services/test_outcome_scheduler.py` — new file, scheduler tests

**Details**:
Config additions to `AnalyticsConfig(BaseModel)`:
- `auto_collect_enabled: bool = False`
- `auto_collect_hour_utc: int = 6` (with validator: 0-23)

Scheduler: `async def run_scheduler(self) -> None` — asyncio loop that calculates
seconds until next `auto_collect_hour_utc`, sleeps, calls existing `collect_outcomes()`,
logs results, repeats. Must NOT acquire operation mutex. Must handle `CancelledError`
gracefully for clean shutdown.

Lifespan wiring: `asyncio.create_task(collector.run_scheduler())` before `yield`,
`task.cancel()` + `await task` after `yield`.

**Depends on**: nothing (independent of Task 1/2)

---

### Task 4: CLI subcommands
**Status**: pending
**Files**:
- `src/options_arena/cli/outcomes.py` — 2 new subcommands
- `tests/unit/cli/test_outcomes.py` — extend with new subcommand tests

**Details**:
New subcommands (sync Typer + `asyncio.run()` pattern, Rich tables):
- `outcomes backtest` — summary table with key performance metrics (total trades,
  win rate, avg return, max drawdown, Sharpe-like ratio by holding period)
- `outcomes equity-curve` — Rich sparkline/table of cumulative returns over time

Both use the 7 new AnalyticsMixin queries from Task 2.

**Depends on**: Task 2

---

### Task 5: API endpoints
**Status**: pending
**Files**:
- `src/options_arena/api/routes/backtest.py` — NEW FILE, 7 GET endpoints
- `src/options_arena/api/app.py` — router registration
- `tests/unit/api/test_analytics_backtest.py` — new file, endpoint tests

**Details**:
New routes under `/api/analytics/backtest/`:
- `GET /equity-curve?direction=&period=` → equity curve data
- `GET /drawdown?period=` → drawdown series
- `GET /sector-performance?holding_days=` → win rate by sector
- `GET /dte-performance?holding_days=` → win rate by DTE bucket
- `GET /iv-performance?holding_days=` → win rate by IV rank
- `GET /greeks-decomposition?groupby=&holding_days=` → delta vs residual P&L
- `GET /holding-comparison` → holding period optimizer data

Same `Depends(get_repo)` + rate limiting pattern as existing analytics endpoints.

**Depends on**: Task 2

---

### Task 6: Vue dashboard (store + view + charts)
**Status**: pending
**Files**:
- `web/package.json` — add `chart.js` dependency
- `web/src/stores/backtest.ts` — NEW FILE, Pinia setup store
- `web/src/views/AnalyticsView.vue` — NEW FILE, 5-tab layout
- `web/src/components/analytics/EquityCurveChart.vue` — NEW FILE
- `web/src/components/analytics/DrawdownChart.vue` — NEW FILE
- `web/src/components/analytics/SectorPerformanceChart.vue` — NEW FILE
- `web/src/components/analytics/GreeksDecompositionChart.vue` — NEW FILE
- `web/src/components/analytics/HoldingComparisonTable.vue` — NEW FILE
- `web/src/components/analytics/AgentAccuracyHeatmap.vue` — NEW FILE
- `web/src/router/index.ts` — add `/analytics` route
- Navigation component — add Analytics link

**Details**:
Pinia store (`useBacktestStore`): async fetchers for all 7 backtest endpoints + existing
agent accuracy/calibration endpoints. Caches responses in refs. Filter state (direction,
holding period, date range) as reactive refs.

AnalyticsView: PrimeVue TabView with 5 tabs:
- **Overview**: Equity curve (Chart.js line), summary cards, drawdown chart
- **Agents**: Accuracy heatmap, confidence calibration scatter, comparison table
  (uses existing `/api/analytics/agent-accuracy` + `/api/analytics/agent-calibration`)
- **Segments**: Sector bars, DTE buckets, IV rank quartiles
- **Greeks**: Stacked bar (delta vs residual) by direction/sector
- **Holding**: Period comparison table with highlighted best periods

Chart.js installed via `cd web && npm install chart.js`.

**Depends on**: Task 5

---

### Task 7: E2E tests
**Status**: pending
**Files**:
- `tests/e2e/analytics-dashboard.spec.ts` — NEW FILE
- Potentially seed data helpers

**Details**:
Playwright E2E tests for analytics dashboard:
- Dashboard page loads at `/analytics`
- All 5 tabs render without errors
- Charts display with seeded data
- Tab switching works correctly
- Empty state handled gracefully (no data scenario)
- Filter controls (direction, holding period) update charts

**Depends on**: Task 6

## Execution Waves

```
Wave 1: [Task 1, Task 3]  — Models + migration, Auto-scheduler (parallel, independent)
Wave 2: [Task 2]          — 7 AnalyticsMixin queries (depends on Task 1 models)
Wave 3: [Task 4, Task 5]  — CLI + API endpoints (parallel, both depend on Task 2)
Wave 4: [Task 6]          — Vue dashboard (depends on Task 5 API)
Wave 5: [Task 7]          — E2E tests (depends on Task 6 dashboard)
```

## Dependencies

### Internal (files modified)
- `src/options_arena/models/analytics.py` — ~7 new models
- `src/options_arena/models/config.py` — AnalyticsConfig extension
- `src/options_arena/data/_analytics.py` — 7 new query methods in AnalyticsMixin
- `src/options_arena/services/outcome_collector.py` — scheduler loop
- `src/options_arena/api/routes/backtest.py` — NEW FILE, 7 endpoints
- `src/options_arena/api/app.py` — router registration + scheduler in lifespan
- `src/options_arena/cli/outcomes.py` — 2 new subcommands
- `data/migrations/029_backtest_indexes.sql` — NEW FILE, 5 indexes
- `web/src/stores/backtest.ts` — NEW FILE
- `web/src/views/AnalyticsView.vue` — NEW FILE
- `web/src/components/analytics/` — ~6 NEW chart component files
- `web/src/router/index.ts` — route addition

### External
- `chart.js` npm dependency (peer of PrimeVue Chart)
- No new Python dependencies

## Success Criteria

| Criterion | Gate |
|-----------|------|
| All 7 new queries return typed models | `mypy --strict` passes |
| Query p95 <500ms on 10K contracts | Benchmark in query tests |
| Scheduler runs without blocking scans | No operation mutex contention |
| Dashboard loads all 5 tabs | Playwright E2E passes |
| All existing tests still pass | `pytest tests/ -n auto` green |
| No regressions on existing endpoints | Existing API tests unchanged |
| `ruff check` + `ruff format` clean | CI gates pass |

## Estimated Effort

- **Task 1**: S (models + migration, ~half day)
- **Task 2**: L (7 SQL queries with tests, ~2-3 days)
- **Task 3**: M (scheduler + lifespan wiring, ~1 day)
- **Task 4**: S (CLI subcommands, ~half day)
- **Task 5**: M (thin REST layer, ~1 day)
- **Task 6**: XL (5-tab dashboard with 6+ charts, ~4 days)
- **Task 7**: S (E2E tests, ~1 day)
- **Total: XL (~10-12 days)**

Critical path: Task 1 → Task 2 → Task 5 → Task 6 → Task 7 (longest chain ~9 days).
Tasks 1 and 3 are independent and can parallel. Tasks 4 and 5 can parallel.

## Tasks Created
- [ ] #430 - Analytics result models + migration 029 (parallel: true)
- [ ] #431 - 7 AnalyticsMixin queries + Greeks decomposition (parallel: false)
- [ ] #432 - Auto-scheduler + config (parallel: true)
- [ ] #433 - CLI subcommands (parallel: true)
- [ ] #434 - API endpoints (parallel: true)
- [ ] #435 - Vue analytics dashboard (parallel: false)
- [ ] #436 - E2E tests (parallel: false)

Total tasks: 7
Parallel tasks: 4 (#430, #432, #433, #434)
Sequential tasks: 3 (#431, #435, #436)
Estimated total effort: 84 hours

## Test Coverage Plan
Total test files planned: 6
Total test cases planned: ~102
- `tests/unit/models/test_analytics_backtest.py` — ~20 model validation tests
- `tests/unit/data/test_repository_backtest.py` — ~35 query tests (5 per query)
- `tests/unit/services/test_outcome_scheduler.py` — ~10 scheduler tests
- `tests/unit/cli/test_outcomes_backtest.py` — ~8 CLI tests
- `tests/unit/api/test_analytics_backtest.py` — ~18 endpoint tests
- `tests/e2e/analytics-dashboard.spec.ts` — ~11 E2E tests
