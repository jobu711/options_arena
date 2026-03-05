---
name: metadata-index
description: Persistent CBOE ticker metadata index for sector/industry/market-cap enrichment across the full optionable universe
status: planned
created: 2026-03-04T22:31:32Z
---

# PRD: metadata-index

## Executive Summary

Enrich all ~5,000 CBOE optionable tickers with GICS sector, industry group, and market cap tier metadata via a persistent SQLite index. Today only ~500 S&P 500 tickers have sector/industry data (from a GitHub CSV). The remaining ~4,500 tickers are invisible to every sector-based filter, making the `full` universe preset effectively useless for targeted scanning. This feature closes the metadata gap by caching yfinance classification data, enabling sector/industry/market-cap filtering across the entire optionable universe.

## Problem Statement

### What problem are we solving?

Options Arena's scan filtering (sectors, industry groups, market cap tiers) only works for S&P 500 constituents. The CBOE optionable universe is ~10x larger, but those tickers have zero classification metadata. Concrete failures today:

- `options-arena scan --preset full --sector technology` silently drops all non-S&P500 tech stocks (AMD, MRVL, PLTR, etc. if not in the index)
- `--industry-group semiconductors` excludes valid semiconductor companies outside S&P 500
- `--market-cap small` cannot pre-filter because market cap data is only fetched per-ticker in Phase 3 (after expensive OHLCV downloads)
- The `full` preset with any sector/industry filter produces the same results as `sp500` — users don't realize they're missing tickers

### Why is this important now?

This is a prerequisite for the planned **Scan Profiles** feature (saved strategy filter combinations). Profiles that specify sector/industry filters would be broken on the `full` universe without metadata coverage. Fixing the data foundation first ensures profiles deliver value across all presets.

### Root Cause

1. **CBOE CSV provides only ticker symbols** — no sector, industry, or fundamental data
2. **S&P 500 CSV provides GICS sector + sub-industry** — but only for ~500 constituents
3. **yfinance `Ticker.info` has sector and industry fields** — but this data is fetched in Phase 3 for top-N tickers only, and never persisted or mapped back to `TickerScore.sector` / `.industry_group`
4. **No persistent metadata cache** — every scan starts from scratch; enrichment data is lost

## User Stories

### US-1: Full-Universe Sector Scan
**As a** trader scanning the full CBOE universe,
**I want** sector filtering to include all optionable tickers (not just S&P 500),
**So that** I can discover opportunities in smaller companies within my target sector.

**Acceptance Criteria:**
- `options-arena scan --preset full --sector technology` returns tech tickers beyond S&P 500
- Coverage: >80% of CBOE tickers have a sector assignment after indexing
- Non-indexed tickers pass through filters (not silently excluded)

### US-2: Industry Group Deep Dive
**As a** sector specialist (e.g., semiconductors trader),
**I want** industry group filtering to work on the full universe,
**So that** I can scan all optionable semiconductor stocks, not just the S&P 500 subset.

**Acceptance Criteria:**
- `--industry-group semiconductors` returns companies like AMD, MRVL, ON, SWKS regardless of index membership
- Industry group mapping uses existing `INDUSTRY_GROUP_ALIASES` (150+ yfinance industry string mappings)
- Unmapped industry strings are logged at WARNING for incremental alias expansion

### US-3: Market Cap Pre-Filtering
**As a** small-cap options trader,
**I want** market cap filtering to reduce the scan universe before OHLCV fetching,
**So that** full-universe scans with `--market-cap small` are faster (fewer tickers to download data for).

**Acceptance Criteria:**
- Market cap tiers from cached metadata applied in Phase 1 (before OHLCV fetch)
- Uncached tickers pass through (not excluded — fail-open behavior)
- Measurable reduction in OHLCV fetch count when market cap filter is active

### US-4: Bulk Metadata Indexing
**As a** power user preparing for a full-universe scan,
**I want** a CLI command to pre-index all CBOE tickers with sector/industry data,
**So that** my first full-universe sector scan has complete metadata coverage.

