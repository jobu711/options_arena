---
name: financialdatasets-ai
description: Integrate financialdatasets.ai REST API as a runtime service to enrich the fundamentals agent with income statements, balance sheets, and financial metrics
status: planned
created: 2026-03-08T17:17:50Z
---

# PRD: financialdatasets-ai

## Executive Summary

The fundamental debate agent currently depends on **OpenBB SDK** (optional, often not
installed) for key financial ratios (P/E, PEG, D/E, revenue growth, profit margin). When
OpenBB is unavailable, the agent loses 18 data fields and falls back to just earnings
proximity, dividends, and IV crush — a significantly degraded analysis that produces
lower-quality debate output.

The **financialdatasets.ai** REST API (already configured as an MCP server for dev use)
provides income statements, balance sheets, cash flows, and financial metrics via a simple
API-key-authenticated HTTP API. This PRD adds a runtime `FinancialDatasetsService` that
calls this API during debates, providing the fundamental agent with rich financial data
(revenue, net income, margins, debt, cash position, growth rates, valuation multiples)
that no existing data source provides. The result: fundamentally grounded options analysis
with balance sheet health, growth trajectory, and valuation depth — even without OpenBB.

## Problem Statement

### What problem are we solving?

The fundamental agent's analysis quality is gated by OpenBB SDK availability. Most
deployments don't have OpenBB installed, leaving the agent with only:
- Earnings calendar proximity (from yfinance)
- Dividend yield (from yfinance)
- Short interest (from yfinance)
- IV crush risk assessment (from scan indicators)

Missing entirely: income statement data, balance sheet health, margin trends, growth rates,
EV/EBITDA, FCF yield, current ratio, and ROE. These are foundational for any fundamental
analysis of options positioning — e.g., a company with deteriorating margins and rising
debt should lower confidence in bullish call recommendations.

### Why is this important now?

- **Debate quality gap**: The fundamental agent is the weakest of the six debate agents
  because it has the least data. Trend, Volatility, and Flow agents all receive rich
  indicator data from the scan pipeline. The fundamental agent often receives near-empty
  context blocks.
- **Proven API**: The financialdatasets.ai MCP is already enabled and tested in dev
  sessions. The API shapes are verified. No research risk.
- **No new dependencies**: The project already uses `httpx` for FRED and CBOE. Adding
  another HTTP data source follows an established pattern with zero new packages.
- **Outcome tracking is live**: With `OutcomeCollector` measuring P&L at T+1/5/10/20,
  we can measure whether richer fundamental context produces better debate verdicts.

## User Stories

### US-1: Debate user gets fundamentally grounded analysis

**As** a debate user, **I want** the fundamental agent to analyze income statement,
balance sheet, and growth data **so that** its direction and confidence reflect the
company's actual financial health, not just earnings proximity.

**Acceptance criteria:**
- When `ARENA_FINANCIAL_DATASETS__API_KEY` is set, the fundamental agent's context block
  includes "## Income Statement (TTM)", "## Balance Sheet", and "## Growth & Valuation"
  sections
- The agent's output references specific financial metrics (e.g., "current ratio of 0.97
  suggests tight liquidity") rather than generic statements
- Debate output quality measurably improves (more `key_fundamental_factors` entries citing
  financial data)

### US-2: Financial data supplements existing OpenBB fields

**As** the system, **I want** financialdatasets.ai to populate the same MarketContext
fields that OpenBB provides (P/E, PEG, P/B, D/E, revenue growth, profit margin) **so
that** the fundamental profile section is populated even without OpenBB installed.

**Acceptance criteria:**
- When both FD and OpenBB provide a field (e.g., `pe_ratio`), FD takes priority
- When FD is unavailable, OpenBB values are used (backward compatible)
- When neither is available, fields remain `None` (existing behavior preserved)
- `render_fundamental_context()` renders the same "## Fundamental Profile" section
  regardless of data source

### US-3: Health check includes Financial Datasets

**As** a user running `options-arena health`, **I want** to see the Financial Datasets
API status **so that** I can verify my API key works before running debates.

