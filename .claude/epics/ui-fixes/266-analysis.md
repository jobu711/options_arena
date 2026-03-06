---
issue: "#266"
title: UI Fixes
analyzed: 2026-03-05T16:16:24Z
estimated_hours: 4
parallelization_factor: 3.0
---

# Parallel Work Analysis: Issue #266

## Overview
Minor cosmetic fixes to the web dashboard. Addresses spacing, responsive design, empty states,
contrast/hover feedback, and typography inconsistencies across Vue 3 SPA components. Scoped to
high-impact, low-risk changes that improve UX without architectural changes.

## Parallel Streams

### Stream A: Spacing, Layout & Responsive Fixes
**Scope**: Fix inconsistent spacing/margins, responsive breakpoints, and mobile overflow
**Files**:
- `web/src/pages/ScanResultsPage.vue` — filter row overflow, empty state styling, delta chip spacing
- `web/src/pages/DashboardPage.vue` — quick-debate width overflow, inconsistent margins, trending table font scale
- `web/src/pages/ScanPage.vue` — past scans row hover affordance
- `web/src/components/TickerDrawer.vue` — drawer width responsive, header gap, loading state
- `web/src/components/DebateProgressModal.vue` — modal width consistency, agent row spacing
- `web/src/components/ScanFilterPanel.vue` — filter grid mobile breakpoint
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 1.5
**Dependencies**: none

### Stream B: Color, Contrast & Dark Theme Consistency
**Scope**: Fix hover contrast, text readability, dark theme inconsistencies, badge contrast
**Files**:
- `web/src/assets/variables.css` — datatable row hover contrast, select dropdown hover
- `web/src/components/DirectionBadge.vue` — neutral badge text contrast
- `web/src/components/RegimeBanner.vue` — volatile regime text contrast
- `web/src/components/debate/AgentCard.vue` — argument text color consistency
- `web/src/components/debate/RiskAgentCard.vue` — field label readability
- `web/src/components/debate/FlowAgentCard.vue` — field label readability
- `web/src/components/ProgressTracker.vue` — phase indicator visibility
- `web/src/components/DimensionalScoreBars.vue` — bar value text styling
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 1.0
**Dependencies**: none

### Stream C: Empty States, Loading States & Interactive Affordances
**Scope**: Improve empty/loading states with proper visual indicators, add missing hover/focus states
**Files**:
- `web/src/pages/ScanResultsPage.vue` — empty state icon + centered container
- `web/src/pages/DashboardPage.vue` — empty state styling, health chip hover
- `web/src/pages/HealthPage.vue` — empty state visual separation
- `web/src/components/TickerDrawer.vue` — loading skeleton, debate row focus state
- `web/src/pages/ScanPage.vue` — past scans row hover styling
- `web/src/components/debate/DebateResultPage.vue` — export button visual distinction
- `web/src/pages/ScanResultsPage.vue` — batch action button hierarchy
**Agent Type**: general-purpose
**Can Start**: immediately
**Estimated Hours**: 1.5
**Dependencies**: none

## Coordination Points

### Shared Files
- `web/src/pages/ScanResultsPage.vue` — Streams A & C (A handles layout/spacing, C handles empty states/buttons)
- `web/src/pages/DashboardPage.vue` — Streams A & C (A handles layout, C handles empty states)
- `web/src/components/TickerDrawer.vue` — Streams A & C (A handles spacing/responsive, C handles loading/focus)

### Sequential Requirements
None — streams work on different CSS properties within shared files. Low merge conflict risk.

## Conflict Risk Assessment
- **Medium Risk**: Three shared files across streams A & C, but they modify different sections
  (layout/sizing vs empty states/interactions). Careful commit ordering will prevent conflicts.

## Parallelization Strategy

**Recommended Approach**: parallel

Launch all 3 streams simultaneously. Shared files are split by concern (layout vs states vs colors)
so merge conflicts are unlikely. Stream B is fully independent (different files entirely).

## Expected Timeline

With parallel execution:
- Wall time: 1.5 hours (max stream)
- Total work: 4.0 hours
- Efficiency gain: 63%

Without parallel execution:
- Wall time: 4.0 hours

## Notes
- All changes are CSS/template-only — no TypeScript logic changes
- Stick to PrimeVue design tokens (`var(--p-*)`) over hardcoded colors
- Test in dark mode (default theme) — all fixes must look correct in dark mode
- Run Playwright E2E tests after to verify no visual regressions
- Out of scope: chart hardcoded dimensions (ScoreHistoryChart, SparklineChart) — those need a responsive
  refactor that's bigger than a cosmetic fix
