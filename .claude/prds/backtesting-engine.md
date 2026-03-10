---
name: backtesting-engine
description: Performance measurement engine with auto-scheduled outcome collection, basic Greeks decomposition, full analytics API, and web dashboard
status: planned
created: 2026-03-08T23:05:00Z
updated: 2026-03-09T23:38:39Z
---

# PRD: backtesting-engine

## Executive Summary

Build a performance measurement engine that analyzes the actual track record of Options
Arena's recommendations. The system auto-collects outcomes on a daily schedule, decomposes
P&L into delta and residual components using entry Greeks, and surfaces results through a
full analytics suite: CLI tables, REST API endpoints, and a Vue dashboard with equity
curves, agent accuracy heatmaps, and multi-dimensional win-rate breakdowns.

The existing infrastructure already collects outcome data at 4 time horizons (T+1/5/10/20)
and persists per-agent predictions. This epic extends that foundation into a complete
backtesting and calibration platform.

## Problem Statement

Options Arena makes recommendations but has no systematic way to answer: "How good are
these recommendations?" The data is being collected (OutcomeCollector, AgentPrediction,
RecommendedContract) but analysis is limited to 6 analytics + 3 agent calibration queries. Users cannot:

- See cumulative performance over time (no equity curve)
- Know which market conditions produce the best outcomes (no sector/DTE/IV segmentation)
- Track drawdowns or identify when the system underperforms (no risk metrics)
- Get results automatically — outcome collection requires manual CLI trigger

This matters now because 384+ issues of infrastructure work have been shipped. The system
generates real recommendations daily. Without performance measurement, there is no feedback
loop to improve scoring weights, agent prompts, or contract selection.

## User Stories

### US-1: Portfolio performance viewer
**As** an options trader using Options Arena daily,
**I want** to see a cumulative equity curve of all recommendations over time,
**so that** I can assess whether the system's recommendations are profitable.

**Acceptance criteria:**
- Equity curve shows cumulative contract return % over calendar time
- Separate curves for bullish vs bearish recommendations
- Summary cards: total trades, win rate, average return, max drawdown
- Filterable by date range (7d, 30d, 90d, all-time)

### US-2: Agent accuracy analyst
**As** a power user tuning the debate system,
**I want** to see per-agent accuracy breakdowns and confidence calibration,
**so that** I can identify which agents are most reliable and adjust vote weights.

**Acceptance criteria:**
- Heatmap: agent name × direction → accuracy %
- Confidence calibration curve: predicted confidence bucket vs actual win rate
- Per-agent stats: total predictions, accuracy, avg confidence, overconfidence ratio
- Agent comparison table sorted by accuracy

> **Note:** Per-agent accuracy and calibration queries already exist in `_debate.py`
> (`get_agent_accuracy()`, `get_agent_confidence_calibration()`). This story extends them
> into the dashboard visualization (heatmap, calibration curve), not re-implementing the backend.

### US-3: Strategy segmentation analyst
**As** a trader optimizing my use of Options Arena,
**I want** to see win rates broken down by sector, DTE bucket, and IV rank,
**so that** I can focus on the conditions where the system performs best.

**Acceptance criteria:**
- Win rate by GICS sector (bar chart)
- Win rate by DTE bucket (0-7, 7-14, 14-30, 30-60, 60+)
- Win rate by IV rank quartile (0-25, 25-50, 50-75, 75-100)
- Score calibration: composite score bucket → actual return (scatter/line)
- All charts filterable by holding period (1d, 5d, 10d, 20d)

### US-4: Greeks P&L decomposition viewer
**As** an options-literate trader,
**I want** to see approximate delta P&L vs residual (theta/vega/gamma),
**so that** I can understand whether returns came from directional moves or other factors.

**Acceptance criteria:**
- Delta P&L = stock_return_pct × entry_delta (for calls; negated for puts)
- Residual P&L = contract_return_pct − delta_pnl
- Aggregated by direction, sector, or time period
- Displayed as stacked bar chart (delta component vs residual component)

### US-5: Automated outcome collection
**As** a hands-off user,
**I want** outcomes to be collected automatically every day,
**so that** I don't have to remember to run `outcomes collect` manually.

**Acceptance criteria:**
- Background scheduler runs daily at a configurable time (default: 06:00 UTC)
- Collects outcomes for all configured holding periods (1, 5, 10, 20 days)
- Logs collection results (contracts processed, errors)
- Skips if no contracts are due for collection
- Configurable via `AnalyticsConfig` (enabled/disabled, schedule time)
- Does not block scan or debate operations (separate from operation mutex)

### US-6: Holding period optimizer
**As** a trader choosing between short and long holds,
**I want** to see which holding period produces the best risk-adjusted returns,
**so that** I can optimize my exit timing.

