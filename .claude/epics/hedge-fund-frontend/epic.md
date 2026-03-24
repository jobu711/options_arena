---
name: hedge-fund-frontend
status: backlog
created: 2026-03-24T13:37:50Z
progress: 0%
prd: .claude/prds/hedge-fund-frontend.md
github: https://github.com/jobu711/options_arena/issues/792
---

# Epic: hedge-fund-frontend

## Overview

Gut rebuild of the Vue 3 frontend as a single-screen "AI hedge fund trading desk" command center. Deletes 7 pages, 8 debate-era components, 2 stores, and 1 type module. Creates 12 new components, 1 new Pinia store with state machine, 1 new type module, rewrites router (8 → 3 routes) and App.vue shell. Masonry CSS Grid layout with collapsible cards. All real-time via 3 WebSocket connections. Pure frontend — zero backend changes.

## Architecture Decisions

- **UPPERCASE enums**: Frontend types match backend wire format directly (`'BULLISH' | 'BEARISH' | 'NEUTRAL'`). No transform layer.
- **No legacy support**: Only handle `RecommendationResponse` from `GET /api/debate/{id}`. Legacy `DebateResultDetail` treated as unsupported.
- **Prices as strings**: All price fields are `string` in TypeScript. Formatted via `Intl.NumberFormat`, never parsed to JS `number`.
- **CSS Grid masonry**: `grid-template-columns: repeat(auto-fill, minmax(400px, 1fr))` with `grid-column: 1 / -1` on pipeline table. No JS masonry library.
- **DeskCard wrapper**: Universal collapsible card component — all grid panels use it as outer shell. Consistent dark surface styling.
- **Pipeline store state machine**: `idle → scanning → scanned` phases. Per-ticker stage tracking (`queued | scored | analyzing | ready | failed`).
- **Dual-path batch**: Explicit `tickers[]` for "Analyze Selected" (user picks rows), omit for auto top-N by score.
- **Heatmap URL fix**: Use `GET /api/market/heatmap` (not `/api/heatmap`).
- **Attribution types match backend**: `sample_sufficient` (not `brier_score`), `condition` (not `condition_key/value`), `sample_count` + win rates.

## Technical Approach

### Types (`types/recommendation.ts`)
New type module with backend-matched interfaces:
- `PipelineStage` — `'queued' | 'scored' | 'analyzing' | 'ready' | 'failed'`
- `PipelineTicker` — extends TickerScore concept with stage tracking + recommendation_id
- `DeskAssessment` — maps to `DeskAssessmentBrief` (6 desks, UPPERCASE direction)
- `PositionRecommendation` — maps to `PositionRecommendationResponse` (prices as strings)
- `RecommendationDetail` — maps to `RecommendationResponse` (assessments + recommendation + metadata)
- `PredictionAccuracy`, `ConditionBucketAccuracy`, `ContractGuidance`, `AttributionReport` — match `models/attribution.py` exactly

### Store (`stores/pipeline.ts`)
Pinia setup-syntax store managing full pipeline lifecycle:
- State: `tickers: Map<string, PipelineTicker>`, `selectedTicker`, `currentRecommendation`, `scanId`, `batchId`, `phase`
- Actions: `startScan()`, `analyzeTicker()`, `analyzeBatch()`, `selectTicker()`, `loadRecommendation()`
- WS callbacks: `onScanProgress()`, `onScanComplete()`, `onDebateComplete()`, `onBatchProgress()`, `onBatchComplete()`

