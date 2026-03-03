---
name: scan-filtering
status: backlog
created: 2026-03-03T21:19:37Z
progress: 0%
prd: .claude/prds/scan-filtering.md
github: https://github.com/jobu711/options_arena/issues/221
---

# Epic: scan-filtering

## Overview

Wire the existing Dimensional Scoring Engine (DSE) output into the persistence layer, API, and web UI. The `compute_dimensional_scores()` and `compute_direction_signal()` functions already exist and are imported by the pipeline — they just need to be called, persisted, and exposed. This unlocks post-scan dimensional filtering (sliders, quick-filter presets), pre-scan universe narrowing (market cap, earnings proximity), and visual context (regime banner, score breakdown).

~866 LOC across ~15 files, 5 tasks in 3 waves.

## Architecture Decisions

1. **Dimensional scores as JSON blob** — Reuse the existing `signals_json` pattern: `DimensionalScores.model_dump_json()` → TEXT column → `model_validate_json()` on read. No normalized table needed for MVP.

2. **Market regime on TickerScore** — Add `market_regime: MarketRegime | None` field to `TickerScore`. Derive from `signals.market_regime` using threshold mapping (>=80 CRISIS, >=60 VOLATILE, >=40 MEAN_REVERTING, <40 TRENDING). Persist as TEXT column.

3. **Server-side filtering** — Extend existing Python list comprehension filter chain in `api/routes/scan.py:get_scores()`. No SQL WHERE clauses needed — 5K tickers filter in <50ms in memory.

4. **Frontend-only presets** — Quick-filter presets are TypeScript constants, not API endpoints. Presets populate the advanced filter panel (user sees + can adjust what was applied).

5. **Pre-scan market cap: skip universe-wide TickerInfo fetch** — Market cap filtering uses the existing `TickerInfo` data fetched for enrichment in Phase 2. Tickers without TickerInfo pass through (no false exclusions). This avoids 5K API calls.

6. **Regime aggregation: mode** — Regime banner shows the most common `MarketRegime` across scored tickers (mode), not a weighted average.

## Technical Approach

### Backend (Wave 1)

- **Migration 015**: 3 `ALTER TABLE` statements adding `dimensional_scores_json TEXT`, `direction_confidence REAL`, `market_regime TEXT` to `ticker_scores`
- **Repository**: Extend `save_ticker_scores()` INSERT with 3 new columns. Extend `_row_to_ticker_score()` deserialization with NULL → None handling for pre-migration data
- **Pipeline Phase 2**: After `score_universe()`, call `compute_dimensional_scores(raw_signals)` and `compute_direction_signal()` for each ticker. Derive `market_regime` from `signals.market_regime` threshold mapping. Assign to `TickerScore` fields
- **Pipeline Phase 4**: No change needed — `save_ticker_scores()` already receives the full `TickerScore` objects; the repository extension handles the new columns
- **TickerScore model**: Add `market_regime: MarketRegime | None = None` field
- **ScanConfig**: Add `market_cap_tiers: list[MarketCapTier]`, `exclude_near_earnings_days: int | None`, `direction_filter: SignalDirection | None`, `min_iv_rank: float | None`

### API (Wave 1)

- **GET /api/scan/{id}/scores**: Add query params: `min_confidence`, `market_regime`, `min_trend`, `min_iv_vol`, `min_flow`, `min_risk`, `max_earnings_days`, `min_earnings_days`. Extend sort to support `direction_confidence`
- **POST /api/scan**: Extend `ScanRequest` with `market_cap_tiers`, `exclude_near_earnings_days`
- **TypeScript types**: Add `dimensional_scores?`, `direction_confidence?`, `market_regime?` to `TickerScore` interface

### Frontend (Wave 2-3)

- **ScanFilterPanel.vue**: Collapsible PrimeVue Panel with Slider/Select/InputNumber for dimensional scores, confidence, regime, earnings proximity. Debounced (300ms)
- **FilterPresets.vue**: 6 quick-filter buttons as TypeScript constants. Clicking populates the filter panel + triggers API reload
- **URL state sync**: All filter values serialized to URL query params via `router.replace()` (extend existing pattern)
- **ScanPage.vue**: Market cap MultiSelect + earnings proximity InputNumber for pre-scan narrowing
- **RegimeBanner.vue**: Color-coded banner above results with strategy hint text
- **DataTable enhancements**: Direction confidence sortable column, expandable rows with 8 bar segments, color-coded scores
- **TickerDrawer**: Dimensional score breakdown section

## Implementation Strategy

### Wave 1: Foundation (Tasks 1-2)
Task 1 wires DSE into the pipeline and persists data. Task 2 exposes it through the API with filtering. These must be sequential (2 depends on 1).

### Wave 2: Post-Scan Filtering (Task 3)
Frontend filter panel, quick-filter presets, and URL state sync. Depends on Task 2 (API params).

