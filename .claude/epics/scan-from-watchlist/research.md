# Research: scan-from-watchlist

## PRD Summary

Add `custom_tickers: list[str]` support throughout the stack so users can scan a specific
ticker list (e.g. their watchlist) instead of the full universe. Pipeline Phase 1 uses
these tickers (intersected with optionable universe) when non-empty, bypassing preset/sector
/industry/theme filters. WatchlistPage gets a "Scan Watchlist" button with WebSocket progress
and navigation to results.

## Relevant Existing Modules

- `models/config.py` — `ScanConfig` with filter fields + `field_validator` normalization
- `scan/pipeline.py` — `_phase_universe()` Phase 1: universe fetch → preset → sector → industry → theme → OHLCV
- `api/schemas.py` — `ScanRequest` with filter fields + validators (`_TICKER_RE`, dedup)
- `api/routes/scan.py` — `start_scan()` handler, `model_copy(update={...})` override pattern
- `api/routes/watchlist.py` — CRUD + ticker validation against optionable universe
- `web/src/stores/scan.ts` — `startScan()` with preset + filter params, WebSocket callbacks
- `web/src/pages/WatchlistPage.vue` — Watchlist CRUD UI, no scan functionality yet
- `web/src/pages/ScanPage.vue` — Full scan flow pattern (button → POST → WebSocket → ProgressTracker → navigate)

## Existing Patterns to Reuse

### 1. Config Override Pattern (`api/routes/scan.py` lines 121-140)
```python
scan_overrides: dict[str, object] = {}
if body.custom_tickers:
    scan_overrides["custom_tickers"] = body.custom_tickers
if scan_overrides:
    scan_override = settings.scan.model_copy(update=scan_overrides)
    effective_settings = settings.model_copy(update={"scan": scan_override})
```
Already used for sectors, market_cap_tiers, direction_filter, etc. — add one more field.

### 2. Ticker Validation Pattern (`api/schemas.py` lines 174-186)
```python
_TICKER_RE = re.compile(r"^(?=.*[A-Z0-9])[A-Z0-9^][A-Z0-9.\-^]{0,9}$")
v = v.upper().strip()
if not _TICKER_RE.match(v): raise ValueError(...)
```
Reuse for `custom_tickers` validator in both ScanConfig and ScanRequest.

### 3. Deduplication Pattern (used in sector/industry validators)
```python
return list(dict.fromkeys(result))  # preserves order, removes duplicates
```

### 4. Sector Filter Pattern (`pipeline.py` lines 268-278)
```python
configured_sectors = self._settings.scan.sectors
if configured_sectors:
    sector_set = frozenset(configured_sectors)
    before_count = len(tickers)
    tickers = [t for t in tickers if sector_map.get(t) in sector_set]
    logger.info("Sector filter: %d -> %d tickers", before_count, len(tickers))
```
Same structure for custom_tickers: check non-empty → intersect → log counts.

### 5. ScanPage WebSocket + ProgressTracker Flow
```
opStore.start('scan') → scanStore.startScan() → useWebSocket(/ws/scan/{id})
→ ProgressTracker component → opStore.finish() → navigate to results
```
WatchlistPage reuses this exact flow, just with `custom_tickers` in the request body.

## Existing Code to Extend

| File | What Exists | What Needs Adding |
|------|------------|-------------------|
| `models/config.py` ScanConfig (~line 32) | 7 filter fields with validators | `custom_tickers: list[str] = []` + `@field_validator` |
| `api/schemas.py` ScanRequest (~line 35) | 8 filter fields with validators | `custom_tickers: list[str] = []` + `@field_validator` |
| `api/routes/scan.py` start_scan (~line 121) | Override dict for 7 filters | 1 additional `if body.custom_tickers:` block |
| `scan/pipeline.py` _phase_universe (~line 246) | Preset + sector + industry + theme filters | Custom tickers branch before preset filter |
| `web/src/stores/scan.ts` startScan (~line 72) | 5 params (preset, sectors, industryGroups, filters, themes) | `customTickers?: string[]` param + body field |
| `web/src/pages/WatchlistPage.vue` | CRUD only (create/delete watchlists, add/remove tickers) | Scan button, WebSocket, ProgressTracker, navigation |

## Potential Conflicts

### 1. Preset Always Required in ScanRequest
`preset: ScanPreset = ScanPreset.SP500` has a default. When `custom_tickers` is provided,
preset is ignored but still present. **No conflict** — the default is fine. Pipeline simply
skips preset filtering when custom_tickers is non-empty.

