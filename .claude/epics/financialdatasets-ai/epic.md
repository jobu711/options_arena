---
name: financialdatasets-ai
status: backlog
created: 2026-03-08T18:06:12Z
progress: 0%
prd: .claude/prds/financialdatasets-ai.md
github: [Will be updated when synced to GitHub]
---

# Epic: financialdatasets-ai

## Overview

Integrate the financialdatasets.ai REST API as a runtime service to enrich the fundamental debate agent with income statements, balance sheets, and financial metrics. Follows the existing OpenBBService/IntelligenceService patterns exactly: DI constructor, never-raises contract, cache-first strategy, conditional creation on config `.enabled`. Adds 16 new `fd_*` fields to `MarketContext`, 3 new context sections for agent prompts, and bumps the fundamental agent prompt to v3.0 with financial health/valuation/growth analysis requirements.

## Architecture Decisions

- **httpx AsyncClient** for HTTP calls (existing pattern, no new dependencies)
- **Never-raises contract**: all service methods return `Type | None`, log at WARNING on error
- **FD > OpenBB > None priority** for 7 overlapping fields (pe_ratio, forward_pe, peg_ratio, price_to_book, debt_to_equity, revenue_growth, profit_margin)
- **`fd_*` prefix** for 16 new MarketContext fields — keeps FD data distinguishable from existing enrichment
- **`FinancialDatasetsConfig.enabled = True`** — service no-ops without API key (matches OpenBB pattern)
- **1-hour cache TTL** (per PRD) — financial data changes less frequently than options data
- **Debate-only** — NOT integrated into scan pipeline (too expensive for 500 tickers)
- **`FinancialDatasetsPackage`** aggregate model wraps metrics + income + balance sheet, fetched in parallel via `asyncio.gather`

## Technical Approach

### Data Models (NEW: `models/financial_datasets.py`)
- `FinancialMetricsData` — frozen, 21 fields (P/E, margins, growth, EPS, FCF yield, ROE, etc.)
- `IncomeStatementData` — frozen, 8 fields (revenue, gross profit, operating income, net income, EPS, etc.)
- `BalanceSheetData` — frozen, 8 fields (assets, liabilities, equity, debt, cash, current assets/liabilities)
- `FinancialDatasetsPackage` — frozen aggregate (ticker, metrics, income, balance_sheet, fetched_at)
- All models: `math.isfinite()` validators on floats, UTC validator on datetime

### Configuration (EXTEND: `models/config.py`)
- `FinancialDatasetsConfig(BaseModel)` nested in `AppSettings`
- Fields: `enabled`, `api_key` (str | None), `base_url`, `request_timeout`, `cache_ttl`
- Env var: `ARENA_FINANCIAL_DATASETS__API_KEY`

### Service (NEW: `services/financial_datasets.py`)
- `FinancialDatasetsService(config, cache, limiter)` — DI pattern
- 3 endpoint methods → `fetch_package()` parallel gather
- httpx AsyncClient with `X-API-KEY` header, `aclose()` lifecycle
- Cache keys: `"fd:metrics:{ticker}"`, `"fd:income:{ticker}"`, `"fd:balance:{ticker}"`

### MarketContext Extension (EXTEND: `models/analysis.py`)
- 16 `fd_*` optional float fields + `financial_datasets_ratio()` method
- Fields added to `validate_optional_finite()` validator

### Context Rendering (EXTEND: `agents/_parsing.py`)
- 3 new sections in `render_fundamental_context()` and `render_context_block()`:
  1. "## Income Statement (TTM)" — revenue, net income, operating income, EPS, margins
  2. "## Balance Sheet" — total debt, cash, total assets, current ratio
  3. "## Growth & Valuation" — revenue growth, earnings growth, EV/EBITDA, FCF yield, ROE
- Sections only rendered when at least one field is non-None

### Fundamental Agent Prompt (EXTEND: `agents/fundamental_agent.py`)
- Bump to VERSION v3.0 with 3 new analysis requirements: financial health, valuation depth, growth trajectory
- Add interpretation rules (high D/E + low current ratio = risk, PEG > 2.0 = overvalued, etc.)

