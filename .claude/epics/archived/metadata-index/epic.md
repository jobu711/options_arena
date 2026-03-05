---
name: metadata-index
status: backlog
created: 2026-03-05T14:31:15Z
progress: 0%
prd: .claude/prds/metadata-index.md
github: https://github.com/jobu711/options_arena/issues/269
---

# Epic: metadata-index

## Overview

Add a persistent SQLite `ticker_metadata` table that caches GICS sector, industry group, and market cap tier for all ~5,000 CBOE optionable tickers. Today only ~500 S&P 500 tickers have classification data. This epic closes the gap by: (1) creating the persistence layer, (2) integrating it into the scan pipeline's Phase 1 (read) and Phase 3 (write-back), (3) adding a bulk `universe index` CLI command, and (4) exposing two API endpoints. All patterns (Repository CRUD, frozen models, migration, CLI/API) already exist in the codebase and are directly reused.

## Architecture Decisions

- **`TickerMetadata` as frozen Pydantic model** in `models/metadata.py` — follows `WatchlistTicker`/`ThemeSnapshot` pattern. Ticker is the natural primary key.
- **`map_yfinance_to_metadata()` lives in `services/universe.py`** — co-located with existing `build_sector_map()`/`build_industry_group_map()` helpers that use the same alias dicts.
- **S&P 500 CSV always takes priority** — Phase 1 loads metadata AFTER building S&P 500 maps, so CSV entries are never overwritten.
- **Fail-open filtering** — tickers without metadata pass through all filters (never silently excluded).
- **Per-ticker upsert in Phase 3, batch upsert in bulk index** — matches existing sequential Phase 3 loop and batch CLI patterns.
- **`ScanPipeline` already has `Repository`** (confirmed in constructor) — no new dependency injection needed for Phase 3 write-back.
- **Reuse `_classify_market_cap()` from `universe.py`** — it already has a public copy with identical thresholds.
- **Operation lock shared with scan/debate** for `POST /api/universe/index` — prevents concurrent DB writes.

## Technical Approach

### Data Layer (Model + Migration + Repository)

- New `models/metadata.py`: `TickerMetadata(BaseModel, frozen=True)` with fields: `ticker`, `sector: GICSSector | None`, `industry_group: GICSIndustryGroup | None`, `market_cap_tier: MarketCapTier | None`, `company_name: str | None`, `raw_sector: str`, `raw_industry: str`, `last_updated: datetime` (UTC validated).
- New `data/migrations/021_create_ticker_metadata.sql`: `ticker_metadata` table with `ticker TEXT PRIMARY KEY`, indexes on `sector` and `industry_group`.
- Repository methods in `data/repository.py`: `upsert_ticker_metadata()`, `upsert_ticker_metadata_batch()`, `get_ticker_metadata()`, `get_all_ticker_metadata()`, `get_stale_tickers(max_age_days)`, `get_metadata_coverage()` — all following existing watchlist/themes patterns.

### Service Layer (Mapping + TickerInfo Extension)

- Add `industry: str = "Unknown"` field to `TickerInfo` model (backward-compatible default).
- Add `industry=str(info.get("industry", "Unknown"))` extraction in `market_data.py`'s `fetch_ticker_info()`.
- New `map_yfinance_to_metadata(ticker_info: TickerInfo) -> TickerMetadata` in `services/universe.py` — resolves raw sector/industry via `SECTOR_ALIASES`/`INDUSTRY_GROUP_ALIASES`, logs unmapped strings at WARNING.

### Pipeline Integration

- **Phase 1** (`_phase_universe()`): After S&P 500 map construction (~line 270), call `self._repo.get_all_ticker_metadata()`, merge into `sector_map`/`industry_group_map` (skip tickers already in CSV maps). Apply market cap pre-filter for cached tiers (fail-open).
- **Phase 3** (`_process_ticker_options()`): After `fetch_ticker_info()` (~line 810), call `map_yfinance_to_metadata()` → `self._repo.upsert_ticker_metadata()`. Enrich `ticker_score.sector`/`.industry_group` if still `None`.

### CLI Command

