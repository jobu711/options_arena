---
name: ticker-universe-improve
status: backlog
created: 2026-03-01T15:11:29Z
progress: 0%
prd: .claude/prds/ticker-universe-improve.md
updated: 2026-03-01T15:35:20Z
github: https://github.com/jobu711/options_arena/issues/161
---

# Epic: ticker-universe-improve

## Overview

Add composable sector filtering, a working ETF preset, and scan result enrichment (sector column + company name in drawer) to the ticker universe system. Leverages existing data sources (Wikipedia S&P 500 sectors, CBOE optionable list, yfinance ticker info) — no new external dependencies. The primary work is wiring data that already flows through the pipeline into the `TickerScore` model, persisting it, and exposing it in the CLI, API, and frontend.

## Architecture Decisions

- **GICSSector StrEnum with alias mapping**: Canonical GICS names contain spaces ("Information Technology"). A `SECTOR_ALIASES: dict[str, GICSSector]` mapping normalizes CLI/API input (lowercase, hyphenated, underscored variants) to canonical enum values. Single mapping shared by CLI and API `mode='before'` validator.
- **TickerScore enrichment over separate lookup**: Sector and company name are added directly to `TickerScore` (not a separate API call) because the data is already available during the scan pipeline. This avoids N+1 queries in the frontend.
- **ETF detection via yfinance `quoteType`**: CBOE CSV lacks an asset-type column. Use yfinance's `Ticker.info["quoteType"] == "ETF"` cross-referenced against the CBOE optionable list. Cache result with 24h TTL, same pattern as existing universe fetches.
- **Nullable columns for backward compatibility**: `sector` and `company_name` added as nullable TEXT columns to `ticker_scores`. Existing scan data remains valid. No backfill required.
- **CLI `--sector` changes from comma-separated string to multi-value option**: The existing stub `--sectors` (comma-separated) is replaced with `--sector` (repeatable flag) using Typer's `list[GICSSector]` pattern. More composable and consistent with `--preset`.

## Technical Approach

### Models Layer
- New `GICSSector(StrEnum)` in `enums.py` with 11 GICS sectors
- `SECTOR_ALIASES` mapping in `enums.py` for case-insensitive normalization
- `ScanConfig.sectors: list[GICSSector] = []` with `mode='before'` validator for alias resolution
- `TickerScore`: add `sector: GICSSector | None = None` and `company_name: str | None = None`
- DB migration: `ALTER TABLE ticker_scores ADD COLUMN sector TEXT` + `company_name TEXT`

### Services Layer
- `UniverseService.fetch_etf_tickers() -> list[str]`: fetch CBOE optionable list, cross-reference with yfinance `quoteType == "ETF"` for a curated subset, cache 24h
- `UniverseService.filter_by_sectors(tickers, sectors, sp500_map) -> list[str]`: pure helper, set intersection

### Pipeline + Repository
- Phase 1: build `sector_map: dict[str, GICSSector]` from existing `sp500_constituents`, apply sector filter if `config.sectors` is non-empty
- Phase 2: attach `ticker_score.company_name` from `fetch_ticker_info()` (already called)
- Phase 3: attach `ticker_score.sector` from `sector_map` after top-N selection
- Repository: add `sector` and `company_name` to INSERT/SELECT in `save_ticker_scores` / `get_scores_for_scan`

### CLI
- Replace `--sectors` stub with `--sector` repeatable flag using `list[GICSSector]`
- Add `universe sectors` subcommand listing GICS sectors with ticker counts
- Wire `ScanPreset.ETFS` to `fetch_etf_tickers()` in `_scan_async`

### API
- `ScanRequest`: add `sectors: list[GICSSector] = []` with `mode='before'` alias validator
- New `GET /api/universe/sectors` endpoint returning `list[SectorInfo]` (name + ticker count)
- Existing `GET /api/scan/{id}/scores` automatically includes `sector` and `company_name` (TickerScore is the response model)

### Frontend
- `TickerScore` TypeScript interface: add `sector: string | null`, `company_name: string | null`
- `ScanResultsPage.vue`: add Sector column (PrimeVue Tag/chip, sortable/filterable)
- `TickerDrawer.vue`: display `company_name` as subtitle in header
- Scan page: add PrimeVue MultiSelect for sector filtering (chips display), pass to `POST /api/scan`
- Scan page: `etfs` option in preset selector (already in `ScanPreset` enum, just needs UI wiring)

## Implementation Strategy

Development phases (ordered by dependency chain):