### Integration Wiring
- **Orchestrator**: `fd_package` param on `build_market_context()` + `run_debate()`, FD > OpenBB priority mapping
- **API**: Service in `lifespan()`, `get_financial_datasets()` dep, fetch in debate route
- **CLI**: Service creation + fetch in debate command, close in `finally`
- **Health**: `check_financial_datasets()` method, added to `check_all()` when enabled

## Implementation Strategy

### Execution Waves
```
Wave 1 ─── Task 1: Models + Config (foundation, no deps)
Wave 2 ─── Task 2: Service          (depends on Task 1)
       ─── Task 3: MarketContext     (depends on Task 1, parallel with Task 2)
Wave 3 ─── Task 4: Rendering + Prompt (depends on Task 3)
Wave 4 ─── Task 5: Integration wiring (depends on Tasks 2, 3, 4)
Wave 5 ─── Task 6: Tests            (depends on all above)
```

### Risk Mitigation
- Never-raises contract ensures API failures can't break debates
- All new params are optional — existing flows work unchanged
- Config-gated: no API key = no service = no impact

## Task Breakdown Preview

- [ ] **Task 1: Models + Config** — `FinancialDatasetsConfig`, 4 frozen FD response models, re-exports, AppSettings field. ~120 LOC new, ~10 LOC modified.
- [ ] **Task 2: Service** — `FinancialDatasetsService` with 3 endpoints + `fetch_package()` + `close()`. Never-raises, cache-first, rate-limited. ~150 LOC new, ~5 LOC re-export.
- [ ] **Task 3: MarketContext extension** — 16 `fd_*` fields on MarketContext, validators, `financial_datasets_ratio()`. ~60 LOC modified.
- [ ] **Task 4: Context rendering + Prompt** — 3 new sections in both render functions, fundamental prompt v3.0 with financial health/valuation/growth analysis. ~80 LOC modified.
- [ ] **Task 5: Integration wiring** — Orchestrator `fd_package` param + priority mapping, API lifespan/deps/route, CLI service creation, health check. ~120 LOC modified across 7 files.
- [ ] **Task 6: Tests** — ~42 tests: model validation (~15), service mocking (~15), extended orchestrator/rendering/health (~12). 2 new + 3 extended test files.

## Dependencies

### External
- financialdatasets.ai REST API (`https://api.financialdatasets.ai`)
- API key via `ARENA_FINANCIAL_DATASETS__API_KEY` env var

### Internal
- `httpx` (already in project)
- `ServiceCache` + `RateLimiter` (existing infrastructure)
- OpenBBService/IntelligenceService patterns (templates)

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Fundamental context coverage | >80% of fd_* fields populated for S&P 500 tickers |
| `key_fundamental_factors` citing financial data | >=2 per debate when FD active |
| API latency (p95) | <2s for full package (3 parallel calls) |
| New tests passing | >=42 |
| Zero regressions | All existing ~4,200 tests pass |
| Health check | "Financial Datasets" row in `options-arena health` when API key set |
| Backward compatibility | All debates work unchanged when `fd_package=None` |

## Estimated Effort

- **Complexity**: Medium (M)
- **New files**: 2 (models + service)
- **Modified files**: 11 (config, analysis, __init__ x2, _parsing, fundamental_agent, orchestrator, commands, app, routes/debate, health)
- **New test files**: 2 + 3 extended
- **Total new/modified LOC**: ~800-1000
- **Risk**: Low — all patterns proven, backward compatible, config-gated

## Tasks Created
- [ ] 001.md - Models + Config — FD response models and FinancialDatasetsConfig (parallel: false)
- [ ] 002.md - FinancialDatasetsService — httpx service with cache and rate limiting (parallel: true)
- [ ] 003.md - MarketContext extension — 16 fd_* fields and financial_datasets_ratio() (parallel: true)
- [ ] 004.md - Context rendering + Fundamental agent prompt v3.0 (parallel: false)
- [ ] 005.md - Integration wiring — orchestrator, API, CLI, health check (parallel: false)
- [ ] 006.md - Comprehensive test suite — model, service, and integration tests (parallel: false)

Total tasks: 6
Parallel tasks: 2 (Tasks 002 + 003 in Wave 2)
Sequential tasks: 4 (Tasks 001, 004, 005, 006)
Estimated total effort: 20-27 hours

## Test Coverage Plan
Total test files planned: 5 (2 new + 3 extended)
Total test cases planned: ~42
