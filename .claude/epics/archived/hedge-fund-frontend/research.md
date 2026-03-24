# Research: hedge-fund-frontend

## PRD Summary

Gut rebuild of the Vue 3 frontend as a single-screen "AI hedge fund trading desk" command center. Replaces the current 8-page multi-navigation UI with a single masonry-grid page: scan → ranked pipeline table → manual recommendation trigger → 6-desk consensus + position detail. All in real-time via WebSocket. No backend changes — pure frontend rebuild consuming existing API.

## Relevant Existing Modules

- `web/src/pages/` — 8 pages (7 deleted, AnalyticsPage kept/rebuilt). New TradingDeskPage replaces all core pages.
- `web/src/components/` — 43 components. 8 debate-era cards deleted, 20+ kept (badges, filters, analytics, charts).
- `web/src/stores/` — 7 Pinia stores (2 deleted: debate, agency). 5 kept. New `pipeline.ts` store created.
- `web/src/composables/` — 3 composables all kept (useWebSocket, useApi, useOperation).
- `web/src/types/` — 10 type modules. `debate.ts` deleted, `ws.ts` enhanced, new `recommendation.ts` created.
- `web/src/router/` — 8 routes → 3 routes (trading-desk, analytics, settings).
- `web/src/utils/formatters.ts` — Kept as-is, provides price/date formatting conventions.
- `web/src/assets/variables.css` — CSS custom properties for dark theme (kept).
- `web/src/App.vue` — Nav bar + layout shell must be rewritten for trading desk.

## Existing Patterns to Reuse

- **Composition API + script setup**: 100% of components use `<script setup lang="ts">`. All new components must follow this.
- **Pinia setup syntax**: All stores use `defineStore('name', () => {...})` with refs, computed, and functions returned.
- **useWebSocket composable**: Generic typed WebSocket with auto-reconnect (exponential backoff, max 5 attempts). Reuse for scan, debate, and batch WS connections.
- **useApi composable**: Typed fetch wrapper with 30s timeout, AbortController, error parsing. Reuse for all REST calls.
- **DataTable with virtual scroll**: Pattern from ScanResultsPage — `scrollable` + `scrollHeight` + `virtualScrollerOptions="{ itemSize: 44 }"` together for >1000 rows.
- **URL-synced sorting**: `@sort` event → `router.replace({ query: {...} })` pattern for persistent sort state.
- **CSS custom properties**: Dark theme via `--p-surface-*` (PrimeVue) + `--accent-green/red/blue/purple` (custom). Monospace: `--font-mono: 'JetBrains Mono', 'Fira Code'`.
- **Price formatting**: `formatPrice(string): string` — Intl.NumberFormat, never parses to JS number.
- **Direction badges**: ConfidenceBadge + DirectionBadge components already implement the badge pattern.
- **Discriminated unions for WS events**: `event.type` narrowing pattern in `types/ws.ts`.

## Existing Code to Extend

- `web/src/stores/scan.ts` — Has scan list, current scan, scores, progress, errors, fetchScores with 15+ filter params. New `pipeline.ts` store builds on this pattern but adds per-ticker stage tracking and recommendation state.
- `web/src/types/ws.ts` — Has ScanEvent, DebateEvent, BatchEvent discriminated unions. Enhance with new stage-tracking events if needed.
- `web/src/types/scan.ts` — Has TickerScore, DimensionalScores, ScanRun, PaginatedResponse. New PipelineTicker type extends TickerScore with stage tracking.
- `web/src/composables/useWebSocket.ts` — Reuse directly for all 3 WS connections (scan, debate, batch).
- `web/src/App.vue` — Rewrite nav bar (5 links → 2-3), keep Toast host and health fetch on mount.
- `web/src/router/index.ts` — Rewrite routes (8 → 3), keep lazy loading pattern.

## Files for Deletion (18 confirmed, all exist)

**Pages (7):** DashboardPage, ScanPage, ScanResultsPage, DebateResultPage, TickerDetailPage, AgencyPage, DesksPage
**Components (8):** AgentCard, FlowAgentCard, FundamentalAgentCard, RiskAgentCard, ContrarianAgentCard, ConsensusPanel, DebateProgressModal, DeskSelector
**Stores (2):** debate.ts, agency.ts
**Types (1):** debate.ts
**APIs (1):** api/agency.ts (discovered during research — not in PRD but part of agency feature)

## Files Requiring Decision (Not in PRD Keep/Delete Lists)