### 2. All Custom Tickers Non-Optionable
If `custom_tickers ∩ optionable_universe = ∅`, the pipeline proceeds with 0 tickers → 0
results. This is valid behavior, not an error. The scan completes with empty results.

### 3. WatchlistPage Imports
WatchlistPage currently doesn't import `useScanStore`, `useOperationStore`, `useWebSocket`,
or `ProgressTracker`. All must be added. No naming conflicts — these are standard composables
used on ScanPage already.

### 4. Operation Mutex
The existing `asyncio.Lock` in the API means a watchlist scan blocks other scans (and vice
versa). This is correct — only one operation at a time. WatchlistPage must check `opStore`
to disable the button during active operations.

## Open Questions

1. **Max custom tickers**: Should we cap `custom_tickers` length? The PRD doesn't specify.
   Recommendation: cap at 200 (larger than any reasonable watchlist, avoids abuse).
2. **CLI support**: PRD explicitly marks `--tickers` and `--watchlist-id` as out of scope.
   No CLI changes needed.

## Recommended Architecture

### Backend (4 files modified, 0 new files)

1. **ScanConfig** (`models/config.py`): Add `custom_tickers: list[str] = []` with
   `@field_validator` that uppercases, strips, validates regex, deduplicates.

2. **ScanRequest** (`api/schemas.py`): Add `custom_tickers: list[str] = []` with same
   validator. Reuse existing `_TICKER_RE`.

3. **Scan route** (`api/routes/scan.py`): Add `custom_tickers` to `scan_overrides` dict
   when non-empty. Single `if` block, 2 lines.

4. **Pipeline Phase 1** (`scan/pipeline.py`): In `_phase_universe()`, after fetching
   optionable universe (~line 218) and building sector_map (~line 243), insert:
   ```
   if custom_tickers non-empty:
       intersect with optionable set
       log excluded tickers
       skip preset/sector/industry/theme filters
       jump to OHLCV fetch
   ```

### Frontend (2 files modified, 0 new files)

5. **Scan store** (`stores/scan.ts`): Add `customTickers?: string[]` parameter to
   `startScan()`. Include in request body when non-empty.

6. **WatchlistPage** (`pages/WatchlistPage.vue`): Add "Scan Watchlist" button +
   scan flow (copied from ScanPage pattern): opStore → startScan → WebSocket →
   ProgressTracker → navigate to results.

### Data Flow
```
WatchlistPage (tickers from activeWatchlist.tickers)
  → scanStore.startScan(preset='full', customTickers=['AAPL','MSFT',...])
  → POST /api/scan { preset: 'full', custom_tickers: ['AAPL','MSFT',...] }
  → scan route threads to ScanConfig via model_copy
  → Pipeline Phase 1: custom_tickers ∩ optionable_universe → skip preset/sector filters
  → Phases 2-4 run normally (scoring, options, persist)
  → WebSocket progress → ProgressTracker
  → Navigate to /scan/{scanId}
```

## Test Strategy Preview

### Existing Test Patterns
- **Pipeline Phase 1**: `tests/unit/scan/test_pipeline_phase1.py` — AsyncMock services, `_make_batch_result()` helpers
- **Scan routes**: `tests/unit/api/test_scan_routes.py` — httpx TestClient, mocked services
- **Schema validation**: `tests/unit/api/test_scan_request_filters.py` — ScanRequest validators
- **Config validation**: `tests/unit/models/test_config*.py`

### New Tests Needed
1. **ScanConfig**: `custom_tickers` validator (uppercase, dedup, regex reject, empty = no-op)
2. **ScanRequest**: `custom_tickers` validator (same as ScanConfig + format errors)
3. **Pipeline Phase 1**: Custom tickers intersect optionable, skip preset/sector filters
4. **Pipeline Phase 1**: All custom tickers non-optionable → 0 results (no error)
5. **Pipeline Phase 1**: Empty custom_tickers → normal preset behavior (regression)
6. **Scan route**: `custom_tickers` threaded through to pipeline config
7. **E2E (Playwright)**: WatchlistPage scan button → progress → results (optional)

### Mocking Patterns
```python
mock_universe = AsyncMock()
mock_universe.fetch_optionable_tickers = AsyncMock(return_value=["AAPL", "MSFT", "GOOG"])
# custom_tickers=["AAPL", "TSLA"] → only "AAPL" passes intersection
```

## Estimated Complexity

**Small-Medium (S-M)**

- 4 Python files modified (all small, well-defined changes)
- 2 frontend files modified (1 store param, 1 page with copy-paste pattern)
- 0 new files, 0 new dependencies, 0 migrations
- All patterns already proven in the codebase
- ~7-10 new tests (unit only, following existing patterns)
- No architectural novelty — pure feature threading
