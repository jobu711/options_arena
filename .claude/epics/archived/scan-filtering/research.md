# Research: scan-filtering

## PRD Summary

Enhanced pre-scan universe narrowing and post-scan result filtering via dimensional scores, quick-filter presets, and market regime awareness. The DSE already computes 8 dimensional score families during Phase 2 but the data is discarded — this is primarily a persistence + API wiring + UI effort.

## Relevant Existing Modules

- `models/` — `DimensionalScores` (frozen, 8 fields), `DirectionSignal` (frozen, confidence 0-1), `MarketRegime` enum (4 values), `MarketCapTier` enum (5 tiers), `TickerScore` (already has `dimensional_scores` and `direction_confidence` fields but not persisted), `ScanConfig` (needs 4 new optional filter fields)
- `scoring/` — `dimensional.py` already has `compute_dimensional_scores()`, `compute_direction_signal()`, `apply_regime_weights()`, and `FAMILY_INDICATOR_MAP` with all 8 families mapped to indicator fields
- `scan/` — 4-phase pipeline. Phase 2 computes dimensional scores. Phase 4 persists but doesn't save dimensional data. Pre-scan filters slot into Phase 1; direction filter post-Phase 2; IV rank in Phase 3
- `data/` — `ticker_scores` table has 9 columns (id, scan_run_id, ticker, composite_score, direction, signals_json, next_earnings, sector, company_name). Migration 014 is latest. Serialization pattern: `model_dump_json()` / `model_validate_json()`
- `api/` — `GET /api/scan/{id}/scores` with server-side Python filtering (min_score, direction, search). `PaginatedResponse` generic. `ScanRequest` accepts preset + sectors
- `cli/` — `scan` command with `--preset` and `--sectors` options. Sync Typer wrapping async
- `services/` — `UniverseService` for ticker universe, `MarketDataService` for OHLCV. Would need market cap filtering and earnings proximity filtering
- `web/` — ScanResultsPage.vue (915 lines), Pinia scan store, PrimeVue DataTable, URL query param sync via `router.replace()`, TypeScript `TickerScore` interface needs extension

## Existing Patterns to Reuse

- **signals_json serialization**: `IndicatorSignals.model_dump_json()` → TEXT column → `model_validate_json()` on read. Reuse identically for `dimensional_scores_json`
- **Server-side list comprehension filtering**: `api/routes/scan.py` lines 195-206 filter `list[TickerScore]` in memory. Extend with dimensional score min/max checks
- **URL query param sync**: ScanResultsPage already syncs sort/order/page/direction/search to URL via `router.replace()`. Extend with filter params
- **ScanRequest sector validation**: `field_validator("sectors")` normalizes aliases and deduplicates. Same pattern for `market_cap_tiers`
- **Optional column migration**: Migrations 007-008 added nullable columns to `ticker_scores` via `ALTER TABLE ADD COLUMN`. Same approach for migration 015
- **Config defaults for backward compatibility**: All `ScanConfig` fields have defaults. New filter fields use `None` / `[]` defaults

## Existing Code to Extend

- `data/repository.py:save_ticker_scores()` — Add `dimensional_scores_json`, `direction_confidence`, `market_regime` to INSERT statement
- `data/repository.py:_row_to_ticker_score()` — Deserialize new columns back to typed fields (with NULL → None handling)
- `api/routes/scan.py:get_scores()` — Add query params for dimensional filters and extend filter chain
- `api/schemas.py:ScanRequest` — Add pre-scan filter fields (market_cap_tiers, exclude_near_earnings_days)
- `models/config.py:ScanConfig` — Add 4 optional filter fields
- `scan/pipeline.py` — Phase 1: apply market cap filter; Phase 2: set market_regime on TickerScore; Phase 4: persist new fields
- `web/src/types/scan.ts:TickerScore` — Add `dimensional_scores?`, `direction_confidence?`, `market_regime?`
- `web/src/pages/ScanResultsPage.vue` — Extract `ScanFilterPanel` and `FilterPresets` components (PRD constraint: file is 915 lines)

## Potential Conflicts

- **ScanResultsPage.vue complexity** — Already 915 lines. PRD explicitly requires extracting at least 2 components (ScanFilterPanel, FilterPresets) to manage complexity. This is an opportunity, not a conflict
- **Market cap universe-wide filtering** — TickerInfo (which has market_cap_tier) is currently only fetched for top-N tickers in Phase 3. Universe-wide market cap filtering in Phase 1 would require TickerInfo fetch for all ~5,286 tickers (expensive). PRD acknowledges this constraint. Alternative: use a cached market cap tier mapping from the universe service
- **IV rank filtering** — Only feasible in Phase 3 (requires option chains). Cannot filter universe-wide by IV rank. PRD scope limits this to top-N buffer
- **Direction confidence not a DB column** — The PRD says to add `direction_confidence REAL` as a column. Currently computed but not stored. Straightforward addition

