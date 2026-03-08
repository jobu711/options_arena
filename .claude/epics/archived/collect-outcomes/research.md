# Research: collect-outcomes

## PRD Summary

Automate outcome collection after every successful scan (eliminating manual button clicks), extend the WebSocket `complete` event to include an `outcomes_collected` count shown in the scan toast, add a "Neutral" direction filter to the HoldingPeriodTable, and fix misleading legend colors in ScoreCalibrationChart and DeltaPerformanceChart.

## Relevant Existing Modules

- `api/routes/scan.py` — `_run_scan_background()` is the injection point for outcome collection. Currently calls `pipeline.run()` then `bridge.complete()` in the `try` block, with `lock.release()` in `finally`.
- `api/ws.py` — `WebSocketProgressBridge.complete(scan_id, *, cancelled)` enqueues the terminal WS event. Needs `outcomes_collected` parameter.
- `services/outcome_collector.py` — `OutcomeCollector` with never-raises `collect_outcomes() -> list[ContractOutcome]`. Already fully implemented.
- `api/deps.py` — `get_outcome_collector()` constructs from `app.state` (analytics config, repo, market_data, options_data). Pattern to reuse in background task.
- `web/src/types/ws.ts` — `ScanCompleteEvent` interface (missing `outcomes_collected`).
- `web/src/pages/ScanPage.vue` — Scan complete toast (currently "Scan #X finished").
- `web/src/components/analytics/HoldingPeriodTable.vue` — `directionOptions` array (missing Neutral).
- `web/src/components/analytics/ScoreCalibrationChart.vue` — `.legend-bar` hardcoded green.
- `web/src/components/analytics/DeltaPerformanceChart.vue` — `.legend-return` hardcoded green.

## Existing Patterns to Reuse

- **Background task pattern**: `_run_scan_background()` uses `try/except/finally` with `bridge.complete()` in `try`, `lock.release()` in `finally`. Outcome collection inserts before `bridge.complete()`.
- **DI construction from app.state**: `get_outcome_collector()` in `deps.py` shows the exact `OutcomeCollector(config=..., repository=..., market_data=..., options_data=...)` construction from `request.app.state`. Same pattern works inline in the background task.
- **Never-raises contract**: `OutcomeCollector.collect_outcomes()` catches all errors internally and returns partial results. Safe to call without additional error handling.
- **WebSocket event extension**: The WS handler sends the entire event dict as JSON. Adding keys to the dict automatically propagates to the frontend — no serialization changes needed.
- **Debate background task pattern**: `routes/debate.py` shows the same `try/except/finally` with `bridge.complete()` pattern. Post-completion work (DB persistence) runs inside `try` before `bridge.complete()`.

## Existing Code to Extend

- `src/options_arena/api/ws.py:62-64` — `WebSocketProgressBridge.complete()`: Add `outcomes_collected: int = 0` kwarg, include in queue dict.
- `src/options_arena/api/routes/scan.py:62-91` — `_run_scan_background()`: After `pipeline.run()` succeeds and `not result.cancelled`, construct `OutcomeCollector` and call `collect_outcomes()`. Pass count to `bridge.complete()`.
- `web/src/types/ws.ts:17-21` — `ScanCompleteEvent`: Add `outcomes_collected: number` field.
- `web/src/pages/ScanPage.vue:85-86` — Toast detail: Conditionally append outcomes count.
- `web/src/components/analytics/HoldingPeriodTable.vue:17-21` — `directionOptions`: Add `{ label: 'Neutral', value: 'neutral' }`.
- `web/src/components/analytics/ScoreCalibrationChart.vue:248-251` — `.legend-bar`: Change to green/red gradient.
- `web/src/components/analytics/DeltaPerformanceChart.vue:205-208` — `.legend-return`: Change to green/red gradient.

## Potential Conflicts

- **None identified**. All changes are additive. The `outcomes_collected` field defaults to `0`, maintaining backward compatibility. The Neutral direction is already supported by the backend `SignalDirection` StrEnum. No existing code paths are modified destructively.

## Open Questions

- **Legend gradient approach**: The PRD says "green/red gradient" for legend swatches. Should this be a CSS `linear-gradient(to right, var(--accent-red), var(--accent-green))` on the 12x12px swatch? Or a split swatch (half red, half green)? Either approach conveys "bars can be either color." Gradient is simpler CSS and more visually clear.

## Recommended Architecture

### Backend Changes (2 files)

1. **`api/ws.py`**: Add `outcomes_collected: int = 0` keyword parameter to `complete()`. Include it in the queue payload dict.

2. **`api/routes/scan.py`**: In `_run_scan_background()`, after `pipeline.run()` returns successfully:
   ```python
   outcomes_count = 0
   if not result.cancelled:
       collector = OutcomeCollector(
           config=request.app.state.settings.analytics,
           repository=request.app.state.repo,
           market_data=request.app.state.market_data,
           options_data=request.app.state.options_data,
       )
       outcomes = await collector.collect_outcomes()
       outcomes_count = len(outcomes)
   actual_id = result.scan_run.id if result.scan_run.id is not None else scan_id
   bridge.complete(actual_id, cancelled=result.cancelled, outcomes_collected=outcomes_count)
   ```

### Frontend Changes (5 files)

3. **`web/src/types/ws.ts`**: Add `outcomes_collected: number` to `ScanCompleteEvent`.

4. **`web/src/pages/ScanPage.vue`**: Update toast detail:
   ```typescript
   const detail = event.outcomes_collected > 0
     ? `Scan #${event.scan_id} finished — ${event.outcomes_collected} outcomes collected`
     : `Scan #${event.scan_id} finished`
   toast.add({ severity: 'success', summary: 'Scan Complete', detail, life: 5000 })
   ```

5. **`web/src/components/analytics/HoldingPeriodTable.vue`**: Add `{ label: 'Neutral', value: 'neutral' }` to `directionOptions`.

6. **`web/src/components/analytics/ScoreCalibrationChart.vue`**: Change `.legend-bar` background to `linear-gradient(to right, var(--accent-red), var(--accent-green))`.

7. **`web/src/components/analytics/DeltaPerformanceChart.vue`**: Change `.legend-return` background to `linear-gradient(to right, var(--accent-red), var(--accent-green))`.

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/api/` contains route tests with mocked services, `AsyncMock` for pipeline/collector, and WebSocket test helpers.
- **New tests needed**:
  - `test_scan_background_collects_outcomes`: Verify `collect_outcomes()` is called after successful non-cancelled scan.
  - `test_scan_background_skips_outcomes_on_cancel`: Verify collection skipped when `result.cancelled`.
  - `test_scan_background_outcomes_failure_nonfatal`: Verify scan succeeds even if `collect_outcomes()` hypothetically raised (though it shouldn't).
  - `test_ws_bridge_complete_includes_outcomes`: Verify `outcomes_collected` appears in queue payload.
  - `test_ws_bridge_complete_default_zero`: Verify default `0` when not passed.
- **E2E**: Existing Playwright tests cover scan flow; may need updating if toast text assertions exist.
- **Frontend**: No unit tests currently (Vitest not set up); changes are UI-only and covered by E2E.

## Estimated Complexity

**S (Small)** — 7 files modified, all changes are additive, no new models or migrations, no architectural decisions. Backend is ~15 lines of logic; frontend is ~10 lines across 5 files. The `OutcomeCollector` is already fully implemented with a never-raises contract. Estimated 1-2 issues in the epic.
