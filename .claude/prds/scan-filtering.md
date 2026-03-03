---
name: scan-filtering
description: Enhanced pre-scan universe narrowing and post-scan result filtering via dimensional scores, quick-filter presets, and market regime awareness
status: planned
created: 2026-03-03T15:57:27Z
---

# PRD: scan-filtering

## Executive Summary

Options Arena computes 8 dimensional score families (trend, iv_vol, hv_vol, flow, microstructure, fundamental, regime, risk), direction confidence, and market regime classification for every ticker during scans — but none of this data reaches the web UI. The scan page offers only 3 universe presets (SP500/Full/ETFs) and a sector multi-select. After scanning, results show a single composite score with basic direction/search filtering.

This PRD delivers rich filtering at both stages: **pre-scan** (narrow the ~5,286 ticker universe before running) and **post-scan** (drill into results using dimensional scores, quick-filter strategy presets, and market regime context). The scoring data already exists — this is primarily a persistence + UI wiring effort.

## Problem Statement

A user scanning the full CBOE universe gets ~5,000 scored tickers back with no way to answer "where should I focus today given current market conditions?" The composite score is a single number that blends 8 dimensions — it cannot distinguish between a high-IV premium-selling setup and a strong-trend momentum play. Users need dimensional filtering to execute different strategies (credit spreads vs directional vs earnings plays) depending on market regime.

**Why now**: The Dimensional Scoring Engine (DSE) was built in Epic 16 (Market Recon) and computes all 8 family scores in Phase 2. The data is computed and discarded on every scan. Exposing it is low-risk, high-value.

## User Stories

### US-1: Post-Scan Quick Filtering by Strategy
**As** an options trader reviewing scan results,
**I want** one-click preset filters (e.g., "High IV Setups", "Momentum Plays", "Earnings Plays"),
**So that** I can instantly narrow 5,000 tickers to the ~50 most relevant for my current strategy.

**Acceptance Criteria**:
- At least 6 quick-filter presets available as buttons on the scan results page
- Clicking a preset applies curated filter combinations (dimensional score thresholds, direction, earnings proximity)
- Active preset is visually highlighted; "Clear" resets all filters
- Filter state persists in URL query params (bookmarkable, shareable)

### US-2: Post-Scan Dimensional Score Filtering
**As** an options trader,
**I want** slider controls for dimensional score families (Trend, IV/Vol, Flow, Risk),
**So that** I can compose custom filter combinations beyond the presets.

**Acceptance Criteria**:
- Collapsible "Advanced Filters" panel on scan results page
- Sliders for: min composite score, min direction confidence, min Trend, min IV/Vol, min Flow, min Risk
- Market regime dropdown (Trending / Mean Reverting / Volatile / Crisis / All)
- Earnings proximity filter (exclude within N days OR only within N days)
- Sliders debounced (300ms) to avoid excessive API calls
- All filters sync to URL query params

### US-3: Pre-Scan Universe Narrowing
**As** an options trader setting up a scan,
**I want** to narrow the universe by market cap tier and earnings proximity before scanning,
**So that** I don't waste time scoring tickers I'll never trade.

**Acceptance Criteria**:
- Market cap multi-select on scan page (Mega / Large / Mid / Small / Micro)
- "Exclude earnings within N days" input on scan page
- Pre-scan filters passed to pipeline and applied at appropriate phases
- Filters are optional — omitting them runs the full universe (backward compatible)

### US-4: Market Regime Context
**As** an options trader viewing scan results,
**I want** to see the current market regime classification at a glance,
**So that** I can choose the right strategy for current conditions.

**Acceptance Criteria**:
- Regime banner displayed above scan results (color-coded: green/blue/orange/red)
- Hint text suggests strategy alignment (e.g., "Volatile — favor premium selling")
- Regime derived from the dominant classification across scored tickers

### US-5: Dimensional Score Visibility
**As** an options trader evaluating a specific ticker,
**I want** to see the 8 dimensional score breakdown (not just the composite),
**So that** I can understand WHY a ticker scored high and which dimensions drive it.

**Acceptance Criteria**:
- Expandable row in DataTable showing 8 horizontal bar segments per ticker
- Direction confidence shown as a sortable column (percentage)
- TickerDrawer sidebar includes dimensional score breakdown section
- Scores color-coded: red (<30), yellow (30-60), green (>60)

## Requirements

### Functional Requirements

#### FR-1: Persist Dimensional Scores to Database
- Add SQL migration (015) with 3 new columns on `ticker_scores`: `dimensional_scores_json TEXT`, `direction_confidence REAL`, `market_regime TEXT`
- Repository persists/reads all 3 fields on `save_ticker_scores()` / `_row_to_ticker_score()`
- Old scans (pre-migration) return NULL — handled gracefully as None

#### FR-2: Expose Dimensional Scores in API
- `GET /api/scan/{id}/scores` response includes `dimensional_scores`, `direction_confidence`, `market_regime` on each `TickerScore`
- New query params: `min_confidence`, `market_regime`, `min_trend`, `min_iv_vol`, `min_flow`, `min_risk`, `max_earnings_days`, `min_earnings_days`
- Sort extended to support `direction_confidence` and `dim_*` family prefixes
- Filtering happens server-side in existing Python in-memory filter chain

#### FR-3: Derive Market Regime Classification
- Pipeline Phase 2 derives `MarketRegime` enum from `signals.market_regime` (normalized 0-100)
- Threshold mapping: >=80 CRISIS, >=60 VOLATILE, >=40 MEAN_REVERTING, <40 TRENDING
- Set on each `TickerScore` before persistence

