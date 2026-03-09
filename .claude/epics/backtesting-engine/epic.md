---
name: backtesting-engine
status: backlog
created: 2026-03-08T23:37:36Z
progress: 0%
prd: .claude/prds/backtesting-engine.md
github: [Will be updated when synced to GitHub]
---

# Epic: backtesting-engine

## Overview

Extend the existing analytics infrastructure (6 queries, OutcomeCollector, AgentPrediction
persistence) into a complete performance measurement platform. Adds 9 new repository
queries, auto-scheduled outcome collection, ~10 REST endpoints, 3 CLI subcommands, and a
Vue dashboard with 5 tabs. All changes are additive — no breaking changes, no new tables,
only a migration for performance indexes.

The existing infrastructure does ~60% of the work. This epic fills the remaining 40%:
equity curves, drawdowns, agent accuracy, segment analysis, Greeks decomposition, and a
visual dashboard.

## Architecture Decisions

1. **Extend existing analytics router, don't create a new one.** New endpoints go under
   `/api/analytics/backtest/` as a sub-router included in the existing analytics router.
   This keeps rate limiting, dependency injection, and error handling consistent.

2. **asyncio.sleep() scheduler, not APScheduler.** The project avoids external scheduler
   deps. A simple `while True: sleep_until_next_run(); collect()` loop in a background
   task is sufficient. Started in lifespan, cancelled on shutdown.

3. **Greeks decomposition uses entry Greeks only.** `delta_pnl = stock_return × delta`
   (negated for puts), `residual = total - delta`. No exit re-pricing. This is approximate
   but requires zero new data fetching.

4. **Chart.js via PrimeVue Chart wrapper.** PrimeVue already provides the Chart component
   shell — just need `chart.js` as a peer dependency. Consistent dark theme styling.

5. **All queries in repository.py, not a new service.** Analytics queries are pure SQL →
   model mapping. No business logic warrants a separate service layer. Keeps the data
   module boundary clean.

6. **Migration for indexes only.** All 9 queries use existing tables. Migration 026 adds
   5 indexes to optimize GROUP BY and JOIN performance on analytics tables.

## Technical Approach

### Backend (Tasks 1-4)

**Models** (`models/analytics.py`): ~10 new frozen result models following existing patterns.
All have `math.isfinite()` validators, `frozen=True`, UTC datetime enforcement.

**Repository** (`data/repository.py`): 9 new query methods appended after existing analytics
section (line 1339+). Pattern: parameterized SQL → `fetchall()` → list comprehension →
frozen model. Median/Sharpe computed in Python (SQLite lacks these). Agent accuracy uses
3-table JOIN: `agent_predictions` → `recommended_contracts` → `contract_outcomes`.

**Scheduler** (`services/outcome_collector.py`): New `run_scheduler()` method — asyncio
loop that sleeps until `auto_collect_hour_utc`, calls existing `collect_outcomes()`, logs
results, repeats. Config: `auto_collect_enabled: bool = False` (opt-in).

**API** (`api/routes/backtest.py`): New router file with ~10 GET endpoints. Registered in
`app.py` under `/api/analytics/backtest`. Same `Depends(get_repo)` + `60/minute` rate limit.

**CLI** (`cli/outcomes.py`): 3 new subcommands extending existing `outcomes` group. Same
sync→async wrapper pattern with Rich table rendering.

### Frontend (Tasks 5-6)

**Store** (`web/src/stores/backtest.ts`): Pinia setup store with async fetchers for all
backtest endpoints. Caches responses in refs. Filter state (direction, holding period,
date range) as reactive refs.

**Page** (`web/src/views/AnalyticsView.vue`): PrimeVue TabView with 5 tabs. Each tab
lazy-loads its data on first activation. Chart.js for line/bar/scatter charts, PrimeVue
DataTable for tabular data.

**Components**: ~6 chart components in `web/src/components/analytics/`. Reuse existing
patterns from `WinRateChart.vue`, `ScoreCalibrationChart.vue`, etc.

## Implementation Strategy

### Dependency Chain
```
Task 1 (Models + Migration)
    ↓
Task 2 (Repository Queries) ← depends on models
    ↓
Task 3 (Auto-Scheduler) ← independent, can parallel with Task 2
    ↓
Task 4 (API + CLI) ← depends on queries
    ↓
Task 5 (Vue Dashboard) ← depends on API
    ↓
Task 6 (E2E Tests) ← depends on dashboard
```

Tasks 2 and 3 can run in parallel (no dependency between queries and scheduler).

### Risk Mitigation
- **Agent data sparsity**: `agent_predictions.recommended_contract_id` may be nullable/sparse.
  Query with LEFT JOIN, return 0 accuracy for agents with no linked outcomes. Documented in UI.
