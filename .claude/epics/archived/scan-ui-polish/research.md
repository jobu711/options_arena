# Research: scan-ui-polish

## PRD Summary

Ground-up visual redesign of the pre-scan interface (`/scan`). Replace 3 PrimeVue Panel accordions with card-based dashboard layout: preset selection cards in a grid, flat always-visible filter sections, active filter summary chips with clear functionality, and a prominent centered launch area. Pure frontend — no backend changes.

## Relevant Existing Modules

- `web/src/pages/ScanPage.vue` (246 lines) — Main page: filter component, launch button, progress tracker, past scans table. Uses `useScanStore`, `useOperationStore`, `useWebSocket`.
- `web/src/components/scan/PreScanFilters.vue` (533 lines) — 3 PrimeVue Panel accordions with 12 filter `ref()` variables, `watch()` → `emitFilters()` pattern. Fetches `/api/universe/preset-info` and `/api/universe/sectors` on mount.
- `web/src/components/SectorTree.vue` (226 lines) — Hierarchical sector/industry group selection with PrimeVue Tree. `max-width: 500px` needs widening.
- `web/src/types/scan.ts` — `PreScanFilterPayload` interface (12 optional fields), `PresetInfo` interface.
- `web/e2e/fixtures/pages/scan.page.ts` — Page object: `selectPreset()` opens dropdown, clicks option.
- `web/e2e/suites/scan/prescan-filters.spec.ts` — 5 tests: preset badge, price/DTE ranges, score filter, panel collapse preservation.

## Existing Patterns to Reuse

### Card Pattern (AgentCard, SummaryCard, DashboardPage)
```css
background: var(--p-surface-800, #1a1a1a);
border: 1px solid var(--p-surface-700, #333);
border-radius: 0.5rem;
padding: 1rem;
```

### Section Title Pattern (DashboardPage, PreScanFilters)
```css
font-size: 0.85rem;
font-weight: 600;
color: var(--p-surface-300, #aaa);
text-transform: uppercase;
letter-spacing: 0.05em;
```

### Filter Label Pattern (PreScanFilters)
```css
font-size: 0.85rem;
color: var(--p-surface-300, #aaa);
margin-bottom: 0.35rem;
font-weight: 500;
```

### Accent Colors (variables.css)
- `--accent-blue: #3b82f6` — Selected preset card border + background tint
- `--accent-green: #22c55e` — Bullish direction chip
- `--accent-red: #ef4444` — Bearish direction chip
- `--accent-yellow: #eab308` — Neutral direction chip

### Hover Pattern (DashboardPage cards)
```css
:hover { border-color: var(--p-surface-500, #666); }
```

### Responsive Grid (DashboardPage config grid)
```css
grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
```

## Existing Code to Extend

- `PreScanFilters.vue` — All 12 `ref()` state variables, `watch()` watchers, `emitFilters()`, `fetchPresetInfo()`, `fetchSectors()` remain unchanged. Template restructured. Add `defineExpose({ clearFilter, clearAll })`.
- `ScanPage.vue` — Add template ref to PreScanFilters, import FilterSummaryChips, wrap launch in card section. Logic unchanged.
- `SectorTree.vue` — CSS-only: change `max-width: 500px` → `max-width: 100%`.
- `scan.page.ts` — `selectPreset()` method: change from dropdown click to `[data-testid="preset-card-{preset}"]` click.

## Preset Definitions (From PreScanFilters.vue + API)

| Preset ID | Label | Icon (PRD) | Description |
|-----------|-------|------------|-------------|
| `sp500` | S&P 500 | `pi-building` | Large-cap U.S. equities |
| `full` | Full Universe | `pi-globe` | All CBOE optionable tickers |
| `etfs` | ETFs | `pi-chart-bar` | Exchange-traded funds |
| `nasdaq100` | NASDAQ 100 | `pi-desktop` | Top NASDAQ-listed companies |
| `russell2000` | Russell 2000 | `pi-th-large` | Small-cap U.S. equities |
| `most_active` | Most Active | `pi-bolt` | Highest options volume today |

Counts fetched dynamically from `/api/universe/preset-info`.

## Data-TestID Attributes (Must Preserve)

### ScanPage
- `scan-title`, `start-scan-btn`, `scan-list-table`, `scan-list-empty`

### PreScanFilters
- `preset-selector` (move to `.preset-grid` container)
- `sector-tree`, `active-sector-filter`
- `market-cap-filter`, `direction-filter`, `earnings-filter`
- `iv-rank-filter`, `min-score-filter`
- `min-price-filter`, `max-price-filter`, `min-dte-filter`, `max-dte-filter`

