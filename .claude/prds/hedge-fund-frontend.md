---
name: hedge-fund-frontend
description: Gut rebuild of Vue 3 frontend as single-screen AI hedge fund trading desk — scan → consensus → recommendation pipeline
status: planned
created: 2026-03-24T12:49:56Z
effort: XL
---

# PRD: hedge-fund-frontend

## Executive Summary

Replace the entire Vue 3 frontend with a single-screen "trading desk" command center. One page shows the full pipeline: launch a scan, watch tickers stream in ranked by score, manually trigger `run_recommendation()` on any scored ticker, and view 6-desk agent consensus with contract-level position details — all in real-time via WebSocket. The current multi-page debate-era UI is deleted. This is a position identification tool, not a portfolio manager.

## Problem Statement

### What problem are we solving?

The backend was rewritten to a unified recommendation system (6 desk agents → synthesis → `PositionRecommendation`) but the frontend still renders the old debate format. The current UI requires navigating between 8 separate pages (Dashboard → Scan → Scan Results → Debate Result) to go from "scan the market" to "see a recommendation." The flow is fragmented, the terminology is stale ("debate" everywhere), and new-format data fields (`assessments`, `recommendation`, `recommendation_protocol`) are silently dropped because the TypeScript types don't include them.

### Why is this important now?

- Backend v3.0.0 is complete — unified agent system, prediction ledger, attribution, strategy mining, confidence decay all merged
- The user wants a full rebuild with a hedge fund aesthetic
- Every new backend feature (model routing costs, desk metrics, prediction tracking) has no frontend surface because the frontend is stuck on debate-era types

## User Stories

### US-1: Real-time scan pipeline
**As a** trader scanning for opportunities,
**I want to** launch a scan and see tickers stream into a ranked table in real-time,
**So that** I can watch the best opportunities surface without waiting for the full scan to complete.

**Acceptance criteria:**
- Select universe preset (SP500, Full, ETFs, NASDAQ 100, Russell 2000, Most Active) and optional filters from a collapsible filter panel
- Click Run — tickers appear in the pipeline table as they're scored, sorted by composite score descending
- Progress indicator shows scan phase and completion percentage
- Can cancel a running scan

### US-2: Manual recommendation trigger
**As a** trader reviewing scan results,
**I want to** trigger `run_recommendation()` on any scored ticker (single or batch-select multiple),
**So that** I control which tickers get full AI analysis — no wasted compute on tickers I'm not interested in.

**Acceptance criteria:**
- Each scored row has an "Analyze" action button for single-ticker recommendation
- Multi-select rows + "Analyze Selected" button for batch recommendation
- Pipeline table shows real-time stage transitions: `scored` → `analyzing` → `ready` (or `failed`)
- Stage badges update via WebSocket events

### US-3: View agent consensus and position details
**As a** trader evaluating an opportunity,
**I want to** click a ticker row and see the full recommendation — 6 desk assessments with direction/confidence/findings, plus the specific contract recommendation with entry/stop/target,
**So that** I can make an informed decision about whether to execute the trade.

**Acceptance criteria:**
- Right panel slides in showing recommendation detail for selected ticker
- 6 desk assessment cards: desk name, direction badge, confidence badge, summary, key findings
- Position card: contract description, strategy, entry price, stop loss, take profit, position size %, risk/reward ratio
- All prices displayed as formatted strings (never parsed to float)
- Missing desks or null fields show graceful fallbacks (`"--"`)

### US-4: Market context via heatmap
**As a** trader wanting market context while scanning,
**I want to** see the S&P 500 heatmap at a glance on the trading desk,
**So that** I understand the broader market environment when evaluating individual opportunities.

**Acceptance criteria:**
- Market heatmap (existing `MarketHeatmap.vue` component) displayed in the market context zone
- Regime banner shows current market regime when available
- Heatmap does not interfere with pipeline table or recommendation panel

### US-5: Batch recommendation from selection
**As a** trader who wants to analyze multiple tickers at once,
**I want to** select several scored tickers and trigger batch `run_recommendation()`,
**So that** I can efficiently analyze a group of interesting opportunities.

**Acceptance criteria:**
- Multi-select checkboxes on pipeline table rows
- "Analyze Selected" button triggers `POST /api/debate/batch` for selected tickers
- All selected rows update stage via batch WebSocket events
- Detail panel loads for any completed recommendation on click

