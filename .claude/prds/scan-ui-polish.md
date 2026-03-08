---
name: scan-ui-polish
description: Ground-up visual redesign of the pre-scan interface — replace accordion panels with card-based dashboard layout, preset selection cards, flat filter sections, and active filter summary chips
status: planned
created: 2026-03-07T20:00:00Z
---

# PRD: scan-ui-polish

## Executive Summary

The pre-scan page (`/scan`) is the primary entry point for running options universe scans. The current UI uses 3 stacked PrimeVue Panel accordions — Strategy and Price & Expiry are collapsed by default, hiding important filters from users. The page has no visual hierarchy and looks like a generic settings form rather than a financial tool. This PRD redesigns the entire pre-scan interface with a clean dashboard style: preset selection as clickable cards in a grid, flat always-visible filter sections, active filter summary chips, and a prominent centered launch area.

## Problem Statement

### What problem are we solving?

1. **Hidden filters** — Strategy and Price & Expiry panels are collapsed by default. Users who don't click to expand them miss 8 of 12 available filter controls (market cap, direction, IV rank, min score, earnings exclusion, price range, DTE range).

2. **No visual impact** — The page is a plain `<h1>Scan</h1>` followed by stacked form elements. There's no visual hierarchy to guide the user through the scan configuration flow. The preset selector is a dropdown that doesn't communicate the differences between the 6 available presets.

3. **Poor scan configuration UX** — There's no summary of what filters are active before launching a scan. The "Run Scan" button floats as a small element with no visual emphasis. Users can't see at a glance what they've configured.

### Why is this important now?