- `options-arena universe index [--force] [--concurrency 5] [--max-age 30]` in `cli/commands.py`.
- Sync wrapper + `asyncio.run()`. Fetches CBOE ticker list, identifies stale/missing tickers, iterates with `RateLimiter` + `asyncio.Semaphore(concurrency)`, Rich progress bar, final coverage report.

### API Endpoints

- `POST /api/universe/index` — background task with operation lock, returns `202` with task ID or `409` if busy.
- `GET /api/universe/metadata/stats` — returns `MetadataStats(total, with_sector, with_industry_group, coverage)` from `repo.get_metadata_coverage()`.
- New `MetadataStats` schema in `api/schemas.py`.

## Implementation Strategy

### Wave 1 — Foundation (Tasks 1-3)
Model, migration, repository CRUD, TickerInfo.industry field. No external integration — pure data layer. Run tests after.

### Wave 2 — Mapping & Pipeline (Tasks 4-5)
`map_yfinance_to_metadata()` helper, Phase 1 metadata loading, Phase 3 write-back. This is the core value — scans start benefiting from cached metadata.

### Wave 3 — CLI & API (Tasks 6-7)
Bulk index CLI command, API endpoints. These provide the initial population mechanism.

### Wave 4 — Tests (Task 8)
Comprehensive unit tests across all layers. Integration test for end-to-end scan-with-metadata flow.

### Risk Mitigation
- **Backward compatibility**: `TickerInfo.industry` has a default — existing serialization cache is safe.
- **Phase 1 ordering**: Metadata merge after S&P 500 maps guarantees CSV priority.
- **Fail-open**: Uncached tickers always pass through filters.
- **Batch isolation**: Individual ticker failures in bulk index are caught and logged, never crash.

## Tasks Created
- [ ] #271 - TickerMetadata model + migration 021 (parallel: true)
- [ ] #273 - Repository CRUD methods for ticker_metadata (parallel: false, depends: #271)
- [ ] #275 - TickerInfo.industry field + market_data extraction (parallel: true)
- [ ] #276 - map_yfinance_to_metadata() helper (parallel: false, depends: #271, #275)
- [ ] #270 - Pipeline integration — Phase 1 loading + Phase 3 write-back (parallel: false, depends: #273, #276)
- [ ] #272 - universe index CLI command (parallel: true, depends: #273, #276)
- [ ] #274 - API endpoints — index trigger + metadata stats (parallel: true, depends: #273, #276)
- [ ] #277 - Integration tests + edge case coverage (parallel: false, depends: #270, #272, #274)

Total tasks: 8
Parallel tasks: 4 (#271, #275, #272, #274)
Sequential tasks: 4 (#273, #276, #270, #277)

## Test Coverage Plan
Total test files planned: 8
Total test cases planned: ~75 (unit) + ~8 (integration) = ~83

## Dependencies

### Internal (all exist — no prerequisite work)
- `SECTOR_ALIASES` (36 entries) + `INDUSTRY_GROUP_ALIASES` (150+ entries) in `models/enums.py`
- `classify_market_cap()` in `services/universe.py`
- `Repository` pattern in `data/repository.py`
- `RateLimiter` + `ServiceCache` in `services/`
- `ScanPipeline.__init__` already accepts `repository: Repository`
- Migration runner in `data/database.py` (auto-applies 021 on connect)

### External
- yfinance `Ticker.info` API (sector, industry, marketCap, shortName fields)
- CBOE optionable universe CSV (already fetched by `UniverseService`)

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Sector coverage after full index | >80% of CBOE tickers |
| Industry group coverage | >70% of CBOE tickers |
| `--preset full --sector X` returns non-S&P500 tickers | Yes |
| Phase 1 metadata load time (5,000 rows) | <50ms |
| Bulk index completes without crash | All ticker failures isolated |
| Phase 3 write-back persists across scans | Yes |
| All existing tests still pass | Yes |
| New tests | ~100-130 |

## Estimated Effort

- **Size**: Medium-Large
- **Tasks**: 8
- **New files**: 2 (model + migration)
- **Modified files**: ~9 across 6 modules
- **New tests**: ~100-130
- **Risk**: Low — all patterns well-established, no new dependencies
- **Critical path**: Tasks 1-2 (data layer) → Task 4-5 (pipeline) → Task 6-7 (CLI/API)