## Open Questions

1. **Market cap data source**: Universe-wide market cap filtering needs TickerInfo for all tickers. Should we (a) batch-fetch TickerInfo for the universe (slow, ~5K API calls) or (b) maintain a cached market cap tier mapping in the universe service (fast, needs periodic refresh)? PRD doesn't specify. **Recommendation**: Option (b) — cached mapping, refreshed with universe cache (24h TTL)
2. **Regime aggregation method**: PRD says "dominant classification across scored tickers" for the regime banner. Should this be (a) mode (most common regime) or (b) weighted average of the regime signal? **Recommendation**: Mode of per-ticker regime classifications
3. **Quick-filter presets location**: PRD says "frontend constant." Should presets be TypeScript-only or also available as an API endpoint for consistency? **Recommendation**: Frontend-only constants (simpler, no API needed)

## Recommended Architecture

### Wave 1: Foundation (Backend)
1. **Migration 015**: Add `dimensional_scores_json TEXT`, `direction_confidence REAL`, `market_regime TEXT` to `ticker_scores`
2. **Repository**: Extend `save_ticker_scores()` and `_row_to_ticker_score()` with new columns
3. **Pipeline Phase 2**: Set `market_regime` on each `TickerScore` using threshold mapping (>=80 CRISIS, >=60 VOLATILE, >=40 MEAN_REVERTING, <40 TRENDING)
4. **Pipeline Phase 4**: Persist dimensional scores (already computed, just not saved)
5. **API response**: Include dimensional_scores, direction_confidence, market_regime in TickerScore response
6. **TypeScript types**: Extend TickerScore interface

### Wave 2: Post-Scan Filters (Frontend + API)
1. **API query params**: Add `min_confidence`, `market_regime`, `min_trend`, `min_iv_vol`, `min_flow`, `min_risk`, `max_earnings_days`, `min_earnings_days` to GET scores endpoint
2. **Server-side filtering**: Extend list comprehension chain
3. **ScanFilterPanel.vue**: Collapsible panel with PrimeVue Slider/Select/Input components
4. **FilterPresets.vue**: 6 quick-filter buttons (High IV Setups, Momentum Plays, Mean Reversion, Income/Theta, Earnings Plays, Low Risk)
5. **URL state sync**: All filter values in query params

### Wave 3: Pre-Scan Filters (Config + Pipeline + Frontend)
1. **ScanConfig**: Add `market_cap_tiers`, `exclude_near_earnings_days`, `direction_filter`, `min_iv_rank`
2. **ScanRequest schema**: Accept new fields
3. **Pipeline**: Apply filters at appropriate phases
4. **ScanPage.vue**: Market cap multi-select, earnings proximity input
5. **CLI**: New `--min-market-cap`, `--exclude-earnings` options

### Wave 4: Polish (Frontend Display)
1. **RegimeBanner.vue**: Color-coded banner above results
2. **Dimensional score display**: Expandable DataTable rows with 8 bar segments
3. **Direction confidence column**: Sortable percentage column
4. **TickerDrawer enhancement**: Dimensional score breakdown section

Waves 2, 3, 4 are independent after Wave 1.

## Test Strategy Preview

- **Repository tests** (`tests/unit/data/test_repository.py`): Test save/retrieve with dimensional_scores_json, direction_confidence, market_regime. Test NULL handling for pre-migration data
- **API route tests** (`tests/unit/api/test_scan_routes.py`): Test new query params, filter combinations, edge cases (all None, all set, invalid values)
- **Pipeline tests** (`tests/unit/scan/test_pipeline_phase2.py`): Test market_regime assignment, dimensional score persistence flow
- **Model tests** (`tests/unit/models/test_scan.py`): Test TickerScore with all new fields populated and None
- **E2E tests** (`web/tests/e2e/`): Filter panel interaction, preset clicks, URL state persistence, regime banner display
- **Fixture pattern**: `@pytest_asyncio.fixture` for db/repo, `make_ticker_score()` factory extended with new fields, `AsyncMock` for service mocks

## Estimated Complexity

**Medium-Large (M-L)** — The scoring infrastructure already exists. This is primarily:
- 1 SQL migration (trivial)
- ~60 LOC repository extension (straightforward)
- ~40 LOC API filter extension (follows existing pattern)
- ~4 new ScanConfig fields (trivial)
- ~5-10 LOC pipeline wiring (Phase 2 + Phase 4)
- ~500 LOC frontend (largest portion: filter panel, presets, regime banner, score display)
- ~70 tests (mixed Python unit + E2E)
- **Total**: ~866 LOC across ~15 files, 4 waves

The backend is small and low-risk. The frontend is the bulk of the work (extraction from 915-line ScanResultsPage + new components).
