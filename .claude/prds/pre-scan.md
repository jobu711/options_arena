---
name: pre-scan
description: Redesigned pre-scan filter panel with collapsible sections, 3 new presets, price/DTE range filters, estimated ticker counts, and educational descriptions
status: planned
created: 2026-03-06T14:07:56Z
---

# PRD: pre-scan

## Executive Summary

ScanPage.vue (398 lines) has all pre-scan filter controls inline with no visual grouping, no educational text, and only 3 preset options (SP500/Full/ETFs). Users lack price range and DTE range controls, and there's no estimated ticker count feedback to help gauge scan scope before launching.

This PRD delivers a redesigned pre-scan filter panel extracted into a new `PreScanFilters.vue` component with 3 collapsible sections (Universe, Strategy, Price & Expiry), 3 new universe presets (Nasdaq 100, Russell 2000, Most Active), 2 new filters (price range, DTE range), estimated ticker counts per preset, and educational descriptions on every control. The result should feel like a modern SaaS filter panel (Linear/Notion aesthetic) within the PrimeVue Aura dark theme.

## Problem Statement

**No visual grouping**: 8 filter controls are laid out in flat rows with no semantic organization. A user scanning for the first time has no guidance on what each filter does or how they relate.

**Missing presets**: Only 3 universe presets (SP500, Full, ETFs). Traders commonly want Nasdaq 100 (tech-heavy growth), Russell 2000 (small-cap alpha), and most-active options tickers (tight spreads, high volume). Every commercial screener offers these.

**No price range control**: `ScanConfig.min_price` defaults to $10 but is invisible to users. There's no max price filter. A trader screening for stocks in the $50–$200 range (optimal for defined-risk strategies) cannot express this.

**No DTE range control**: `PricingConfig.dte_min/dte_max` (30–365 days) control contract selection but aren't user-adjustable. Traders using weekly options (7–14 DTE) or LEAPs (180+ DTE) have no way to target their preferred expiration window.

**No scope feedback**: Users launch scans with no idea how many tickers will be processed. A full-universe scan is ~5,000 tickers (slow); an SP500 scan is ~500 (fast). This information exists in the backend but isn't surfaced.

**Bloated page component**: ScanPage.vue at 398 lines violates the project's <150-line page guideline. Filter state, options arrays, and template markup are all inline.

**Why now**: All infrastructure exists — ScanConfig, ScanRequest, universe service with caching, metadata index with market cap tiers. This is primarily a UI extraction + 2 new config fields + 3 new fetch methods.

## User Stories

### US-1: Collapsible Filter Sections

**As** an options trader setting up a scan,
**I want** filters organized into logical collapsible sections,
**So that** I can focus on the controls relevant to my current decision without visual clutter.

**Acceptance Criteria**:
- Three sections: "Universe" (expanded), "Strategy" (expanded), "Price & Expiry" (collapsed)
- Each section header shows a badge with count of active (non-default) filters
- Clicking a section header toggles expand/collapse
- Uses PrimeVue Panel with `:toggleable="true"` (project pattern)

### US-2: Expanded Preset Options

**As** an options trader,
**I want** 6 universe presets including Nasdaq 100, Russell 2000, and Most Active,
**So that** I can quickly target the ticker universe matching my trading strategy.

**Acceptance Criteria**:
- 6 presets: S&P 500, Full Universe, ETFs, Nasdaq 100, Russell 2000, Most Active
- Each preset shows label and estimated ticker count badge (e.g., "S&P 500 ~503")
- Selected preset description shown as muted text below selector
- S&P 500 remains the default
- New presets backed by corresponding backend fetch methods with 24h caching

### US-3: Price Range Filter

**As** a trader targeting stocks in a specific price range,
**I want** min and max price inputs,
**So that** I can filter out penny stocks (below $10) or expensive names (above $500) before scanning.

**Acceptance Criteria**:
- Min Price InputNumber (default: $10, existing `ScanConfig.min_price`)
- Max Price InputNumber (default: empty = no limit)
- Applied during Phase 3 liquidity pre-filter alongside existing `min_price` check
- Both values sent in `POST /api/scan` request body
- Validation: min_price >= 0, max_price >= min_price when both set

### US-4: DTE Range Filter

**As** a trader with a specific expiration target,
**I want** min and max DTE (days to expiration) inputs,
**So that** I can target weeklies (7–14 DTE), monthlies (30–60 DTE), or LEAPs (180+ DTE).

**Acceptance Criteria**:
- Min DTE InputNumber (default: empty = use PricingConfig.dte_min = 30)
- Max DTE InputNumber (default: empty = use PricingConfig.dte_max = 365)
- When set, overrides `PricingConfig.dte_min/dte_max` for contract selection in Phase 3
- Validation: min_dte >= 0, max_dte >= 1, min_dte <= max_dte when both set

### US-5: Estimated Ticker Count

**As** a user configuring scan filters,
**I want** to see how many tickers will be scanned before I click Run,
**So that** I can gauge scan duration and adjust filters to narrow or widen scope.

