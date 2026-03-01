---
name: ticker-universe-improve
description: Add sector/industry filtering and proper ETF preset to the ticker universe system
status: backlog
created: 2026-03-01T09:58:41Z
---

# PRD: ticker-universe-improve

## Executive Summary

Enhance the Options Arena ticker universe system with composable filtering capabilities. Users will be able to filter scan universes by GICS sector (via a new `--sector` flag) and scan a properly detected ETF universe (replacing the current stub). Both features will be available in the CLI and the Vue Web UI, enabling more targeted and efficient options analysis workflows.

## Problem Statement

The current universe system offers only two functional presets (`FULL` ~5,286 tickers, `SP500` ~500 tickers) with no way to narrow by sector or asset type. Users who want to analyze only Technology or Healthcare options must scan the entire S&P 500 and manually sift through results. The `ETFS` preset exists as an enum value but is a no-op that silently falls back to the full universe — misleading and useless.

**Why now**: The scan pipeline, scoring engine, and debate system are mature (v2.1.0). The bottleneck has shifted from "can we analyze options" to "can we quickly find the right options to analyze." Filtering is the highest-leverage improvement for daily workflow efficiency.

## User Stories

### US-1: Sector-Filtered Scan (CLI)

**As** an options trader focused on a specific sector,
**I want** to scan only tickers in that sector,
**So that** I get faster, more relevant results without noise from unrelated sectors.

**Acceptance Criteria:**
- `options-arena scan --sector technology` scans only Technology sector tickers
- Multiple sectors supported: `--sector technology --sector healthcare`
- `--sector` composes with `--preset`: `--preset sp500 --sector technology` scans S&P 500 Tech tickers only
- Invalid sector names produce a clear error listing valid options
- Scan output shows the active sector filter in the header

### US-2: Sector-Filtered Scan (Web UI)

**As** a web UI user,
**I want** to select one or more sectors from a dropdown before starting a scan,
**So that** I can target my analysis without using the CLI.

**Acceptance Criteria:**
- Scan page shows a multi-select sector filter (chips or dropdown)
- Selected sectors are passed to the scan API endpoint
- Scan results header reflects the active sector filter
- Default is "all sectors" (no filter)

### US-5: Sector Displayed in Scan Results

**As** an options trader reviewing scan results,
**I want** to see each ticker's GICS sector in the results table,
**So that** I can quickly identify sector concentration and diversify my analysis.

**Acceptance Criteria:**
- Scan results table shows a **Sector** column for each of the top 25 recommended tickers
- Sector is displayed as a colored chip/badge (e.g., "Information Technology", "Health Care")
- Tickers without sector data (non-S&P 500) show `"—"`
- Sector column is sortable and filterable
- Works in both fresh scans and when viewing historical scan results

### US-6: Company Name in Ticker Drawer

**As** a user who clicks on a ticker in the scan results,
**I want** to see the company's full name in the slide-in drawer,
**So that** I immediately know which company the ticker represents without needing to look it up.

**Acceptance Criteria:**
- Clicking a ticker row opens the TickerDrawer with the **company full name** displayed as a subtitle beneath the ticker symbol
- Company name comes from existing `TickerInfo.company_name` (yfinance data)
- If company name is unavailable, show `"—"` (not an empty space)
- No additional API call required — data is included in the scan score response

### US-3: ETF Universe Preset

**As** an options trader who trades ETF options,
**I want** a working `--preset etfs` that scans optionable ETFs,
**So that** I can analyze ETF options without wading through individual equities.

**Acceptance Criteria:**
- `options-arena scan --preset etfs` scans only ETFs detected from CBOE data
- ETF detection is programmatic (not a hardcoded list)
- The preset works in both CLI and Web UI
- `options-arena universe list --preset etfs` shows the detected ETF count
- `options-arena universe stats` includes ETF count alongside existing stats

### US-4: List Available Sectors

**As** a user unfamiliar with GICS sector names,
**I want** to see a list of valid sector values,
**So that** I know what to pass to `--sector`.

**Acceptance Criteria:**
- `options-arena universe sectors` (or similar subcommand) lists all available GICS sectors
- Each sector shows the count of tickers in the current universe
- Works offline if universe data is cached

## Requirements

### Functional Requirements

#### FR-1: Sector Filtering

- **Sector source**: GICS sectors from the existing Wikipedia S&P 500 data source (already fetched in Phase 1 of the pipeline)
- **Filter logic**: After universe tickers are assembled, filter to only those whose sector matches any of the provided sector values
- **Sector values**: Use the 11 standard GICS sectors as a `GICSSector(StrEnum)`. Values use canonical GICS names (which contain spaces: "Information Technology", "Health Care", etc.). StrEnum members use uppercase with underscores for Python identifiers:
  - `COMMUNICATION_SERVICES = "Communication Services"`
  - `CONSUMER_DISCRETIONARY = "Consumer Discretionary"`
  - `CONSUMER_STAPLES = "Consumer Staples"`
  - `ENERGY = "Energy"`
  - `FINANCIALS = "Financials"`
  - `HEALTH_CARE = "Health Care"`
  - `INDUSTRIALS = "Industrials"`
  - `INFORMATION_TECHNOLOGY = "Information Technology"`
  - `MATERIALS = "Materials"`
  - `REAL_ESTATE = "Real Estate"`
  - `UTILITIES = "Utilities"`
