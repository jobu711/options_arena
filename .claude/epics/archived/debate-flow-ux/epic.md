---
name: debate-flow-ux
status: backlog
created: 2026-03-06T17:48:50Z
progress: 0%
prd: .claude/prds/debate-flow-ux.md
github: https://github.com/jobu711/options_arena/issues/306
---

# Epic: debate-flow-ux

## Overview

Fix the three broken pieces of the scan-to-debate user journey: (1) enable the permanently
disabled "Debate This Ticker" button in TickerDrawer, (2) surface v2 consensus data
(agreement score, dissenters, contrarian challenge) on DebateResultPage, and (3) add
back-to-scan navigation when a debate originated from a scan. The backend already computes,
persists, and serves all required data — this is almost entirely a frontend wiring epic
with 2 lines of Python to expose `scan_run_id`.

## Architecture Decisions

- **Auto-navigate on debate complete** — matches the existing ScanResultsPage pattern. The
  drawer closes naturally when router navigates to `/debate/{id}`.
- **Keep drawer open during modal** — DebateProgressModal overlays the drawer. No need to
  close/reopen.
- **Tooltip-only on 409** — disable button with tooltip "Operation in progress" when
  `operationStore.inProgress` is true. No toast (matches ScanPage pattern).
- **Replicate ScanResultsPage debate flow** — `startDebate()` → modal → WebSocket → navigate.
  The exact code exists in ScanResultsPage lines 159-191; adapt for TickerDrawer.
- **ConsensusPanel as separate component** — reusable, testable, keeps DebateResultPage clean.
- **No database migrations** — `ai_theses.scan_run_id` column already exists and is nullable.

## Technical Approach

### Backend (2 lines)

1. `src/options_arena/api/schemas.py` — Add `scan_run_id: int | None = None` to `DebateResultDetail`
2. `src/options_arena/api/routes/debate.py` — Add `scan_run_id=row.scan_run_id,` in `get_debate()` response construction

### Frontend Types

`web/src/types/debate.ts` — Add 5 optional fields to `DebateResult` interface:
- `contrarian_dissent?: string | null`
- `agent_agreement_score?: number | null`
- `dissenting_agents?: string[]`
- `agents_completed?: number | null`
- `scan_run_id?: number | null`

### ConsensusPanel Component (new)

`web/src/components/ConsensusPanel.vue` — Props: `agreementScore`, `agentsCompleted`,
`dissentingAgents`, `contrarianDissent`. Renders agreement percentage bar, dissenting
agent names, contrarian challenge text. Hidden when `agreementScore` is null (v1 debates).

### DebateResultPage Changes

- Import and place `ConsensusPanel` between thesis banner and agent cards grid
- Conditional: `v-if="isV2 && debate?.agent_agreement_score != null"`
- Add `data-testid="consensus-panel"` for E2E
- Add "Back to Scan Results" `Button` with `v-if="debate?.scan_run_id"` in page header

### TickerDrawer Debate Button

- Remove hardcoded `disabled` attribute
- Add `@click="startDebate"` handler (adapted from ScanResultsPage pattern)
- Import: `DebateProgressModal`, `useDebateStore`, `useOperationStore`, `useWebSocket`, `useToast`
- Add local state: `debateModalVisible`, `debatingTicker`
- Wire: POST → WebSocket → `router.push('/debate/{id}')` on complete
- Disable when `operationStore.inProgress` (tooltip: "Operation in progress")
- Disable during active debate (prevent double-submit)
- `onUnmounted` cleanup for WebSocket close

## Implementation Strategy

### Wave 1: Type/Schema Updates (parallelizable BE + FE)
- Backend `scan_run_id` addition (2 Python lines)
- TS `DebateResult` interface additions (5 lines)

### Wave 2: ConsensusPanel + DebateResultPage (depends on Wave 1 types)
- Create `ConsensusPanel.vue`
- Integrate in `DebateResultPage.vue` + add back-to-scan nav

### Wave 3: TickerDrawer Debate Button (depends on Wave 1 types)
- Wire click handler, modal, WebSocket, navigation

### Wave 4: Testing
- Backend: pytest for schema + route handler `scan_run_id`
- E2E: full scan → drawer → debate → result → consensus → back-to-scan flow

## Task Breakdown Preview

- [ ] Task 1: Add `scan_run_id` to API schema/route + add 5 fields to TS `DebateResult` interface
- [ ] Task 2: Create `ConsensusPanel.vue` component + integrate in `DebateResultPage` + back-to-scan nav
- [ ] Task 3: Wire debate button in `TickerDrawer.vue` with modal, WebSocket, and navigation
- [ ] Task 4: Add backend test for `scan_run_id` in debate response + E2E test for full flow

## Dependencies

### Internal (all exist)
- `POST /api/debate` — accepts `{ ticker, scan_id }`, returns `{ debate_id }`
- `WS /ws/debate/{id}` — streams agent progress + completion events
- `GET /api/debate/{id}` — returns `DebateResultDetail` (needs `scan_run_id` addition)
- `DebateProgressModal.vue` — reusable single-debate modal
- `useWebSocket` composable — generic WebSocket management
- `useOperationStore` — operation lock state
- `ai_theses.scan_run_id` — DB column already exists

### External
- None

## Success Criteria (Technical)

| Criteria | Validation |
|----------|-----------|
| Debate button enabled in TickerDrawer | Click triggers `POST /api/debate` with ticker + scan_id |
| WebSocket streams progress | DebateProgressModal shows agent status updates |
| Auto-navigate on complete | Router pushes to `/debate/{id}` after `complete` event |
| Consensus panel renders for v2 | Agreement %, dissenting agents, contrarian text visible |
| Consensus panel hidden for v1 | No panel when `agent_agreement_score` is null |
| Back-to-scan link present | `Button` visible when `scan_run_id` is set, navigates to `/scan/{id}` |
| Back-to-scan link absent | Hidden for standalone debates |
| Double-click prevention | Button disabled during active debate |
| Operation lock respect | Button disabled with tooltip when global operation in progress |
| `scan_run_id` in API response | `GET /api/debate/{id}` includes nullable `scan_run_id` field |
| All existing tests pass | No regressions |

## Estimated Effort

**Size: S (Small)** — 4 tasks, ~200-250 lines of new/changed code

- 2 lines Python backend (additive, no migrations)
- ~100-150 lines new `ConsensusPanel.vue`
- ~50 lines TickerDrawer additions (adapted from existing pattern)
- ~30 lines DebateResultPage additions
- 5 lines TS type additions
- ~50-80 lines tests

All patterns are established and the exact debate flow code exists in ScanResultsPage to replicate.

## Tasks Created
- [ ] #307 - Add scan_run_id to API schema and consensus fields to TS interface (parallel: true)
- [ ] #308 - Create ConsensusPanel component, integrate in DebateResultPage with back-to-scan nav (parallel: true, after #307)
- [ ] #309 - Wire debate button in TickerDrawer with modal, WebSocket, and navigation (parallel: true, after #307)
- [ ] #310 - Add backend test for scan_run_id and E2E test for debate flow (parallel: false, after #307-#309)

Total tasks: 4
Parallel tasks: 3 (#307 standalone; #308+#309 in parallel after #307)
Sequential tasks: 1 (#310 after all)
Estimated total effort: 6.5 hours

## Test Coverage Plan
Total test files planned: 2
Total test cases planned: 7 (3 backend schema + 4 E2E)