**Acceptance Criteria**:
- Each preset option displays estimated ticker count from `GET /api/universe/preset-info`
- Counts fetched once on page load, not on every filter change
- Counts come from cached metadata (fast), not live API queries
- Display format: "~503" with "estimated" label (clearly approximate)

### US-7: Slim ScanPage

**As** a developer maintaining the codebase,
**I want** ScanPage.vue under 150 lines with filter logic extracted,
**So that** the page follows project conventions and is easier to modify.

**Acceptance Criteria**:
- New `PreScanFilters.vue` component owns all filter state and controls
- ScanPage composes PreScanFilters + Run button + ProgressTracker + Past Scans table
- PreScanFilters emits single `@update:filters` event with complete typed payload
- All existing `data-testid` attributes preserved for E2E test compatibility

## Requirements

### Functional Requirements

#### FR-1: New ScanPreset Members
- Add `NASDAQ100 = "nasdaq100"`, `RUSSELL2000 = "russell2000"`, `MOST_ACTIVE = "most_active"` to `ScanPreset` StrEnum in `models/enums.py`
- Pipeline dispatch handles all 6 presets in `scan/pipeline.py`
- CLI help text updated in `cli/commands.py`

#### FR-2: New ScanConfig Fields
- Add to `ScanConfig` in `models/config.py`:
  - `max_price: float | None = None` — validator: `math.isfinite(v) and v >= 0`
  - `min_dte: int | None = None` — validator: `0 <= v <= 730`
  - `max_dte: int | None = None` — validator: `1 <= v <= 730`
- Cross-field model_validator: `min_dte <= max_dte`, `max_price >= min_price`

#### FR-3: Extended ScanRequest & Override Wiring
- Add `min_price`, `max_price`, `min_dte`, `max_dte` to `ScanRequest` in `api/schemas.py`
- Wire into `scan_overrides` dict in `api/routes/scan.py` (conditional pattern)
- Forward `min_dte`/`max_dte` to `PricingConfig.dte_min`/`dte_max` via immutable copy

#### FR-4: Universe Service — New Fetch Methods
- `fetch_nasdaq100_constituents() -> list[str]`: GitHub CSV + CBOE cross-reference, 24h cache, curated fallback
- `fetch_russell2000_tickers() -> list[str]`: Metadata index query for `market_cap_tier == SMALL`, intersect CBOE optionable, 24h cache
- `fetch_most_active() -> list[str]`: Curated seed list (~250 high-volume names), CBOE cross-reference, 24h cache

#### FR-5: Preset-Info Endpoint
- `GET /api/universe/preset-info` returns `list[PresetInfo]` with `preset`, `label`, `description`, `estimated_count`
- Uses `asyncio.gather` for parallel count fetches
- New `PresetInfo` response model in `api/schemas.py`

#### FR-6: Pipeline Integration
- `max_price` filter: Phase 3 liquidity pre-filter (`pipeline.py` ~line 604), alongside existing `min_price`
- 3 new preset dispatch branches in `pipeline.py` (~line 305)
- DTE forwarding: scan route builds `pricing_override` when `min_dte`/`max_dte` set

#### FR-7: PreScanFilters.vue Component
- 3 collapsible Panel sections with active filter count badges
- Preset selector with ticker count badges and description
- Reuses SectorTree.vue and ThemeChips.vue as-is (unchanged interfaces)
- New: min/max price InputNumber, min/max DTE InputNumber
- Emits `PreScanFilterPayload` typed object on any change
- Educational description line beneath each control

#### FR-8: ScanPage Refactor
- Extract filters → PreScanFilters, page reduced from 398 → ~130 lines
- Page fetches presetInfos, sectorHierarchy, themes on mount
- Composes PreScanFilters + Button + ProgressTracker + Past Scans DataTable

### Non-Functional Requirements

#### NFR-1: Performance
- Preset-info endpoint: parallel fetches, returns from 24h cache (~50ms)
- No new API calls on filter change — counts from cached data
- PreScanFilters is a single component render, no deep tree

#### NFR-2: Backward Compatibility
- All new config fields default to `None` — existing scans unchanged
- All new ScanRequest fields are optional — existing API callers unaffected
- Existing E2E tests pass without modification (data-testid preserved)
- Existing 3 presets unchanged in behavior

#### NFR-3: Accessibility
- Panel sections keyboard-navigable (PrimeVue built-in)
- Filter descriptions provide context for screen readers
- Badge counts announce active filter state

## Success Criteria

| Metric | Target |
|--------|--------|
| ScanPage.vue line count | < 150 (down from 398) |
| Preset options available | 6 (up from 3) |
| New filter controls | 4 (min price, max price, min DTE, max DTE) |
| Estimated counts shown | Yes, per preset |
| Existing E2E tests | All pass, no modifications |
| Zero regressions | All 3,921+ existing tests pass |

## Constraints & Assumptions