- **CLI alias mapping**: Since canonical GICS names contain spaces, CLI users need slug-style aliases. Maintain a `SECTOR_ALIASES: dict[str, GICSSector]` mapping that maps lowercase/hyphenated/underscored variants to canonical enum values (e.g., `"technology"` → `INFORMATION_TECHNOLOGY`, `"health-care"` → `HEALTH_CARE`, `"consumer-discretionary"` → `CONSUMER_DISCRETIONARY`). This mapping is used by both CLI normalization and the API `mode='before'` validator.
- **Composition**: `--sector` narrows within the current preset. `--preset full --sector technology` filters the full CBOE universe to tickers that are also in S&P 500 Technology. `--preset sp500 --sector technology` filters S&P 500 to Technology only.
- **Note**: Sector data is only available for S&P 500 constituents (from Wikipedia). For the `FULL` preset, sector filtering effectively intersects with S&P 500 membership. This limitation should be documented clearly.
- **Multiple sectors**: OR logic — ticker matches if it belongs to any of the specified sectors
- **Case insensitivity**: Accept `technology`, `Technology`, `TECHNOLOGY`, `information-technology`, `information_technology` — normalize to the canonical GICS name. Implementation: add a `mode='before'` `field_validator` on `ScanConfig.sectors` (and/or `ScanRequest.sectors`) that normalizes input strings to canonical `GICSSector` values via a lookup mapping (e.g., `{"technology": GICSSector.INFORMATION_TECHNOLOGY, "info-tech": ...}`). CLI-level normalization alone is insufficient — the API layer must also normalize.

#### FR-2: ETF Detection and Preset

- **Detection approach**: Programmatic ETF identification from CBOE data. Investigate:
  1. CBOE CSV may have an asset type or product type column distinguishing ETFs from equities
  2. If not, use an external reference (e.g., a lightweight ETF list endpoint or heuristic based on known ETF issuers/patterns)
  3. Fallback: maintain a curated seed list of ~50 popular ETFs that auto-refreshes from a reliable source
- **Implementation**: `UniverseService.fetch_etf_tickers() -> list[str]` with same caching pattern (24h TTL)
- **Preset activation**: `ScanPreset.ETFS` routes to `fetch_etf_tickers()` instead of falling back to `FULL`
- **Universe stats**: `universe stats` and `universe list` support `--preset etfs`

#### FR-3: Enrich TickerScore with Sector and Company Name

The scan results table and ticker drawer need data that currently does not flow through the `TickerScore` model. Two new optional fields must be added to the pipeline:

- **`sector: GICSSector | None = None`** — GICS sector from the existing `SP500Constituent` data (Wikipedia). `None` for tickers not in S&P 500. Populated during Phase 1 universe assembly when the `sp500_sectors` mapping is already built.
- **`company_name: str | None = None`** — Full company name from `TickerInfo.company_name` (yfinance). `None` if ticker info fetch failed. Populated during Phase 2 when `fetch_ticker_info()` is already called for each ticker.

**Data flow**:
```
Phase 1: sp500_constituents → build dict[str, GICSSector] → attach to TickerScore.sector
Phase 2: fetch_ticker_info() → TickerScore.company_name = ticker_info.company_name
  → GET /api/scan/{id}/scores returns sector + company_name in each TickerScore
    → Frontend TickerScore interface gains sector: string | null, company_name: string | null
```

**Persistence**: Add `sector TEXT` and `company_name TEXT` columns to the `ticker_scores` table (new migration). Nullable — backward compatible with existing scan data.

#### FR-4: API Endpoint Changes

- **`POST /api/scans`**: Accept optional `sectors: list[GICSSector]` in request body (typed enum, not raw `str` — per project no-raw-strings rule; FastAPI auto-validates enum values and returns 422 on invalid sectors)
- **`GET /api/universe/sectors`**: New endpoint returning available sectors with ticker counts
- **`GET /api/universe/list`**: Add `preset=etfs` support
- **`GET /api/scan/{id}/scores`**: Response `TickerScore` objects now include `sector` and `company_name` fields (nullable, backward compatible — existing clients ignore unknown fields)

#### FR-5: Web UI Changes

- **Scan page**: Add a multi-select sector filter component (PrimeVue MultiSelect or Chips)
- **Scan page**: ETF preset option in the existing preset selector
- **Scan results table**: Add a **Sector** column after the Ticker column displaying `TickerScore.sector`. Use a colored chip/badge for the sector name. Show `"—"` for tickers without sector data. Column should be sortable and filterable.
- **Ticker drawer (slide-in)**: Display the **company full name** (`TickerScore.company_name`) as a subtitle beneath the ticker symbol in the drawer header. Show `"—"` if `company_name` is null. This provides immediate context without requiring a separate API call.
- **Universe page** (if exists): Show sector breakdown

### Non-Functional Requirements