| File | Current Usage | Recommendation |
|------|--------------|----------------|
| `TickerDrawer.vue` | Imports useDebateStore (deleted), only used by ScanResultsPage (deleted) | DELETE — replaced by new detail panel |
| `ProgressTracker.vue` | Used by deleted pages only | KEEP — repurpose for ScanProgressCard |
| `DimensionalScoreBars.vue` | Used by TickerDrawer (deleted) but independent | KEEP — useful in recommendation detail |
| `ScoreHistoryChart.vue` | Used by deleted pages but independent | KEEP — useful in analytics |
| `ModelRoutingPanel.vue` | Not imported anywhere currently | KEEP — V2 settings page will use it |
| `RecommendationCostTable.vue` | Not imported anywhere currently | KEEP — V2 settings page will use it |
| `SummaryCard.vue` (analytics) | Used by AnalyticsPage | KEEP — part of analytics |

## Potential Conflicts

- **No import conflicts**: Zero cross-imports between keep and delete file lists. All deleted components only import from other deleted components/stores. Safe to delete in any order.
- **`types/index.ts` barrel export**: Re-exports `debate.ts` — must remove that re-export when debate types are deleted.
- **App.vue nav links**: Currently links to deleted pages — must update simultaneously with page deletion.
- **DebateEvent naming**: Backend endpoints still use `/api/debate` naming. Frontend abstracts this in the API layer but types/stores should use "recommendation" terminology internally.
- **Enum case mismatch**: Backend returns UPPERCASE enums (`"BULLISH"`, `"BEARISH"`, `"NEUTRAL"`). PRD type definitions use lowercase (`'bullish' | 'bearish' | 'neutral'`). Frontend types must match backend casing.

## Backend API Verification

**All 17 PRD-referenced endpoints confirmed to exist:**

| Endpoint | Status | Notes |
|----------|--------|-------|
| `POST /api/scan` | ✓ | Request: ScanRequest, Response: ScanStarted (202) |
| `WS /ws/scan/{id}` | ✓ | Events: progress, complete, error |
| `GET /api/scan/{id}/scores` | ✓ | Paginated TickerScore response |
| `POST /api/debate/batch` | ✓ | Request: BatchDebateRequest with scan_id + optional tickers |
| `WS /ws/batch/{id}` | ✓ | Events: agent, batch_progress, batch_complete, error |
| `POST /api/debate` | ✓ | Request: DebateRequest with ticker + optional scan_id |
| `WS /ws/debate/{id}` | ✓ | Events: progress, complete, error |
| `GET /api/debate/{id}` | ✓ | Returns RecommendationResponse OR legacy DebateResultDetail |
| `GET /api/market/heatmap` | ✓ | Note: route is `/api/market/heatmap` not `/api/heatmap` |
| `GET /api/health` | ✓ | LivenessResponse |
| `GET /api/universe/preset-info` | ✓ | list[PresetInfo] |
| `GET /api/universe/sectors` | ✓ | list[SectorHierarchy] |
| `GET /api/analytics/attribution` | ✓ | AttributionReport with window_days param |

**PRD Type Discrepancies (all resolved — frontend types must match backend):**

1. **Enum casing**: PRD uses lowercase → **fix to UPPERCASE** (`'BULLISH' | 'BEARISH' | 'NEUTRAL'`)
2. **Heatmap URL**: PRD says `GET /api/heatmap` → **fix to `GET /api/market/heatmap`**
3. **PredictionAccuracy**: PRD has `brier_score: number | null` → **fix to `sample_sufficient: boolean`**
4. **ConditionBucketAccuracy**: PRD has `condition_key` + `condition_value` → **fix to single `condition: string`**
5. **ContractGuidance**: PRD has `sample_size` → **fix to `sample_count: number`**, add `delta_win_rate: number`, `dte_win_rate: number`
6. **Legacy debate response**: PRD silent on this → **ignore legacy `DebateResultDetail`, only support `RecommendationResponse`**

## Decisions (Resolved)

