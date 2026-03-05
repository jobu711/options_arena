# Research: metadata-index

## PRD Summary

Enrich all ~5,000 CBOE optionable tickers with GICS sector, industry group, and market cap tier metadata via a persistent SQLite index. Today only ~500 S&P 500 tickers have classification data (from a GitHub CSV). This feature closes the metadata gap by caching yfinance classification data, enabling sector/industry/market-cap filtering across the entire optionable universe.

Key deliverables: `TickerMetadata` model, `ticker_metadata` SQLite table (migration 021), yfinance-to-metadata mapping helper, Phase 1 metadata loading, Phase 3 write-back enrichment, `options-arena universe index` CLI command, and two API endpoints.

## Relevant Existing Modules

- **`models/`** — `TickerInfo` (frozen, has `sector: str` raw + `market_cap_tier`), `TickerScore` (mutable, has `sector: GICSSector | None` + `industry_group: GICSIndustryGroup | None`), enums (`GICSSector`, `GICSIndustryGroup`, `MarketCapTier`, `SECTOR_ALIASES`, `INDUSTRY_GROUP_ALIASES`). New `TickerMetadata` model goes in `models/metadata.py`.
- **`data/`** — `Database` (WAL, migrations), `Repository` (typed CRUD). New migration `021_create_ticker_metadata.sql` and 6 new repository methods.
- **`services/market_data.py`** — `fetch_ticker_info()` returns `TickerInfo` with sector/market_cap/company_name. Private `_classify_market_cap()` already classifies tiers. `TickerInfo` needs new `industry: str = "Unknown"` field (FR-4).
- **`services/universe.py`** — `fetch_optionable_tickers()` provides the ~5,000 ticker list. `build_sector_map()` and `build_industry_group_map()` already resolve aliases. New `map_yfinance_to_metadata()` helper goes here.
- **`scan/pipeline.py`** — Phase 1 (`_phase_universe()`, lines 228–270) builds `sector_map`/`industry_group_map` from S&P 500 CSV only. Phase 3 (`_process_ticker_options()`, line 810) only writes back `company_name`. Both phases need extension.
- **`cli/commands.py`** — `universe_app` Typer subcommand group (line 866) with `refresh`, `list`, `sectors`, `stats`. New `index` command added here.
- **`api/routes/universe.py`** — Existing `GET /api/universe`, `POST /api/universe/refresh`, `GET /api/universe/sectors`. New `POST /api/universe/index` and `GET /api/universe/metadata/stats`.

## Existing Patterns to Reuse

- **Watchlist/Themes Repository pattern**: `INSERT OR REPLACE` upsert on primary key, `_row_to_*` static helpers, `Row` named column access, enum reconstruction via `GICSSector(raw_sector)`, optional `commit: bool = True` parameter for atomic batches.
- **Frozen Pydantic model pattern**: `ConfigDict(frozen=True)`, UTC validator on `datetime` fields, `| None` unions for optional fields. Follow `WatchlistTicker` / `ThemeSnapshot` as template.
- **Migration pattern**: `CREATE TABLE IF NOT EXISTS`, additive columns, `TEXT` storage for enums, sequential numbering (next = 021). No `schema_version` manipulation in migration files.
- **CLI Typer pattern**: Sync wrapper + `asyncio.run(_async())`, Rich progress bars, `--force` flags as `bool` with `typer.Option()`.
- **API background task pattern**: `asyncio.create_task()` with operation lock (same `asyncio.Lock` used by scan/batch-debate), counter-based task IDs, `409` if lock already held.
- **Service DI pattern**: `Depends(get_repo)` / `Depends(get_universe)` in `deps.py`, services registered on `app.state` in `lifespan()`.
- **Alias resolution pattern**: `SECTOR_ALIASES.get(key.strip().lower())` → `GICSSector`, `INDUSTRY_GROUP_ALIASES.get(key.strip().lower())` → `GICSIndustryGroup`. Log unmapped strings at WARNING.
- **Batch isolation**: `asyncio.gather(*tasks, return_exceptions=True)` — one ticker failure never crashes the batch.

## Existing Code to Extend

| File | Current State | Change Needed |
|------|--------------|---------------|
| `models/market_data.py` (~line 166) | `TickerInfo` has `sector: str` but no `industry` field | Add `industry: str = "Unknown"` (backward-compatible default) |
| `services/market_data.py` (~line 443) | `fetch_ticker_info()` extracts `info.get("sector")` but not `info.get("industry")` | Add `industry=str(info.get("industry", "Unknown"))` to constructor |
| `scan/pipeline.py` (~lines 228–270) | Phase 1 builds sector/industry maps from S&P 500 CSV only | After S&P 500 maps, load `ticker_metadata` from DB, merge (CSV priority) |
| `scan/pipeline.py` (~line 810) | Phase 3 only writes `ticker_score.company_name` from `TickerInfo` | Add metadata upsert + enrich `ticker_score.sector`/`.industry_group` if `None` |
| `data/repository.py` (end of file) | No metadata methods | Add 6 CRUD methods following watchlist/themes patterns |
| `cli/commands.py` (~line 995) | `universe_app` has 4 commands | Add `index` subcommand |
| `api/routes/universe.py` (~line 115) | 3 existing endpoints | Add 2 new metadata endpoints |
| `api/schemas.py` | No metadata schemas | Add `MetadataStats(BaseModel)` |
| `models/__init__.py` (~line 81) | No metadata re-exports | Add `TickerMetadata` re-export |

## New Files to Create

