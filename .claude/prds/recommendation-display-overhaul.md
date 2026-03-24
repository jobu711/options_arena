---
name: recommendation-display-overhaul
description: Overhaul DebateResultPage and types to natively render RecommendationResponse format with 6-desk assessments, position details, quant metrics, and spread strategies
status: researched
created: 2026-03-23T23:36:20Z
effort: L
---

# PRD: recommendation-display-overhaul

## Executive Summary

The backend's recommendation system was rewritten in 3.0.0 to return structured `RecommendationResponse` objects with 6 desk assessments, position recommendations (entry/stop/target), and quant metrics. The frontend's `DebateResultPage` still renders the old `DebateResultDetail` format — bull/bear/thesis layout with JSON.parse on raw strings. When the API returns new-format data, the frontend silently drops the `assessments`, `recommendation`, and `recommendation_protocol` fields because they don't exist in the TypeScript `DebateResult` type.

This epic updates the frontend to natively consume both response formats, rendering the new 6-desk structured layout for current recommendations while preserving backward compatibility for legacy debate records.

## Problem Statement

**The backend returns a discriminated union (`RecommendationResponse | DebateResultDetail`) from `GET /api/debate/{id}`, but the frontend treats all responses as a single `DebateResult` type that only covers old-format fields.**

Concrete issues:

1. **Silent data loss**: New-format responses contain `assessments: DeskAssessmentBrief[]` and `recommendation: PositionRecommendationResponse` — these fields are not in the frontend type and are discarded by TypeScript.

2. **Missing position details**: The new format includes `entry_price`, `stop_loss`, `take_profit`, `position_size_pct`, `risk_reward_ratio`, `strategy`, and `strategy_rationale`. None of this is rendered.

3. **Missing quant metrics**: Even the old format includes `hv_yang_zhang`, `skew_25d`, `smile_curvature`, `prob_above_current`, `target_vanna`, `target_charm`, `target_vomma`, `iv_surface_residual`, `surface_fit_r2` — none exposed to the frontend.

4. **Missing spread strategies**: Both formats can include `SpreadDetail` with legs, max profit/loss, risk/reward, breakevens, and strategy rationale. Not rendered.

5. **Fragile JSON parsing**: `vol_response` and `bull_rebuttal` are stored as raw JSON strings in the old format and parsed with `try/catch JSON.parse()` — no error logging, no fallback UI.

6. **Agent card duplication**: 5 agent card components (`AgentCard`, `FlowAgentCard`, `FundamentalAgentCard`, `RiskAgentCard`, `ContrarianAgentCard`) duplicate ~50 lines of identical CSS each.

## User Stories

### US1: View new-format recommendation
**As a** trader reviewing an AI recommendation,
**I want to** see all 6 desk assessments with their direction, confidence, and key findings,
**So that** I understand the reasoning from each analytical perspective.

**Acceptance criteria:**
- Each desk assessment renders as a card with desk name, direction badge, confidence badge, summary text, and key findings list
- All 6 desks (trend, volatility, flow, fundamental, risk, contrarian) are displayed when present
- Missing desks show no card (not an empty card)

### US2: View position recommendation details
**As a** trader preparing to execute a trade,
**I want to** see the recommended entry price, stop loss, take profit, position size, and risk/reward ratio,
**So that** I can evaluate the trade setup before placing an order.

**Acceptance criteria:**
- Position details panel shows: contract description, entry price, stop loss, take profit (all as formatted currency strings — never parsed to float)
- Position size shown as percentage
- Risk/reward ratio displayed
- Strategy name and rationale visible
- Panel only renders when `recommendation` field is present

### US3: View spread strategy details
**As a** trader evaluating multi-leg strategies,
**I want to** see spread legs, max profit/loss, breakevens, and P.O.P. estimate,
**So that** I can assess the risk profile before execution.

**Acceptance criteria:**
- Spread panel shows: spread type, individual legs (option type, strike, expiration, side, quantity), net premium, max profit, max loss, risk/reward ratio, P.O.P. estimate, breakeven prices
- All prices displayed as formatted strings (Decimal precision)
- Panel only renders when `spread` field is present