## Architecture & Design

### Chosen Approach

Single-screen trading desk command center with three zones:

1. **Top bar** — scan controls (preset, filters, run button, live status)
2. **Left/center** — market heatmap (collapsible) + opportunity pipeline table
3. **Right panel** — recommendation detail (slides in on row selection)

One page replaces Dashboard, Scan, Scan Results, and Debate Result. Zero navigation for the core workflow.

### Module Changes

**Delete** (presentation-layer only — no backend changes):
- Pages: `DashboardPage.vue`, `ScanPage.vue`, `ScanResultsPage.vue`, `DebateResultPage.vue`, `TickerDetailPage.vue`, `AgencyPage.vue`, `DesksPage.vue`
- Components: `AgentCard.vue`, `FlowAgentCard.vue`, `FundamentalAgentCard.vue`, `RiskAgentCard.vue`, `ContrarianAgentCard.vue`, `ConsensusPanel.vue`, `DebateProgressModal.vue`, `DeskSelector.vue`
- Stores: `debate.ts`, `agency.ts`
- Types: `debate.ts`

**Keep** (reuse as-is):
- `MarketHeatmap.vue`, `ConfidenceBadge.vue`, `DirectionBadge.vue`, `HealthDot.vue`, `SparklineChart.vue`, `RegimeBanner.vue`
- `ScanFilterPanel.vue`, `FilterPresets.vue`, `PresetCard.vue`, `PreScanFilters.vue`, `FilterSummaryChips.vue`, `SectorTree.vue`
- All `analytics/*` components
- Composables: `useApi.ts`, `useWebSocket.ts`, `useOperation.ts`
- Stores: `scan.ts`, `health.ts`, `heatmap.ts`, `operation.ts`, `weights.ts`, `backtest.ts`
- Utils: `formatters.ts`

**Create new**:
- `pages/TradingDeskPage.vue` — single-screen command center
- `pages/AnalyticsPage.vue` — lightweight rebuild for historical performance (reuses existing analytics components)
- `components/DeskCard.vue` — universal card wrapper for masonry grid: header bar (title, collapse toggle, status badge), collapsible body, consistent dark surface styling. All grid panels use this as their outer shell.
- `components/OpportunityTable.vue` — live-updating pipeline table with stage badges, sortable/filterable, multi-select checkboxes. Must use `scrollable`, `scrollHeight`, and `virtualScrollerOptions="{ itemSize: 44 }"` together for virtual scroll (PrimeVue requirement). Spans full grid width via `grid-column: 1 / -1`.
- `components/DeskAssessmentCard.vue` — single unified card for any desk assessment (replaces 5 duplicate cards). One per desk, flows into masonry grid.
- `components/AgentConsensus.vue` — compact 6-desk consensus summary (direction + confidence per desk in a dense layout)
- `components/PositionCard.vue` — entry/stop/target/contract/R:R display
- `components/PipelineStatus.vue` — stage badge component (queued/scored/analyzing/ready/failed)
- `components/ScanControlBar.vue` — top bar with preset selector, collapsible filter panel, run button, analyze selected button, live status
- `components/ScanProgressCard.vue` — scan phase progress (phase name, progress bar, ticker count, elapsed time). Visible only during active scan.
- `components/analytics/AttributionPanel.vue` — prediction attribution report: per-source accuracy, condition buckets, contract guidance. Consumes `GET /api/analytics/attribution` (currently unexposed)
- `stores/pipeline.ts` — Pinia store managing scan → recommend flow state machine
- `types/recommendation.ts` — new types for recommendation response, desk assessments, position details, attribution report

### Route Structure (8 → 3)

```typescript
const routes: RouteRecordRaw[] = [
  { path: '/', name: 'trading-desk', component: () => import('../pages/TradingDeskPage.vue') },
  { path: '/analytics', name: 'analytics', component: () => import('../pages/AnalyticsPage.vue') },
  { path: '/settings', name: 'settings', component: () => import('../pages/SettingsPage.vue') },  // V2: model routing, weights
]
```

### Data Models

