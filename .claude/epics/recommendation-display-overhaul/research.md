# Research: recommendation-display-overhaul

## PRD Summary

Update the Vue 3 frontend to natively render the new `RecommendationResponse` format (6 desk assessments, position recommendations, quant metrics, spread strategies) from `GET /api/debate/{id}`, while preserving backward compatibility for legacy `DebateResultDetail` records. Consolidate 5 duplicated agent card components into a shared shell. Extract duplicated formatting utilities into a shared composable.

## Relevant Existing Modules

- `web/src/pages/DebateResultPage.vue` (399 lines) — Primary page to overhaul. Currently renders old format only (bull/bear/thesis layout with JSON.parse on vol_response string).
- `web/src/types/debate.ts` (127 lines) — TypeScript interfaces. Missing `RecommendationResponse`, `DeskAssessmentBrief`, `PositionRecommendationResponse`, `SpreadDetail`, and quant metric types.
- `web/src/stores/debate.ts` (249 lines) — Pinia store. `fetchDebate()` casts response as single `DebateResult` type — needs union handling.
- `web/src/components/AgentCard.vue` (127 lines) — Generic agent card, duplicated CSS base.
- `web/src/components/FlowAgentCard.vue` (122 lines) — Flow desk card, 46 lines shared CSS.
- `web/src/components/FundamentalAgentCard.vue` (127 lines) — Fundamental desk card, 46 lines shared CSS.
- `web/src/components/RiskAgentCard.vue` (150 lines) — Risk desk card, 46 lines shared CSS.
- `web/src/components/ContrarianAgentCard.vue` (117 lines) — Contrarian desk card, 46 lines shared CSS.
- `web/src/components/ConsensusPanel.vue` (213 lines) — Agreement display. Works for new format but hardcodes "8 agents" — needs dynamic count.
- `web/src/components/ConfidenceBadge.vue` (50 lines) — Reuse directly in desk assessment cards.
- `web/src/components/DirectionBadge.vue` (40 lines) — Reuse directly in desk assessment cards.
- `src/options_arena/api/schemas.py` — Backend source of truth for both response formats.
- `src/options_arena/api/routes/debate.py` — Dual-table lookup logic (recommendation_results first, ai_theses fallback).

## Existing Patterns to Reuse

### 1. Discriminated union pattern (WebSocket events)
**Where**: `web/src/types/ws.ts`, consumed in `web/src/composables/useWebSocket.ts`
**How to apply**: Same `switch(event.type)` pattern. Frontend detects format via `'assessments' in response` type guard. Store exposes a computed `isNewFormat` flag.

### 2. Agent card layout (5 components)
**Where**: All agent card `.vue` files share identical structure: `.agent-card` → `.agent-header` (icon + name + ConfidenceBadge) → `.agent-field` or `.agent-section` content.
**How to apply**: Extract into `AgentCardShell.vue` with named slots (`#header-extra`, `#default`). All 5 existing cards and new `DeskAssessmentCard` wrap this shell.

### 3. Field label/value pattern
**Where**: `FlowAgentCard.vue`, `RiskAgentCard.vue`, `FundamentalAgentCard.vue` — `.field-label` (0.7rem uppercase) + `.field-value` (0.85rem body text).
**How to apply**: Reuse in `PositionRecommendationPanel` and `QuantMetricsPanel` for structured data display.

### 4. Nullable field guarding
**Where**: `RiskAgentCard.vue` lines 31-49 — pattern of `v-if="field != null"` per optional field, with computed formatters for percentages.
**How to apply**: Same pattern for quant metrics (all nullable) and spread details (optional).

### 5. Price string formatting
**Where**: `web/src/utils/formatters.ts` (or inline in components) — `Intl.NumberFormat` with `style: 'currency'`, `Number()` only for display, never storage.
**How to apply**: Use for `entry_price`, `stop_loss`, `take_profit`, `net_premium`, `max_profit`, `max_loss`, `strike` in spread legs. All arrive as strings from Decimal serialization.

### 6. Responsive card grid
**Where**: `DebateResultPage.vue` — `grid-template-columns: repeat(auto-fill, minmax(350px, 1fr))`.
**How to apply**: Same grid for desk assessment cards (6 cards, auto-wrapping).

### 7. Summary card pattern (analytics)
**Where**: `web/src/components/analytics/SummaryCard.vue` — flex column with large value + small label.
**How to apply**: Reference layout for position details panel (entry price, stop loss, R:R ratio as prominent values).