### US4: View quant metrics
**As a** quantitative trader,
**I want to** see volatility surface metrics, higher-order Greeks, and surface mispricing signals,
**So that** I can validate the recommendation against my own vol analysis.

**Acceptance criteria:**
- Quant metrics panel shows: HV (Yang-Zhang), 25-delta skew, smile curvature, prob above current, target vanna/charm/vomma
- Surface mispricing section shows: IV surface residual, surface fit R², dimensionality flag
- All values formatted to appropriate decimal places (Greeks: 4dp, percentages: 1dp, R²: 3dp)
- Panel only renders when at least one quant field is non-null
- Null individual fields display as "--"

### US5: View legacy debate results
**As a** user browsing historical debates,
**I want to** see old-format debates rendered correctly,
**So that** historical data remains accessible.

**Acceptance criteria:**
- Old-format debates render with existing bull/bear/thesis/vol layout
- No regressions in current rendering for legacy records
- Page detects format via discriminant field and routes to correct layout

### US6: Debate list shows format indicator
**As a** user browsing the debate list,
**I want to** distinguish between new recommendations and legacy debates,
**So that** I know which format to expect when clicking through.

**Acceptance criteria:**
- List view shows a subtle indicator (tag or icon) for recommendation vs legacy debate
- Both formats link correctly to detail page

## Requirements

### Functional Requirements

#### FR1: Discriminated union types
Add TypeScript types for the new `RecommendationResponse` format alongside existing `DebateResult`. Create a discriminated union with a type guard:
- `RecommendationResponse`: has `assessments` and `recommendation` fields
- `DebateResultDetail`: has `bull_response`, `thesis` fields (existing `DebateResult`)
- Type guard: check for `assessments` field presence

**Files:** `web/src/types/debate.ts`

#### FR2: Store handles both formats
Update `useDebateStore.fetchDebate()` to store the response in a union type and expose a computed that identifies the format.

**Files:** `web/src/stores/debate.ts`

#### FR3: DebateResultPage format routing
Page detects response format and renders the appropriate layout:
- New format → desk assessment grid + position panel + quant metrics
- Old format → existing bull/bear/thesis layout (preserved)

**Files:** `web/src/pages/DebateResultPage.vue`

#### FR4: DeskAssessmentCard component
New component for rendering a single desk assessment (direction, confidence, summary, key findings). Replaces the per-agent card pattern for new-format responses.

**Files:** `web/src/components/DeskAssessmentCard.vue`

#### FR5: PositionRecommendationPanel component
New component for rendering position details (entry, stop, target, size, R:R, strategy).

**Files:** `web/src/components/PositionRecommendationPanel.vue`

#### FR6: SpreadDetailPanel component
New component for rendering spread strategy (legs table, max P&L, breakevens, P.O.P.).

**Files:** `web/src/components/SpreadDetailPanel.vue`

#### FR7: QuantMetricsPanel component
New component for rendering vol surface metrics and higher-order Greeks.

**Files:** `web/src/components/QuantMetricsPanel.vue`

#### FR8: AgentCardShell shared component
Extract the duplicated card frame (header, border-left accent, section/list patterns) from 5 existing agent cards into a single shell component with slots. Refactor existing cards to use it.

**Files:** `web/src/components/AgentCardShell.vue`, plus refactoring `AgentCard.vue`, `FlowAgentCard.vue`, `FundamentalAgentCard.vue`, `RiskAgentCard.vue`, `ContrarianAgentCard.vue`

#### FR9: Formatting composable
Extract duplicated `formatPct`, `formatReturnPct`, `formatPrice`, `formatDuration` functions into a shared composable.

**Files:** `web/src/composables/useFormatters.ts`

### Non-Functional Requirements