#### FR-4: Quick-Filter Presets
- 6 presets: High IV Setups, Momentum Plays, Mean Reversion, Income/Theta, Earnings Plays, Low Risk
- Each preset is a named combination of filter parameter values
- Defined as a frontend constant (not persisted) — easy to tune
- Presets populate the advanced filter panel (user can see and adjust what was applied)

#### FR-5: Advanced Filter Panel (Post-Scan)
- Collapsible PrimeVue Panel with sliders, selects, and inputs
- All values sync to URL query params and trigger paginated API reload
- Debounced slider inputs (300ms)

#### FR-6: Pre-Scan Universe Controls
- `ScanConfig` extended with: `market_cap_tiers`, `exclude_near_earnings_days`, `direction_filter`, `min_iv_rank`
- `POST /api/scan` request accepts new fields
- Pipeline applies filters at appropriate phases (market cap in Phase 1, direction post-Phase 2, IV rank in Phase 3)

#### FR-7: Dimensional Score Display
- DataTable expandable rows with 8 bar segments
- Direction confidence as sortable column
- TickerDrawer dimensional scores section

#### FR-8: Regime Context Banner
- Color-coded banner above results showing dominant market regime
- Strategy hint text per regime

### Non-Functional Requirements

#### NFR-1: Performance
- Adding dimensional scores to API response adds ~72 bytes per ticker (~360KB for 5K tickers) — negligible
- Server-side filtering in Python memory remains sufficient for 5K tickers with additional fields
- Slider debounce (300ms) prevents excessive API calls

#### NFR-2: Backward Compatibility
- All new ScanConfig fields have None/empty defaults — existing scans are unaffected
- Old scan results (pre-migration) display "--" for missing dimensional data
- API response shape is additive (new fields only, no removals)

#### NFR-3: URL State Persistence
- All filter values serialized to URL query params (existing pattern)
- Browser back/forward preserves filter state
- Deep links work (shareable filtered result views)

## Success Criteria

| Metric | Target |
|--------|--------|
| Dimensional scores exposed in API | 100% of new scans include all 8 families |
| Quick-filter presets available | 6 presets, one-click application |
| Filter-to-results latency | < 500ms (server-side filter + render) |
| Pre-scan filter adoption | User can narrow universe by market cap and earnings |
| Regime classification accuracy | Matches computed signal thresholds consistently |
| Backward compatibility | Zero breaking changes to existing scan behavior |

## Constraints & Assumptions

- **SQLite persistence** — JSON blob for dimensional scores (consistent with `signals_json` pattern)
- **PrimeVue component library** — all new UI controls use existing PrimeVue primitives (Slider, Select, Panel, MultiSelect)
- **ScanResultsPage.vue is 915 lines** — must extract at least 2 components (ScanFilterPanel, FilterPresets) to manage complexity
- **Market cap tier requires TickerInfo** — pre-scan market cap filtering needs TickerInfo fetch, which is already done for top-N tickers but would need expansion for universe-wide filtering
- **IV rank filtering requires option chains** — only feasible in Phase 3 (top-N buffer), not universe-wide

## Out of Scope

- **Custom saved filter profiles** — defer to v2; presets are hardcoded in frontend for now
- **Composable AND/OR filter logic** — ThinkOrSwim-style filter groups (complex DSL, low ROI for MVP)
- **Regime-adaptive preset tuning** — presets don't auto-adjust based on regime (manual selection)
- **Backtesting filters** — "would this filter have caught NVDA last week?" (separate feature)
- **Real-time streaming filters** — WebSocket-based live filter updates (batch scan only)
- **Frontend unit tests (Vitest)** — E2E coverage via Playwright; Vitest deferred per project convention

## Dependencies

### Internal
- **DimensionalScores model** (`models/scoring.py:15`) — already exists, frozen, validated
- **MarketRegime enum** (`models/enums.py:141`) — already exists
- **MarketCapTier enum** (`models/enums.py`) — already exists
- **compute_dimensional_scores()** (`scoring/dimensional.py`) — already runs in Phase 2
- **DirectionSignal.confidence** (`models/scoring.py`) — already computed in pipeline
- **signals_json persistence pattern** (`repository.py:139`) — reuse for dimensional_scores_json
- **URL query param sync** (`ScanResultsPage.vue:331`) — extend existing pattern

### External
- None — all data sources and libraries already in use

## Implementation Waves

| Wave | Focus | Scope | Depends On |
|------|-------|-------|------------|
| 1 | Foundation: persist + expose dimensional data | Migration, repo, API, TypeScript types | Nothing |
| 2 | Post-scan filters: advanced panel + quick presets | UI components, API params | Wave 1 |
| 3 | Pre-scan filters: universe narrowing controls | Config, pipeline, ScanPage UI | Wave 1 |
| 4 | Polish: regime banner, confidence column, score display | Display components | Wave 1 |

Waves 2, 3, 4 are independent after Wave 1 — can be parallelized.

## Estimated Effort

| Wave | Backend | Frontend | Tests | Total |
|------|---------|----------|-------|-------|
| 1 Foundation | ~105 LOC | ~20 LOC | ~35 | ~160 |
| 2 Post-Scan Filters | ~20 LOC | ~260 LOC | ~10 E2E | ~290 |
| 3 Pre-Scan Filters | ~80 LOC | ~100 LOC | ~20 | ~200 |
| 4 Polish | 0 | ~210 LOC | ~6 E2E | ~216 |
| **Total** | **~205** | **~590** | **~71** | **~866** |
