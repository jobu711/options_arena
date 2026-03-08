---
name: scan-ui-polish
status: backlog
created: 2026-03-07T16:58:08Z
progress: 0%
prd: .claude/prds/scan-ui-polish.md
github: https://github.com/jobu711/options_arena/issues/335
---

# Epic: scan-ui-polish

## Overview

Visual redesign of the pre-scan page (`/scan`). Replace 3 PrimeVue Panel accordions with a card-based dashboard: clickable preset cards in a responsive grid, flat always-visible filter sections, removable filter summary chips, and a prominent centered launch area. Pure presentation-layer changes — all business logic, stores, API contracts, and WebSocket flows unchanged.

## Architecture Decisions

- **No new dependencies** — uses existing PrimeVue components (Button, Badge, InputNumber, Select, MultiSelect, Tree) and CSS custom properties from `variables.css`
- **Component extraction** — PresetCard and FilterSummaryChips as new leaf components; keeps PreScanFilters and ScanPage under line limits
- **defineExpose for filter clearing** — ScanPage gets a template ref to PreScanFilters; chip clear events flow: FilterSummaryChips → ScanPage → PreScanFilters.clearFilter(key)
- **CSS Grid responsive** — `repeat(auto-fill, minmax())` for all grids; no media queries needed
- **Scoped CSS only** — no global style changes; all new styles follow existing card/section patterns

## Technical Approach

### Component Tree (Post-Redesign)
```
ScanPage.vue (~280 lines)
├── Page header (h1 + subtitle)
├── PreScanFilters (restructured, ~400 lines)
│   ├── Preset grid → PresetCard × 6
│   ├── Strategy section (flat card, CSS grid)
│   ├── Price & Expiry section (flat card, CSS grid)
│   └── Sectors section → SectorTree
├── FilterSummaryChips (~120 lines)
├── Launch section (styled card, centered button)
├── ProgressTracker (when scanning)
└── Past Scans (DataTable)
```

### Data Flow
```
PreScanFilters → emit('update:filters') → ScanPage.currentFilters
ScanPage.currentFilters → :filters prop → FilterSummaryChips
FilterSummaryChips → emit('clear-filter') → ScanPage → preFiltersRef.clearFilter(key)
FilterSummaryChips → emit('clear-all') → ScanPage → preFiltersRef.clearAll()
```

### Key Patterns
- **Card styling**: `background: var(--p-surface-800)`, `border: 1px solid var(--p-surface-700)`, `border-radius: 0.5rem`, `padding: 1rem`
- **Selected preset**: `border-color: var(--accent-blue)`, `background: rgba(59, 130, 246, 0.08)`
- **Section titles**: `0.85rem`, uppercase, `letter-spacing: 0.05em`, `var(--p-surface-300)`

## Task Breakdown

- [ ] Task 1: Create PresetCard.vue — clickable card with icon, label, description, count, selected/disabled states
- [ ] Task 2: Create FilterSummaryChips.vue — generate chips from PreScanFilterPayload, removable with X, "Clear All" link
- [ ] Task 3: Restructure PreScanFilters.vue — remove 3 Panel accordions, replace with preset grid + flat Strategy/Price sections, add defineExpose({ clearFilter, clearAll })
- [ ] Task 4: Update ScanPage.vue — page header, template ref on PreScanFilters, FilterSummaryChips integration, launch card section
- [ ] Task 5: Update SectorTree.vue CSS — widen max-width to 100%, blend Panel with parent card
- [ ] Task 6: Update E2E tests — scan.page.ts selectPreset() for cards, prescan-filters.spec.ts remove panel expansion steps and collapse test
- [ ] Task 7: Build verification — TypeScript build, E2E tests pass, visual check at 375/768/1024/1440px

## Dependencies

### Internal (all existing, no changes)
- `PreScanFilterPayload` type in `web/src/types/scan.ts`
- PrimeVue Button, Select, MultiSelect, InputNumber, Badge, Tree
- PrimeIcons: `pi-building`, `pi-globe`, `pi-chart-bar`, `pi-desktop`, `pi-th-large`, `pi-bolt`
- Stores: `useScanStore`, `useOperationStore`
- API: `/api/universe/preset-info`, `/api/universe/sectors`

### External
- None

## Success Criteria (Technical)

| Gate | Target |
|------|--------|
| All 12 filters visible without panel expansion | Yes |
| Preset cards render with icon, name, description, count | Yes |
| Selected preset card has blue accent border | Yes |
| Filter summary chips display for non-default filters | Yes |
| Chip X clears individual filter | Yes |
| "Clear All" clears all filters | Yes |
| `npm run build` passes (no TS errors) | Yes |
| All E2E tests in `suites/scan/` pass | Yes |
| All existing `data-testid` attributes preserved | Yes |
| Responsive at 375px, 768px, 1024px, 1440px | Yes |

## Tasks Created
- [ ] #336 - Create PresetCard.vue component (parallel: true)
- [ ] #337 - Create FilterSummaryChips.vue component (parallel: true)
- [ ] #338 - Restructure PreScanFilters.vue + SectorTree CSS (depends: #336)
- [ ] #339 - Update ScanPage.vue layout + FilterSummaryChips integration (depends: #337, #338)
- [ ] #340 - Update E2E tests + build verification (depends: #338, #339)

Total tasks: 5
Parallel tasks: 2 (#336, #337)
Sequential tasks: 3 (#338 → #339 → #340)
Estimated total effort: 10 hours

## Test Coverage Plan
Total test files planned: 2 (E2E only — scan.page.ts, prescan-filters.spec.ts)
Total test cases planned: 5 (updated E2E tests)

## Estimated Effort

**Medium** — 7 files (2 new, 5 modified), pure frontend, no backend. 5 tasks across 2 waves (parallel leaf components, then sequential integration). Main complexity: PreScanFilters template restructure while preserving 12 refs, watchers, and emission logic.
