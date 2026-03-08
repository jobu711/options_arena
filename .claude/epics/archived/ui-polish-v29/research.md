# Research: ui-polish-v29

## PRD Summary

Three independent UI polish items plus a scan duration display:
1. **Score filter 10x bug (F1)** — `PreScanFilters.vue:374` has `:max="10"` but composite scores are 0–100. Step is 0.5 (should be 5). Description says "(0-10)".
2. **Contracts in TickerDrawer (F5)** — Add recommended contracts section fetching from existing `/api/analytics/ticker/{ticker}/contracts` endpoint.
3. **"View All Debates" link (F13)** — Add link on DashboardPage recent debates section to full debate history.
4. **Scan duration display** — Compute and show `completed_at - started_at` on scan list items.

## Relevant Existing Modules

- `web/src/components/scan/PreScanFilters.vue` — Score filter bug location (lines 369-383)
- `web/src/components/TickerDrawer.vue` — Drawer with indicators, debates, history. Needs contracts section.
- `web/src/pages/DashboardPage.vue` — Recent debates (lines 407-429), latest scan card (lines 305-324)
- `web/src/pages/ScanPage.vue` — Scan list DataTable with columns: ID, Preset, Scanned, Scored, Recs, Date (lines 152-194)
- `web/src/types/scan.ts` — `ScanRun` (lines 2-11), `RecommendedContract` (lines 99-122), `PreScanFilterPayload` (lines 145-160)
- `web/src/router/index.ts` — 7 routes, NO `/debates` route exists
- `web/src/composables/useApi.ts` — Typed `api<T>()` fetch wrapper
- `web/src/stores/scan.ts` — `useScanStore` with `fetchScans()`, `latestScan` computed
- `web/src/stores/debate.ts` — `useDebateStore` with `fetchDebates(limit)` action

## Existing Patterns to Reuse

### TickerDrawer Parallel Data Loading
```typescript
// web/src/components/TickerDrawer.vue (lines 70-118)
watch(() => props.score?.ticker, async (ticker) => {
  const [debateData, historyData] = await Promise.all([
    api<DebateResultSummary[]>('/api/debate', { params: { ticker, limit: 5 } }),
    api<HistoryPoint[]>(`/api/ticker/${ticker}/history`, { params: { limit: 20 } })
  ])
})
```
**Apply**: Add third parallel fetch for contracts endpoint.

### Duration Formatting (DebateResultPage.vue)
```typescript
// web/src/pages/DebateResultPage.vue (lines 38-40)
function formatDuration(ms: number): string {
  if (ms < 1000) return `${ms}ms`
  return `${(ms / 1000).toFixed(1)}s`
}
```
**Apply**: Adapt for scan duration (minutes+seconds format instead of ms/seconds).

### DirectionBadge Component
Already used in TickerDrawer and ScanResultsPage — reuse for contract direction display.

### PrimeVue Tag Component
Used across app for categorical badges (call/put, bullish/bearish). Reuse for contract option_type.

### Section Header Pattern (DashboardPage)
```vue
<section class="section">
  <h2>Recent Debates</h2>
  <!-- content -->
</section>
```
**Apply**: Add "View All" RouterLink in header, using flex layout with `justify-content: space-between`.

## Existing Code to Extend

| File | What Exists | What Changes |
|------|-------------|--------------|
| `PreScanFilters.vue:374-375` | `:max="10"`, `:step="0.5"` | → `:max="100"`, `:step="5"` |
| `PreScanFilters.vue:376-377` | `:minFractionDigits="1"`, `:maxFractionDigits="1"` | → `0`, `0` |
| `PreScanFilters.vue:383` | `"(0-10)"` | → `"(0-100)"` |
| `TickerDrawer.vue` (watch) | 2-item `Promise.all` | Add 3rd fetch for contracts |
| `TickerDrawer.vue` (template) | Debates + history sections | Add "Recommended Contracts" section |
| `DashboardPage.vue:408` | `<h2>Recent Debates</h2>` | Add "View All" RouterLink |
| `DashboardPage.vue:305-324` | Latest scan card with meta | Add duration text |
| `ScanPage.vue:152-194` | DataTable columns | Add Duration column |

## Backend Verification (All Endpoints Exist)

