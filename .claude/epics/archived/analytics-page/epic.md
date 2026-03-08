---
name: analytics-page
status: done
created: 2026-03-06T17:36:17Z
completed: 2026-03-07T17:58:00Z
progress: 100%
prd: .claude/prds/analytics-page.md
github: https://github.com/jobu711/options_arena/issues/290
---

# Epic: analytics-page

## Overview

Deliver `AnalyticsPage.vue` — a frontend page consuming 6 existing backend analytics endpoints. The nav link and route already exist but the page component was never created. This is a **frontend-only epic** (plus one SQL migration): zero new Python backend logic needed. All API endpoints, Pydantic models, and repository queries are implemented and tested.

8 new files: 1 TypeScript types file, 1 page component, 5 sub-components, 1 DB migration.

## Architecture Decisions

| Decision | Choice | Rationale |
|----------|--------|-----------|
| Chart library | Vanilla SVG | Chart.js not installed; project uses SVG charts (ScoreHistoryChart, SparklineChart). No new dependency. |
| State management | Component-local `ref()` | Single-page data, no cross-page sharing needed. PRD explicitly excludes Pinia store. |
| API layer | `useApi` composable | Project standard — all pages use `api<T>()` from `useApi.ts`. |
| Component structure | `pages/AnalyticsPage.vue` + `components/analytics/*.vue` | Follows existing pattern (thin page orchestrator + extracted sub-components). |
| Empty states | Three-tier hierarchy | Page-level (no contracts), data-level (no outcomes), panel-level (no data for specific chart). |

## Technical Approach

### Frontend Components

**Page orchestrator**: `AnalyticsPage.vue` (~120 lines)
- Loads summary on mount, then parallel-fetches 4 datasets via `Promise.all()`
- Passes typed props to 5 sub-components
- Owns lookback period state (7/14/30/60/90 days)
- Owns "Collect Outcomes" button with loading/409 handling (replicate DashboardPage pattern)

**5 sub-components** in `components/analytics/`:
| Component | Visualization | Data Source | Controls |
|-----------|--------------|-------------|----------|
| `SummaryCard.vue` | Card grid (key metrics) | `GET /api/analytics/summary?lookback_days=N` | Lookback dropdown |
| `WinRateChart.vue` | SVG bar chart (3 bars) | `GET /api/analytics/win-rate` | None |
| `ScoreCalibrationChart.vue` | SVG bars + line overlay | `GET /api/analytics/score-calibration?bucket_size=N` | Bucket size dropdown (5/10/20) |
| `HoldingPeriodTable.vue` | PrimeVue DataTable | `GET /api/analytics/holding-period?direction=X` | Direction filter dropdown |
| `DeltaPerformanceChart.vue` | SVG grouped bars | `GET /api/analytics/delta-performance?bucket_size=0.1&holding_days=N` | Holding days selector (1/5/10/20) |

### Backend Services

No new backend code. Existing endpoints consumed:
- 5 GET analytics endpoints (win-rate, score-calibration, holding-period, delta-performance, summary)
- 1 POST collect-outcomes (202 response, operation mutex)

### Infrastructure

**DB Migration 022** — 3 performance indexes:
```sql
CREATE INDEX IF NOT EXISTS idx_co_exit_date ON contract_outcomes(exit_date);
CREATE INDEX IF NOT EXISTS idx_rc_created_at ON recommended_contracts(created_at);
CREATE INDEX IF NOT EXISTS idx_ts_scan_direction ON ticker_scores(scan_run_id, direction);
```

## Implementation Strategy

### Wave 1 — Foundation (no dependencies)
- TypeScript interfaces in `analytics.ts` (matches 6 Python models)
- DB migration 022 (3 indexes)

### Wave 2 — Page Scaffold (depends on Wave 1 types)
- `AnalyticsPage.vue` with data loading, empty states, collect outcomes button
- `SummaryCard.vue` with lookback selector