```typescript
// types/recommendation.ts

type PipelineStage = 'queued' | 'scored' | 'analyzing' | 'ready' | 'failed'

/** Reuses existing DimensionalScores from types/scan.ts */
interface DimensionalScores {
  trend: number | null
  iv_vol: number | null
  hv_vol: number | null
  flow: number | null
  microstructure: number | null
  fundamental: number | null
  regime: number | null
  risk: number | null
}

interface PipelineTicker {
  ticker: string
  composite_score: number
  direction: 'bullish' | 'bearish' | 'neutral'
  direction_confidence: number | null
  dimensional_scores: DimensionalScores | null
  sector: string | null
  company_name: string | null
  stage: PipelineStage
  recommendation_id: number | null
}

/** Maps to backend DeskAssessmentBrief (schemas.py:584) */
interface DeskAssessment {
  desk: string    // 'trend' | 'volatility' | 'flow' | 'fundamental' | 'risk' | 'contrarian'
  direction: string
  confidence: number
  summary: string
  key_findings: string[]
}

/** Maps to backend PositionRecommendationResponse (schemas.py:605) */
interface PositionRecommendation {
  ticker: string
  option_type: string | null
  strike: string | null
  expiration: string | null
  recommended_contract: string
  entry_price: string       // Decimal as string — never parse to number
  stop_loss: string | null
  take_profit: string | null
  position_size_pct: number  // float 0.0-1.0
  risk_reward_ratio: number  // float > 0
  direction: string
  confidence: number
  strategy: string | null
  strategy_rationale: string
  rationale: string
}

/** Maps to backend RecommendationResponse (schemas.py:654) */
interface RecommendationDetail {
  id: number
  ticker: string
  assessments: DeskAssessment[]
  recommendation: PositionRecommendation
  is_fallback: boolean
  recommendation_protocol: string
  duration_ms: number
  total_tokens: number
  citation_density: number
  model_used: string
  created_at: string
  scan_run_id: number | null
}
```

/** Maps to backend PredictionAccuracy (models/attribution.py) */
interface PredictionAccuracy {
  source: string           // PredictionSource enum value
  total: int
  correct: int
  accuracy: number
  brier_score: number | null
}

/** Maps to backend ConditionBucketAccuracy (models/attribution.py) */
interface ConditionBucketAccuracy {
  source: string
  condition_key: string
  condition_value: string
  total: int
  correct: int
  accuracy: number
}

/** Maps to backend ContractGuidance (models/attribution.py) */
interface ContractGuidance {
  optimal_delta_low: number
  optimal_delta_high: number
  optimal_dte_low: number
  optimal_dte_high: number
  sample_size: number
}