| Endpoint | Response | Limit Param | Status |
|----------|----------|-------------|--------|
| `GET /api/analytics/ticker/{ticker}/contracts` | `RecommendedContract[]` | `limit: int = 50` (1-200) | Active |
| `GET /api/debate` | `DebateResultSummary[]` | `limit: int = 20` (1-100), optional `ticker` filter | Active |
| `GET /api/scan` | `ScanRun[]` | `limit: int = 10` | Active |

**min_score validation**: Backend accepts `0.0+` (non-negative, finite). No upper-bound validator but composite scores are always 0-100.

**ScanRun fields**: Both `started_at` (datetime, UTC) and `completed_at` (datetime | null, UTC) exist on backend and frontend types.

**RecommendedContract fields**: 25+ fields including `option_type`, `strike` (string/Decimal), `expiration`, `delta` (nullable), `direction`, `composite_score`. All Decimal fields serialized as JSON strings.

## Potential Conflicts

- **No conflicts identified** — all 4 changes are independent frontend edits touching separate template sections
- Backend endpoints already exist and are stable
- TypeScript types already defined for all response models

## Open Questions

1. **"View All Debates" destination** — No `/debates` list route exists. Options:
   - **Option A**: Create minimal `DebateListPage.vue` at `/debates` with DataTable (new file + route)
   - **Option B**: Link to existing `/scan` page (debates accessible per scan result)
   - **Recommendation**: Option A for clean UX, but it adds scope. PRD prefers simplicity — defer to implementation.

2. **Contracts limit in drawer** — PRD says "max 3", endpoint default is 50. Use `?limit=3` query param.

## Recommended Architecture

All changes are **frontend-only** — no backend modifications needed.

### Wave 1 (All Parallel — Independent Changes)

**F1: Score Filter Fix** — 5 property changes in `PreScanFilters.vue`
- `:max="100"`, `:step="5"`, `:minFractionDigits="0"`, `:maxFractionDigits="0"`, description text

**F5: Contracts in TickerDrawer** — Extend `TickerDrawer.vue`
- Add `contracts` ref + loading state
- Add to existing `Promise.all` in watcher
- New template section with Tag (CALL/PUT), strike, expiration, delta, DirectionBadge
- Empty state: "No contract recommendations yet."
- Error handling: silent catch (don't crash drawer)

**F13: "View All Debates" Link** — Edit `DashboardPage.vue`
- Add RouterLink/Button after `<h2>Recent Debates</h2>`
- Target: `/scan` page (Option B — pragmatic, no new page needed)
- Style: PrimeVue Button with `severity="secondary"` and `link` appearance

**F4: Scan Duration** — Edit `DashboardPage.vue` + `ScanPage.vue`
- Utility function `formatScanDuration(scan: ScanRun): string`
- Compute `completed_at - started_at`, format as "Xm Ys" or "Xs" or "--"
- Add to DashboardPage latest scan card
- Add Duration column to ScanPage DataTable

### Wave 2 (After Wave 1)

- E2E test updates for prescan filter range
- Visual verification of contracts section, duration, "View All" link

## Test Strategy Preview

### Existing E2E Coverage
- `prescan-filters.spec.ts` — Tests filter panel, could verify max/step values
- `scan-results-table.spec.ts` — Tests TickerDrawer opening, could verify contracts section
- `dashboard.spec.ts` — Tests DashboardPage rendering, could verify "View All" link + duration

### Testing Approach
- **No frontend unit tests exist** (Vitest not configured). All validation via Playwright E2E.
- **Existing test infrastructure**: Page Object Model, `mockAllApis()`, builders (`buildScanRun()`), self-healing locators
- **New tests needed**: Verify score filter max=100, contracts render in drawer, "View All" link navigates, duration displays
- **Mock patterns**: Use existing `api-handlers.ts` mock infrastructure for contracts endpoint

### Key Test Files
- `web/e2e/suites/scan/prescan-filters.spec.ts`
- `web/e2e/suites/scan/scan-results-table.spec.ts`
- `web/e2e/suites/navigation/dashboard.spec.ts`
- `web/e2e/fixtures/mocks/api-handlers.ts`
- `web/e2e/fixtures/builders/scan.builders.ts`

## Estimated Complexity

**S (Small)** — All 4 items are frontend-only edits to existing components. No new backend endpoints, no new models, no database changes. The contracts section in TickerDrawer is the largest item (~40 lines of template + ~15 lines of script). Total: ~4 files modified, ~100-150 lines added/changed.
