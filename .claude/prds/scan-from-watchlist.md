---
name: scan-from-watchlist
description: Allow users to run the scan pipeline against tickers in a watchlist
status: planned
created: 2026-03-04T09:03:41Z
---

# PRD: scan-from-watchlist

## Executive Summary

Add a "Scan Watchlist" action that runs the full scoring pipeline (indicators, scoring,
option chain analysis) against only the tickers in a user's watchlist instead of the
entire S&P 500 / full universe. This threads a custom ticker list through the backend
stack and adds a one-click scan trigger on the WatchlistPage in the web UI.

## Problem Statement

Users create watchlists to track specific tickers they care about. Currently, the only
way to get fresh scores for those tickers is to run a full-universe scan (500-5,000
tickers) and then search for their watchlist tickers in the results. This is slow and
wasteful — a scan of 5 watchlist tickers should take seconds, not minutes.

There is no `custom_tickers` support anywhere in the stack. The scan pipeline only
accepts a `ScanPreset` enum (SP500 / FULL / ETFS), with no way to pass an explicit
ticker list.

## User Stories

### US-1: Scan watchlist from web UI
**As a** user on the Watchlist page,
**I want to** click "Scan Watchlist" and have the pipeline run on only my watchlist tickers,
**So that** I get fresh composite scores, direction signals, and option recommendations
for the tickers I'm actively monitoring.

**Acceptance Criteria:**
- A "Scan Watchlist" button is visible on WatchlistPage when a watchlist is selected
- Button is disabled when no watchlist is selected, watchlist has no tickers, or another
  operation is in progress
- Clicking the button starts a scan with only the watchlist's tickers
- Progress is shown inline via ProgressTracker (same as ScanPage)
- On completion, user is navigated to the scan results page
- Only the watchlist tickers appear in the scan results

### US-2: Custom tickers via API
**As an** API consumer,
**I want to** pass a `custom_tickers` array in the `POST /api/scan` request body,
**So that** I can scan any arbitrary set of tickers without using a preset.

**Acceptance Criteria:**
- `ScanRequest` accepts `custom_tickers: list[str]` (default empty)
- When non-empty, the pipeline scans only those tickers (intersected with the optionable
  universe for validation)
- Preset/sector/industry/theme filters are bypassed when custom tickers are provided
- Post-scoring filters (market cap, earnings, direction, IV rank) still apply
- Tickers are uppercased, deduplicated, and validated against the ticker format regex

## Requirements

### Functional Requirements

1. **ScanConfig model** (`models/config.py`): Add `custom_tickers: list[str] = []` with
   uppercase/deduplicate validator
2. **Pipeline Phase 1** (`scan/pipeline.py`): When `custom_tickers` is non-empty, intersect
   with optionable universe and skip preset/sector/industry/theme filters. OHLCV fetch and
   min-bars filter still apply.
3. **ScanRequest schema** (`api/schemas.py`): Add `custom_tickers: list[str] = []` with
   format validation
4. **Scan route** (`api/routes/scan.py`): Thread `custom_tickers` from request body to
   `ScanConfig` via existing `model_copy(update={...})` pattern
5. **Scan store** (`web/stores/scan.ts`): Extend `startScan()` to accept `custom_tickers`
   in filters and include in request body
6. **WatchlistPage** (`web/pages/WatchlistPage.vue`): Add "Scan Watchlist" button, scan
   initiation, WebSocket progress, and navigation to results

### Non-Functional Requirements

- **Performance**: Scanning 5-20 tickers should complete in under 30 seconds (vs 2-5 min
  for full universe)
- **Validation**: Custom tickers must be validated against optionable universe — invalid
  tickers are silently filtered out, not rejected
- **Backwards compatibility**: Empty `custom_tickers` (the default) preserves existing
  preset-based behavior exactly

## Success Criteria

- User can scan a 5-ticker watchlist and see results within 30 seconds
- Only watchlist tickers appear in scan results
- Existing preset-based scans are unaffected (no regression)
- All Python tests pass, mypy strict passes, ruff clean
- Frontend builds with vue-tsc --noEmit

## Constraints & Assumptions

- Custom tickers are intersected with optionable universe (CBOE list), not passed
  blindly to OHLCV fetch. Non-optionable tickers are silently excluded.
- The scan still uses `preset='full'` as the base (for SP500 sector mapping). The preset
  only matters for the initial universe filter which custom_tickers overrides.
- WebSocket progress on WatchlistPage reuses the same pattern as ScanPage — no new
  WebSocket infrastructure needed.

## Out of Scope

- CLI `--tickers` or `--watchlist-id` flag (can be added later)
- New `ScanPreset.WATCHLIST` enum value (unnecessary — custom_tickers is more flexible)
- Persisting which watchlist a scan came from in `scan_runs` table
- Dedicated "watchlist scan" preset tag in the Past Scans table

## Dependencies

- Existing watchlist CRUD (complete: `api/routes/watchlist.py`, `stores/watchlist.ts`)
- Existing scan pipeline (complete: `scan/pipeline.py`, Phase 1-4)
- Existing WebSocket progress bridge (complete: `api/ws.py`, `composables/useWebSocket.ts`)
- Existing ProgressTracker component (complete: `components/ProgressTracker.vue`)