## Existing Code to Extend

### `web/src/types/debate.ts` — Add new interfaces
- Add `RecommendationResponse` (11 fields + nested types)
- Add `DeskAssessmentBrief` (5 fields: desk, direction, confidence, summary, key_findings)
- Add `PositionRecommendationResponse` (16 fields, all strings for Decimals)
- Add `SpreadDetail` (9 fields) and `SpreadLegDetail` (8 fields)
- Add `QuantMetrics` convenience type (10 fields from DebateResultDetail)
- Add type guard: `isRecommendationResponse(data: unknown): data is RecommendationResponse`
- Add union: `type DebateOrRecommendation = RecommendationResponse | DebateResult`

### `web/src/stores/debate.ts` — Handle union response
- Change `currentDebate` from `ref<DebateResult | null>` to `ref<DebateOrRecommendation | null>`
- Add computed `isNewFormat` using type guard
- `fetchDebate()` returns union type, no casting needed

### `web/src/pages/DebateResultPage.vue` — Format routing
- Add conditional rendering: `v-if="isNewFormat"` → new layout, `v-else` → existing layout
- New layout: header → position panel → spread panel → desk grid → quant panel → consensus → metadata
- Old layout: preserved as-is (thesis banner → consensus → agent cards → metadata)

### `web/src/components/ConsensusPanel.vue` — Dynamic agent count
- Line 54: Change hardcoded "8" to prop-driven count or remove fixed denominator
- Works for both formats with minor adjustment

## Potential Conflicts

### 1. Agent card refactoring during active rendering
**Risk**: Refactoring 5 agent cards into shell + content while DebateResultPage still imports them. If shell extraction and page overhaul happen in wrong order, intermediate state breaks.
**Mitigation**: Extract AgentCardShell first (wave 1), then refactor existing cards to use it (wave 2), then add new-format rendering (wave 3).

### 2. Store type widening
**Risk**: Changing `currentDebate` type from `DebateResult` to `DebateOrRecommendation` could cause TypeScript errors in components that assume the old type.
**Mitigation**: Use type narrowing in every consumer. Components that render old format use `v-if="!isNewFormat"` with type guard assertion.

### 3. ConsensusPanel agent count
**Risk**: ConsensusPanel displays "X/8 agents participated" — wrong for new format (6 desks).
**Mitigation**: Accept `totalDesks` prop (default 6 for new, 8 for old). Minor change.

### 4. List endpoint ambiguity
**Risk**: `GET /api/debate` returns `DebateResultSummary` for both old and new records — same shape. Frontend can't distinguish format until clicking into detail.
**Mitigation**: Add subtle visual indicator on list items. The `model_name` field differs (new uses "llama-3.3-70b" etc., old uses older model names) but this is fragile. Better: accept that list view is format-agnostic.

## Open Questions

1. **Quant metrics in new format?** The `RecommendationResponse` schema does NOT include quant fields (`hv_yang_zhang`, `skew_25d`, etc.) — these only exist in `DebateResultDetail`. Should the backend be extended to include them in the new format, or are they intentionally omitted? **Impact**: If omitted, the quant panel only renders for legacy debates.

2. **Spread in new format?** `RecommendationResponse` does not include a `spread` field — only `DebateResultDetail` has `spread: SpreadDetail | None`. Is spread data available for new-format recommendations? **Impact**: Determines whether SpreadDetailPanel renders for new results.

3. **Lossy fields acceptable?** The new format loses: per-desk `risks`, `contracts_referenced`, `tools_used`, `model_used` (per desk), full `MarketContext`, `DeskMetrics` timing, and `AssessmentSummary` (direction votes). Is the `DeskAssessmentBrief` (desk, direction, confidence, summary, key_findings) sufficient for the UI, or should the API be enriched?

4. **Format indicator on list?** Should the debate list show whether a result is new-format (recommendation) vs old-format (debate)? The `DebateResultSummary` schema is identical for both. If yes, backend needs a discriminant field (e.g., `format: 'recommendation' | 'debate'`).

## Recommended Architecture

### Type system
```
types/debate.ts (extended)
├── DebateResult (existing, for old format)
├── RecommendationResponse (NEW)
│   ├── DeskAssessmentBrief
│   └── PositionRecommendationResponse
├── SpreadDetail + SpreadLegDetail (NEW)
├── QuantMetrics (convenience extraction type)
├── DebateOrRecommendation = union
└── isRecommendationResponse() type guard
```

