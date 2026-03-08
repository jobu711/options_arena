# Research: analytics-page

## PRD Summary

The `/analytics` nav link and Vue Router route already exist but `AnalyticsPage.vue` was never created — clicking "Analytics" shows a blank page. This epic delivers:
- `AnalyticsPage.vue` with 5 visualization panels consuming 6 existing backend endpoints
- TypeScript types matching 6 Python analytics models
- "Collect Outcomes" button (POST trigger with 409 handling)
- DB migration 022 adding 3 performance indexes
- No new Python backend logic needed (except migration SQL)

## Relevant Existing Modules

- **`src/options_arena/api/routes/analytics.py`** — 9 endpoints fully implemented and tested (7 GET + 1 POST + 1 path-param GET). Rate-limited (60/min query, 5/min collect).
- **`src/options_arena/models/analytics.py`** — 9 frozen Pydantic models with validators (WinRateResult, ScoreCalibrationBucket, IndicatorAttributionResult, HoldingPeriodResult, DeltaPerformanceResult, PerformanceSummary, RecommendedContract, ContractOutcome, NormalizationStats).
- **`src/options_arena/data/repository.py`** — 8+ analytics query methods returning typed models.
- **`web/src/composables/useApi.ts`** — `api<T>(path, options)` composable with ApiError class, timeout, params support.
- **`web/src/types/index.ts`** — Line 16 already re-exports from `./analytics` (file doesn't exist yet).
- **`web/src/router/index.ts`** — Line 36-39: `/analytics` route already registered with lazy import.
- **`web/src/App.vue`** — Line 32: nav link to `/analytics` already exists.
- **`web/src/components/ScoreHistoryChart.vue`** — Existing SVG line chart (600x200, direction colors, tooltips).
- **`web/src/components/SparklineChart.vue`** — Existing SVG sparkline (80x24).
- **`data/migrations/`** — 21 migrations; next available is **022**.

## Existing Patterns to Reuse

### 1. Page Component Pattern (DashboardPage, ScanResultsPage)
- `<script setup lang="ts">`, load data in `onMounted()`, thin orchestrator (<150 lines)
- `Promise.all()` for parallel API fetches
- `useToast()` for success/error/warning notifications
- Loading state via `ref<boolean>(false)` + PrimeVue `DataTable :loading`

### 2. SVG Chart Pattern (ScoreHistoryChart, SparklineChart)
- Vanilla SVG — **Chart.js is NOT installed** and the project intentionally avoids it
- Direction color mapping: green (bullish), red (bearish), yellow (neutral)
- Computed SVG paths, hover tooltips, responsive viewBox
- Fallback for insufficient data (< 2 points → show "—")

### 3. Empty State Pattern (ScanResultsPage)
- `<template #empty>` slot with icon + descriptive message
- Centered flex layout, `var(--p-surface-500)` color
- Actionable: link to relevant page (e.g., Scan page)

### 4. Toast Pattern (DashboardPage)
- `toast.add({ severity, summary, detail, life: 5000 })`
- 409 handling: severity `warn`, "Operation Busy" message

### 5. Outcome Collection Pattern (DashboardPage)
- Already implemented in DashboardPage — `api<{ outcomes_collected: number }>('/api/analytics/collect-outcomes', { method: 'POST' })` with loading state, success toast, 409 handling. Can replicate directly.

### 6. useApi Composable
```typescript
api<T>(path: string, options?: { method?, body?, params?, signal?, timeout? }): Promise<T>
// ApiError with .status for HTTP error handling
// params: Record<string, string | number | undefined> for query strings
```

## Existing Code to Extend

| File | What Exists | What Needs Creating/Changing |
|------|------------|------------------------------|
| `web/src/types/analytics.ts` | Does NOT exist (re-export stub in index.ts) | Create 6 interfaces + OutcomeCollectionResult |
| `web/src/pages/AnalyticsPage.vue` | Does NOT exist (route registered) | Create full page component |
| `web/src/components/analytics/` | Directory does NOT exist | Create 5 sub-components |
| `data/migrations/022_analytics_indexes.sql` | Does NOT exist | Create with 3 indexes |
| `web/src/types/index.ts` | Already re-exports analytics types | No change needed |
| `web/src/router/index.ts` | Route already registered | No change needed |
| `web/src/App.vue` | Nav link already exists | No change needed |

## Potential Conflicts

### 1. Chart.js vs SVG Decision
- **PRD says** use PrimeVue Chart (Chart.js wrapper)
- **Codebase reality**: Chart.js is NOT installed; project uses vanilla SVG charts
- **Mitigation**: Use SVG charts like existing components. Avoids adding a dependency (chart.js + primevue/chart). If Chart.js is desired, must `npm install chart.js` first.
- **Recommendation**: Use SVG for consistency with existing codebase. Simpler, lighter, no new dependency.

### 2. Pinia Store vs Component State
- PRD says "No Pinia store needed" (out of scope)
- Component-local `ref()` state is sufficient for a single page
- No conflict — align with PRD decision

### 3. Duplicate Outcome Collection Button
- DashboardPage already has a "Collect Outcomes" button with identical logic
- Analytics page will have its own button — no conflict, just code duplication
- Could extract to shared composable later, but PRD says no over-engineering

## Open Questions

1. **Chart.js or SVG?** PRD specifies PrimeVue Chart (Chart.js), but codebase uses SVG exclusively. Recommend SVG for consistency unless stakeholder prefers Chart.js (requires `npm install chart.js`).
2. **Indicator Attribution chart** — PRD explicitly defers to v2.10. Confirm no stub/placeholder needed.
3. **Accessibility** — PRD mentions "chart data also available as tables." Should every chart have a hidden/toggle table, or is the HoldingPeriodTable sufficient as the accessible alternative?

## Recommended Architecture

### File Structure
```
web/src/
  types/
    analytics.ts                          # 6 interfaces + OutcomeCollectionResult
  pages/
    AnalyticsPage.vue                     # Thin orchestrator (~120 lines)
  components/
    analytics/
      SummaryCard.vue                     # PerformanceSummary display + lookback selector
      WinRateChart.vue                    # SVG bar chart (3 bars)
      ScoreCalibrationChart.vue           # SVG dual-series (bars + line overlay)
      HoldingPeriodTable.vue              # PrimeVue DataTable with direction filter
      DeltaPerformanceChart.vue           # SVG grouped bars by delta bucket

data/migrations/
  022_analytics_indexes.sql               # 3 CREATE INDEX IF NOT EXISTS
```

### Data Flow
1. `AnalyticsPage.vue` mounts → loads summary first
2. If `total_contracts > 0`: parallel-fetches win-rate, score-calibration, holding-period, delta-performance via `Promise.all()`
3. Each sub-component receives data as typed props
4. "Collect Outcomes" button triggers POST → on success, refetches all data
5. Lookback/filter changes trigger targeted refetches

### Empty State Hierarchy
- `total_contracts === 0` → Full-page empty: "No recommendations yet. Run a scan."
- `total_with_outcomes === 0` → Data-specific empty: "N recommendations but no outcomes. Click Collect Outcomes."
- Individual panels: per-panel empty when their specific data array is empty

### TypeScript Interfaces (matching Python models)
```typescript
interface WinRateResult {
  direction: 'bullish' | 'bearish' | 'neutral'
  total_contracts: number; winners: number; losers: number; win_rate: number
}
interface ScoreCalibrationBucket {
  score_min: number; score_max: number; contract_count: number
  avg_return_pct: number; win_rate: number
}
interface HoldingPeriodResult {
  holding_days: number; direction: 'bullish' | 'bearish' | 'neutral'
  avg_return_pct: number; median_return_pct: number; win_rate: number; sample_size: number
}
interface DeltaPerformanceResult {
  delta_min: number; delta_max: number; holding_days: number
  avg_return_pct: number; win_rate: number; sample_size: number
}
interface PerformanceSummary {
  lookback_days: number; total_contracts: number; total_with_outcomes: number
  overall_win_rate: number | null; avg_stock_return_pct: number | null
  avg_contract_return_pct: number | null; best_direction: string | null; best_holding_days: number | null
}
interface OutcomeCollectionResult { outcomes_collected: number }
```

### Migration SQL
```sql
CREATE INDEX IF NOT EXISTS idx_co_exit_date ON contract_outcomes(exit_date);
CREATE INDEX IF NOT EXISTS idx_rc_created_at ON recommended_contracts(created_at);
CREATE INDEX IF NOT EXISTS idx_ts_scan_direction ON ticker_scores(scan_run_id, direction);
```

## Test Strategy Preview

### Existing Test Patterns
- **E2E (Playwright)**: 38+ tests in `web/e2e/` — page navigation, API mocking, interaction flows
- **Python unit tests**: 3,921 tests — repository tests mock aiosqlite, API tests use TestClient
- **Frontend**: No Vitest unit tests yet (Playwright E2E covers integration)

### Test Approach for This Epic
- **Migration test**: Add to existing migration test suite — verify indexes created
- **E2E tests**: Navigate to `/analytics`, verify page renders, verify empty state, mock API responses for chart rendering, test Collect Outcomes button
- **No frontend unit tests** per project convention (E2E coverage preferred)

## Estimated Complexity

**Medium (M)** — Justification:
- Zero new backend logic (only migration SQL)
- 8 new files (1 types, 1 page, 5 components, 1 migration)
- All API endpoints and models already exist and are tested
- SVG charting follows established project patterns
- Main complexity is in chart SVG layout (4 chart components)
- ~500-700 lines of new frontend code total
- Risk: SVG chart layout for score calibration (dual-axis) and delta performance (grouped bars) requires careful coordinate math
