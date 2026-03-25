---
name: intel-wave2-data-sources
description: Seven new external data source services — GDELT, EIA, BLS, GSCPI, Treasury, Comtrade, USASpending — plus expanded FRED (8→20 series)
status: backlog
created: 2026-03-24T15:48:29Z
updated: 2026-03-25T13:41:06Z
effort: L
---

# PRD: intel-wave2-data-sources

## Executive Summary

Implement 7 new async service classes that fetch real-time intelligence data from free public APIs (GDELT global news, EIA energy prices, BLS labor statistics, NY Fed supply chain pressure, US Treasury fiscal data, UN Comtrade trade flows, USASpending defense contracts) plus expand the existing FredService from 8 to 20 macro series. Each service follows the established `ServiceBase[ConfigT]` pattern with httpx, caching, rate limiting, and never-raises contracts. Based on analysis of the [Crucix](https://github.com/calesthio/Crucix) intelligence platform's 30-source architecture, these 7+1 represent the highest-alpha sources for options trading decisions.

## Problem Statement

### What problem are we solving?

Options Arena's external data is limited to yfinance (market/options data) and FRED (8 macro series). To build cross-domain intelligence (Wave 3+), we need structured data from economic, energy, labor, supply chain, fiscal, trade, defense, and news event sources. These data sources are all free, well-documented, and update frequently enough to be useful for options trading context.

### Why is this important now?

Wave 2 depends on Wave 1 (models). Waves 3-7 depend on Wave 2 (data sources feed into the delta engine, intelligence collector, and desk agent). This is the data layer that powers everything.

### Crucix Reference

This PRD is informed by analysis of [Crucix](https://github.com/calesthio/Crucix) (6,800 stars, AGPL-3.0), which implements 30 intelligence sources across 6 tiers. Of those 30 sources, alpha ranking for options trading identified:

- **Tier 1 (direct alpha)**: FRED, EIA, BLS, GDELT, GSCPI, Treasury — all included
- **Tier 2 (indirect alpha)**: Comtrade, USASpending — added in this refinement; ACLED dropped (GDELT covers conflict, OAuth2 complexity not justified)
- **Tier 3-4 (low/no alpha)**: 14 sources (satellite fire, radiation, HF radio, ADS-B, Bluesky, patents, etc.) — skipped, no systematic options signal

Crucix's delta engine architecture (`lib/delta/engine.mjs`) confirms Wave 3's design — configurable percent thresholds, severity tiers, risk direction assessment.

## Requirements

### Functional Requirements

#### FR-1: GDELT Service (`services/gdelt.py`)

- **API**: `https://api.gdeltproject.org/api/v2/doc/doc` (DOC 2.0)
- **Auth**: None required
- **Rate limit**: 1 request per 5 seconds — use `RateLimiter(rps=0.2)` (Crucix uses 5.5s delay; project pattern is token-bucket, not bare semaphore)
- **Methods**:
  - `fetch_news_snapshot(query: str) -> GdeltSnapshot | None` — search recent global articles
  - `fetch_ticker_news(ticker: str, company_name: str) -> GdeltSnapshot | None` — ticker-specific news (Options Arena addition, not in Crucix)
- **Category classification**: keyword matching on article titles → GdeltCategory enum (conflict, economy, health, crisis, other — matches Crucix categories)
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
- **Parsing**: stdlib `csv` module (preferred for simplicity over pandas, though `services/CLAUDE.md` permits pandas for CSV). Wide-format CSV, extract last non-empty numeric column per row for latest vintage estimate.
- **Classification**: >1.0 std dev → ELEVATED, <-1.0 → LOOSE, else NORMAL (matches Crucix thresholds)
- **Trend**: Compare last 3 months — rising if monotonically increasing, falling if decreasing, else NEUTRAL
- **Cache**: key `gscpi:snapshot`, TTL 86400s

#### FR-5: Treasury Fiscal Service (`services/treasury_fiscal.py`)

- **API**: `https://api.fiscaldata.treasury.gov/services/api/fiscal_service/` (REST, no auth)
- **Methods**:
  - `fetch_fiscal_snapshot() -> FiscalSnapshot | None`
- **Endpoints** (fetched in parallel):
  - Debt to Penny: `v2/accounting/od/debt_to_penny?sort=-record_date&page[size]=1`
  - Average Interest Rates: `v2/accounting/od/avg_interest_rates?sort=-record_date&page[size]=1`
  - **Daily Treasury Statement**: `v1/accounting/dts/dts_table_1?sort=-record_date&page[size]=1` — daily cash inflows/outflows (added from Crucix reference; not in original PRD)
- **Cache**: key `treasury:fiscal`, TTL 86400s

#### FR-6: Extend FredService — Expand from 8 to 20 Series

In existing `src/options_arena/services/fred.py`, expand `_MACRO_SERIES` registry with 12 new series. Also extend `MacroContext` in `models/macro.py` with corresponding fields.

**New series (12 additions):**

| Series ID | Display Name | TTL (hours) | Transform | Alpha Rationale |
|-----------|-------------|-------------|-----------|-----------------|
| `BAMLH0A0HYM2` | HY Credit Spread (OAS) | 24 | PASSTHROUGH | Credit stress → IV expansion signal |
| `ICSA` | Initial Jobless Claims | 24 | PASSTHROUGH | Weekly leading indicator, moves markets |
| `M2SL` | M2 Money Supply | 168 | YOY_PCT_CHANGE | Liquidity proxy |
| `WALCL` | Fed Balance Sheet | 168 | PASSTHROUGH | QE/QT signal (trillions USD) |
| `GOLDAMGBD228NLBM` | Gold Price (USD/oz) | 24 | PASSTHROUGH | Risk-off proxy |
| `DTWEXBGS` | USD Trade-Weighted Index | 24 | PASSTHROUGH | Dollar strength → multinational earnings |
| `MORTGAGE30US` | 30Y Mortgage Rate | 168 | PCT_TO_DECIMAL | Housing/REIT sector impact |
| `MICH` | Michigan Inflation Expectations | 168 | PASSTHROUGH | Forward-looking consumer sentiment |
| `DGS30` | 30-Year Treasury | 24 | PCT_TO_DECIMAL | Long end of yield curve |
| `PCEPILFE` | Core PCE | 168 | YOY_PCT_CHANGE | Fed's preferred inflation gauge |
| `PCEPI` | PCE Price Index | 168 | YOY_PCT_CHANGE | Headline PCE |
| `DEXUSEU` | USD/EUR Exchange Rate | 24 | PASSTHROUGH | FX risk for multinationals |

**Existing 8 series (unchanged):** DGS10, DGS2, T10Y2Y, FEDFUNDS, VIXCLS, CPIAUCSL, INDPRO, UNRATE.

**Required changes:**
- `services/fred.py`: Add 12 entries to `_MACRO_SERIES` list and `_SERIES_TO_FIELD` mapping
- `models/macro.py`: Add 12 `float | None` fields to `MacroContext`. **Critical**: all 12 new field names MUST be appended to the `_MACRO_FIELDS` tuple — the `isfinite()` validator fires only on fields listed there. Each new field must have a docstring specifying units and example values (matching existing field pattern).
- Add convenience method `fetch_credit_spread() -> float | None` for delta engine consumption

#### FR-7: Comtrade Service (`services/comtrade.py`)

- **API**: `https://comtradeapi.un.org/data/v1/get/C/M` (monthly goods, v1 REST)
- **Auth**: Free API key required (set via `ARENA_COMTRADE__API_KEY`). Free tier allows 500 requests/day — sufficient for monthly batch pulls.
- **Methods**:
  - `fetch_trade_snapshot() -> TradeSnapshot | None`
- **Commodities** (HS codes, one API call per commodity group using heading-level codes):
  - Crude petroleum (HS 2709)
  - Natural gas (HS 2711)
  - Gold (HS 7108)
  - Semiconductors (HS 8541 + HS 8542 — two separate codes, can be combined in one query via comma-separated `cmdCode`)
  - Arms & ammunition (HS 93 — single heading-level query covers 9301-9307, avoids 7 individual calls against 500/day free-tier budget)
- **Total API calls per snapshot**: ~5 queries (well within 500/day free tier)
- **Focus**: US-China bilateral flows + global totals for each commodity
- **Signal**: 3-month trend direction via comparison (same pattern as GSCPI)
- **Guard**: Returns None if `api_key is None`
- **Cache**: key `comtrade:snapshot`, TTL 86400s (monthly data, 1-2 month publication lag)
- **Options alpha**: Leading indicator for semiconductor sector IV (NVDA, AMD, INTC, SOXX) and energy sector dynamics via US-China trade flow trends

#### FR-8: USASpending Service (`services/usaspending.py`)

- **API**: `https://api.usaspending.gov/api/v2/search/spending_by_award/`
- **Auth**: None required
- **Rate limit**: No documented rate limit; use conservative `RateLimiter(rps=1.0)` as courtesy
- **Methods**:
  - `fetch_defense_snapshot() -> DefenseSnapshot | None`
- **Filters**: Agency = Department of Defense, lookback = 14 days (configurable), sorted by amount descending, top 50 awards
- **Signal**: Aggregated value and top recipients → defense sector company signals (RTX, LMT, NOC, L3Harris)
- **Cache**: key `usaspending:defense`, TTL 86400s
- **Options alpha**: Earnings surprise proxy for defense contractors; abnormally large contracts → short-term sector tailwinds

### Non-Functional Requirements

- All services inherit `ServiceBase[ConfigT]`
- All services follow never-raises contract (catch all, log WARNING, return None)
- httpx.AsyncClient created in `__init__`, closed in `close()`
- Timeouts via `asyncio.wait_for(coro, timeout=config.request_timeout)`
- Batch via `asyncio.gather(*tasks, return_exceptions=True)`
- All return frozen Pydantic models, never raw dicts
- No new dependencies beyond httpx (already in stack)
- Windows compatible (no Unix-only deps)

## Wave 1 Impact (Must Update Before Wave 2)

The following Wave 1 (`intel-wave1-foundation`) PRD must be amended to include these shapes before Wave 2 can start. These are NOT forward instructions — they are blocking dependencies that must be resolved in Wave 1's scope.

### New Models to Add to Wave 1 `intelligence_sources.py`

| Model | Fields | Notes |
|-------|--------|-------|
| `TradeSeries` | commodity (StrategicCommodity), reporter_country (str), partner_country (str\|None), trade_value (float), period (str), flow_direction (TradeFlowDirection) | Single Comtrade series reading. `trade_value` uses `float` (not `Decimal`) — these are aggregate trade statistics, not transaction prices. Consistent with Wave 1's exemption: "No Decimal fields expected in intelligence models." |
| `TradeSnapshot` | series (list[TradeSeries]), us_china_semiconductor (float\|None), us_china_energy (float\|None), fetched_at (datetime, UTC) | Frozen, `completeness_ratio()` |
| `DefenseContract` | recipient (str), amount (float), description (str), agency (str), award_date (date) | Single USASpending award. `amount` uses `float` — aggregate government contract values, not tradeable prices. Same exemption as above. |
| `DefenseSnapshot` | contracts (list[DefenseContract]), total_value (float), top_agencies (list[str]), fetched_at (datetime, UTC) | Frozen, `completeness_ratio()` |
| `TreasuryStatement` | deposits (float), withdrawals (float), closing_balance (float), record_date (date) | Daily Treasury Statement cash flow. All values use `float` (government accounting aggregates). |

### Model Modifications to Add to Wave 1

| File | Change |
|------|--------|
| `models/enums.py` | Add `TradeFlowDirection` (import_flow, export_flow) and `StrategicCommodity` (crude_petroleum, natural_gas, semiconductors, gold, arms). Note: renamed from `TradeFlowType` to `TradeFlowDirection` — "direction" is semantically correct (import vs export), avoiding confusion with `bilateral` which is a relationship, not a flow direction. US-China bilateral filtering is handled by the `partner_country` field on `TradeSeries`. |
| `models/intelligence_sources.py` | Add `TradeSeries`, `TradeSnapshot`, `DefenseContract`, `DefenseSnapshot`, `TreasuryStatement` |
| `models/intelligence_sources.py` | Define `FiscalSnapshot` with `daily_statement: TreasuryStatement | None = None` field from the start (schema inclusion, not a post-hoc migration) |
| `models/intelligence_sources.py` | Ensure `EnergySnapshot` and `LaborSnapshot` both include `fetched_at: datetime (UTC)` — required for cache staleness checks and delta engine. All snapshot models must have `fetched_at`. |
| `models/intelligence.py` | Define `IntelligenceSnapshot` with all 8 source fields from the start: gdelt, energy, labor, supply_chain, fiscal, macro, **trade**, **defense** (all `| None`). **Critical**: `completeness_ratio()` must use `len(_SOURCE_FIELDS)` tuple, not a hardcoded literal. This prevents breakage when fields are added/removed. |
| `models/config.py` | Add `ComtradeConfig`, `UsaSpendingConfig`; wire into `AppSettings` |

**Note**: `models/macro.py` expansion (12 new fields) is owned by **Wave 2 FR-6**, not Wave 1. Wave 1 ships with the existing 8-field MacroContext unchanged. The FRED series expansion and corresponding MacroContext fields are Wave 2 work.

### New Config Classes to Add to Wave 1

| Config | Key Fields |
|--------|------------|
| `ComtradeConfig(FiniteFieldsMixin)` | enabled (bool=True), api_key (SecretStr\|None), request_timeout (float=15.0), cache_ttl (int=86400) |
| `UsaSpendingConfig(FiniteFieldsMixin)` | enabled (bool=True), request_timeout (float=10.0), cache_ttl (int=86400), lookback_days (int=14) |

Note: all new service configs inherit `ServiceBase[XxxConfig]` (e.g., `ServiceBase[ComtradeConfig]`), NOT `ServiceBase[ServiceConfig]`. Each service has its own dedicated config type, matching the `FinancialDatasetsService` pattern rather than the `FredService` pattern.

Wire into `AppSettings`:
```python
comtrade: ComtradeConfig = ComtradeConfig()
usaspending: UsaSpendingConfig = UsaSpendingConfig()
```

Env override examples:
- `ARENA_COMTRADE__API_KEY=your_key` → `settings.comtrade.api_key`
- `ARENA_USASPENDING__LOOKBACK_DAYS=30` → `settings.usaspending.lookback_days`

## Success Criteria

- Each service has unit tests with mocked httpx responses
- Never-raises verified: injecting exceptions → returns None, logs WARNING
- Cache hit/miss tested
- `uv run mypy src/ --strict` passes
- `uv run ruff check . --fix && uv run ruff format .` passes
- All 7 new test files pass: `uv run pytest tests/unit/services/test_gdelt.py test_eia.py test_bls.py test_gscpi.py test_treasury_fiscal.py test_comtrade.py test_usaspending.py -v`
- Extended FRED series: `uv run pytest tests/unit/services/test_fred.py -v` passes
- Extended MacroContext: `uv run pytest tests/unit/models/test_macro.py -v` passes
- Manual smoke test: with real API keys, each service returns valid data

## Out of Scope

- Intelligence orchestrator (Wave 3)
- Delta engine (Wave 3)
- SQLite persistence (Wave 3)
- Alert system (Wave 4)
- Agent integration (Wave 5)
- ACLED conflict events (dropped — GDELT covers conflict news, ACLED OAuth2 adds complexity for marginal alpha gain)
- Social media sources: Reddit, Telegram, Bluesky (Wave 8)
- Geopolitical sensors: satellite fire (FIRMS), military aircraft (ADS-B), ship tracking (AIS), radiation (Safecast/EPA) — no systematic options alpha
- Infrastructure sensors: Cloudflare Radar, KiwiSDR, CISA KEV — no options alpha
- Patents, Space/CelesTrak — no options alpha

## Dependencies

- **Wave 1** (intel-wave1-foundation) — models and config classes must exist. Wave 1 PRD must be amended with the shapes listed in "Wave 1 Impact" above **before** Wave 1 implementation begins. This is a blocking dependency, not a deferred update.

## Files to Create/Modify

| File | Action |
|------|--------|
| `src/options_arena/services/gdelt.py` | **Create** |
| `src/options_arena/services/eia.py` | **Create** |
| `src/options_arena/services/bls.py` | **Create** |
| `src/options_arena/services/gscpi.py` | **Create** |
| `src/options_arena/services/treasury_fiscal.py` | **Create** |
| `src/options_arena/services/comtrade.py` | **Create** |
| `src/options_arena/services/usaspending.py` | **Create** |
| `src/options_arena/services/fred.py` | Modify — add 12 FRED series + `fetch_credit_spread()` |
| `src/options_arena/services/__init__.py` | Modify — re-export new services |
| `src/options_arena/models/macro.py` | Modify — add 12 fields to MacroContext, extend `_MACRO_FIELDS` |
| `tests/unit/models/test_macro.py` | Modify — tests for 12 new MacroContext fields |
| `tests/unit/services/test_gdelt.py` | **Create** |
| `tests/unit/services/test_eia.py` | **Create** |
| `tests/unit/services/test_bls.py` | **Create** |
| `tests/unit/services/test_gscpi.py` | **Create** |
| `tests/unit/services/test_treasury_fiscal.py` | **Create** |
| `tests/unit/services/test_comtrade.py` | **Create** |
| `tests/unit/services/test_usaspending.py` | **Create** |