- **Russell 2000 is approximate**: Uses metadata index `market_cap_tier == SMALL` as proxy. Not the official Russell 2000 index composition. Label clearly states "Small-cap equities" not "Russell 2000 Index."
- **Most Active is curated**: Static seed list of ~250 names. Updated manually, not dynamically ranked by volume. Acceptable for a single-user tool.
- **Nasdaq 100 CSV source**: Depends on external GitHub-hosted CSV. Curated fallback list if fetch fails.
- **PrimeVue Panel**: Project standard for collapsible sections. Not Accordion (not used elsewhere).
- **ScanPage < 150 lines**: Strict target per `web/CLAUDE.md` convention. Achieved by moving all filter state and controls into PreScanFilters.
- **DTE override vs default**: When user sets DTE range via UI, it overrides `PricingConfig.dte_min/dte_max` for that scan only. Default scans still use PricingConfig defaults (30–365).

## Out of Scope

- **Saved scan presets** — Persisting named filter configurations for one-click recall. Separate PRD.
- **Dynamic "most active" ranking** — Real-time volume-based ranking requires market data at universe level. Curated list is sufficient for now.
- **PCR / unusual activity filters** — Post-scan dimensional filters, separate feature.
- **Dollar volume slider** — Adjustable `min_dollar_volume` threshold. Separate feature.
- **Sort fixes** — Column sorting for sector/direction/earnings. Separate issue.
- **Frontend unit tests (Vitest)** — E2E via Playwright per project convention.
- **Preset-adaptive filter defaults** — Presets don't auto-adjust other filter values.

## Dependencies

### Internal
- **`ScanConfig`** (`models/config.py`) — extend with `max_price`, `min_dte`, `max_dte`
- **`ScanPreset`** (`models/enums.py`) — add 3 new members
- **`ScanRequest`** (`api/schemas.py`) — add 4 new fields + `PresetInfo` model
- **`scan route`** (`api/routes/scan.py`) — override wiring + pricing forwarding
- **`universe route`** (`api/routes/universe.py`) — new preset-info endpoint
- **`UniverseService`** (`services/universe.py`) — 3 new fetch methods
- **`ScanPipeline`** (`scan/pipeline.py`) — 3 new preset branches + max_price filter
- **`CLI commands`** (`cli/commands.py`) — help text + list branches
- **`SectorTree.vue`** (`components/SectorTree.vue`) — reuse as-is
- **`ThemeChips.vue`** (`components/scan/ThemeChips.vue`) — reuse as-is
- **`scan.ts` store** (`stores/scan.ts`) — extend `StartScanOptions`
- **`scan.ts` types** (`types/scan.ts`) — add `PresetInfo`, `PreScanFilterPayload`

### External
- Nasdaq-100 CSV from GitHub/datahub (with curated fallback)
- No new package dependencies

## Implementation Waves

| Wave | Focus | Scope | Depends On |
|------|-------|-------|------------|
| 1 | Backend foundation: enums, config, schemas, route wiring | ~95 LOC Python | Nothing |
| 2 | Universe service: 3 fetch methods, preset-info endpoint | ~180 LOC Python | Wave 1 |
| 3 | Pipeline: 3 preset branches, max_price filter, CLI | ~45 LOC Python | Wave 1 |
| 4 | Frontend: types, store, PreScanFilters.vue, ScanPage refactor | ~330 LOC TS/Vue, -270 LOC removed | Wave 1 |

Waves 2, 3, 4 are independent after Wave 1.

## Estimated Effort

| Wave | Backend | Frontend | Tests | Total |
|------|---------|----------|-------|-------|
| 1 Backend Foundation | ~95 LOC | 0 | ~30 | ~125 |
| 2 Universe Service | ~180 LOC | 0 | ~25 | ~205 |
| 3 Pipeline + CLI | ~45 LOC | 0 | ~15 | ~60 |
| 4 Frontend | 0 | ~330 LOC | ~4 E2E | ~334 |
| **Total** | **~320** | **~330** | **~74** | **~724** |

## Risk Register

| Risk | Severity | Mitigation |
|------|----------|------------|
| Nasdaq 100 CSV source unreliable | MEDIUM | Curated fallback list of ~100 names if fetch fails |
| Russell 2000 approximation inaccurate | LOW | Label says "Small-cap equities" not "Russell 2000 Index". Metadata-based, updates with index rebuilds |
| Most Active list goes stale | LOW | Curated list of blue-chip high-volume names. These rarely change. Updated manually per release |
| DTE override conflicts with PricingConfig | LOW | Explicit forwarding in scan route. Documented override precedence. Only overrides for that scan |
| data-testid breakage in E2E tests | MEDIUM | Explicit preservation checklist. Grep verification before/after |
| PreScanFilters.vue exceeds line count | LOW | Target ~300 lines. Can extract section sub-components if needed |
| Preset-info endpoint slow on cold cache | MEDIUM | Uses `asyncio.gather` for parallel fetches. All methods cache for 24h |
