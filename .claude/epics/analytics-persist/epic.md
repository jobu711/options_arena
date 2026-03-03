---
name: analytics-persist
status: backlog
created: 2026-03-03T10:21:32Z
progress: 0%
prd: .claude/prds/analytics-persist.md
github: https://github.com/jobu711/options_arena/issues/209
---

# Epic: analytics-persist

## Overview

Close the feedback loop on scan recommendations by persisting recommended contracts, tracking their outcomes over multiple holding periods, capturing normalization distributions, and exposing analytics queries via API. Currently Phase 3 discards contract recommendations and Phase 4 only persists ScanRun + TickerScore. This epic adds 3 tables, an outcome collection service, and 8 analytics endpoints.

## Architecture Decisions

1. **Single Repository, not separate AnalyticsRepository** — Keep all methods in `Repository` with `# --- Analytics ---` grouping. Both share the same `Database` instance and the split adds complexity without benefit at this scale (~12 new methods).

2. **Migrations 011/012/013** — Research confirmed migration 010 is taken by `intelligence_tables.sql`. Renumber all three.

3. **Holding periods configurable** — `AnalyticsConfig.holding_periods: list[int] = [1, 5, 10, 20]` plus at-expiry. Not hardcoded.

4. **Expired contract handling via intrinsic value** — yfinance doesn't have historical option prices. For expired contracts, compute intrinsic value from stock price at expiry (max(0, S-K) for calls, max(0, K-S) for puts). Flag `collection_method = "intrinsic"`.

5. **Outcome collection via both CLI and API** — CLI command `options-arena outcomes collect` for manual/cron use, plus `POST /api/analytics/collect-outcomes` for web UI trigger.

6. **All analytics models in single `analytics.py`** — One new file for all models (RecommendedContract, ContractOutcome, NormalizationStats, and 6 query result models). Keeps the models layer clean.

## Technical Approach

### Data Layer
- 3 new migrations: `recommended_contracts`, `contract_outcomes`, `normalization_metadata`
- Repository methods follow existing `save_*()` / `get_*()` / `_row_to_*()` patterns
- Analytics queries use JOINs across `recommended_contracts` + `contract_outcomes` + `ticker_scores`
- Decimal stored as TEXT, reconstructed via `Decimal(row["col"])`

### Pipeline Integration
- Phase 3: Capture `ticker_info.current_price` as entry stock price into `OptionsResult.entry_prices`
- Phase 4: Build `RecommendedContract` list from recommendations + entry prices, persist alongside scan run
- Phase 2: `compute_normalization_stats()` captures per-indicator distributions, persist in Phase 4

### Service Layer
- `OutcomeCollector` class: config + repository + market_data DI
- Queries contracts from N days ago without outcomes at that holding period
- Fetches current stock quote, computes stock/contract return percentages
- Handles expired contracts (intrinsic value), never raises

### API & CLI
- `api/routes/analytics.py` with 8 GET + 1 POST endpoint
- DI via existing `get_repository()` + new `get_outcome_collector()`
- CLI `outcomes` subcommand group (collect, summary)

## Task Breakdown Preview

4 tasks, executed sequentially (each depends on the prior):

- [ ] **Task 1: Foundation — models, config, migrations** — All Pydantic models in `analytics.py`, `OutcomeCollectionMethod` enum, `AnalyticsConfig`, 3 SQL migrations, re-exports. Pure data shapes, no logic. (~30 tests)
- [ ] **Task 2: Contract & normalization persistence** — Repository save/get methods for contracts + normalization, `OptionsResult.entry_prices` field, pipeline Phase 3 capture + Phase 4 persist, `compute_normalization_stats()` in scoring. (~45 tests)
- [ ] **Task 3: Outcome tracking service + CLI** — `OutcomeCollector` service, repository outcome methods, CLI `outcomes` command group, P&L computation, expired contract handling. (~35 tests)
- [ ] **Task 4: Analytics queries + API endpoints** — 6 analytics repository query methods, `api/routes/analytics.py` with 9 endpoints, DI wiring, app registration. (~35 tests)

## Dependencies

- **Migration 010 (intelligence_tables)** must be merged to master first (already done via market-recon epic)
- **Phase 3 spot price** available via `ticker_info.current_price` — confirmed in research
- **yfinance `fetch_quote()`** already exists for outcome collection

## Success Criteria (Technical)

- All scan recommendations persisted with entry prices and Greeks
- Outcome collection works for T+1, T+5, T+10, T+20 holding periods
- Expired contracts handled via intrinsic value computation
- 6 analytics queries return typed results (win rate, score calibration, indicator attribution, holding period, delta performance, summary)
- All 9 API endpoints return correct data
- ~145 new tests passing
- `ruff check`, `pytest`, `mypy --strict` all green

## Estimated Effort

- **4 tasks** with sequential dependencies
- **~145 new tests** total
- **3 new files**: `models/analytics.py`, `services/outcome_collector.py`, `api/routes/analytics.py`
- **3 new migrations**: 011, 012, 013
- **~10 edited files**: scan/models, scan/pipeline, data/repository, models/__init__, models/enums, models/config, scoring/normalization, api/app, api/deps, cli/app
- **Complexity: L (Large)** — 4 implementation sessions

## Tasks Created

- [ ] #210 - Foundation — models, config, migrations (parallel: false)
- [ ] #211 - Contract and normalization persistence (parallel: false)
- [ ] #212 - Outcome tracking service and CLI (parallel: false)
- [ ] #213 - Analytics queries and API endpoints (parallel: false)

Total tasks: 4
Parallel tasks: 0
Sequential tasks: 4
Estimated total effort: 22-30 hours

## Test Coverage Plan

Total test files planned: 7
Total test cases planned: ~145
- `tests/unit/models/test_analytics.py` (~30 tests)
- `tests/unit/data/test_analytics_repository.py` (~12 tests)
- `tests/unit/scan/test_contract_persistence.py` (~5 tests)
- `tests/unit/scoring/test_normalization_stats.py` (~6 tests)
- `tests/unit/services/test_outcome_collector.py` (~16 tests)
- `tests/unit/data/test_outcome_repository.py` (~8 tests)
- `tests/unit/data/test_analytics_queries.py` (~16 tests)
- `tests/unit/api/test_analytics_routes.py` (~13 tests)