### New (PRD)
- `preset-card-{preset}` on each PresetCard

## Potential Conflicts

1. **E2E panel expansion steps** — prescan-filters.spec.ts tests expand collapsed panels before setting inputs. With flat layout, these steps become unnecessary and will fail if kept. Mitigation: Remove panel expansion locators, interact with inputs directly.
2. **Preset selector testid** — Currently on `<Select>` dropdown. PRD moves it to `.preset-grid` container. Mitigation: Update scan.page.ts `selectPreset()` to click card by `preset-card-{preset}` testid.
3. **Panel collapse test** — Test #5 ("Panel collapse preserves filter state") tests accordion state persistence. No longer applicable. Mitigation: Delete or replace with equivalent "filters always visible" test.
4. **Badge count assertion** — Tests check `.p-badge` inside dropdown option. With cards, badge location changes. Mitigation: Update selectors to find count in PresetCard.
5. **PreScanFilters line count** — Currently 533 lines. Extracting PresetCard + FilterSummaryChips should reduce it to ~350-400 lines.

## Open Questions

1. **Preset descriptions** — PresetInfo from API includes `description` field. Should PresetCard display it, or use hardcoded descriptions? (PRD says "description" — likely use API response.)
2. **PrimeVue Button size="large"** — PRD assumes this prop exists in PrimeVue 4.x. Need to verify at implementation time. Fallback: custom CSS.

## Recommended Architecture

### New Component Tree
```
ScanPage.vue (~250 lines)
├── Page header (h1 + subtitle)
├── PreScanFilters (restructured)
│   ├── Section 1: Select Universe
│   │   └── PresetCard grid (6 cards)
│   ├── Section 2: Strategy (flat card)
│   │   └── CSS grid: MarketCap, Direction, IVRank, MinScore, Earnings
│   ├── Section 3: Price & Expiry (flat card)
│   │   └── CSS grid: MinPrice, MaxPrice, MinDTE, MaxDTE
│   └── Section 4: Sectors
│       └── SectorTree (Panel for collapse only)
├── FilterSummaryChips
│   ├── Removable chips for active filters
│   └── "Clear All" link (2+ chips)
├── Launch Section (styled card, centered)
│   └── Button size="large" severity="success"
├── ProgressTracker (when scanning)
└── Past Scans section (DataTable)
```

### Data Flow
```
PreScanFilters → emit('update:filters') → ScanPage.currentFilters
ScanPage.currentFilters → :filters prop → FilterSummaryChips
FilterSummaryChips → emit('clear-filter', key) → ScanPage → preFiltersRef.clearFilter(key)
FilterSummaryChips → emit('clear-all') → ScanPage → preFiltersRef.clearAll()
```

### defineExpose Pattern (New)
```typescript
// PreScanFilters.vue
function clearFilter(key: string): void {
  // Reset specific ref to default based on key
}
function clearAll(): void {
  // Reset all refs to defaults
}
defineExpose({ clearFilter, clearAll })
```

## Test Strategy Preview

### Existing Test Patterns
- Playwright with page object model (`web/e2e/fixtures/pages/`)
- `data-testid` selectors with self-healing fallbacks (text content, aria-label)
- API route interception for mock responses (`page.route()`)
- WebSocket mocking via `page.route` for `ws://` URLs

### E2E Changes Required
| File | Changes |
|------|---------|
| `scan.page.ts` | `selectPreset()`: click `[data-testid="preset-card-{preset}"]` instead of dropdown |
| `prescan-filters.spec.ts` | Remove panel expansion steps (3 tests affected). Remove panel collapse test. Update badge selectors for card layout. |

### Unaffected E2E Tests
- `scan-launch.spec.ts` — Interacts with start button and progress, not filters
- `scan-results-table.spec.ts` — Tests results page, not pre-scan
- `earnings-overlay.spec.ts` — Tests results page earnings column
- `scan-delta.spec.ts` — Tests scan comparison, not pre-scan

## Estimated Complexity

**M (Medium)** — 7 files changed (2 new, 5 modified), pure frontend, no backend changes, no new dependencies. All business logic unchanged. Main complexity is restructuring PreScanFilters template while preserving all state/emit logic and E2E compatibility.

### Effort Breakdown
- Wave 1 (PresetCard + FilterSummaryChips): ~80 + ~150 lines, straightforward
- Wave 2 (PreScanFilters restructure): Template rewrite, most complex wave
- Wave 3 (ScanPage layout): Minor additions
- Wave 4 (SectorTree CSS + E2E updates): Small changes
- Wave 5 (Verification): Build, typecheck, E2E