### Component hierarchy (new format)
```
DebateResultPage.vue
├── [v-if="isNewFormat"]
│   ├── RecommendationHeader (ticker, direction, confidence, protocol tag)
│   ├── PositionRecommendationPanel (entry, stop, target, size, R:R)
│   ├── SpreadDetailPanel (v-if spread exists)
│   ├── DeskAssessmentCard × N (grid, one per assessment)
│   │   └── uses AgentCardShell (shared frame)
│   ├── QuantMetricsPanel (v-if any quant field present) — OLD FORMAT ONLY per current API
│   ├── ConsensusPanel (if agreement data present)
│   └── MetadataStrip (model, duration, tokens, citation density, protocol)
├── [v-else — old format, preserved]
│   ├── ThesisBanner
│   ├── ConsensusPanel
│   ├── AgentCardShell → AgentCard (trend/bull)
│   ├── AgentCardShell → FlowAgentCard
│   ├── AgentCardShell → FundamentalAgentCard
│   ├── AgentCardShell → AgentCard (volatility, from JSON.parse)
│   ├── AgentCardShell → RiskAgentCard
│   ├── AgentCardShell → ContrarianAgentCard
│   └── MetadataStrip
```

### New components (4)
1. **`DeskAssessmentCard.vue`** (~80 lines) — Renders `DeskAssessmentBrief`: desk icon + name, DirectionBadge, ConfidenceBadge, summary, key_findings list. Color derived from desk name via lookup map.
2. **`PositionRecommendationPanel.vue`** (~100 lines) — Grid of price fields (entry, stop, target), position size bar, R:R ratio, strategy tag, rationale text. All prices as formatted strings.
3. **`SpreadDetailPanel.vue`** (~120 lines) — PrimeVue DataTable for legs (option_type, strike, expiration, side, quantity, bid, ask, delta). Summary row: net premium, max P&L, R:R, POP, breakevens.
4. **`QuantMetricsPanel.vue`** (~80 lines) — Two-column grid: HV + vol surface (left), higher-order Greeks (right). Conditional render per non-null field.

### Shared extraction (2)
5. **`AgentCardShell.vue`** (~60 lines) — Shared card frame: border-left accent, header (icon + name + badge slot), default slot for content. Eliminates 230 lines of duplicated CSS.
6. **`composables/useFormatters.ts`** (~50 lines) — `formatPrice`, `formatPct`, `formatReturnPct`, `formatGreek`, `formatDuration`. Consolidates duplicated functions from 4+ components.

### Implementation waves
- **Wave 1 (foundation)**: Types, store, AgentCardShell, useFormatters composable
- **Wave 2 (refactor)**: Migrate 5 existing agent cards to use AgentCardShell, fix ConsensusPanel
- **Wave 3 (new format)**: DeskAssessmentCard, PositionRecommendationPanel, SpreadDetailPanel, QuantMetricsPanel
- **Wave 4 (integration)**: DebateResultPage format routing, MetadataStrip extension, testing

## Test Strategy Preview

### Existing test patterns
- No frontend tests currently exist in `web/src/__tests__/` (directory structure defined in CLAUDE.md but not populated)
- Backend debate route has E2E tests in `tests/e2e/`
- Component test pattern from CLAUDE.md uses Vitest + Vue Test Utils

### Recommended test approach
- **Type guard tests**: Unit test `isRecommendationResponse()` with both format fixtures
- **Component tests**: Mount new components with mock data, verify render output
- **Snapshot tests**: Capture DebateResultPage rendering for both formats
- **Manual visual testing**: Both formats render correctly in browser (dark theme)
- **Regression**: Existing old-format debate IDs still render correctly after changes

### Test fixtures needed
- Mock `RecommendationResponse` JSON (6 assessments, full position details)
- Mock `DebateResultDetail` JSON (old format with bull/bear/thesis)
- Mock `SpreadDetail` JSON (2-leg vertical spread)

## Estimated Complexity

**L (Large)** — 7-10 days of focused work.

Justification:
- 4 new components + 2 shared extractions + 1 major page overhaul
- Type system extension (union type, type guard, 6+ new interfaces)
- Store modification (union handling, computed format detection)
- 5 existing component refactors (agent cards → shell pattern)
- ConsensusPanel fix
- No backend changes needed (API is ready)
- Testing (manual + type guard unit tests)
- Risk: moderate — refactoring active rendering path requires care to avoid regressions