/** Maps to backend AttributionReport (models/attribution.py:250) */
interface AttributionReport {
  window_days: number
  total_recommendations: number
  total_outcomes: number
  source_accuracy: PredictionAccuracy[]
  condition_accuracy: ConditionBucketAccuracy[]
  contract_guidance: ContractGuidance | null
}
```

All prices remain as `string` per project convention — formatted for display via `Intl.NumberFormat`, never stored as JavaScript `number`.

### Core Logic & Flow

**Pipeline state machine** (`stores/pipeline.ts`):

```
[idle] --scan started--> [scanning]
[scanning] --ticker scored--> add to tickers map, stage='scored'
[scanning] --scan complete--> [scanned] (all tickers scored, user reviews)
[scanned] --user clicks Analyze on row--> stage='analyzing' for that ticker
[scanned] --user selects rows + Analyze Selected--> stage='analyzing' for batch
[analyzing] --ticker ready--> stage='ready', set recommendation_id
[analyzing] --ticker failed--> stage='failed'
```

Store state:
- `tickers: Map<string, PipelineTicker>` — live pipeline state, keyed by ticker symbol
- `selectedTicker: string | null` — which row is expanded in detail panel
- `currentRecommendation: RecommendationDetail | null` — loaded detail for selected ticker
- `scanId: number | null` — active scan ID (for WebSocket connection)
- `batchId: number | null` — active batch ID (for WebSocket connection)
- `phase: 'idle' | 'scanning' | 'scanned'` — pipeline phase

**WebSocket integration**:
1. Scan progress: `WS /ws/scan/{scanId}` — updates tickers map as scores arrive
2. Batch progress: `WS /ws/batch/{batchId}` — updates stage badges per-ticker (user-initiated batch)
3. Single recommendation: `WS /ws/debate/{debateId}` — for single-ticker analysis

**Recommendation is always user-initiated**: The user reviews scan results, then explicitly triggers analysis on individual tickers (Analyze button) or a selection (multi-select + Analyze Selected). No auto-trigger.

### Layout — Masonry Grid

The Trading Desk uses a CSS Grid masonry layout — cards of varying heights that pack
efficiently without wasted whitespace. Each card is a self-contained panel with a header
bar and content area. Cards reflow based on available space and content.

**Grid configuration**: `display: grid; grid-template-columns: repeat(auto-fill, minmax(400px, 1fr)); grid-auto-rows: min-content; gap: 1rem;` — cards size to their content height and fill columns naturally.

**Card system**: Every panel is a `DeskCard.vue` wrapper — consistent header bar (title + collapse toggle + optional status badge), rounded corners, subtle border, dark surface background. Cards can be collapsed to header-only to reclaim space.

```
┌──────────────────────────────────────────────────────────────────────────┐
│  OPTIONS ARENA                    [Trading Desk]  [Analytics]   ● Live  │
├──────────────────────────────────────────────────────────────────────────┤
│  ┌─ SCAN CONTROL ──────────────────────────────────────────────────────┐│
│  │  [SP500 ▾] [Filters ▾] [▶ Run Scan] [Cancel]  [Analyze Selected]  ││
│  └─────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌─────────────────────────────┐  ┌──────────────────────────────────┐  │
│  │ ◉ MARKET CONTEXT        [−]│  │ ◉ SCAN PROGRESS              [−]│  │
│  │                             │  │                                  │  │
│  │  S&P 500 Heatmap            │  │  Phase: Scoring  ████░░  67%    │  │
│  │  ┌─────────────────────┐   │  │  347 / 503 tickers              │  │
│  │  │ AAPL MSFT GOOG AMZN│   │  │  Elapsed: 1m 23s                │  │
│  │  │ META NVDA TSLA ...  │   │  │                                  │  │
│  │  └─────────────────────┘   │  └──────────────────────────────────┘  │
│  │  Regime: Trending           │                                        │
│  └─────────────────────────────┘                                        │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐│
│  │ ◉ OPPORTUNITY PIPELINE (347 tickers)                         [−] ☰ ││
│  │                                                                      ││
│  │  ☐  Ticker   Score  Dir  Conf   Sector          Stage    Action     ││
│  │  ─────────────────────────────────────────────────────────────────  ││
│  │  ☐  AAPL     8.7    ▲    87%    Technology      ✓ Ready  [View]    ││
│  │  ☐  NVDA     8.3    ▲    82%    Technology      ⟳ ...    [View]    ││
│  │  ☐  TSLA     7.9    ▼    74%    Cons. Disc.     ⟳ ...             ││
│  │  ☐  META     7.6    ▲    71%    Technology      ● Scored [Analyze] ││
│  │  ☐  AMZN     7.2    ▲    68%    Cons. Disc.     ● Scored [Analyze] ││
│  │  ☐  GOOG     6.9    ►    55%    Technology      ● Scored [Analyze] ││
│  │  ...                                                                 ││
│  │  ● Scored  ⟳ Analyzing  ✓ Ready  ✕ Failed                          ││
│  └──────────────────────────────────────────────────────────────────────┘│
│                                                                          │
│  ┌──────────────────────────┐  ┌──────────────────────────────────────┐  │
│  │ ◉ AGENT CONSENSUS    [−]│  │ ◉ POSITION DETAIL                [−]│  │
│  │                          │  │                                      │  │
│  │  AAPL — Bullish (87%)    │  │  Buy AAPL 195C 4/18                 │  │
│  │                          │  │                                      │  │
│  │  Trend       ▲    82%   │  │  Entry:    $4.20                    │  │
│  │  Volatility  ▲    76%   │  │  Stop:     $2.10                    │  │
│  │  Flow        ▲    91%   │  │  Target:   $8.40                    │  │
│  │  Fundamental ▲    68%   │  │  R/R:      2.0x                     │  │
│  │  Risk        ►    55%   │  │  Size:     5%                       │  │
│  │  Contrarian  ▲    74%   │  │  Strategy: Long call                │  │
│  │                          │  │                                      │  │
│  └──────────────────────────┘  │  "Strong momentum with vol support  │  │
│                                 │   and institutional flow confirms..." │  │
│  ┌──────────────────────────┐  │                                      │  │
│  │ ◉ DESK: TREND         [−]│  └──────────────────────────────────────┘  │
│  │                          │                                            │
│  │  Direction: ▲ Bullish    │  ┌──────────────────────────────────────┐  │
│  │  Confidence: 82%         │  │ ◉ DESK: VOLATILITY              [−]│  │
│  │                          │  │                                      │  │
│  │  Key Findings:           │  │  Direction: ▲ Bullish               │  │
│  │  • SMA crossover above   │  │  Confidence: 76%                    │  │
│  │    200-day confirmed     │  │                                      │  │
│  │  • ADX at 32 — strong    │  │  Key Findings:                      │  │
│  │    trend regime          │  │  • IV rank 23rd pctl — cheap        │  │
│  │  • ROC accelerating      │  │  • HV > IV — vol underpriced        │  │
│  │                          │  │  • Term structure in contango       │  │
│  └──────────────────────────┘  └──────────────────────────────────────┘  │
│  ... (remaining desk cards flow into grid)                               │
└──────────────────────────────────────────────────────────────────────────┘
```

**Card inventory** (all collapsible):

| Card | Grid Behavior | Visibility |
|------|--------------|------------|
| Market Context | 1-col, medium height | Always (collapsible) |
| Scan Progress | 1-col, short | During scan only |
| Opportunity Pipeline | Full-width (spans all columns) | Always after first scan |
| Agent Consensus | 1-col, medium | When ticker selected with recommendation |
| Position Detail | 1-col, medium | When ticker selected with recommendation |
| Desk Assessment x6 | 1-col each, variable height | When ticker selected with recommendation |

**Masonry behavior**:
- Before scan: only Market Context card visible (centered, welcoming state)
- During scan: Market Context + Scan Progress cards, then Pipeline appears and grows
- After scan: Pipeline takes full width, Market Context stays in flow
- Ticker selected: Pipeline contracts, consensus + position + 6 desk cards flow into the grid below/beside it
- Collapse any card: remaining cards reflow to fill the space
- No ticker selected: consensus/position/desk cards hidden, Pipeline takes full width

**CSS implementation**: Use CSS `grid-template-columns: repeat(auto-fill, minmax(400px, 1fr))` with `grid-column: 1 / -1` on the Pipeline card to force full-width span. Individual cards use `break-inside: avoid` for proper packing. No JavaScript masonry library needed — pure CSS Grid.

## Requirements

### Functional Requirements

1. **FR-1**: Single-page trading desk with scan → recommend → view pipeline
2. **FR-2**: Real-time WebSocket updates for scan progress and recommendation stage transitions
3. **FR-3**: Manual "Analyze" button on any scored ticker row (single recommendation)
4. **FR-4**: Multi-select rows + "Analyze Selected" for batch recommendation
5. **FR-5**: Recommendation detail panel with 6 desk assessments + position card
6. **FR-6**: Market heatmap displayed in collapsible context zone
7. **FR-7**: Pre-scan filter panel (reuse existing `PreScanFilters.vue`)
8. **FR-8**: Post-scan inline filtering of pipeline table (reuse existing `ScanFilterPanel.vue`)
9. **FR-9**: Pipeline table sortable by score, direction, confidence, stage
10. **FR-10**: Scan cancellation via WebSocket cancel message
11. **FR-11**: Analytics page with existing analytics components + new Attribution panel (secondary page)
12. **FR-12**: Navigation reduced to 2-3 links (Trading Desk, Analytics, optionally Settings)

### Non-Functional Requirements

1. **NFR-1**: Dark theme (PrimeVue Aura dark preset) — hedge fund aesthetic
2. **NFR-2**: Prices never parsed to JavaScript `number` — string formatting only
3. **NFR-3**: All components use `<script setup lang="ts">` Composition API
4. **NFR-4**: No `any` types — full TypeScript coverage
5. **NFR-5**: Scoped CSS on all custom components
6. **NFR-6**: WebSocket connections cleaned up on unmount
7. **NFR-7**: Virtual scroll on pipeline table for >1000 rows — requires PrimeVue DataTable `scrollable` + `scrollHeight` + `virtualScrollerOptions="{ itemSize: 44 }"` together
8. **NFR-8**: Monospace font for all numeric data

## API Surface

**No new backend endpoints required.** All existing endpoints are sufficient:

| Frontend Action | Backend Endpoint | Method |
|----------------|-----------------|--------|
| Launch scan | `POST /api/scan` | REST |
| Scan progress | `WS /ws/scan/{id}` | WebSocket |
| Get scan scores | `GET /api/scan/{id}/scores` | REST |
| Batch recommend | `POST /api/debate/batch` | REST |
| Batch progress | `WS /ws/batch/{id}` | WebSocket |
| Single recommend | `POST /api/debate` | REST |
| Single progress | `WS /ws/debate/{id}` | WebSocket |
| Get recommendation | `GET /api/debate/{id}` | REST |
| Market heatmap | `GET /api/heatmap` | REST |
| System health | `GET /api/health` | REST |
| Universe presets | `GET /api/universe/preset-info` | REST |
| Sectors | `GET /api/universe/sectors` | REST |
| Attribution report | `GET /api/analytics/attribution` | REST |

Backend route renaming (debate → recommend) is desirable but out of scope — cosmetic, separate epic.

## Testing Strategy

### Component Tests (Vitest + Vue Test Utils)
- `OpportunityTable`: sort behavior, stage badge rendering, row selection, virtual scroll activation
- `DeskCard`: collapse/expand toggle, header rendering, status badge slot
- `AgentConsensus`: renders all 6 desks summary, handles partial desks (3-4 present)
- `DeskAssessmentCard`: direction badge, confidence badge, key findings list, all desk types
- `PositionCard`: price string display (never parsed), null fields show `"--"`, strategy text
- `PipelineStatus`: all 5 stage states render correctly
- `ScanControlBar`: preset selection, filter toggle, run/cancel button states
- `AttributionPanel`: renders per-source accuracy table, condition bucket breakdown, contract guidance card; handles null/empty states

### Store Tests
- `pipeline.ts`: full state machine — idle → scanning → scanned transitions, user-initiated analyze (single + batch), ticker map updates, selectedTicker/currentRecommendation management

### Integration Tests (MSW mocking)
- Full pipeline flow: mock scan WebSocket → scores arrive → user triggers analyze → recommendation completes → detail loads
- Scan with 0 results → table empty, no analyze buttons
- Single analyze: click Analyze on row → stage transitions → detail panel loads
- Batch analyze: multi-select rows → Analyze Selected → batch WebSocket → all rows update
- Recommendation failure → stage shows `failed`, detail panel shows fallback
- WebSocket disconnect/reconnect mid-pipeline
- Cancel scan during scanning phase

### Edge Cases
- All 6 desks present vs. partial (3-4 desks)
- Fallback recommendation (`is_fallback: true`, `confidence: 0.2`)
- Null `recommendation` field (no position details)
- Empty `key_findings` array
- Very long summary text truncation
- 1000+ tickers in pipeline table (virtual scroll)

## Success Criteria

1. User can go from "open the app" to "see a recommendation with entry/stop/target" without navigating away from the main page
2. Pipeline stages update in real-time — no manual refresh
3. Entire scan → recommend flow completes with zero page transitions
4. Existing analytics components remain accessible on the Analytics page
5. All prices displayed as formatted currency strings, never parsed to float

## Constraints & Assumptions

- **Vue 3 + TypeScript + PrimeVue Aura dark** — existing tech stack preserved
- **No new backend endpoints** — frontend consumes existing API as-is
- **Backend "debate" naming persists** — routes still say `/api/debate`, frontend abstracts this away in the API layer
- **Single-user localhost tool** — no auth, no multi-user state, no mobile optimization needed
- **The existing `recommendation-display-overhaul` PRD is superseded** — this PRD covers a superset of that scope

## Out of Scope

- Portfolio management / P&L tracking (user manages this in their brokerage)
- Backend route renaming (debate → recommend) — separate cosmetic epic
- Settings page (model routing, weight tuning UI) — V2 follow-up
- Agency/chat interface (interactive desk agent queries) — V2 follow-up
- Mobile responsive design — localhost desktop tool
- Backend changes of any kind — pure frontend rebuild

## Dependencies

- **Internal**: Unified recommendation system (merged), prediction ledger (merged), all backend APIs stable
- **External**: PrimeVue (existing), Vue 3 (existing), Vite (existing)
- **Supersedes**: `.claude/prds/recommendation-display-overhaul.md` (researched, not yet parsed)