- **Performance**: Sector filtering adds negligible overhead (in-memory set intersection on cached data)
- **Backward compatibility**: Existing `--preset sp500` and `--preset full` behavior unchanged when `--sector` is not provided
- **Test coverage**: Every new public method has unit tests. Pipeline integration tests cover sector + preset composition.
- **Type safety**: Sector values use a `GICSSector` StrEnum. No raw strings at module boundaries.

## Success Criteria

| Metric | Target |
|--------|--------|
| Sector-filtered scan works end-to-end (CLI + Web) | Pass |
| ETF preset returns >0 ETFs programmatically | Pass |
| `--sector` composes with all existing presets | Pass |
| Sector column visible in scan results table for top 25 tickers | Pass |
| Company name displayed in TickerDrawer header on ticker click | Pass |
| All new code passes `ruff check`, `mypy --strict`, `pytest` | Pass |
| No regression in existing 2,328+ tests | Pass |
| Sector filter visible and functional in Web UI | Pass |

## Constraints & Assumptions

- **Sector data limited to S&P 500**: Wikipedia only provides GICS sectors for S&P 500 constituents. Filtering the `FULL` universe by sector will implicitly intersect with S&P 500 membership. This is acceptable for v1 — a broader sector data source (e.g., financial data API) could be added later.
- **ETF detection accuracy**: Programmatic detection may not be 100% accurate. False positives (non-ETF classified as ETF) are tolerable; false negatives (missing popular ETFs) should be minimized.
- **No new external dependencies**: Prefer using existing data sources (CBOE, Wikipedia) or lightweight HTTP calls. No new paid APIs.
- **Windows compatibility**: All new code must work on Windows (no POSIX-only patterns).

## Out of Scope

- **Sub-industry filtering**: Only GICS sector level, not industry/sub-industry (Wikipedia doesn't provide sub-industry reliably)
- **Data source resilience**: No new fallback sources, schema drift detection, or universe size validation (explicitly deprioritized)
- **Universe versioning/snapshots**: No historical universe queries
- **Custom ticker list input**: No arbitrary CSV import or comma-separated ticker input (could be a separate PRD)
- **Watchlist-as-universe**: Scanning only watchlist tickers (could be a separate PRD)
- **Market cap filtering**: Classification exists but filtering by cap tier is not in scope

## Dependencies

- **Existing Wikipedia S&P 500 fetch**: Already provides GICS sector data — no new data source needed for sector filtering
- **Existing CBOE fetch**: ETF detection depends on CBOE CSV column analysis or an additional lightweight data source
- **PrimeVue MultiSelect component**: Already available in the frontend dependency tree
- **Models module**: New `GICSSector` StrEnum needed
- **Scan pipeline**: Phase 1 universe assembly needs sector filter injection point
- **API module**: New endpoint + request body changes

## Technical Notes

### Sector Filtering Architecture

```
CLI: --sector technology --sector healthcare
  → ScanConfig.sectors: list[GICSSector] = []
    → pipeline.Phase1: filter universe_tickers by sp500_sectors mapping
      → Only tickers where sp500_sectors[ticker] in config.sectors pass through
```

### ETF Detection Strategy

Investigate in order of preference:
1. **CBOE CSV analysis**: Check if the CSV has a column indicating product type (equity vs ETF)
2. **SEC EDGAR**: Free API for fund classification (CIK-based lookup)
3. **Known issuer prefixes**: ETFs from iShares, SPDR, Vanguard, Invesco have recognizable patterns
4. **Curated seed + validation**: Maintain a seed list, validate against CBOE optionable list

### Files Likely Modified

- `src/options_arena/models/enums.py` — `GICSSector` StrEnum
- `src/options_arena/models/config.py` — `ScanConfig.sectors` field
- `src/options_arena/models/scan.py` — `TickerScore`: add `sector: GICSSector | None = None` and `company_name: str | None = None` fields
- `src/options_arena/services/universe.py` — `fetch_etf_tickers()`, sector filtering helpers
- `src/options_arena/scan/pipeline.py` — Phase 1 sector filter injection + attach sector/company_name to TickerScore during pipeline
- `src/options_arena/data/repository.py` — persist and retrieve `sector` + `company_name` from `ticker_scores` table
- `data/migrations/` — new migration adding `sector TEXT` and `company_name TEXT` columns to `ticker_scores`
- `src/options_arena/cli/` — `--sector` flag on scan command. **Typer caveat**: multi-value enum options require `list[GICSSector]` annotation with `typer.Option([], "--sector", "-s")`. If Typer's CLI parser doesn't resolve lowercase `list` for multi-value options, fall back to `typing.List[GICSSector]` (Typer docs still show `typing.List` for this pattern). Verify during implementation.
- `src/options_arena/api/routes/` — new sector endpoints, scan request body
- `web/src/types/scan.ts` — `TickerScore` interface: add `sector: string | null` and `company_name: string | null`
- `web/src/pages/ScanResultsPage.vue` — add Sector column to DataTable (after Ticker column)
- `web/src/components/TickerDrawer.vue` — display `company_name` as subtitle in drawer header
