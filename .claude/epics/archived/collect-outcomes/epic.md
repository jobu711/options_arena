---
name: collect-outcomes
status: backlog
created: 2026-03-07T22:14:51Z
progress: 0%
prd: .claude/prds/collect-outcomes.md
github: https://github.com/jobu711/options_arena/issues/342
---

# Epic: collect-outcomes

## Overview

Automate outcome collection after every successful scan, extend the WebSocket `complete` event to surface the count in the frontend toast, add a "Neutral" direction filter to HoldingPeriodTable, and fix misleading legend colors in two analytics charts. All changes are additive — no migrations, no new models, no architectural decisions.

## Architecture Decisions

- **Inject before `bridge.complete()`**: Outcome collection runs inside the existing `try` block in `_run_scan_background()`, after `pipeline.run()` succeeds but before `bridge.complete()`. This keeps it within the operation lock and leverages the never-raises contract.
- **Reuse `get_outcome_collector()` DI pattern**: Construct `OutcomeCollector` inline using the same `request.app.state` services as `deps.py:get_outcome_collector()`.
- **Default parameter for backward compatibility**: `outcomes_collected: int = 0` on `bridge.complete()` ensures existing callers (debate routes, error paths) work unchanged.
- **CSS gradient for legend accuracy**: Use `linear-gradient(to right, var(--accent-red), var(--accent-green))` on legend swatches to convey "bars can be either color" — simpler than split swatches and visually clear.

## Technical Approach

### Backend (2 files)

1. **`api/ws.py` line 62**: Add `outcomes_collected: int = 0` keyword parameter to `WebSocketProgressBridge.complete()`. Include `"outcomes_collected": outcomes_collected` in the queue payload dict.

2. **`api/routes/scan.py` lines 78-82**: After `pipeline.run()` succeeds, before `bridge.complete()`:
   - Guard with `not result.cancelled`
   - Construct `OutcomeCollector` from `request.app.state` (matching `deps.py` pattern)
   - `await collector.collect_outcomes()` → get count
   - Pass `outcomes_collected=len(outcomes)` to `bridge.complete()`

### Frontend (5 files)

3. **`web/src/types/ws.ts` line 20**: Add `outcomes_collected: number` to `ScanCompleteEvent` interface.

4. **`web/src/pages/ScanPage.vue` line 86**: Update success toast detail to conditionally include outcomes count when `event.outcomes_collected > 0`.

5. **`web/src/components/analytics/HoldingPeriodTable.vue` line 20**: Add `{ label: 'Neutral', value: 'neutral' }` to `directionOptions` array.

6. **`web/src/components/analytics/ScoreCalibrationChart.vue` line 249**: Change `.legend-bar` background from `var(--accent-green)` to `linear-gradient(to right, var(--accent-red), var(--accent-green))`.

7. **`web/src/components/analytics/DeltaPerformanceChart.vue` line 207**: Change `.legend-return` background from `var(--accent-green)` to `linear-gradient(to right, var(--accent-red), var(--accent-green))`.

### Tests

- `test_ws_bridge_complete_includes_outcomes`: Verify `outcomes_collected` in queue payload.
- `test_ws_bridge_complete_default_zero`: Verify default `0` when kwarg omitted.
- `test_scan_background_collects_outcomes`: Mock `OutcomeCollector`, verify `collect_outcomes()` called after successful non-cancelled scan.
- `test_scan_background_skips_outcomes_on_cancel`: Verify collection skipped when `result.cancelled`.
- Check existing E2E tests for toast text assertions that may need updating.

## Implementation Strategy

Two tasks, executed sequentially:
1. **Backend + tests**: Extend `ws.py` and `scan.py`, write unit tests. This is the foundation.
2. **Frontend**: TypeScript type, toast update, direction filter, legend fixes. Quick UI changes.

Risk is minimal — all changes are additive, `OutcomeCollector` is already battle-tested, and the `outcomes_collected` default ensures backward compatibility.

## Task Breakdown Preview

- [ ] Task 1: Backend — Extend WebSocket bridge and inject outcome collection into scan background task, with unit tests
- [ ] Task 2: Frontend — Update WS type, toast message, Neutral direction filter, and chart legend colors

## Dependencies

- `OutcomeCollector` service — already implemented with never-raises contract
- `WebSocketProgressBridge` — extending existing method
- `request.app.state` services — already available in background task context
- No external dependencies, no migrations, no new packages

## Success Criteria (Technical)

- `uv run pytest tests/ -n auto -q` — all pass (existing + new)
- `uv run ruff check . --fix && uv run ruff format .` — clean
- `uv run mypy src/ --strict` — clean
- `cd web && npm run build` — clean
- Scan completion toast shows outcomes count when > 0
- HoldingPeriodTable direction filter includes Neutral
- Chart legends show green/red gradient instead of solid green

## Estimated Effort

- **Size**: S (Small)
- **Files modified**: 7 (2 backend + 5 frontend)
- **New lines of code**: ~30 backend (including tests), ~10 frontend
- **Tasks**: 2
- **Critical path**: Backend task must complete first (frontend depends on WS type change)

## Tasks Created
- [ ] #343 - Extend WebSocket bridge and inject outcome collection into scan background task (parallel: false)
- [ ] #344 - Frontend — WS type, toast, Neutral filter, and chart legend fixes (parallel: false, depends on #343)

Total tasks: 2
Parallel tasks: 0
Sequential tasks: 2
Estimated total effort: 3-4 hours

## Test Coverage Plan
Total test files planned: 1
Total test cases planned: 7