### Wave 3: Pre-Scan + Polish (Tasks 4-5)
Independent after Task 1. Pre-scan universe narrowing (config → pipeline → UI) and display polish (regime banner, score display, expandable rows).

### Dependency Graph
```
Task 1 (persist) → Task 2 (API) → Task 3 (post-scan UI)
Task 1 (persist) → Task 4 (pre-scan)
Task 1 (persist) → Task 5 (display polish)
```
Tasks 3, 4, 5 are independent of each other.

## Task Breakdown Preview

- [ ] **Task 1: Persist dimensional scores** — Migration 015, TickerScore.market_regime field, repository extension, pipeline Phase 2 DSE wiring (call compute_dimensional_scores + compute_direction_signal + market_regime derivation), Python tests (~35)
- [ ] **Task 2: API dimensional filtering** — GET scores query params (8 new filters + sort), ScanRequest pre-scan fields, server-side filter chain extension, TypeScript type updates, Python tests (~15)
- [ ] **Task 3: Post-scan filter UI** — ScanFilterPanel.vue (sliders, selects, debounce), FilterPresets.vue (6 presets as TS constants), URL state sync, E2E tests (~10)
- [ ] **Task 4: Pre-scan universe narrowing** — ScanConfig fields, pipeline Phase 1 market cap + earnings filtering, ScanPage.vue controls, CLI options (--market-cap, --exclude-earnings), Python tests (~15)
- [ ] **Task 5: Regime banner + score display** — RegimeBanner.vue (color-coded + strategy hints), DataTable expandable rows (8 bar segments), direction confidence column, TickerDrawer dimensional section, E2E tests (~6)

## Dependencies

### Internal (all exist — no new code needed)
- `DimensionalScores` model (`models/scoring.py`) — frozen, 8 fields, validated
- `DirectionSignal` model (`models/scoring.py`) — frozen, confidence [0-1]
- `MarketRegime` enum (`models/enums.py`) — 4 values
- `MarketCapTier` enum (`models/enums.py`) — 5 tiers
- `compute_dimensional_scores()` (`scoring/dimensional.py`) — imported in pipeline, not called
- `compute_direction_signal()` (`scoring/dimensional.py`) — imported in pipeline, not called
- `signals_json` persistence pattern (`repository.py`) — model_dump_json → TEXT → model_validate_json

### External
- None — all libraries already in use (PrimeVue Slider, Panel, MultiSelect, etc.)

## Success Criteria (Technical)

| Metric | Target | Verification |
|--------|--------|-------------|
| Dimensional scores persisted | All 8 families in every new scan | `SELECT dimensional_scores_json FROM ticker_scores` non-NULL |
| Direction confidence persisted | 0.0-1.0 on every ticker | `SELECT direction_confidence FROM ticker_scores` non-NULL |
| Market regime classified | One of 4 enum values per ticker | `SELECT market_regime FROM ticker_scores` non-NULL |
| API filtering latency | < 100ms for 5K tickers | Server-side list comprehension timing |
| Backward compatibility | Pre-migration scans display "--" | Load old scan, verify no errors |
| Quick-filter presets | 6 presets, one-click | E2E test clicks each preset |
| URL state persistence | Bookmarkable filter URLs | E2E test deep link |
| All existing tests pass | 0 regressions | `uv run pytest tests/ -v` |

## Estimated Effort

| Task | Backend LOC | Frontend LOC | Tests | Total |
|------|-------------|-------------|-------|-------|
| 1 Persist | ~120 | 0 | ~35 | ~155 |
| 2 API Filtering | ~50 | ~25 (TS types) | ~15 | ~90 |
| 3 Post-Scan UI | 0 | ~300 | ~10 E2E | ~310 |
| 4 Pre-Scan | ~80 | ~100 | ~15 | ~195 |
| 5 Display Polish | 0 | ~180 | ~6 E2E | ~186 |
| **Total** | **~250** | **~605** | **~81** | **~936** |

Medium-Large effort. Backend is small and low-risk (wiring existing functions). Frontend is the bulk (~65%).

## Tasks Created
- [ ] #222 - Persist dimensional scores in pipeline and database (parallel: false)
- [ ] #224 - API dimensional filtering and TypeScript types (parallel: false, depends: #222)
- [ ] #223 - Post-scan filter UI with presets and URL state (parallel: true, depends: #224)
- [ ] #225 - Pre-scan universe narrowing controls (parallel: true, depends: #222)
- [ ] #226 - Regime banner and dimensional score display (parallel: true, depends: #222)

Total tasks: 5
Parallel tasks: 3 (#223, #225, #226 — independent after their deps)
Sequential tasks: 2 (#222 → #224)
Estimated total effort: 30-40 hours

## Test Coverage Plan
Total test files planned: 8
Total test cases planned: ~81 (35 unit + 15 API + 10 E2E + 15 pipeline/model + 6 E2E)
