---
name: ui-polish-v29
status: backlog
created: 2026-03-06T17:52:57Z
progress: 0%
prd: .claude/prds/ui-polish-v29.md
github: [Will be updated when synced to GitHub]
---

# Epic: ui-polish-v29

## Overview

Four independent frontend-only fixes that make existing data more accessible: fix the score filter range bug (max 10 → 100), add recommended contracts to TickerDrawer, add "View All Debates" link on dashboard, and display scan duration on scan lists. Zero backend changes — all endpoints and types already exist.

## Architecture Decisions

- **Frontend-only** — No backend endpoints, models, or DB changes needed. All data sources verified in research.
- **"View All Debates" → link to `/scan`** — No new DebateListPage. The scan page already surfaces debates per scan result. Creating a dedicated page adds scope without proportional value. A simple RouterLink to `/scan` is the pragmatic choice (PRD Option B).
- **Contracts limit=3** — PRD specifies max 3 contracts in drawer. Use `?limit=3` query param on existing endpoint (supports 1-200).
- **Client-side duration** — Compute scan duration from `completed_at - started_at` in the browser. No new backend field needed.
- **Reuse existing components** — DirectionBadge for contract direction, PrimeVue Tag for call/put, existing `api<T>()` composable for fetching.

## Technical Approach

### Files to Modify (4 files)

| File | Changes |
|------|---------|
| `web/src/components/scan/PreScanFilters.vue` | Fix `:max`, `:step`, fraction digits, description text (5 prop changes) |
| `web/src/components/TickerDrawer.vue` | Add contracts ref, parallel fetch in watcher, template section (~55 lines) |
| `web/src/pages/DashboardPage.vue` | Add "View All" RouterLink in debates header, duration in latest scan card |
| `web/src/pages/ScanPage.vue` | Add Duration column to scan DataTable |

### No New Files

All changes extend existing components. No new pages, composables, stores, or types needed.

## Implementation Strategy

All 4 items are independent — they touch separate files or separate sections within the same file. Implementation can proceed as a single wave with E2E verification after.

### Wave 1: All Changes (Parallel-Safe)

1. **Score filter fix** — 5 property edits in PreScanFilters.vue (~5 min)
2. **Contracts in TickerDrawer** — Script additions (ref, fetch, error handling) + template section (~30 min)
3. **"View All" link** — RouterLink in DashboardPage debates header (~5 min)
4. **Scan duration** — `formatScanDuration()` utility + column in ScanPage + inline in DashboardPage (~15 min)

### Wave 2: Verification

- Build frontend (`npm run build`)
- Run existing E2E tests to catch regressions
- Update E2E mocks/tests if needed for new contracts section

## Task Breakdown Preview

- [ ] Task 1: Fix score filter range in PreScanFilters.vue (max, step, fractionDigits, description)
- [ ] Task 2: Add recommended contracts section to TickerDrawer.vue (fetch + render + empty/error states)
- [ ] Task 3: Add "View All" debates link + scan duration display on DashboardPage.vue and ScanPage.vue
- [ ] Task 4: Update E2E test mocks and add contract/duration assertions
- [ ] Task 5: Build verification + full E2E test run

## Dependencies

### Internal (All Verified)
- `GET /api/analytics/ticker/{ticker}/contracts` — Returns `RecommendedContract[]` with `limit` param (1-200)
- `GET /api/debate` — Returns `DebateResultSummary[]` with optional `ticker` and `limit` params
- `RecommendedContract` type in `web/src/types/scan.ts` (lines 99-122)
- `ScanRun.completed_at` field (nullable datetime, exists on backend + frontend)
- `DirectionBadge` component (existing, used in TickerDrawer and ScanResultsPage)
- `api<T>()` composable in `web/src/composables/useApi.ts`

### External
- None

## Success Criteria (Technical)

| Criterion | Verification |
|-----------|-------------|
| Score filter accepts 0–100 with step 5 | E2E: verify InputNumber max/step attributes |
| Contracts render in TickerDrawer (max 3) | E2E: mock contracts API, verify section renders |
| "View All" link navigates to `/scan` | E2E: click link, verify navigation |
| Scan duration shows "Xm Ys" / "Xs" / "--" | E2E: verify duration text in scan list |
| No E2E regressions | Full Playwright suite passes |
| Frontend builds cleanly | `vue-tsc --noEmit && vite build` succeeds |

## Estimated Effort

**S (Small)** — ~1-2 hours total. 4 files modified, ~100-150 lines added/changed. All frontend-only, no backend/DB work. No new architectural patterns introduced.