**Acceptance Criteria:**
- `options-arena universe index` fetches yfinance info for all uncached/stale CBOE tickers
- Progress bar shows completion percentage and ETA
- `--force` flag re-indexes all tickers regardless of staleness
- `--max-age 30` controls staleness threshold (default 30 days)
- Individual ticker failures are logged and skipped (never crash the batch)
- Final report shows: indexed count, sector coverage %, unmapped industry strings

### US-5: Incremental Enrichment
**As a** regular scan user,
**I want** the metadata index to grow automatically as I run scans,
**So that** I don't need to manually run the bulk index command to get good coverage.

**Acceptance Criteria:**
- Phase 3 writes sector/industry/market_cap metadata to the index for every ticker it processes
- Second scan of the same ticker reads from cache (no redundant yfinance calls)
- Metadata TTL of 30 days ensures freshness without excessive API calls

## Requirements

### Functional Requirements

#### FR-1: TickerMetadata Model
- New Pydantic model: `TickerMetadata` (frozen, in `models/metadata.py`)
- Fields: `ticker`, `sector: GICSSector | None`, `industry_group: GICSIndustryGroup | None`, `market_cap_tier: MarketCapTier | None`, `company_name`, `raw_sector`, `raw_industry`, `last_updated: datetime` (UTC)
- `raw_sector` / `raw_industry` preserve yfinance free-text for debugging alias mapping

#### FR-2: SQLite Persistence
- New table: `ticker_metadata` with ticker as PRIMARY KEY
- Migration: `data/migrations/021_create_ticker_metadata.sql`
- Indexes on `sector` and `industry_group` columns
- Repository CRUD: `upsert_ticker_metadata()`, `upsert_ticker_metadata_batch()`, `get_ticker_metadata()`, `get_all_ticker_metadata()`, `get_stale_tickers()`, `get_metadata_coverage()`

#### FR-3: yfinance-to-Metadata Mapping
- New standalone helper: `map_yfinance_to_metadata()` in `services/universe.py`
- Uses existing `SECTOR_ALIASES` (36 entries) to resolve yfinance sector → `GICSSector`
- Uses existing `INDUSTRY_GROUP_ALIASES` (150+ entries) to resolve yfinance industry → `GICSIndustryGroup`
- Uses existing `_classify_market_cap()` for market cap tier
- Logs unmapped sector/industry strings at WARNING level

#### FR-4: TickerInfo.industry Field
- Add `industry: str = "Unknown"` to the existing `TickerInfo` model
- Extract `info["industry"]` from yfinance in `market_data.py`
- Backward compatible (default value, frozen model)

#### FR-5: Phase 1 Metadata Loading
- After S&P 500 CSV processing, load all cached `ticker_metadata` from SQLite
- Merge into `sector_map` and `industry_group_map` (S&P 500 CSV takes priority — canonical GICS source)
- Log enriched coverage: "After metadata enrichment: sector_map=3200, industry_group_map=2800"
- Apply market cap pre-filter using cached tiers (fail-open: uncached tickers pass through)

#### FR-6: Phase 3 Write-Back
- After `fetch_ticker_info()` for each top-N ticker, map result to `TickerMetadata` and upsert
- Enrich `TickerScore.sector` and `.industry_group` if still `None` after Phase 1
- Incremental: each scan improves coverage for subsequent scans

#### FR-7: Bulk Index CLI Command
- `options-arena universe index [--force] [--concurrency 5] [--max-age 30]`
- Fetches yfinance `Ticker.info` for stale/missing tickers in the CBOE universe
- Uses existing `RateLimiter` and `ServiceCache` infrastructure
- Rich progress bar with ticker count and percentage
- Reports final coverage statistics

#### FR-8: API Endpoints
- `POST /api/universe/index` — trigger bulk indexing (background task, operation lock)
- `GET /api/universe/metadata/stats` — return `{ total: int, with_sector: int, coverage: float }`

### Non-Functional Requirements