**Acceptance criteria:**
- Comparison table: holding period × avg return, median return, win rate, Sharpe-like ratio
- Best holding period highlighted per direction (bullish vs bearish)
- Drawdown by holding period (worst single-trade loss)

## Requirements

### Functional Requirements

#### FR-1: Auto-Scheduled Outcome Collection
- Add `asyncio`-based background scheduler to `OutcomeCollector`
- Configurable via `AnalyticsConfig`: `auto_collect_enabled: bool = False`,
  `auto_collect_hour_utc: int = 6`
- Scheduler starts in FastAPI `lifespan()` and CLI `serve` command
- Uses `asyncio.sleep()` loop with next-run calculation (no external scheduler dependency)
- Logs each run: contracts due, collected, errors
- Respects existing `return_exceptions=True` isolation pattern

#### FR-2: Greeks P&L Decomposition
- New model `GreeksDecomposition(BaseModel, frozen=True)`:
  `delta_pnl: float`, `residual_pnl: float`, `total_pnl: float`
- Computation: `delta_pnl = stock_return_pct * entry_delta` (negated for puts)
- `residual_pnl = contract_return_pct - delta_pnl`
- Added as computed fields on `ContractOutcome` or as a separate query result
- Aggregation functions: by direction, sector, time bucket

#### FR-3: Extended Analytics Queries
New methods in `_analytics.py` (AnalyticsMixin), all return frozen Pydantic models:
- `get_win_rate_by_sector()` → `list[SectorPerformanceResult]`
- `get_win_rate_by_dte_bucket()` → `list[DTEBucketResult]`
- `get_win_rate_by_iv_rank()` → `list[IVRankBucketResult]`
- `get_equity_curve(direction?)` → `list[EquityCurvePoint]`
- `get_drawdown_series()` → `list[DrawdownPoint]`
- `get_greeks_decomposition(groupby?)` → `list[GreeksDecompositionResult]`
- `get_holding_period_comparison()` → `list[HoldingPeriodComparison]`

> `get_agent_accuracy()` and `get_agent_confidence_calibration()` already exist in
> `_debate.py` (DebateMixin) — not duplicated here.

#### FR-4: REST API Endpoints
New routes under `/api/analytics/backtest/`:
- `GET /equity-curve?direction=&period=` → equity curve data
- `GET /drawdown?period=` → drawdown series
- `GET /sector-performance?holding_days=` → win rate by sector
- `GET /dte-performance?holding_days=` → win rate by DTE bucket
- `GET /iv-performance?holding_days=` → win rate by IV rank
- `GET /greeks-decomposition?groupby=` → delta vs residual P&L
- `GET /holding-comparison` → holding period optimizer data

> Agent accuracy (`/api/analytics/agent-accuracy`), agent calibration
> (`/api/analytics/agent-calibration`), and manual collection
> (`/api/analytics/collect-outcomes`) are already live — not duplicated.

#### FR-5: CLI Subcommands
Extend `outcomes` command group:
- `outcomes backtest` → summary table with key performance metrics
- `outcomes equity-curve` → ASCII sparkline or Rich chart of cumulative returns
- Existing `outcomes collect`, `outcomes summary`, `outcomes agent-accuracy`,
  `outcomes calibration`, and `outcomes agent-weights` unchanged

#### FR-6: Vue Dashboard Page
New route `/analytics` with tabbed layout:
- **Overview tab**: Equity curve (Chart.js line), summary cards, drawdown chart
- **Agents tab**: Accuracy heatmap, confidence calibration scatter, agent comparison table
- **Segments tab**: Sector bars, DTE buckets, IV rank quartiles, score calibration
- **Greeks tab**: Stacked bar (delta vs residual) by direction/sector
- **Holding tab**: Period comparison table with highlighted best periods
- Pinia store: `useBacktestStore` with async fetchers + caching
- All charts: Chart.js (already available via PrimeVue) or lightweight alternative

### Non-Functional Requirements

#### NFR-1: Performance
- All analytics queries must complete in <500ms for up to 10,000 contracts
- Equity curve query uses SQL window functions, not Python iteration
- Dashboard initial load <2s with lazy-loaded chart data
- Auto-collector must not impact scan/debate latency (runs on separate async task)

#### NFR-2: Data Integrity
- All new models use `frozen=True` (immutable snapshots)
- All float fields guarded with `math.isfinite()` validators
- All datetime fields enforce UTC via `field_validator`
- Greeks decomposition handles None Greeks gracefully (returns None, not NaN)

#### NFR-3: Backward Compatibility
- Existing analytics endpoints unchanged (no breaking changes)
- New endpoints under `/api/analytics/backtest/` namespace
- Existing `contract_outcomes` table schema unchanged — new queries only
- Auto-collector disabled by default (`auto_collect_enabled = False`)

