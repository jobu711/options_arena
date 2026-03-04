---
name: scan-from-watchlist
status: backlog
created: 2026-03-04T09:09:26Z
progress: 0%
prd: .claude/prds/scan-from-watchlist.md
github: https://github.com/jobu711/options_arena/issues/242
---

# Epic: scan-from-watchlist

## Overview

Thread a `custom_tickers: list[str]` field through the full stack — from ScanConfig model
to API schema to scan pipeline Phase 1 to the frontend scan store — so users can scan an
explicit ticker list instead of a preset universe. Add a "Scan Watchlist" button to
WatchlistPage that triggers this flow with the active watchlist's tickers.

6 files modified, 0 new files, 0 migrations, 0 new dependencies.

## Architecture Decisions

1. **No new ScanPreset enum** — `custom_tickers: list[str] = []` on ScanConfig is more
   flexible than a `WATCHLIST` preset. Empty list (default) preserves existing behavior.

2. **Intersection, not passthrough** — Custom tickers are intersected with the CBOE
   optionable universe. Non-optionable tickers are silently excluded with a log warning.
   This prevents invalid tickers from reaching OHLCV fetch.

3. **Bypass preset/sector/industry/theme filters** — When `custom_tickers` is non-empty,
   the pipeline skips all universe-narrowing filters (preset, sectors, industry_groups,
   theme_filters). Post-scoring filters (market cap, earnings, direction, IV rank) still
   apply since they're quality gates, not universe selectors.

4. **Reuse ScanPage WebSocket pattern** — WatchlistPage uses the same `useWebSocket` +
   `ProgressTracker` + `useOperationStore` flow as ScanPage. No new WebSocket infrastructure.

5. **Cap at 200 tickers** — Validator rejects lists exceeding 200 tickers to prevent abuse.
   This is well beyond any reasonable watchlist size.

## Technical Approach

### Backend (4 files)

**models/config.py — ScanConfig**
- Add `custom_tickers: list[str] = []`
- `@field_validator`: uppercase, strip, validate against `_TICKER_RE`, deduplicate via
  `dict.fromkeys()`, reject if len > 200

**api/schemas.py — ScanRequest**
- Add `custom_tickers: list[str] = []`
- Same validator as ScanConfig (reuse existing `_TICKER_RE` already in the file)

**api/routes/scan.py — start_scan()**
- Add `if body.custom_tickers: scan_overrides["custom_tickers"] = body.custom_tickers`
  in the existing override block (~2 lines)

**scan/pipeline.py — _phase_universe()**
- After fetching optionable universe and building sector_map, insert custom_tickers branch:
  - If `settings.scan.custom_tickers` is non-empty:
    - Intersect with `frozenset(all_tickers)` (optionable universe)
    - Log excluded tickers at WARNING, valid count at INFO
    - Set `tickers = validated_custom` and skip to OHLCV fetch
  - Else: existing preset/sector/industry/theme filter chain (unchanged)

### Frontend (2 files)

**stores/scan.ts — startScan()**
- Add `customTickers?: string[]` parameter
- Include `custom_tickers` in request body when non-empty

**pages/WatchlistPage.vue**
- Import `useScanStore`, `useOperationStore`, `useWebSocket`, `ProgressTracker`
- Add "Scan Watchlist" button (disabled when: no watchlist selected, 0 tickers, or
  `opStore.isActive`)
- Add `runWatchlistScan()`: extract tickers from `activeWatchlist.tickers` → call
  `scanStore.startScan('full', [], [], {}, [], tickers)` → connect WebSocket →
  show ProgressTracker → navigate to `/scan/${scanId}` on complete
- `onUnmounted` cleanup for WebSocket

### Data Flow
```
WatchlistPage → scanStore.startScan(preset='full', customTickers=[...])
  → POST /api/scan { custom_tickers: [...] }
  → scan route: model_copy(update={custom_tickers: [...]})
  → Pipeline Phase 1: custom_tickers ∩ optionable → skip preset filters → OHLCV fetch
  → Phases 2-4 unchanged
  → WebSocket progress → ProgressTracker → navigate to results
```

## Implementation Strategy

### Wave 1: Backend (issues #1-#3)
Foundation — model + schema + pipeline. Can be fully tested without frontend.

### Wave 2: Frontend (issue #4)
Wire scan store + WatchlistPage UI. Depends on Wave 1 being deployed.

### Risk Mitigation
- Empty `custom_tickers` (default) is a no-op — zero regression risk
- Pipeline change is an `if/else` branch before existing code — existing paths untouched
- All patterns are proven (sector filter, model_copy override, ScanPage WebSocket flow)

## Task Breakdown Preview

- [ ] #1 — Backend models: Add `custom_tickers` to ScanConfig + ScanRequest with validators
- [ ] #2 — Pipeline Phase 1: Custom tickers branch (intersect + bypass preset filters)
- [ ] #3 — API route: Thread `custom_tickers` through scan_overrides + tests
- [ ] #4 — Frontend: Scan store param + WatchlistPage scan button with WebSocket progress

## Dependencies

All prerequisites are complete:
- Watchlist CRUD: `api/routes/watchlist.py`, `stores/watchlist.ts`
- Scan pipeline: `scan/pipeline.py` (Phase 1-4)
- WebSocket progress bridge: `api/ws.py`, `composables/useWebSocket.ts`
- ProgressTracker component: `components/ProgressTracker.vue`
- Operation mutex: `useOperationStore`, `asyncio.Lock`

No external dependencies, no new packages, no migrations.

## Success Criteria (Technical)

- `POST /api/scan { custom_tickers: ["AAPL","MSFT"] }` returns 202 and scans only those tickers
- Empty `custom_tickers` preserves exact existing behavior (regression test)
- Non-optionable tickers silently excluded (intersection test)
- WatchlistPage "Scan Watchlist" button triggers scan and shows progress
- `uv run ruff check . --fix && uv run ruff format .` — clean
- `uv run pytest tests/ -v` — all pass
- `uv run mypy src/ --strict` — clean
- `cd web && npx vue-tsc --noEmit` — clean

## Estimated Effort

**Small-Medium** — 4 tasks, ~7-10 new tests

- Wave 1 (backend): 3 tasks, all small and well-defined
- Wave 2 (frontend): 1 task, pattern copy from ScanPage
- No architectural novelty — pure feature threading through existing patterns

## Tasks Created

- [ ] #243 - Add custom_tickers to ScanConfig and ScanRequest (parallel: true)
- [ ] #244 - Pipeline Phase 1 custom tickers branch (parallel: false, depends: #243)
- [ ] #245 - Thread custom_tickers through scan API route (parallel: true, depends: #243)
- [ ] #246 - Scan store param and WatchlistPage scan button (parallel: false, depends: #243-#245)

Total tasks: 4
Parallel tasks: 2 (#244 + #245 parallel after #243)
Sequential tasks: 2 (#244 depends on #243; #246 depends on all)
Estimated total effort: 5-8 hours

## Test Coverage Plan

Total test files planned: 4
Total test cases planned: ~20
- `tests/unit/models/test_custom_tickers_config.py` (7 tests)
- `tests/unit/api/test_custom_tickers_schema.py` (3 tests)
- `tests/unit/scan/test_pipeline_custom_tickers.py` (7 tests)
- `tests/unit/api/test_scan_custom_tickers_route.py` (3 tests)
