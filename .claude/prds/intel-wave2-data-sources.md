---
name: intel-wave2-data-sources
description: Five new external data source services — GDELT, EIA, BLS, GSCPI, Treasury — plus FRED credit spread extension
status: backlog
created: 2026-03-24T15:48:29Z
effort: L
---

# PRD: intel-wave2-data-sources

## Executive Summary

Implement 5 new async service classes that fetch real-time intelligence data from free public APIs (GDELT global news, EIA energy prices, BLS labor statistics, NY Fed supply chain pressure, US Treasury fiscal data) plus extend the existing FredService with credit spread data. Each service follows the established `ServiceBase[ConfigT]` pattern with httpx, caching, rate limiting, and never-raises contracts.

## Problem Statement

### What problem are we solving?

Options Arena's external data is limited to yfinance (market/options data) and FRED (8 macro series). To build cross-domain intelligence (Wave 3+), we need structured data from economic, energy, labor, supply chain, and news event sources. These data sources are all free, well-documented, and update frequently enough to be useful for options trading context.

### Why is this important now?

Wave 2 depends on Wave 1 (models). Waves 3-7 depend on Wave 2 (data sources feed into the delta engine, intelligence collector, and desk agent). This is the data layer that powers everything.

## Requirements

### Functional Requirements

#### FR-1: GDELT Service (`services/gdelt.py`)

- **API**: `https://api.gdeltproject.org/api/v2/doc/doc` (DOC 2.0)
- **Auth**: None required
- **Rate limit**: 1 request per 5 seconds — use dedicated semaphore
- **Methods**:
  - `fetch_news_snapshot(query: str) -> GdeltSnapshot | None` — search recent global articles
  - `fetch_ticker_news(ticker: str, company_name: str) -> GdeltSnapshot | None` — ticker-specific news
- **Category classification**: keyword matching on article titles → GdeltCategory enum
- **Cache**: key `gdelt:{query_hash}`, TTL 900s (15 min, matches GDELT update frequency)
- **Inherits**: `ServiceBase[GdeltConfig]`
- **Returns**: `GdeltSnapshot` frozen model or None

#### FR-2: EIA Service (`services/eia.py`)

- **API**: `https://api.eia.gov/v2/{path}` (v2 REST)
- **Auth**: Free API key required (set via `ARENA_EIA__API_KEY`)
- **Methods**:
  - `fetch_energy_snapshot() -> EnergySnapshot | None`
- **Series** (fetched in parallel via `asyncio.gather`):
  - WTI crude (facets: series=RWTC, path=/petroleum/pri/spt/data/)
  - Brent crude (facets: series=RBRTE)
  - Natural gas Henry Hub (facets: series=RNGWHHD, path=/natural-gas/pri/fut/data/)
  - Crude inventories (facets: series=WCESTUS1, path=/petroleum/stoc/wstk/data/)
- **Signal generation**:
  - `PRICE_SPIKE`: WTI daily change >5%
  - `INVENTORY_SURPRISE`: WoW crude inventory change >5M bbl
  - `SPREAD_ANOMALY`: Brent-WTI spread >$10 or <-$2
- **Guard**: Returns None if `api_key is None`
- **Cache**: key `eia:snapshot`, TTL 3600s

#### FR-3: BLS Service (`services/bls.py`)

- **API**: `POST https://api.bls.gov/publicAPI/v1/timeseries/data/` (v1, no auth; v2 with optional key)
- **Methods**:
  - `fetch_labor_snapshot() -> LaborSnapshot | None`
- **Series** (single POST batch for all 5):
  - CPI-U All Items (CUUR0000SA0)
  - Core CPI ex Food & Energy (CUUR0000SA0L1E)
  - Unemployment Rate (LNS14000000)
  - Nonfarm Payrolls thousands (CES0000000001)
  - PPI Final Demand (WPUFD49104)