**Acceptance criteria:**
- `options-arena health` includes a "Financial Datasets" row when the API key is configured
- Shows green with latency when API responds, red with error when unreachable
- Row is omitted when no API key is configured (not an error)

### US-4: Service handles errors gracefully

**As** a user, **I want** debates to work normally if the Financial Datasets API is down
**so that** a third-party outage never breaks my workflow.

**Acceptance criteria:**
- API timeout/error returns `None`, logged at WARNING — never raises
- Debate proceeds with OpenBB/yfinance data as fallback (or empty fundamental profile)
- No user-visible error when API key is missing — service simply doesn't activate

## Requirements

### Functional Requirements

#### FR-1: Pydantic Models for API Responses
- `FinancialMetricsData` — frozen model with 21 fields: P/E, P/B, PEG, EV/EBITDA, D/E,
  gross/operating/net margin, ROE, ROA, current ratio, revenue/earnings/FCF growth, EPS,
  FCF per share, FCF yield, book value per share, market cap, enterprise value, report period
- `IncomeStatementData` — frozen model with 8 fields: revenue, gross profit, operating
  income, net income, EPS, diluted EPS, R&D expense, report period
- `BalanceSheetData` — frozen model with 8 fields: total assets, total liabilities,
  shareholders equity, total debt, cash and equivalents, current assets, current liabilities,
  report period
- `FinancialDatasetsPackage` — frozen aggregate: ticker, metrics, income statement, balance
  sheet, fetched_at
- All models: `math.isfinite()` validators on floats, UTC validator on datetime

#### FR-2: Service Layer
- `FinancialDatasetsService` class with DI constructor: `config`, `cache`, `limiter`
- Single `httpx.AsyncClient` with `base_url` and `X-API-KEY` header
- 3 endpoint methods:
  - `fetch_financial_metrics(ticker)` — `GET /financial-metrics?ticker=X&period=ttm&limit=1`
  - `fetch_income_statement(ticker)` — `GET /financials/income-statements?ticker=X&period=ttm&limit=1`
  - `fetch_balance_sheet(ticker)` — `GET /financials/balance-sheets?ticker=X&period=quarterly&limit=1`
- `fetch_package(ticker)` — parallel gather of all 3, returns `FinancialDatasetsPackage`
- Never-raises contract: all methods return `None` on any error
- Two-tier caching with configurable TTL (default 1 hour)

#### FR-3: Configuration
- `FinancialDatasetsConfig(BaseModel)` nested in `AppSettings`
- Fields: `enabled` (bool), `api_key` (str | None), `base_url` (str),
  `request_timeout` (float), `cache_ttl` (int)
- Env var: `ARENA_FINANCIAL_DATASETS__API_KEY` via pydantic-settings nested delimiter

#### FR-4: MarketContext Extension
- 16 new optional fields on `MarketContext` with `fd_` prefix:
  - Income: `fd_revenue`, `fd_net_income`, `fd_operating_income`, `fd_eps`
  - Margins: `fd_gross_margin`, `fd_operating_margin`, `fd_net_margin`
  - Balance sheet: `fd_total_debt`, `fd_cash_and_equivalents`, `fd_total_assets`,
    `fd_current_ratio`
  - Growth/valuation: `fd_revenue_growth`, `fd_earnings_growth`, `fd_ev_to_ebitda`,
    `fd_free_cash_flow_yield`, `fd_return_on_equity`
- `financial_datasets_ratio()` method measuring field coverage (0.0-1.0)
- Overlapping fields (`pe_ratio`, `peg_ratio`, `price_to_book`, `debt_to_equity`,
  `revenue_growth`, `profit_margin`) populated with FD > OpenBB > None priority

#### FR-5: Context Rendering
- 3 new sections in `render_fundamental_context()`:
  1. "## Income Statement (TTM)" — revenue (formatted $X.XB), net income, operating income,
     EPS, margins
  2. "## Balance Sheet" — total debt, cash, total assets, current ratio
  3. "## Growth & Valuation" — revenue growth, earnings growth, EV/EBITDA, FCF yield, ROE
- Same 3 sections in `render_context_block()` (general agent context)
- Each section only rendered when at least one field is non-None