## Success Criteria

| Metric | Target |
|--------|--------|
| Analytics query count | 16+ (currently 9) |
| Query response time (p95) | <500ms for 10K contracts |
| Dashboard chart types | 6+ (equity, drawdown, heatmap, bars, scatter, stacked bar) |
| Agent accuracy tracking | All 8 debate agents individually measured |
| Auto-collection reliability | 99%+ daily runs without manual intervention |
| Outcome coverage | >80% of contracts aged >20d have all 4 holding period outcomes |
| Test coverage | >90% on new repository queries and models |

## Constraints & Assumptions

### Constraints
- SQLite only (no Postgres/Redis) — all queries must work with aiosqlite
- Chart.js or PrimeVue Charts for frontend (no D3.js — too heavy for this project)
- Entry Greeks only for decomposition (no re-computation at exit — that's a future phase)
- Raw returns only (no commission/slippage model in v1)
- Auto-scheduler uses asyncio, not APScheduler or Celery

### Assumptions
- Sufficient outcome data exists after several weeks of daily scans (~50+ contracts)
- Entry Greeks (delta especially) are accurate enough for approximate decomposition
- Users run `options-arena serve` long enough for auto-collection to trigger
- SQLite window functions (`OVER`, `LAG`, `SUM() OVER`) are sufficient for equity curve

## Out of Scope

- **Hypothetical replay** — re-running the pipeline with different parameters against historical data
- **Fee/slippage modeling** — commission, bid-ask cost, assignment fees
- **Full Greeks re-computation at exit** — would require re-pricing at exit time
- **Multi-leg spread backtesting** — only single-contract P&L
- **Real-time P&L streaming** — outcomes are batch-collected, not live
- **Position sizing / Kelly criterion** — all contracts treated as 1 unit
- **Realized vs implied volatility decomposition** — requires historical realized vol capture
- **Portfolio correlation analysis** — single-contract analysis only
- **PDF/Excel export of backtest reports** — CLI and web only for v1
- **Intraday mark-to-market** — daily resolution only

## Dependencies

### Internal
- `data/_analytics.py` — 7 new query methods in AnalyticsMixin
- `models/analytics.py` — ~7 new frozen models
- `models/config.py` — `AnalyticsConfig` extensions (scheduler fields)
- `services/outcome_collector.py` — scheduler loop addition
- `api/routes/analytics.py` — new endpoint registrations
- `cli/outcomes.py` — new subcommands
- `web/src/views/` — new `AnalyticsView.vue` page
- `web/src/stores/` — new `backtest.ts` Pinia store
- `data/migrations/029_backtest_indexes.sql` — performance indexes (no schema changes)

### External
- Chart.js or PrimeVue Charts (likely already bundled with PrimeVue)
- No new Python dependencies expected (asyncio scheduler, SQL window functions)

## Implementation Phases

### Phase 1: Models & Queries (Backend foundation)
- Define ~7 new analytics result models in `models/analytics.py`
- Implement 7 new query methods in `_analytics.py` (AnalyticsMixin) with SQL window functions
- Add database indexes for query performance (`029_backtest_indexes.sql`)
- Add `GreeksDecomposition` computation logic
- Agent accuracy/calibration models and queries already exist — not duplicated
- Tests: unit tests for all models and queries (~100+ tests)

### Phase 2: Auto-Scheduler & CLI (Backend services)
- Implement asyncio-based daily scheduler in `OutcomeCollector`
- Extend `AnalyticsConfig` with scheduler settings
- Wire scheduler into FastAPI `lifespan()` and `serve` command
- Add CLI subcommands (`outcomes backtest`, `outcomes equity-curve`)
- Tests: scheduler tests (mock time), CLI integration tests

### Phase 3: API Endpoints (REST layer)
- Register 7 new endpoints under `/api/analytics/backtest/`
- Agent accuracy/calibration endpoints already live under `/api/analytics/` — not duplicated
- Rate limiting consistent with existing analytics endpoints
- OpenAPI schema documentation
- Tests: endpoint tests with test database

### Phase 4: Vue Dashboard (Frontend)
- Create `AnalyticsView.vue` with tabbed layout (5 tabs)
- Implement `useBacktestStore` Pinia store
- Build chart components (equity curve, heatmap, bars, scatter, stacked bar)
- Add `/analytics` route to Vue Router
- Add navigation link in sidebar/header
- Tests: E2E tests with Playwright

### Estimated Effort
- Phase 1: L (3-4 days) — heaviest SQL and model work
- Phase 2: M (2 days) — scheduler + CLI
- Phase 3: M (1-2 days) — thin REST layer over queries
- Phase 4: XL (4-5 days) — 5 dashboard tabs with 6+ chart types
- **Total: XL (10-13 days)**