- **MoM change**: `(latest - previous) / previous * 100` when both periods available
- **Note**: CPI/Unemployment overlap with FRED. BLS adds NFP + PPI + MoM deltas. No dedup needed — IntelligenceSnapshot carries both sources.
- **Cache**: key `bls:labor`, TTL 86400s (monthly data)

#### FR-4: GSCPI Service (`services/gscpi.py`)

- **Source**: CSV download from `https://www.newyorkfed.org/medialibrary/research/interactives/data/gscpi/gscpi_interactive_data.csv`
- **Auth**: None
- **Methods**:
  - `fetch_supply_chain_snapshot() -> SupplyChainSnapshot | None`
- **Parsing**: stdlib `csv` module (NOT pandas — services layer). Wide-format CSV, extract last non-empty numeric column per row for latest vintage estimate.
- **Classification**: >1.0 std dev → ELEVATED, <-1.0 → LOOSE, else NORMAL
- **Trend**: Compare last 3 months — rising if monotonically increasing, falling if decreasing, else NEUTRAL
- **Cache**: key `gscpi:snapshot`, TTL 86400s

#### FR-5: Treasury Fiscal Service (`services/treasury_fiscal.py`)

- **API**: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/` (REST, no auth)
- **Methods**:
  - `fetch_fiscal_snapshot() -> FiscalSnapshot | None`
- **Endpoints** (fetched in parallel):
  - Debt to Penny: `v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1`
  - Average Interest Rates: `v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=1`
- **Cache**: key `treasury:fiscal`, TTL 86400s

#### FR-6: Extend FredService for Credit Spreads

In existing `src/options_arena/services/fred.py`:
- Add `BAMLH0A0HYM2` (ICE BofA High Yield OAS) to `_MACRO_SERIES` registry
- TTL: 24h, transform: PASSTHROUGH (value is already in basis points)
- Add method `fetch_credit_spread() -> float | None`
- This enables the delta engine to track credit stress

### Non-Functional Requirements

- All services inherit `ServiceBase[ConfigT]`
- All services follow never-raises contract (catch all, log WARNING, return None)
- httpx.AsyncClient created in `__init__`, closed in `close()`
- Timeouts via `asyncio.wait_for(coro, timeout=config.request_timeout)`
- Batch via `asyncio.gather(*tasks, return_exceptions=True)`
- All return frozen Pydantic models, never raw dicts
- No new dependencies beyond httpx (already in stack)
- Windows compatible (no Unix-only deps)

## Success Criteria

- Each service has unit tests with mocked httpx responses
- Never-raises verified: injecting exceptions → returns None, logs WARNING
- Cache hit/miss tested
- `uv run mypy src/ --strict` passes
- `uv run pytest tests/unit/services/test_gdelt.py test_eia.py test_bls.py test_gscpi.py test_treasury_fiscal.py -v` all pass
- Manual smoke test: with real API keys, each service returns valid data

## Out of Scope

- Intelligence orchestrator (Wave 3)
- Delta engine (Wave 3)
- SQLite persistence (Wave 3)
- Alert system (Wave 4)
- Agent integration (Wave 5)

## Dependencies

- **Wave 1** (intel-wave1-foundation) — models and config classes must exist

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/gdelt.py` | **Create** |
| `src/options_arena/services/eia.py` | **Create** |
| `src/options_arena/services/bls.py` | **Create** |
| `src/options_arena/services/gscpi.py` | **Create** |
| `src/options_arena/services/treasury_fiscal.py` | **Create** |
| `src/options_arena/services/fred.py` | Modify — add BAMLH0A0HYM2 series |
| `src/options_arena/services/__init__.py` | Modify — re-export new services |
| `tests/unit/services/test_gdelt.py` | **Create** |
| `tests/unit/services/test_eia.py` | **Create** |
| `tests/unit/services/test_bls.py` | **Create** |
| `tests/unit/services/test_gscpi.py` | **Create** |
| `tests/unit/services/test_treasury_fiscal.py` | **Create** |