### Wave 3 — Chart Components (parallel, depend on Wave 2)
- `WinRateChart.vue` — simplest chart (3 bars)
- `ScoreCalibrationChart.vue` — dual-series (bars + line)
- `HoldingPeriodTable.vue` — PrimeVue DataTable
- `DeltaPerformanceChart.vue` — grouped bars by delta bucket

### Wave 4 — Polish & Testing (depends on Wave 3)
- Empty states on every panel
- Responsive 2x2→1-column grid
- E2E tests (Playwright)

## Task Breakdown Preview

- [ ] Task 1: Create TypeScript analytics types + DB migration 022
- [ ] Task 2: Create AnalyticsPage.vue shell with data loading, empty states, and Collect Outcomes button
- [ ] Task 3: Create SummaryCard.vue with lookback period selector
- [ ] Task 4: Create WinRateChart.vue (SVG bar chart)
- [ ] Task 5: Create ScoreCalibrationChart.vue (SVG dual-series chart with bucket size selector)
- [ ] Task 6: Create HoldingPeriodTable.vue (PrimeVue DataTable with direction filter)
- [ ] Task 7: Create DeltaPerformanceChart.vue (SVG grouped bars with holding days selector)
- [ ] Task 8: Responsive layout polish, per-panel empty states, and E2E tests

## Dependencies

### Internal (all satisfied)
- 6 analytics API endpoints — implemented and tested
- 9 Pydantic analytics models — implemented with validators
- `useApi` composable — available
- Router route + nav link — already wired
- `types/index.ts` re-export — already declared (awaiting file creation)

### External
- PrimeVue (installed: v4.5.4) — DataTable, Button, Select, Card, Skeleton
- No new npm dependencies needed

## Success Criteria (Technical)

| Criterion | Measure |
|-----------|---------|
| Page renders at `/analytics` | Nav link no longer shows blank page |
| All 5 data panels populated | Each calls its endpoint and displays data |
| Collect Outcomes button works | POST fires, toast on success, 409 handled |
| Empty states clear | Three tiers: no contracts, no outcomes, no panel data |
| DB indexes created | Migration 022 applies cleanly |
| Page load < 500ms | All 5 API calls resolve within budget (warm DB) |
| Responsive layout | 2x2 grid collapses to single column on narrow screens |
| TypeScript strict | `npm run type-check` passes |
| E2E coverage | Analytics page navigation, data display, collect button |

## Estimated Effort

**Medium** — ~500-700 lines of new frontend code across 8 files.
- Wave 1: ~30 min (types + migration)
- Wave 2: ~1 hr (page + summary card)
- Wave 3: ~2 hr (4 chart/table components — SVG layout is the main effort)
- Wave 4: ~1 hr (polish + E2E tests)
- **Total: ~4-5 hours implementation**
- **Critical path**: SVG coordinate math for ScoreCalibrationChart (dual-axis) and DeltaPerformanceChart (grouped bars)

## Tasks Created
- [ ] #291 - Create TypeScript analytics types and DB migration 022 (parallel: true)
- [ ] #293 - Create AnalyticsPage.vue shell with data loading and Collect Outcomes (parallel: false)
- [ ] #295 - Create SummaryCard.vue with lookback period selector (parallel: true)
- [ ] #297 - Create WinRateChart.vue SVG bar chart (parallel: true)
- [ ] #292 - Create ScoreCalibrationChart.vue SVG dual-series chart (parallel: true)
- [ ] #294 - Create HoldingPeriodTable.vue with direction filter (parallel: true)
- [ ] #296 - Create DeltaPerformanceChart.vue SVG grouped bars (parallel: true)
- [ ] #298 - Responsive layout polish, per-panel empty states, and E2E tests (parallel: false)

Total tasks: 8
Parallel tasks: 6 (#291, #295, #297, #292, #294, #296)
Sequential tasks: 2 (#293 depends on #291; #298 depends on all)
Estimated total effort: 9.75 hours

## Test Coverage Plan
Total test files planned: 3 (analytics.spec.ts, analytics.page.ts, analytics.builders.ts)
Total test cases planned: 7+ E2E tests