1. **Models + Migration** (foundation — everything else depends on this)
2. **Services** (ETF detection, sector helpers)
3. **Pipeline + Repository** (wire data through, persist)
4. **CLI** (expose to terminal users)
5. **API** (expose to web frontend)
6. **Frontend** (consume enriched data)
7. **Tests** (validate everything end-to-end)

Risk mitigation:
- ETF detection accuracy: start with yfinance `quoteType` cross-referenced against CBOE list. If unreliable, fall back to curated seed list of ~100 popular ETFs.
- Typer `list` vs `List` for multi-value options: test early, fall back to `typing.List` if needed.
- GICS sector names from Wikipedia must match enum values exactly. Add a mapping layer to handle minor formatting differences.

## Task Breakdown Preview

- [ ] Task 1: GICSSector enum, alias mapping, ScanConfig.sectors, TickerScore fields, DB migration
- [ ] Task 2: UniverseService ETF detection + sector filtering helpers
- [ ] Task 3: Pipeline sector filter injection + TickerScore enrichment + Repository persistence
- [ ] Task 4: CLI --sector flag, universe sectors subcommand, ETF preset wiring
- [ ] Task 5: API ScanRequest.sectors, GET /universe/sectors endpoint, enriched responses
- [ ] Task 6: Frontend sector column, company name in drawer, sector MultiSelect, ETF preset
- [ ] Task 7: Tests — unit (models, services, pipeline, API), integration (CLI + pipeline), E2E (Playwright)

## Dependencies

- **Existing**: Wikipedia S&P 500 fetch (sector data), CBOE fetch (optionable universe), yfinance `Ticker.info` (company name, quoteType), PrimeVue MultiSelect component
- **Internal ordering**: Task 1 (models) blocks all others. Tasks 2-3 block 4-6. Task 7 runs last.
- **No new external dependencies**: All data sources already in use. No new paid APIs.

## Success Criteria (Technical)

- `GICSSector` StrEnum has exactly 11 members matching canonical GICS sector names
- `SECTOR_ALIASES` resolves all common variants (lowercase, hyphenated, underscored, short names)
- `ScanConfig.sectors` validator normalizes input via aliases before validation
- `TickerScore.sector` populated for all S&P 500 tickers, `None` for non-S&P 500
- `TickerScore.company_name` populated for all tickers where `fetch_ticker_info` succeeds
- `ticker_scores` table migration adds nullable columns without breaking existing data
- `ScanPreset.ETFS` returns > 0 ETFs from `fetch_etf_tickers()`
- `--sector technology` filters scan universe to IT sector tickers only
- `POST /api/scan` with `sectors: ["Information Technology"]` works
- `GET /api/universe/sectors` returns 11 sectors with accurate ticker counts
- Scan results DataTable shows Sector column with colored chips
- TickerDrawer header shows company full name as subtitle
- All existing 2,328+ Python tests + 38 E2E tests pass (zero regressions)
- `ruff check`, `ruff format`, `mypy --strict` all pass

## Tasks Created

- [ ] #165 - GICSSector enum, alias mapping, TickerScore enrichment, DB migration (parallel: false)
- [ ] #166 - UniverseService ETF detection and sector filtering helpers (parallel: true)
- [ ] #167 - Pipeline sector filter injection and TickerScore enrichment (parallel: true)
- [ ] #168 - CLI --sector flag, universe sectors subcommand, ETF preset wiring (parallel: true)
- [ ] #162 - API ScanRequest.sectors, GET /universe/sectors, enriched responses (parallel: true)
- [ ] #163 - Frontend sector column, company name in drawer, sector filter, ETF preset (parallel: false)
- [ ] #164 - Integration tests for sector filtering, ETF preset, enriched scan results (parallel: false)

Total tasks: 7
Parallel tasks: 4 (#166, #167, #168, #162)
Sequential tasks: 3 (#165, #163, #164)

### Dependency Graph

```
#165 (Models + Migration)
 ├── #166 (Services)  ──┐
 └── #167 (Pipeline)  ──┼── #168 (CLI)  ──┐
                        └── #162 (API)  ──┼── #163 (Frontend) ── #164 (Tests)
```

## Estimated Effort

- **7 tasks**, ordered by dependency chain
- #165 (Models + Migration) is the critical path — everything depends on it
- #166 + #167 can run in parallel after #165 completes
- #168 + #162 can run in parallel after #167 completes
- #163 (Frontend) is the largest single task (3 component changes + TypeScript types)
- #166 (ETF detection) has the most uncertainty (yfinance quoteType reliability)
- #164 (Tests) runs last, validates everything end-to-end