### Components (12 new)
1. `DeskCard.vue` — universal collapsible card wrapper (header bar + collapse toggle + status badge)
2. `ScanControlBar.vue` — preset selector, collapsible filter panel, run/cancel, analyze selected
3. `OpportunityTable.vue` — PrimeVue DataTable with virtual scroll, multi-select, stage badges, sort
4. `PipelineStatus.vue` — stage badge component (5 states with colors/icons)
5. `ScanProgressCard.vue` — scan phase progress (phase name, bar, ticker count, elapsed)
6. `DeskAssessmentCard.vue` — unified desk card (replaces 5 duplicate cards)
7. `AgentConsensus.vue` — compact 6-desk summary (direction + confidence per desk)
8. `PositionCard.vue` — entry/stop/target/contract/R:R/strategy display
9. `TradingDeskPage.vue` — single-screen masonry grid assembling all components
10. `AnalyticsPage.vue` — lightweight rebuild reusing existing analytics components
11. `AttributionPanel.vue` — prediction attribution report (source accuracy, condition buckets, contract guidance)
12. (ScanControlBar embeds filter panel via existing PreScanFilters/ScanFilterPanel)

### Router & Shell
- 3 routes: `/` (TradingDeskPage), `/analytics` (AnalyticsPage), `/settings` (placeholder)
- App.vue: minimal top bar (logo, 2-3 nav links, health dot), full-height content area

### Delete List (19 files)
- Pages (7): Dashboard, Scan, ScanResults, DebateResult, TickerDetail, Agency, Desks
- Components (9): AgentCard, FlowAgentCard, FundamentalAgentCard, RiskAgentCard, ContrarianAgentCard, ConsensusPanel, DebateProgressModal, DeskSelector, TickerDrawer
- Stores (2): debate.ts, agency.ts
- Types (1): debate.ts
- Also: ProgressTracker.vue (replaced by ScanProgressCard), api/agency.ts

## Tasks Created

### Wave 1 — Foundation (parallel)
- [ ] [P] #795 - Types & pipeline store foundation (L, 6-8h)
- [ ] [P] #798 - Router & App shell rewrite (S, 2-3h)

### Wave 2 — Atomic Components (depends on #795)
- [ ] #799 - Atomic components — DeskCard, PipelineStatus, ScanProgressCard (M, 4-5h)

### Wave 3 — Feature Components (parallel, depends on #795+#799)
- [ ] [P] #801 - ScanControlBar component (M, 4-5h)
- [ ] [P] #797 - OpportunityTable component (L, 6-8h)
- [ ] [P] #800 - Recommendation detail components (M, 5-6h)

### Wave 4 — Integration (parallel where noted)
- [ ] #802 - TradingDeskPage assembly + WebSocket wiring (XL, 8-10h)
- [ ] [P] #793 - Analytics page rebuild + AttributionPanel (M, 4-5h)

### Wave 5 — Cleanup & Testing (sequential)
- [ ] #794 - Delete old files & clean imports (M, 3-4h)
- [ ] #796 - Test suite — component, store, and integration tests (L, 8-10h)

Total tasks: 10
Parallel tasks: 6 (#795, #798, #801, #797, #800, #793)
Sequential tasks: 4 (#799, #802, #794, #796)
Estimated total effort: 50-64 hours

## Test Coverage Plan
Total test files planned: 10
Total test cases planned: 61+

## Dependencies

- **Internal**: All backend APIs stable and verified (17 endpoints confirmed)
- **External**: PrimeVue 4.5.4 (existing), Vue 3.5.29 (existing), Pinia 3.0.4 (existing)
- **Supersedes**: `.claude/prds/recommendation-display-overhaul.md`

## Success Criteria (Technical)

1. Single-page trading desk renders with masonry grid layout
2. Scan launches and tickers stream into pipeline table in real-time via WebSocket
3. "Analyze" button triggers recommendation, stage badge updates via WS
4. "Analyze Selected" batch triggers multiple recommendations
5. Clicking a ready ticker shows 6-desk consensus + position detail
6. All prices displayed as formatted strings, never parsed to float
7. Analytics page renders with attribution panel
8. All 21 old files deleted, zero import errors
9. `npm run build` succeeds with zero TypeScript errors
10. Component + store tests pass

## Estimated Effort

**XL** — 10 tasks, ~12 new components, 1 state machine store, router + shell rewrite, 21 file deletions, 3 WebSocket integrations, masonry grid CSS, full test suite. Largest frontend change in project history.
