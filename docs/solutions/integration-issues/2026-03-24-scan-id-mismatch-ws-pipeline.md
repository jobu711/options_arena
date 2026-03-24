---
title: "Scan counter ID vs DB ID mismatch breaks WS-to-REST score loading"
date: 2026-03-24
module: options_arena.api.routes.scan
problem_type: integration_issue
severity: critical
symptoms:
  - "Pipeline table stays empty after scan completes"
  - "'Failed to load scores' toast error after scan"
  - "Progress card stuck at 100% persist indefinitely"
  - "WS connects to dead scan IDs, immediately closes"
  - "Analyze spinner never resolves to Ready"
tags:
  - scan-id
  - websocket
  - counter-vs-db-id
  - pipeline-store
  - score-loading
  - vue-watcher-loop
root_cause: "POST /api/scan returns an in-memory counter ID (1,2,3...) but GET /api/scan/{id}/scores expects the database row ID (49,50,51...). The frontend used the counter ID for REST calls, getting 404/422 errors."
---

## Problem

After a scan completed successfully (tickers scored, persisted to DB), the frontend
pipeline table remained empty. The "Failed to load scores" error toast appeared. The
scan progress card stayed visible at 100% for 42+ minutes.

Multiple cascading issues:

1. Score fetching used wrong ID type (counter vs DB)
2. `onScanComplete` overwrote the counter-based `scanId` with the DB ID, re-triggering
   the Vue watcher and creating a WS connection loop to dead scan queues
3. `onScanProgress` unconditionally set `phase = 'scanning'`, reverting the phase after
   completion when late WS events arrived
4. `page_size: 500` exceeded the API max of 200, causing 422 validation error
5. WS `complete` events were unreliably delivered (race between API response and WS connect)

## Root Cause

The backend has two ID systems for scans:

- **Counter ID**: In-memory incrementing counter (resets on restart). Used for WS queue
  routing (`scan_queues[counter_id]`). Returned by `POST /api/scan`.
- **Database ID**: SQLite auto-increment row ID. Used by all REST endpoints
  (`GET /api/scan/{db_id}/scores`).

The WS `complete` event sends the DB ID (line 102-103 in `scan.py`):
```python
actual_id = result.scan_run.id if result.scan_run.id is not None else scan_id
bridge.complete(actual_id, ...)
```

The frontend stored both IDs in a single `scanId` ref, causing:
- Watcher loop: `onScanComplete` writes DB ID → watcher fires → WS connects to DB ID
  (no queue) → closes → reconnects → loop
- Phase revert: Late `progress` events reset `phase` from `scanned` back to `scanning`

## Solution

1. **Separate ID tracking**: `scanId` (counter, for WS) and `dbScanId` (database, for REST)
   in the pipeline store. `onScanComplete` only writes to `dbScanId`.

2. **Completion poll safety net**: Poll `GET /api/status` every 5s. When `busy: false` and
   phase is still `scanning`, fetch latest scan from `GET /api/scan?limit=1` and load scores.
   Same pattern for debate completion.

3. **Guard phase transitions**: `onScanProgress` only transitions `idle → scanning`, never
   `scanned → scanning`.

4. **Fix page_size**: 500 → 200 (API max enforced by Pydantic validator).

5. **Debate poll**: Same completion poll pattern for debate/recommendation WS events.

## Prevention Rule

When a backend returns IDs from two different systems (operation counter vs database),
**never store them in the same variable**. Track them separately and document which ID
type each API endpoint expects. Always add a completion poll as a safety net for
WebSocket-delivered events — WS delivery is best-effort, not guaranteed.

## Related

- `src/options_arena/api/routes/scan.py` lines 101-103, 227, 244
- `web/src/stores/pipeline.ts` — `scanId` vs `dbScanId` separation
- `web/src/pages/TradingDeskPage.vue` — completion polls for scan and debate
- `docs/solutions/async-bugs/2026-03-16-websocket-toctou-race.md` — related WS issue