| File | Purpose |
|------|---------|
| `src/options_arena/models/metadata.py` | `TickerMetadata` frozen Pydantic model (FR-1) |
| `data/migrations/021_create_ticker_metadata.sql` | `ticker_metadata` table with ticker PK + sector/industry/market_cap indexes (FR-2) |

## Potential Conflicts

- **`TickerInfo` serialization cache**: Adding `industry` field with default is backward-compatible — existing cached JSON deserializes correctly via `model_validate_json()` (Pydantic v2 accepts missing fields with defaults). No cache invalidation needed.
- **`_classify_market_cap` is private**: Two copies exist (`market_data.py:201` and `universe.py:323`). For `map_yfinance_to_metadata()` in `universe.py`, can import from `market_data` (intra-`services/` import is acceptable) or use the existing `universe.py` copy.
- **Phase 1 ordering**: Metadata load MUST happen after S&P 500 map construction to preserve CSV priority. Insert point is after line 270 (both maps built), before custom tickers branch at line 272.
- **Operation lock contention**: `POST /api/universe/index` must use the same `asyncio.Lock` as scan/debate. Indexing and scanning are mutually exclusive — correct behavior per NFR constraints.
- **`scan/pipeline.py` needs Repository access**: Pipeline constructor already receives services. Need to add `Repository` dependency for Phase 3 write-back (or pass through an existing service). Check if `ScanPipeline.__init__` already has `repo` parameter.

## Open Questions

1. **Where should `map_yfinance_to_metadata()` live?** PRD says `services/universe.py`, but it could also be a static method on `TickerMetadata` or a standalone module. `universe.py` aligns with existing `build_sector_map()`/`build_industry_group_map()` helpers — recommend keeping there.
2. **Should Phase 3 write-back be async-batched or per-ticker?** Per-ticker upsert is simpler and matches the sequential Phase 3 loop. Batch upsert (`executemany`) only needed for the bulk index command.
3. **Pipeline Repository dependency**: Does `ScanPipeline` already have a `Repository` instance? If not, it needs one for Phase 3 write-back. Check if it's passed through `ScanConfig` or directly.
4. **`TickerInfo.industry` field**: PRD says add `industry: str = "Unknown"`. The `market_data.py` service already extracts `sector` from yfinance `info` dict. Adding `industry` extraction is a 1-line change. Confirm this doesn't need a separate PR for backward compat (it shouldn't — default value handles it).

## Recommended Architecture

### Data Flow

```
Bulk Index (CLI/API):
  UniverseService.fetch_optionable_tickers() → [5000 tickers]
  → for each ticker: MarketDataService.fetch_ticker_info() → TickerInfo
  → map_yfinance_to_metadata(TickerInfo) → TickerMetadata
  → Repository.upsert_ticker_metadata(TickerMetadata)

Scan Phase 1 (Enrichment):
  Build S&P 500 sector_map + industry_group_map (existing)
  → Repository.get_all_ticker_metadata() → [TickerMetadata]
  → Merge into sector_map and industry_group_map (CSV takes priority)

Scan Phase 3 (Write-Back):
  MarketDataService.fetch_ticker_info(ticker) → TickerInfo (existing)
  → map_yfinance_to_metadata(TickerInfo) → TickerMetadata
  → Repository.upsert_ticker_metadata(TickerMetadata)
  → Enrich ticker_score.sector/industry_group if still None
```

### Implementation Waves

**Wave 1 — Foundation (no external dependencies)**
- `TickerMetadata` model + migration 021 + repository CRUD methods
- `TickerInfo.industry` field addition

**Wave 2 — Mapping & Pipeline Integration**
- `map_yfinance_to_metadata()` helper in `services/universe.py`
- Phase 1 metadata loading in `scan/pipeline.py`
- Phase 3 write-back in `scan/pipeline.py`

**Wave 3 — CLI & API**
- `options-arena universe index` CLI command
- `POST /api/universe/index` + `GET /api/universe/metadata/stats` API endpoints

**Wave 4 — Tests**
- Unit tests per module (model, repository, service, pipeline, CLI, API)
- Integration test: full scan with metadata enrichment

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/{module}/test_*.py`, fixtures in `conftest.py`, `aiosqlite` `:memory:` for DB tests, `unittest.mock.patch` for service mocking
- **Model tests**: `tests/unit/models/test_metadata.py` — frozen, UTC validator, enum constraints
- **Repository tests**: `tests/unit/data/test_repository_metadata.py` — upsert, get, batch, stale ticker queries (follow `test_repository_watchlist.py` pattern)
- **Service tests**: `tests/unit/services/test_universe_metadata.py` — `map_yfinance_to_metadata()` with various yfinance strings, unmapped alias logging
- **Pipeline tests**: `tests/unit/scan/test_pipeline_metadata.py` — Phase 1 merge, Phase 3 write-back
- **CLI tests**: `tests/unit/cli/test_universe_index.py` — command invocation, progress, error handling
- **API tests**: `tests/unit/api/test_universe_metadata.py` — endpoint responses, lock contention
- **Estimated test count**: ~100-130 new tests

## Estimated Complexity

**Medium-Large (M-L)**

Justification:
- Touches 9+ existing files across 6 modules (models, data, services, scan, cli, api)
- 2 new files (model + migration)
- 6 new repository methods
- Pipeline integration at two phases (Phase 1 + Phase 3)
- New CLI command with progress bar and rate limiting
- 2 new API endpoints with background task + lock
- ~100-130 new tests
- No new external dependencies (reuses yfinance, aiosqlite, existing enums/aliases)
- Well-defined patterns exist for every layer — execution risk is low, scope is the main driver
