# Research: debate-flow-ux

## PRD Summary

The scan-to-debate workflow — the product's core user journey — has three UX defects:
1. **Debate button permanently disabled** — `TickerDrawer.vue:267` has hardcoded `disabled` attribute
2. **Consensus data invisible** — 4 consensus fields computed/persisted/served by API but missing from TS types and not rendered
3. **No back-to-scan navigation** — `scan_run_id` stored in DB but not exposed in API or frontend

## Relevant Existing Modules

- `web/src/components/TickerDrawer.vue` — Drawer with disabled debate button (line 267). Props: `visible`, `score: TickerScore | null`, `scanId: number`. Has `useRouter()`, receives scan context via props.
- `web/src/pages/DebateResultPage.vue` — ~569 lines. Fetches via `useDebateStore.fetchDebate()`. Has `isV2` computed for v2 protocol detection. Missing consensus panel and back-nav.
- `web/src/components/DebateProgressModal.vue` — ~351 lines. Supports single + batch mode via `batchMode` prop. Single mode props: `visible`, `ticker`, `agents`, `error`. Emits `update:visible`.
- `web/src/types/debate.ts` — `DebateResult` interface missing 5 fields: `contrarian_dissent`, `agent_agreement_score`, `dissenting_agents`, `agents_completed`, `scan_run_id`.
- `web/src/stores/debate.ts` — `startDebate(ticker, scanId)`, `fetchDebate(id)`, `updateAgentProgress()`, `setDebateComplete()`, `reset()`.
- `web/src/stores/operation.ts` — `useOperationStore` with `inProgress` computed, `start(type)`, `finish()`.
- `web/src/composables/useWebSocket.ts` — Generic WebSocket composable. Returns `{ connected, reconnecting, send, close }`.
- `src/options_arena/api/schemas.py` — `DebateResultDetail` has all 4 consensus fields but missing `scan_run_id`.
- `src/options_arena/api/routes/debate.py` — `get_debate()` extracts consensus from `ExtendedTradeThesis` JSON but doesn't include `row.scan_run_id` in response.
- `src/options_arena/data/` — `DebateRow.scan_run_id: int | None` already typed and populated from DB.

## Existing Patterns to Reuse

- **Debate-from-scan pattern** (`ScanResultsPage.vue` lines 159-191): The exact pattern for wiring debate button exists — `startDebate()` → modal → WebSocket → navigate on complete. Replicate in TickerDrawer.
- **v2 conditional rendering** (`DebateResultPage.vue`): `isV2 = computed(() => debate.value?.debate_protocol === 'v2')` already used for agent cards. Reuse for consensus panel visibility.
- **PrimeVue Button with router link**: Used throughout for navigation. Back-to-scan link should use `Button` with `severity="secondary"`, `icon="pi pi-arrow-left"`.
- **Operation lock check**: `useOperationStore().inProgress` used in ScanPage to disable buttons. Apply same pattern to debate button.
- **DebateProgressModal single mode**: Already supports single-ticker debates — just pass `ticker`, `agents`, `error` props (no `batchMode`).

## Existing Code to Extend

- `web/src/types/debate.ts` — Add 5 optional fields to `DebateResult` interface (5 lines)
- `src/options_arena/api/schemas.py:333` — Add `scan_run_id: int | None = None` to `DebateResultDetail` (1 line)
- `src/options_arena/api/routes/debate.py:601-647` — Add `scan_run_id=row.scan_run_id,` to response construction (1 line)
- `web/src/components/TickerDrawer.vue:261-269` — Replace hardcoded `disabled` with click handler, add modal + WebSocket integration (~50 lines)
- `web/src/pages/DebateResultPage.vue` — Add `ConsensusPanel` import + placement + back-to-scan `Button` (~30 lines)

## Potential Conflicts

- **None significant.** The feature touches frontend display code that no other PRD/epic is modifying. The 2-line Python backend change is additive (new optional field).
- **Operation lock nuance**: Single debates do NOT use the operation lock (confirmed in route handler comments). The button should only check `operationStore.inProgress` for UX feedback, not as a hard gate.

## Open Questions

1. **Navigate on complete vs "View Result" button**: PRD says "navigate to `/debate/{id}` or show 'View Result' button." The ScanResultsPage pattern navigates automatically. Should TickerDrawer do the same (auto-navigate closes drawer), or show a button in the modal? **Recommendation**: Auto-navigate (matches existing pattern, simpler).
2. **Drawer close on debate start**: Should the drawer remain open while the modal shows, or close? **Recommendation**: Keep drawer open — modal overlays it. Drawer closes when navigating to debate result.
3. **Toast on 409**: PRD says disable with tooltip on 409. Should we also show a toast? **Recommendation**: Tooltip only (less intrusive, matches ScanPage pattern).

## Recommended Architecture

### Wave 1: Type/Schema Updates (Backend + Frontend, parallelizable)
- Add `scan_run_id` to `DebateResultDetail` schema (1 line)
- Add `scan_run_id=row.scan_run_id` to `get_debate()` response (1 line)
- Add 5 fields to `DebateResult` TS interface (5 lines)

### Wave 2: ConsensusPanel + DebateResultPage (after Wave 1)
- Create `ConsensusPanel.vue` — agreement bar, dissenting list, contrarian text
- Integrate in `DebateResultPage.vue` between thesis banner and agent cards
- Add back-to-scan `Button` in page header

### Wave 3: TickerDrawer Debate Button (after Wave 1)
- Remove `disabled`, add `@click="startDebate"` with operation lock check
- Import DebateProgressModal, debate store, WebSocket composable, toast
- Wire full debate flow: POST → WebSocket → navigate on complete
- Add `onUnmounted` cleanup for WebSocket

### Wave 4: Testing
- E2E: scan → drawer → debate → result → back-to-scan
- Unit/integration: ConsensusPanel rendering, v1 vs v2 conditionals, back-nav visibility

## Test Strategy Preview

- **E2E tests** (`web/e2e/`): Playwright with 4 parallel workers, isolated DBs. Pattern: `test('description', async ({ page }) => { ... })`.
- **Frontend unit tests**: Not yet established (Vitest planned but not implemented). ConsensusPanel could be first.
- **Backend tests** (`tests/`): pytest + pytest-asyncio. Schema changes testable via model instantiation. Route handler testable with mock repository.
- **Mocking**: debate store uses `pinia` testing utils; API calls mocked via `msw` or direct store manipulation.

## Estimated Complexity

**Size: S (Small)**

Justification:
- 2 lines of Python backend changes (additive, no migrations)
- 1 new Vue component (~100-150 lines)
- 3 existing files modified with well-understood patterns
- All data already flows end-to-end; just needs frontend wiring
- Existing debate flow pattern in ScanResultsPage provides exact template to replicate
- No architectural decisions — all patterns established