#### FR-6: Fundamental Agent Prompt Update
- Bump FUNDAMENTAL_SYSTEM_PROMPT to VERSION v3.0
- Add 3 new analysis requirements:
  - Financial health analysis (debt, cash position, current ratio)
  - Valuation depth (EV/EBITDA, FCF yield, P/E vs earnings growth)
  - Growth trajectory (revenue growth vs earnings growth, margin trends)
- Add interpretation rules (high D/E + low current ratio = risk, revenue growth + margin
  expansion = tailwind, PEG > 2.0 = overvalued relative to growth)

#### FR-7: Integration Wiring
- `build_market_context()` — new `fd_package` parameter, maps FD fields to MarketContext
- `run_debate()` — new `fd_package` parameter, passes through to build_market_context
- CLI debate command — create service, fetch package, pass to run_debate
- API lifespan — create service on startup, close on shutdown
- API debate routes — fetch package before run_debate calls

#### FR-8: Health Check
- `check_financial_datasets()` in HealthService — GET with API key, return `HealthStatus`
- Added to `check_all()` gather list when config enabled

### Non-Functional Requirements

#### NFR-1: Performance
- Maximum 3 API calls per ticker per debate (metrics + income + balance sheet in parallel)
- Cache TTL of 1 hour means repeated debates for the same ticker don't re-fetch
- Total FD fetch adds < 2 seconds to debate flow (parallel with other enrichment)
- Prompt token increase: ~200-300 tokens for 3 new context sections (within 8192 budget)

#### NFR-2: Reliability
- Never-raises pattern: API failures degrade gracefully to existing data sources
- `asyncio.wait_for(timeout)` on every HTTP call — no unbounded waits
- `asyncio.gather(return_exceptions=True)` in fetch_package — partial failures isolated

#### NFR-3: Security
- API key stored in environment variable, never in code or config files
- Key accessed via `pydantic-settings` `SecretStr | None` or `str | None` with env binding
- No API key logged at any level

#### NFR-4: Testability
- All HTTP calls mockable via httpx mock/respx
- `TestModel` override pattern maintained for agent tests
- No real API calls in unit test suite

## Success Criteria

| Metric | Target |
|--------|--------|
| Fundamental agent context coverage | > 80% of fields populated (vs ~30% without OpenBB) |
| `key_fundamental_factors` entries citing financial data | >= 2 per debate (currently ~0 without OpenBB) |
| API call latency (p95) | < 2 seconds for full package |
| Test coverage | >= 42 new tests passing |
| Zero regressions | All existing ~4,200 tests pass |
| Health check | Financial Datasets row appears in `options-arena health` |

## Constraints & Assumptions

### Constraints
- **API rate limits**: financialdatasets.ai has rate limits (exact TPS unknown). Mitigated
  by 1-hour cache TTL and rate limiter integration.
- **Debate-only**: FD is called only during debates (1 ticker at a time), NOT during scan
  pipeline (too expensive for 500 tickers). Scan uses existing indicators only.
- **No new Python dependencies**: Uses existing `httpx` for HTTP calls.

### Assumptions
- User has a valid financialdatasets.ai API key (free tier available)
- API response shapes match verified MCP tool responses (tested with AAPL live data)
- API provides data for all major U.S. equities (verified for S&P 500 tickers)

## Out of Scope

- **Cash flow statement endpoint**: FCF data already available via financial metrics
  endpoint (`free_cash_flow_per_share`, `free_cash_flow_yield`). Separate call unnecessary.
- **SEC filings text analysis**: `getFilingItems` provides 10-K/10-Q sections but parsing
  multi-page text is a separate feature.
- **News from FD**: `getNews` available but OpenBB already provides news sentiment. No
  duplication needed.
- **Segmented revenue**: `getSegmentedRevenues` is interesting but adds complexity without
  clear options analysis value.
- **Historical financial trends**: Multi-period comparison (e.g., 4 quarters of income
  statements) would require prompt redesign. Single TTM snapshot is sufficient for v1.
- **Replacing OpenBB entirely**: OpenBB still needed for unusual flow and news sentiment.
  FD supplements/replaces only the fundamental metrics portion.
- **Scan pipeline integration**: Too expensive for batch use. Debate-only.