- **Sector coverage**: Filter NULL sectors in `get_win_rate_by_sector()`. Show "N/A" count.
- **Chart.js install**: Verify `web/package.json` in Task 5 preflight. If missing, `npm install chart.js`.

### Testing Approach
Each task includes its own tests. No separate test-only task.
- Tasks 1: Model validation tests (valid/invalid/roundtrip)
- Task 2: Repository query tests (in-memory SQLite, 4-5 per query)
- Task 3: Scheduler tests (mock `asyncio.sleep`, mock `datetime.now`)
- Task 4: API endpoint tests (httpx AsyncClient) + CLI tests (CliRunner)
- Task 5: Component rendering (if Vitest available)
- Task 6: Playwright E2E for dashboard page

## Task Breakdown Preview

- [ ] **Task 1: Analytics result models + migration 026** — Define ~10 new frozen result models (EquityCurvePoint, DrawdownPoint, AgentAccuracyResult, ConfidenceCalibrationBucket, SectorPerformanceResult, DTEBucketResult, IVRankBucketResult, GreeksDecompositionResult, HoldingPeriodComparison) in `models/analytics.py`. Add migration 026 with 5 performance indexes. Model validation tests.

- [ ] **Task 2: Repository backtesting queries** — Implement 9 new query methods in `repository.py`: `get_equity_curve()`, `get_drawdown_series()`, `get_agent_accuracy()`, `get_agent_confidence_calibration()`, `get_win_rate_by_sector()`, `get_win_rate_by_dte_bucket()`, `get_win_rate_by_iv_rank()`, `get_greeks_decomposition()`, `get_holding_period_comparison()`. Query unit tests with in-memory SQLite.

- [ ] **Task 3: Auto-scheduled outcome collection** — Extend `AnalyticsConfig` with `auto_collect_enabled`/`auto_collect_hour_utc`. Add `run_scheduler()` to OutcomeCollector. Wire into FastAPI `lifespan()` and `serve` command. Scheduler tests.

- [ ] **Task 4: Backtest API endpoints + CLI subcommands** — Create `routes/backtest.py` with ~10 GET endpoints under `/api/analytics/backtest/`. Add 3 CLI subcommands (`outcomes backtest`, `outcomes agents`, `outcomes equity-curve`). API + CLI tests.

- [ ] **Task 5: Vue analytics dashboard** — Install Chart.js. Create `useBacktestStore` Pinia store, `AnalyticsView.vue` with 5 PrimeVue tabs (Overview, Agents, Segments, Greeks, Holding), ~6 chart components, `/analytics` route + nav link.

- [ ] **Task 6: E2E tests + integration polish** — Playwright E2E tests for analytics dashboard. Verify all 5 tabs render with mock data. End-to-end flow: collect → query → display. Final lint/typecheck/test pass.

## Dependencies

### Internal (files modified)
- `src/options_arena/models/analytics.py` — ~10 new models
- `src/options_arena/models/config.py` — AnalyticsConfig extension
- `src/options_arena/data/repository.py` — 9 new query methods
- `src/options_arena/services/outcome_collector.py` — scheduler loop
- `src/options_arena/api/routes/backtest.py` — NEW FILE, ~10 endpoints
- `src/options_arena/api/app.py` — router registration + scheduler in lifespan
- `src/options_arena/cli/outcomes.py` — 3 new subcommands
- `data/migrations/026_backtest_indexes.sql` — NEW FILE, 5 indexes
- `web/src/stores/backtest.ts` — NEW FILE
- `web/src/views/AnalyticsView.vue` — NEW FILE
- `web/src/components/analytics/` — ~6 NEW chart component files

### External
- `chart.js` npm dependency (peer of PrimeVue Chart)
- No new Python dependencies

## Success Criteria (Technical)

| Criterion | Gate |
|-----------|------|
| All 9 new queries return typed models | `mypy --strict` passes |
| Query p95 <500ms on 10K contracts | Benchmark in query tests |
| Scheduler runs without blocking scans | No operation mutex contention |
| Dashboard loads all 5 tabs | Playwright E2E passes |
| All existing tests still pass | `pytest tests/ -n auto` green |
| No regressions on existing endpoints | Existing API tests unchanged |
| `ruff check` + `ruff format` clean | CI gates pass |

## Estimated Effort

- **Task 1**: S (models + migration, ~half day)
- **Task 2**: L (9 SQL queries with tests, ~3 days)
- **Task 3**: M (scheduler + lifespan wiring, ~1 day)
- **Task 4**: M (thin REST + CLI layer, ~1-2 days)
- **Task 5**: XL (5-tab dashboard with 6+ charts, ~4 days)
- **Task 6**: S (E2E tests + polish, ~1 day)
- **Total: XL (~10-12 days)**

Critical path: Task 1 → Task 2 → Task 4 → Task 5 (longest chain ~9 days).
Task 3 is independent and can parallel with Task 2.