#### NFR1: Price string safety
All `Decimal`-as-string fields (`entry_price`, `stop_loss`, `take_profit`, `strike`, `bid`, `ask`, `net_premium`, `max_profit`, `max_loss`) must NEVER be parsed to JavaScript `number` for storage or computation. Use `Number()` only inside display formatting functions. Type these as `string` in TypeScript.

#### NFR2: Null defense
Every nullable field must be guarded with `v-if` or `?? '--'` before rendering. No `null` should render as the string `"null"`.

#### NFR3: No layout regression
Legacy debate records must render identically to current behavior. Visual regression check required.

#### NFR4: Bundle size
New components should not increase initial bundle size. Use same lazy-loading pattern (route-level code splitting already in place).

#### NFR5: Dark theme consistency
New components must use existing CSS custom properties (`--accent-*`, `--p-surface-*`, `--font-mono`). No hardcoded colors.

## Success Criteria

| Metric | Target |
|--------|--------|
| New-format field coverage | 100% of `RecommendationResponse` fields rendered |
| Legacy rendering regressions | Zero — old debates render identically |
| Duplicated agent card CSS | Reduced from ~250 lines across 5 files to ~50 lines in shared shell |
| Duplicated formatting functions | Consolidated into single composable |
| Price string violations | Zero `parseFloat()` / `Number()` on price fields outside formatters |

## Constraints & Assumptions

- **Backend is stable**: No backend changes required. The API already returns the correct data — the frontend just isn't consuming it.
- **Dual-table lookup persists**: The backend will continue returning both formats for the foreseeable future. Old `ai_theses` records won't be migrated.
- **PrimeVue 4.5.4**: Use existing PrimeVue components (DataTable for spread legs, Tag for badges). No new dependencies.
- **No new routes**: The existing `/debate/:id` route handles both formats. No router changes needed.

## Out of Scope

- **Backend API changes**: This is frontend-only work.
- **Design system / token overhaul**: Tracked separately as `frontend-design-system` epic.
- **Debate list page redesign**: The list endpoint (`GET /api/debate`) returns `DebateResultSummary` which works for both formats. Only a minor format indicator is added.
- **Analytics integration**: Connecting recommendation outcomes to analytics charts is a separate concern.
- **PDF export for new format**: Export endpoint returns Markdown; PDF generation is backend work.

## Dependencies

| Dependency | Type | Status |
|------------|------|--------|
| `GET /api/debate/{id}` dual-table lookup | Backend API | Shipped (3.0.0) |
| `RecommendationResponse` schema | Backend model | Shipped (schemas.py:584-689) |
| `DebateResultDetail` schema | Backend model | Shipped (schemas.py:489-577) |
| PrimeVue 4.5.4 (DataTable, Tag, Badge) | Frontend dep | Already installed |
| Existing agent card components | Frontend | In place, will be refactored |

## Implementation Notes

### Format detection strategy
The cleanest discriminant is checking for the `assessments` field:
```typescript
function isRecommendation(data: unknown): data is RecommendationResponse {
  return Array.isArray((data as RecommendationResponse).assessments)
}
```

### Component hierarchy (new format)
```
DebateResultPage
├── RecommendationHeader (ticker, direction, confidence, protocol badge)
├── PositionRecommendationPanel (entry, stop, target, size, R:R)
├── SpreadDetailPanel (if spread exists)
├── DeskAssessmentCard × 6 (grid layout, one per desk)
├── QuantMetricsPanel (if quant fields exist)
├── ConsensusPanel (preserved, works for both formats)
└── MetadataStrip (model, duration, tokens, citation density)
```

### Component hierarchy (old format — preserved)
```
DebateResultPage
├── ThesisBanner (direction, confidence, bull/bear scores)
├── ConsensusPanel (agreement score, dissenting agents)
├── AgentCardShell → AgentCard (bull/trend)
├── AgentCardShell → FlowAgentCard
├── AgentCardShell → FundamentalAgentCard
├── AgentCardShell → AgentCard (volatility, from JSON.parse)
├── AgentCardShell → RiskAgentCard
├── AgentCardShell → ContrarianAgentCard
└── MetadataStrip
```