## Dependencies

### External
- financialdatasets.ai REST API (https://api.financialdatasets.ai)
- API key from https://financialdatasets.ai

### Internal
- `httpx` (already in project)
- `ServiceCache` and `RateLimiter` (existing infrastructure)
- `OpenBBService` pattern (template for implementation)

## Implementation Waves

```
Wave 1 (foundation) ──── Models + Config (no deps)
Wave 2 (service)    ──── FinancialDatasetsService (depends on Wave 1)
Wave 3 (context)    ──── MarketContext extension (depends on Wave 1, parallel with Wave 2)
Wave 4 (prompts)    ──── Context rendering + agent prompt (depends on Wave 3)
Wave 5 (wiring)     ──── CLI, API, orchestrator integration (depends on Waves 2, 3, 4)
Wave 6 (health)     ──── Health check (depends on Wave 2)
Wave 7 (tests)      ──── ~42 tests across 5 files (depends on all waves)
```

## Files Affected

| File | Action |
|------|--------|
| `src/options_arena/models/financial_datasets.py` | **NEW** — 4 frozen Pydantic models |
| `src/options_arena/services/financial_datasets.py` | **NEW** — API service |
| `src/options_arena/models/config.py` | ADD `FinancialDatasetsConfig` + AppSettings field |
| `src/options_arena/models/analysis.py` | ADD 16 fields to MarketContext |
| `src/options_arena/models/__init__.py` | ADD re-exports |
| `src/options_arena/services/__init__.py` | ADD re-export |
| `src/options_arena/agents/_parsing.py` | EXTEND render functions (3 new sections) |
| `src/options_arena/agents/fundamental_agent.py` | UPDATE prompt to v3.0 |
| `src/options_arena/agents/orchestrator.py` | ADD `fd_package` param to 2 functions |
| `src/options_arena/cli/commands.py` | ADD service creation + fetch |
| `src/options_arena/api/app.py` | ADD service to lifespan |
| `src/options_arena/api/routes/debate.py` | ADD FD fetch in handlers |
| `src/options_arena/services/health.py` | ADD health check |
| `tests/unit/models/test_financial_datasets.py` | **NEW** — ~15 tests |
| `tests/unit/services/test_financial_datasets.py` | **NEW** — ~15 tests |
| 3 existing test files | EXTEND — ~12 tests |

## API Reference (Verified via MCP)

### Endpoints (3 calls per ticker)

| Endpoint | Path | Wrapper Key | Key Fields |
|----------|------|-------------|------------|
| Financial Metrics | `/financial-metrics?ticker=X&period=ttm&limit=1` | `"financial_metrics"` | P/E, P/B, PEG, D/E, margins, growth, EPS, FCF yield, ROE |
| Income Statement | `/financials/income-statements?ticker=X&period=ttm&limit=1` | `"income_statements"` | revenue, gross profit, operating income, net income, EPS, R&D |
| Balance Sheet | `/financials/balance-sheets?ticker=X&period=quarterly&limit=1` | `"balance_sheets"` | assets, liabilities, equity, debt, cash, current assets/liabilities |

### Authentication
- Header: `X-API-KEY: <key>`
- Env var: `ARENA_FINANCIAL_DATASETS__API_KEY`

### Verified Response Examples (AAPL, live MCP call)

**Financial Metrics**: `price_to_earnings_ratio: 34.3`, `price_to_book_ratio: 45.8`,
`peg_ratio: 1.78`, `debt_to_equity: 3.30`, `gross_margin: 0.482`,
`operating_margin: 0.355`, `net_margin: 0.293`, `revenue_growth: 0.403`,
`earnings_growth: 0.533`, `current_ratio: 0.974`, `free_cash_flow_yield: 0.013`

**Income Statement**: `revenue: 435,617,000,000`, `gross_profit: 206,157,000,000`,
`operating_income: 141,070,000,000`, `net_income: 117,777,000,000`, `eps: 7.92`

**Balance Sheet**: `total_assets: 379,297,000,000`, `total_debt: 90,509,000,000`,
`cash: 45,317,000,000`, `equity: 88,190,000,000`, `current_ratio: 0.974`
