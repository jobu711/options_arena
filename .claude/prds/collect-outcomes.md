---
name: collect-outcomes
description: Auto-collect outcomes after scan completion and fix analytics UI issues
status: planned
created: 2026-03-07T22:09:50Z
---

# PRD: collect-outcomes

## Executive Summary

Automate outcome collection so it triggers after every successful scan, eliminating the manual "Collect Outcomes" button click currently required on the analytics page. Include the outcomes count in the scan completion notification for user feedback. Additionally, fix three known UI issues in the analytics chart components.

## Problem Statement

The outcomes collection system requires manual intervention — a user must navigate to the analytics page and click "Collect Outcomes" to fetch current prices for previously recommended contracts. This creates a broken feedback loop: users run scans but never see analytics because they forget (or don't know) to trigger collection. The analytics page shows an empty state with a confusing prompt, making the feature feel incomplete.

Additionally, three UI bugs on the analytics page degrade trust in the data:
1. The holding period filter is missing the "Neutral" direction option
2. Two chart legends always show green for "Avg Return" even when bars are red (negative returns)

## User Stories

### US-1: Automatic outcome collection after scan
**As a** user who runs scans regularly,
**I want** outcomes to be collected automatically when a scan finishes,
**So that** the analytics page has up-to-date data without manual steps.

**Acceptance Criteria:**
- After a successful (non-cancelled) scan completes, `OutcomeCollector.collect_outcomes()` runs automatically
- The scan completion toast shows the number of outcomes collected (e.g., "Scan #5 finished - 12 outcomes collected")
- If no outcomes are eligible for collection (no previous scans old enough), the toast shows the standard "Scan #X finished" message
- The manual "Collect Outcomes" button remains on the analytics page as a fallback
- Outcome collection does not block the scan completion signal — the WebSocket `complete` event fires after collection
- A failed outcome collection (network error, etc.) does not affect the scan success status

### US-2: Neutral direction filter in holding period table
**As a** user analyzing holding period performance,
**I want** to filter by "Neutral" direction in addition to Bullish/Bearish/All,
**So that** I can see how neutral-signal contracts perform across holding periods.

**Acceptance Criteria:**
- The direction dropdown in HoldingPeriodTable includes a "Neutral" option
- Selecting "Neutral" passes `?direction=neutral` to the backend API
- Results display correctly with the existing `warn` severity Tag styling

### US-3: Accurate chart legend colors
**As a** user reading analytics charts,
**I want** the legend to accurately reflect the bar colors used in the chart,
**So that** the legend is not misleading when bars show negative returns.

**Acceptance Criteria:**
- ScoreCalibrationChart legend swatch for "Avg Return" shows a green/red gradient (matching actual bar behavior)
- DeltaPerformanceChart legend swatch for "Avg Return" shows the same green/red gradient
- No hardcoded color values — use existing CSS custom properties

## Requirements

### Functional Requirements

**FR-1: Backend — Inject outcome collection into scan background task**
- In `_run_scan_background()` (`api/routes/scan.py`), after `pipeline.run()` succeeds:
  - Guard with `not result.cancelled`
  - Create `OutcomeCollector` from `request.app.state` services
  - Call `await collector.collect_outcomes()` (never-raises contract)
  - Pass count to `bridge.complete(..., outcomes_collected=len(outcomes))`
- Outcome collection runs while the operation lock is held (before `finally` releases it)

**FR-2: Backend — Extend WebSocket complete event**
- Add `outcomes_collected: int = 0` keyword parameter to `WebSocketProgressBridge.complete()`
- Include `outcomes_collected` in the queue payload
- Default `0` ensures backward compatibility with existing callers

**FR-3: Frontend — Update WebSocket type and toast**
- Add `outcomes_collected: number` to `ScanCompleteEvent` TypeScript interface
- Update scan completion toast to show outcomes count when > 0

**FR-4: Frontend — Add Neutral direction option**
- Add `{ label: 'Neutral', value: 'neutral' }` to `directionOptions` in `HoldingPeriodTable.vue`

**FR-5: Frontend — Fix chart legend colors**
- Change `.legend-bar` in `ScoreCalibrationChart.vue` to green/red gradient
- Change `.legend-return` in `DeltaPerformanceChart.vue` to green/red gradient

### Non-Functional Requirements

- **Performance**: Outcome collection adds a few seconds after scan (quote fetches for past contracts). Acceptable latency since the scan completion signal has already been sent to the frontend.
- **Reliability**: `OutcomeCollector.collect_outcomes()` has a never-raises contract. A collection failure must not crash the scan background task or prevent lock release.
- **Backward compatibility**: The `outcomes_collected` field defaults to `0`, so older frontend versions handle it gracefully (`0 > 0` is false, standard toast shown).

## Success Criteria

- Analytics page shows outcome data without any manual button clicks after running scans on consecutive days
- Scan completion toast includes outcomes count when outcomes were collected
- HoldingPeriodTable direction filter includes all three directions (Bullish, Bearish, Neutral)
- Chart legends accurately represent the color scheme of their bars
- All existing tests pass; new tests cover the WebSocket event extension

## Constraints & Assumptions

- **Assumption**: Outcome collection is lightweight (a few quote fetches per holding period). Holding the operation lock during collection is acceptable.
- **Assumption**: `OutcomeCollector` needs contracts from previous scans that are 1/5/10/20 days old. A first-ever scan will collect 0 outcomes (no prior contracts exist).
- **Constraint**: The WebSocket loop breaks on `type: "complete"` — no additional events can be sent after it. Outcomes count must be included in the complete event itself.
- **Constraint**: Operation mutex (asyncio.Lock) must remain held during outcome collection to prevent race conditions with concurrent scans.

## Out of Scope

- Creating a Pinia store for analytics (component-local state is appropriate for the single-page use case)
- Adding an indicator attribution chart component (backend endpoint exists but no frontend yet)
- Fixing the CLI `outcomes collect` private `_db.conn` access code smell
- Removing the manual "Collect Outcomes" button (kept as fallback)
- Changing outcome collection to run outside the operation lock (deferred optimization)

## Dependencies

- `OutcomeCollector` service (`services/outcome_collector.py`) — already implemented, never-raises contract
- `WebSocketProgressBridge` (`api/ws.py`) — needs parameter extension
- App-scoped services on `request.app.state` (repo, market_data, options_data, settings) — already available in background task context

## Files to Modify

| File | Change |
|------|--------|
| `src/options_arena/api/ws.py` | Add `outcomes_collected` param to `complete()` |
| `src/options_arena/api/routes/scan.py` | Inject outcome collection in `_run_scan_background()` |
| `web/src/types/ws.ts` | Add `outcomes_collected` to `ScanCompleteEvent` |
| `web/src/pages/ScanPage.vue` | Update toast to show outcomes count |
| `web/src/components/analytics/HoldingPeriodTable.vue` | Add Neutral direction option |
| `web/src/components/analytics/ScoreCalibrationChart.vue` | Fix legend color |
| `web/src/components/analytics/DeltaPerformanceChart.vue` | Fix legend color |