- The scan page is the most visited page in the app — every analysis workflow starts here
- New users find the collapsed panels confusing (they don't know to expand them)
- The rest of the app (DashboardPage, DebateResultPage, ScanResultsPage) has received visual polish — the scan launcher is the last major UI that hasn't been updated

## User Stories

### US-1: Preset Selection Cards
**As a** user configuring a scan,
**I want** to see all 6 scan presets as visual cards with descriptions and ticker counts,
**So that** I can quickly understand and choose the right universe without opening a dropdown.

**Acceptance Criteria:**
- 6 cards displayed in a responsive grid (3 per row on desktop, 2 on tablet, 1 on mobile)
- Each card shows: icon, preset name, description, estimated ticker count
- Selected card has blue border accent + subtle background tint
- Cards are disabled during active scan
- Clicking a card selects it (replaces the current Select dropdown)

### US-2: Flat Filter Sections
**As a** user who needs to set price range or strategy filters,
**I want** all filter controls visible without expanding hidden panels,
**So that** I don't miss important configuration options.

**Acceptance Criteria:**
- Strategy filters (Market Cap, Direction, IV Rank, Min Score, Earnings exclusion) displayed in a flat card section with grid layout — always visible
- Price & Expiry filters (Min/Max Price, Min/Max DTE) displayed in a separate flat card section — always visible
- Sector filter (SectorTree) in its own section — the tree itself can be collapsible since it's large
- No PrimeVue Panel accordions wrapping the Strategy or Price & Expiry sections

### US-3: Active Filter Summary
**As a** user about to launch a scan,
**I want** to see a summary of all active filters as chips/tags before clicking Run,
**So that** I can verify my configuration at a glance.

**Acceptance Criteria:**
- Chip row displayed above the Run Scan button
- Each active filter rendered as a removable chip (e.g., "Bullish Only", "IV Rank > 30%", "$50 - $200", "3 Sectors")
- Clicking the X on a chip clears that individual filter
- "Clear All" link appears when 2+ filters are active
- Chips only shown for non-default filter values (preset is not shown as a chip)

### US-4: Prominent Launch Area
**As a** user ready to start a scan,
**I want** a visually prominent, centered launch section,
**So that** the primary action is unmistakable.

**Acceptance Criteria:**
- Launch button centered in a styled card section
- Button is `size="large"` with scan icon
- When scanning: ProgressTracker replaces the launch area
- Filter summary chips appear above the button in the same card

## Requirements

### Functional Requirements

#### FR-1: PresetCard Component
- New `web/src/components/scan/PresetCard.vue` component
- Props: `preset: string`, `label: string`, `description: string`, `count: number`, `icon: string`, `selected: boolean`, `disabled: boolean`
- Emits: `select: [preset: string]`
- Visual states: default (dark card), selected (blue border + tint), hover (lighter border), disabled (opacity 0.5)
- Icons mapped per preset:
  - `sp500` → `pi-building`
  - `full` → `pi-globe`
  - `etfs` → `pi-chart-bar`
  - `nasdaq100` → `pi-desktop`
  - `russell2000` → `pi-th-large`
  - `most_active` → `pi-bolt`
- `data-testid="preset-card-{preset}"` on each card

#### FR-2: FilterSummaryChips Component
- New `web/src/components/scan/FilterSummaryChips.vue` component
- Props: `filters: PreScanFilterPayload`, `sectorCount: number`, `industryGroupCount: number`, `disabled: boolean`
- Emits: `clear-filter: [key: string]`, `clear-all: []`
- Chip generation logic:
  - `direction_filter` → "Bullish Only" / "Bearish Only" / "Neutral Only"
  - `market_cap_tiers` → "Mega, Large" (comma-separated, capitalized)
  - `min_iv_rank` → "IV Rank > {N}%"
  - `min_score` → "Score > {N}"
  - `exclude_near_earnings_days` → "Exclude {N}d Earnings"
  - `min_price` + `max_price` → "$50 - $200" or "Min $50" or "Max $200"
  - `min_dte` + `max_dte` → "DTE 14d - 90d" or "DTE > 14d" or "DTE < 90d"
  - `sectorCount` → "3 Sectors"
  - `industryGroupCount` → "2 Industry Groups"
- Each chip has a close (X) button
- "Clear All" link at end when 2+ chips

#### FR-3: PreScanFilters Restructure
- Remove 3 PrimeVue Panel accordions from template
- Replace with 4 flat sections:
  1. **Select Universe** — preset grid using PresetCard components
  2. **Strategy** — flat card with CSS grid of filter controls (Market Cap, Direction, IV Rank, Min Score, Earnings)
  3. **Price & Expiry** — flat card with CSS grid (Min/Max Price, Min/Max DTE)
  4. **Sectors** — SectorTree in its own section
- All 12 `ref()` state variables, `watch()`, `emitFilters()`, API fetches unchanged
- Add `defineExpose({ clearFilter, clearAll })` for parent component to reset individual filters
- Preserve all existing `data-testid` attributes on input elements
- Move `data-testid="preset-selector"` to the `.preset-grid` container

#### FR-4: ScanPage Layout Update
- Page header with title + subtitle description
- FilterSummaryChips component between filters and launch button
- Template ref on PreScanFilters for `clearFilter`/`clearAll` calls
- Launch button in a styled card section, centered
- Past Scans section with header showing scan count

#### FR-5: SectorTree Style Update
- Widen `max-width` from `500px` to `100%` to span full filter section
- Adjust Panel background to blend with parent card section

### Non-Functional Requirements

#### NFR-1: Responsive Layout
- Preset grid: `grid-template-columns: repeat(auto-fill, minmax(220px, 1fr))` — 3 columns on desktop, 2 on tablet, 1 on mobile
- Filter grids: `grid-template-columns: repeat(auto-fill, minmax(200px, 1fr))` — natural responsive reflow
- No media queries needed — CSS grid `auto-fill` + `minmax` handles responsiveness

#### NFR-2: Visual Consistency
- All new styles use existing CSS custom properties (accent colors, surface scale, font-mono)
- Card pattern: `background: var(--p-surface-800)`, `border: 1px solid var(--p-surface-700)`, `border-radius: 0.5rem`, `padding: 1rem`
- Section titles: `font-size: 0.85rem`, `font-weight: 600`, `color: var(--p-surface-300)`, `text-transform: uppercase`, `letter-spacing: 0.05em`
- Transitions: `0.15s` for border-color and background changes
- All `<style scoped>` — no global CSS additions
- Selected preset: `border-color: var(--accent-blue)`, `background: rgba(59, 130, 246, 0.08)`

#### NFR-3: E2E Test Compatibility
- All existing `data-testid` attributes preserved on input elements
- `scan.page.ts` page object updated: `selectPreset()` clicks card instead of dropdown
- `prescan-filters.spec.ts` updated: remove panel expansion steps (filters always visible), update preset badge assertions, rewrite panel-collapse test

#### NFR-4: No Business Logic Changes
- All filter emit/watch/API logic unchanged
- No changes to scan store, WebSocket flow, operation lock, or backend API contracts
- Pure presentation-layer changes

## Success Criteria

| Metric | Target |
|--------|--------|
| All 12 filters visible without expanding panels | Yes |
| Preset selection via visual cards | Yes |
| Active filter summary chips displayed before launch | Yes |
| Filter clear via chip X button works | Yes |
| All E2E tests in `suites/scan/` pass | Yes |
| Frontend builds with no TypeScript errors | Yes |
| Responsive at 375px, 768px, 1024px, 1440px | Yes |

## Constraints & Assumptions

### Constraints
- Must use existing PrimeVue components and CSS custom properties — no new UI libraries
- All `data-testid` attributes must be preserved for E2E test compatibility
- ScanPage must remain < 350 lines (extract components if needed)
- No changes to Python backend or API contracts

### Assumptions
- PrimeIcons include `pi-building`, `pi-globe`, `pi-chart-bar`, `pi-desktop`, `pi-th-large`, `pi-bolt`
- PrimeVue Button `size="large"` prop is available in PrimeVue 4.x
- `defineExpose()` works correctly with template refs in Vue 3.5+

## Out of Scope

- **Animation/transitions** on page load or filter changes — keep it clean and simple
- **Preset comparison view** (side-by-side metric comparison) — future enhancement
- **Filter presets/saved configurations** — future enhancement
- **Drag-to-reorder filter sections** — unnecessary complexity
- **Dark/light mode toggle** — dark mode only (financial tool convention)

## Dependencies

### Internal
- `PreScanFilterPayload` type in `web/src/types/index.ts` — used by FilterSummaryChips
- PrimeVue Button, Select, MultiSelect, InputNumber, Badge — existing imports
- PrimeIcons — existing dependency
- `useWebSocket`, `useScanStore`, `useOperationStore` — existing composables/stores (no changes)

### External
- None — pure frontend changes using existing dependencies

## Technical Design Reference

### File Changes

| File | Action | Purpose |
|------|--------|---------|
| `web/src/components/scan/PresetCard.vue` | **Create** | Clickable preset card with icon, name, description, count, selected state |
| `web/src/components/scan/FilterSummaryChips.vue` | **Create** | Active filter chips with clear functionality |
| `web/src/components/scan/PreScanFilters.vue` | **Edit** | Remove Panel accordions, add preset grid + flat filter sections + defineExpose |
| `web/src/pages/ScanPage.vue` | **Edit** | Page header, FilterSummaryChips, launch card section, template ref |
| `web/src/components/SectorTree.vue` | **Edit** | CSS: widen max-width, blend Panel with parent |
| `web/e2e/fixtures/pages/scan.page.ts` | **Edit** | Update selectPreset() for card-based selection |
| `web/e2e/suites/scan/prescan-filters.spec.ts` | **Edit** | Remove panel expansion steps, update assertions |

### Implementation Waves

| Wave | Tasks | Can Parallelize? |
|------|-------|-----------------|
| 1 | Create PresetCard.vue, Create FilterSummaryChips.vue | Yes (independent components) |
| 2 | Restructure PreScanFilters.vue template + styles + defineExpose | After Wave 1 |
| 3 | Restructure ScanPage.vue layout + imports + logic | After Wave 2 |
| 4 | SectorTree.vue CSS + E2E test updates | After Wave 3 |
| 5 | Build, typecheck, run E2E tests, visual verification | After Wave 4 |