1. **Enum casing**: Use **UPPERCASE** to match backend wire format (`'BULLISH' | 'BEARISH' | 'NEUTRAL'`). No transform layer — types match the wire directly.
2. **Legacy debate response**: **Remove legacy support entirely**. Frontend only handles `RecommendationResponse`. If `GET /api/debate/{id}` returns legacy `DebateResultDetail`, treat as error/unsupported.
3. **ScanProgressCard**: Build **new component from scratch**. Existing ProgressTracker is too coupled to old multi-page flow. ProgressTracker can be deleted with the old pages.
4. **DimensionalScores**: Backend model has **8 fields** (trend, iv_vol, hv_vol, flow, microstructure, fundamental, regime, risk) per `models/scoring.py`. PRD is correct. Research initially misreported 4 — corrected.
5. **Attribution report types**: Match **actual backend models** (backend is source of truth):
   - `PredictionAccuracy`: use `sample_sufficient: boolean` (not `brier_score`)
   - `ConditionBucketAccuracy`: use `condition: string` (not `condition_key` + `condition_value`)
   - `ContractGuidance`: use `delta_win_rate: number`, `dte_win_rate: number`, `sample_count: number` (not `sample_size`)
6. **Batch selection**: `scan_id` is always required. Pass explicit `tickers: string[]` when user multi-selects rows ("Analyze Selected"). Omit `tickers` to auto-select top `limit` tickers by composite score. This gives two clean UX paths:
   - **"Analyze Selected"** (user picks rows) → `{ scan_id, tickers: ["AAPL", "MSFT", ...] }`
   - **"Analyze Top N"** (auto-select) → `{ scan_id, limit: 5 }`

## Recommended Architecture

### Phase 1: Foundation (Infrastructure)
1. Create new TypeScript types (`types/recommendation.ts`) matching actual backend response shapes
2. Create `stores/pipeline.ts` with state machine (idle → scanning → scanned)
3. Rewrite `router/index.ts` to 3 routes
4. Rewrite `App.vue` shell for trading desk layout

### Phase 2: Core Components
5. Build `DeskCard.vue` — universal collapsible card wrapper
6. Build `ScanControlBar.vue` — preset selector, filter toggle, run/cancel
7. Build `OpportunityTable.vue` — sortable/filterable DataTable with virtual scroll, multi-select, stage badges
8. Build `PipelineStatus.vue` — stage badge component
9. Build `ScanProgressCard.vue` — scan phase progress indicator

### Phase 3: Recommendation Detail
10. Build `DeskAssessmentCard.vue` — unified desk card (replaces 5 duplicate cards)
11. Build `AgentConsensus.vue` — compact 6-desk summary
12. Build `PositionCard.vue` — entry/stop/target/R:R display

### Phase 4: Integration & Polish
13. Build `TradingDeskPage.vue` — single-screen masonry grid assembling all components
14. WebSocket integration — scan progress, recommendation stage transitions
15. Rebuild `AnalyticsPage.vue` — lightweight wrapper reusing existing analytics components + new AttributionPanel
16. Delete old files (pages, components, stores, types)

### Phase 5: Testing
17. Component tests (Vitest + Vue Test Utils)
18. Store tests (pipeline state machine)
19. Integration tests (MSW mocking)

## Test Strategy Preview

- **Existing test setup**: Vitest + Vue Test Utils (component tests), Playwright (e2e)
- **Test location**: `web/tests/` or colocated `*.test.ts` files
- **Store testing**: Direct store instantiation with `createPinia()` + `setActivePinia()`
- **Component testing**: `mount()` with PrimeVue plugin stubs
- **WebSocket mocking**: Mock `useWebSocket` composable return values
- **API mocking**: MSW (Mock Service Worker) for integration tests
- **Key test files to create**:
  - `OpportunityTable.test.ts` — sort, filter, select, virtual scroll, stage badges
  - `DeskCard.test.ts` — collapse/expand, header rendering
  - `AgentConsensus.test.ts` — all 6 desks, partial desks
  - `DeskAssessmentCard.test.ts` — all desk types, null handling
  - `PositionCard.test.ts` — price strings, null fallbacks
  - `PipelineStatus.test.ts` — all 5 stages
  - `pipeline.test.ts` — full state machine transitions

## Estimated Complexity

**XL** — Justification:
- 12+ new components to build from scratch
- 1 new Pinia store with complex state machine
- New TypeScript type definitions matching backend models
- Full router rewrite (8 → 3 routes)
- App.vue shell rewrite
- 18 files to delete (with import chain cleanup)
- 3 WebSocket integrations (scan, debate, batch)
- Masonry grid CSS layout with responsive card system
- 8+ files requiring decisions beyond PRD lists
- Component + store + integration test coverage
- Type discrepancies between PRD and backend require resolution
- Largest frontend change in project history — touches every layer