#### NFR-1: Performance
- Phase 1 metadata load: <50ms for 5,000 rows (SQLite single-table scan)
- Bulk index runtime: ~15-30 min for full universe at 2 rps / 5 concurrent (acceptable per user confirmation)
- No impact on scan runtime when metadata is already cached

#### NFR-2: Data Integrity
- S&P 500 CSV always takes priority over yfinance-derived metadata (canonical GICS source)
- `INSERT OR REPLACE` semantics — re-indexing a ticker overwrites stale data cleanly
- UTC timestamps with validator on `last_updated`
- NaN/Inf defense on all float fields (project-wide pattern)

#### NFR-3: Resilience
- Individual ticker failures during bulk index never crash the batch
- Uncached tickers pass through filters (fail-open, not fail-closed)
- Rate limiter prevents yfinance throttling

#### NFR-4: Observability
- Log unmapped sector/industry strings at WARNING (enables alias expansion)
- Log metadata coverage percentage after Phase 1 enrichment
- CLI reports final coverage stats after indexing

## Success Criteria

| Metric | Target |
|--------|--------|
| Sector coverage after full index | >80% of CBOE tickers |
| Industry group coverage after full index | >70% of CBOE tickers |
| `--preset full --sector X` returns non-S&P500 tickers | Yes |
| Phase 1 metadata load time | <50ms |
| Bulk index completes without crash | Yes, all ticker failures isolated |
| Incremental enrichment works across scans | Phase 3 write-back persists |

## Constraints & Assumptions

### Constraints
- **yfinance rate limits**: ~2 rps conservative; Yahoo may throttle aggressively at higher rates
- **yfinance data quality**: sector/industry strings are free-text, not standardized GICS. Mapping depends on `SECTOR_ALIASES` and `INDUSTRY_GROUP_ALIASES` coverage
- **SQLite single-writer**: bulk index holds the DB connection; no concurrent scans during indexing (existing operation lock pattern handles this)
- **Windows compatibility**: all async patterns must use `signal.signal()`, not `loop.add_signal_handler()`

### Assumptions
- yfinance `Ticker.info` is available for most CBOE optionable tickers (some may return empty/error)
- GICS sector/industry classifications change rarely (~annually during GICS reclassification)
- 30-day TTL is sufficient for metadata freshness
- Users are willing to run a one-time ~30min index command for full coverage

## Out of Scope

- **Real-time metadata updates** — 30-day TTL is sufficient; no live refresh needed
- **Alternative data sources** (SEC EDGAR SIC codes, Nasdaq listings CSV) — yfinance provides adequate coverage
- **Web UI for indexing** — CLI command and API endpoint are sufficient for MVP; frontend trigger deferred
- **Scan Profiles feature** — depends on this epic but is a separate deliverable
- **ETF classification** — ETFs don't have meaningful GICS sectors; excluded from metadata enrichment
- **International tickers** — CBOE universe is US equities only

## Dependencies

### Internal
- `SECTOR_ALIASES` dict (`models/enums.py`) — must cover yfinance sector strings (36 entries exist)
- `INDUSTRY_GROUP_ALIASES` dict (`models/enums.py`) — must cover yfinance industry strings (150+ entries exist)
- `_classify_market_cap()` (`services/market_data.py`) — reused for market cap tier classification
- `RateLimiter` + `ServiceCache` (`services/`) — reused for bulk fetching
- `Repository` pattern (`data/repository.py`) — CRUD methods follow existing watchlist/analytics patterns
- Sequential migration numbering — next available is `021`

### External
- **yfinance** `Ticker.info` API — provides sector, industry, marketCap, shortName fields
- **CBOE optionable universe CSV** — provides the ticker list to index (already fetched by `UniverseService`)

## Technical Design Reference

Detailed implementation design (file paths, code patterns, data flow, migration SQL, repository methods, pipeline integration points, CLI command structure, and implementation wave ordering) is documented in the plan file: `.claude/plans/serialized-doodling-shell.md`
