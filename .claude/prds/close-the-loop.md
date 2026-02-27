---
name: close-the-loop
description: v2.1.0 release adding continuity features — contract persistence, scan diff, watchlists, debate trends, sector filters, earnings alerts, auto-refresh
status: backlog
created: 2026-02-27T21:07:17Z
---

# PRD: Options Arena v2.1.0 "Close the Loop"

## Context

Options Arena v2.0.0 delivers a complete screen-analyze-decide workflow: 4-phase scan
pipeline, 18 technical indicators, composite scoring, 3-5 agent AI debate, and a full-stack
Web UI. But the loop breaks after "decide" — users get a recommendation and then nothing.
Every session starts from zero. There's no way to track what changed between scans, review
past contract recommendations, or maintain a persistent watchlist. The `--sectors` CLI flag
is stubbed out, and the `watchlists`/`watchlist_tickers` DB tables exist but are completely
unused.

v2.1.0 closes these gaps. The release theme is **continuity** — making Options Arena a tool
users return to daily, not a one-shot scanner.

## Features in Scope

| # | Feature | Tier | Effort | Description |
|---|---------|------|--------|-------------|
| 1 | Contract Persistence | T1 | S | Save recommended OptionContracts to SQLite. Populate TickerDetail.contracts in API. |
| 2 | Scan Diff View | T1 | S | Compare two scan runs: new/removed tickers, score deltas, direction changes. |
| 3 | Sector & Market Cap Filters | T1 | S | Implement the stubbed `--sectors` flag. Add `--cap-tier`. Wire to API + Web UI. |
| 4 | Watchlists | T2 | M | Full CRUD on existing DB tables. Scan integration (replace mode). Web UI page. CLI commands. |
| 5 | Debate Replay & Trend | T2 | S | Time-series view of debate confidence/direction per ticker. Chart.js line chart. |
| 6 | Earnings Proximity Alerts | T1 | S | Surface `next_earnings` in ticker table + drawer. Warning badge for < 7 days. |
| 7 | Auto-Refresh Dashboard | T1 | S | Poll health (30s) + latest scan (60s) on interval. Frontend-only. |

## Out of Scope

- P&L scenario analysis / payoff diagrams (v2.2.0)
- Option chain explorer / full chain browsing (v2.2.0)
- Position tracking / trade journal (v2.2.0)
- IV rank heatmap visualization (v2.2.0)
- Multi-provider AI (Anthropic, OpenAI) (v2.2.0)
- Scan scheduling / cron jobs (v2.3.0)
- User authentication (v2.3.0)

---

## Parallel Work Stream Design

The work is decomposed for **4 Claude Code instances** running in parallel, with a
foundation stream that must complete first.

### Execution Timeline

```
Hour 0-3:   Stream 0 (Foundation) ── Instance A ── merge to master
            ┌──────────────────────────────────────────────────────┐
Hour 3-8:   │ Stream 1 (Contracts+Diff) ── Instance A             │
            │ Stream 2 (Watchlists) ──────── Instance B           │  PARALLEL
            │ Stream 3 (Trends+Quick) ────── Instance C           │
            └──────────────────────────────────────────────────────┘
Hour 8-9:   Merge PRs: Stream 3 → Stream 1 → Stream 2
Hour 9-12:  Stream 4 (Filters) ────── Instance D ── (after Stream 2 merged)
Hour 12-13: Merge Stream 4, integration test, tag v2.1.0
```

### Stream Dependency Graph

```
Stream 0 (Foundation)
    │
    ├──► Stream 1 (Contract Persistence + Scan Diff)
    │
    ├──► Stream 2 (Watchlists)
    │        │
    │        └──► Stream 4 (Sector & Market Cap Filters)
    │             ↑ waits for Stream 2 because both modify pipeline.py Phase 1
    │
    └──► Stream 3 (Debate Trend + Earnings + Auto-Refresh)
```

### Merge Order

1. **Stream 3** first — no `pipeline.py` changes, cleanest merge
2. **Stream 1** second — touches `pipeline.py` Phase 4 only (isolated from Phase 1)
3. **Stream 2** third — touches `pipeline.py` Phase 1
4. **Stream 4** last — adds to Phase 1 AFTER watchlist filter from Stream 2

---

## Stream 0: Foundation

**Instance**: A (runs first, blocking)
**Duration**: 2-3 hours
**Branch**: `feat/v2.1-foundation`

### Purpose

Create shared DB schema, Pydantic models, and API schema types so all feature streams
can import from them without merge conflicts on shared files.

### Deliverables

#### Migration `006_v2_1_features.sql`

```sql
-- Recommended contracts per scan run
CREATE TABLE IF NOT EXISTS recommended_contracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER NOT NULL REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    contract_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_recommended_contracts_scan_ticker
    ON recommended_contracts(scan_run_id, ticker);

-- Watchlist description column (tables already exist from migration 001)
ALTER TABLE watchlists ADD COLUMN description TEXT;
```

#### New file: `src/options_arena/models/watchlist.py`

```python
class Watchlist(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int | None = None
    name: str
    description: str | None = None
    created_at: datetime
    # UTC validator on created_at

class WatchlistTicker(BaseModel):
    model_config = ConfigDict(frozen=True)
    id: int | None = None
    watchlist_id: int
    ticker: str
    added_at: datetime
    # UTC validator on added_at

class WatchlistDetail(BaseModel):
    model_config = ConfigDict(frozen=True)
    watchlist: Watchlist
    tickers: list[WatchlistTicker]
    ticker_count: int
```

#### New file: `src/options_arena/models/diff.py`

```python
class ScoreChange(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    old_score: float
    new_score: float
    delta: float          # new - old
    old_direction: SignalDirection
    new_direction: SignalDirection
    direction_changed: bool

class ScanDiffResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    old_scan_id: int
    new_scan_id: int
    added_tickers: list[str]
    removed_tickers: list[str]
    score_changes: list[ScoreChange]

class DebateTrendPoint(BaseModel):
    model_config = ConfigDict(frozen=True)
    debate_id: int
    created_at: datetime   # UTC validator
    direction: SignalDirection
    confidence: float      # [0.0, 1.0] validator
    bull_score: float
    bear_score: float
    is_fallback: bool
```

#### Update: `src/options_arena/models/__init__.py`

Add re-exports for Watchlist, WatchlistTicker, WatchlistDetail, ScoreChange,
ScanDiffResult, DebateTrendPoint.

#### Extend: `src/options_arena/api/schemas.py`

Add new sections for v2.1 schemas:

```python
# --- v2.1.0: Watchlist schemas ---
class WatchlistCreateRequest(BaseModel):
    name: str
    description: str | None = None

class WatchlistUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

class WatchlistAddTickerRequest(BaseModel):
    ticker: str

# --- v2.1.0: Scan diff schemas ---
class ScanDiffRequest(BaseModel):
    compare_to: int   # scan_id to compare against

# --- v2.1.0: Debate trend schemas ---
class DebateTrendResponse(BaseModel):
    ticker: str
    points: list[DebateTrendPoint]

# --- v2.1.0: Extended scan request ---
# (Sector filters added by Stream 4, but reserve the section here)
```

#### Tests (~30)

- Watchlist/WatchlistTicker model construction, frozen enforcement, UTC validation
- ScoreChange, ScanDiffResult, DebateTrendPoint construction and JSON roundtrip
- confidence validator on DebateTrendPoint
- Migration 006 runs without error (integration test)
- models/__init__.py re-exports all new symbols

### Files Created/Modified

| File | Action |
|------|--------|
| `data/migrations/006_v2_1_features.sql` | CREATE |
| `src/options_arena/models/watchlist.py` | CREATE |
| `src/options_arena/models/diff.py` | CREATE |
| `src/options_arena/models/__init__.py` | MODIFY (add re-exports) |
| `src/options_arena/api/schemas.py` | MODIFY (append new classes) |
| `tests/unit/models/test_watchlist.py` | CREATE |
| `tests/unit/models/test_diff.py` | CREATE |

---

## Stream 1: Contract Persistence + Scan Diff

**Instance**: A (reuses foundation instance after merge)
**Duration**: 5-6 hours
**Branch**: `feat/v2.1-contracts-diff`
**Depends on**: Stream 0 merged

### Feature 1: Contract Persistence

**Problem**: Recommended contracts vanish after scan completes. `TickerDetail.contracts`
returns an empty list (documented gap in `schemas.py:47`). Users can't review what was
recommended last week.

**Implementation**:

1. **Repository** (`data/repository.py`) — add methods:
   - `save_recommended_contracts(scan_run_id: int, ticker: str, contracts: list[OptionContract]) -> None`
     — serialize each contract via `model_dump_json()` (includes greeks), INSERT rows
   - `get_recommended_contracts(scan_run_id: int, ticker: str) -> list[OptionContract]`
     — SELECT by scan_run_id+ticker, deserialize via `OptionContract.model_validate_json()`
   - `get_all_recommendations_for_scan(scan_run_id: int) -> dict[str, list[OptionContract]]`
     — SELECT all for a scan, group by ticker

2. **Pipeline Phase 4** (`scan/pipeline.py` `_phase_persist()`) — after `save_ticker_scores()`:
   ```python
   # Persist recommended contracts
   for ticker, contracts in options_result.recommendations.items():
       if contracts:
           await self._repository.save_recommended_contracts(scan_id, ticker, contracts)
   ```
   This is ~5 lines added around line 530, after the existing score persistence.

3. **API scan route** (`api/routes/scan.py`) — update `GET /api/scan/{scan_id}/scores/{ticker}`:
   - Change `TickerDetail.contracts` from `list[str]` to `list[OptionContract]`
   - Populate from `repo.get_recommended_contracts(scan_id, ticker)`

4. **Web UI TickerDrawer** — contracts section now populated (currently shows empty list)

### Feature 2: Scan Diff View

**Problem**: Users run scans daily but can't see what changed. No way to compare two runs.

**Implementation**:

1. **Repository** (`data/repository.py`) — add method:
   - `get_scan_diff(old_scan_id: int, new_scan_id: int) -> ScanDiffResult`
     — SQL: LEFT JOIN old scores with new scores on ticker, compute added/removed/changed
     — Returns `ScanDiffResult` model (from Stream 0's `models/diff.py`)

2. **API** (`api/routes/scan.py`) — add endpoint:
   - `GET /api/scan/{scan_id}/diff?compare_to={other_id}` → `ScanDiffResult`
   - 404 if either scan not found

3. **CLI** (`cli/commands.py`) — add `--diff` flag to scan command:
   - After scan completes, if `--diff` is passed, compare to previous scan
   - Render Rich table: `+NVDA (new)`, `-META (removed)`, `AAPL: 72.3 → 68.1 (-4.2)`

4. **Web UI** — new `ScanDiffView.vue` component:
   - Dropdown on ScanResultsPage: "Compare to: [Previous scan | Select scan...]"
   - Table with color-coded rows: green (added), red (removed), yellow (changed)
   - Score delta column with arrows

### Tests (~35)

- Repository: save/get contracts roundtrip, get_scan_diff with known data
- API: GET .../scores/{ticker} returns populated contracts, GET .../diff returns correct diff
- Pipeline: verify contracts persisted in Phase 4 (mock repository)
- CLI: --diff flag produces output (capture stdout)
- Vue: ScanDiffView renders added/removed/changed rows

### Files Created/Modified

| File | Action | Conflict Risk |
|------|--------|---------------|
| `src/options_arena/data/repository.py` | MODIFY (add 3 methods) | LOW — append-only |
| `src/options_arena/scan/pipeline.py` | MODIFY (Phase 4, ~5 lines) | LOW — Phase 4 only |
| `src/options_arena/api/routes/scan.py` | MODIFY (update ticker detail, add diff endpoint) | LOW |
| `src/options_arena/api/schemas.py` | MODIFY (update TickerDetail.contracts type) | LOW |
| `src/options_arena/cli/commands.py` | MODIFY (add --diff flag) | LOW |
| `web/src/components/ScanDiffView.vue` | CREATE | NONE |
| `web/src/pages/ScanResultsPage.vue` | MODIFY (add diff toggle) | LOW |
| `web/src/stores/scan.ts` | MODIFY (add diffScans action) | LOW |
| `tests/unit/data/test_repository_contracts.py` | CREATE | NONE |
| `tests/unit/data/test_repository_diff.py` | CREATE | NONE |
| `tests/unit/api/test_scan_diff.py` | CREATE | NONE |

---

## Stream 2: Watchlists

**Instance**: B
**Duration**: 5-6 hours
**Branch**: `feat/v2.1-watchlists`
**Depends on**: Stream 0 merged

### Problem

Every session starts from scratch. Users can't save tickers they're tracking or run
focused scans on just their picks. The `watchlists` and `watchlist_tickers` tables
exist in the DB (migration 001) but have zero implementation — no models, no repository
methods, no API, no UI.

### Implementation

1. **Repository** (`data/repository.py`) — add 7 methods:
   - `create_watchlist(name: str, description: str | None) -> int` (returns ID)
   - `get_watchlist_by_id(watchlist_id: int) -> Watchlist | None`
   - `get_watchlist_by_name(name: str) -> Watchlist | None`
   - `get_all_watchlists() -> list[Watchlist]`
   - `add_ticker_to_watchlist(watchlist_id: int, ticker: str) -> None`
   - `remove_ticker_from_watchlist(watchlist_id: int, ticker: str) -> None`
   - `get_tickers_for_watchlist(watchlist_id: int) -> list[WatchlistTicker]`
   - `update_watchlist(watchlist_id: int, name: str | None, description: str | None) -> None`
   - `delete_watchlist(watchlist_id: int) -> None`

2. **Pipeline Phase 1** (`scan/pipeline.py` `_phase_universe()`) — add watchlist mode:
   - `ScanPipeline.run()` gains optional `watchlist_tickers: list[str] | None = None`
   - If provided, skip universe/preset fetch entirely — use watchlist tickers as the universe
   - This is **replace mode**: watchlist tickers are the ONLY tickers scanned

3. **API** — new router `api/routes/watchlist.py`:
   - `POST /api/watchlists` → `Watchlist` (201)
   - `GET /api/watchlists` → `list[Watchlist]`
   - `GET /api/watchlists/{id}` → `WatchlistDetail` (watchlist + tickers + count)
   - `PUT /api/watchlists/{id}` → `Watchlist` (update name/description)
   - `DELETE /api/watchlists/{id}` → 204
   - `POST /api/watchlists/{id}/tickers` → `WatchlistTicker` (201)
   - `DELETE /api/watchlists/{id}/tickers/{ticker}` → 204
   - Register in `api/app.py`: `app.include_router(watchlist_router)`

4. **API scan integration** — extend `ScanRequest`:
   - Add `watchlist_id: int | None = None` field
   - When provided, resolve watchlist tickers from DB, pass to pipeline

5. **CLI** — new `watchlist` subcommand group in `cli/commands.py`:
   - `options-arena watchlist create "My Picks" --description "Weekly analysis"`
   - `options-arena watchlist list`
   - `options-arena watchlist show "My Picks"`
   - `options-arena watchlist add "My Picks" AAPL MSFT NVDA`
   - `options-arena watchlist remove "My Picks" MSFT`
   - `options-arena watchlist delete "My Picks"`
   - `options-arena scan --watchlist "My Picks"` (replace-mode scan)

6. **Web UI**:
   - **New page** `WatchlistPage.vue` at route `/watchlists`
   - Watchlist list (cards with name, description, ticker count, created date)
   - Create watchlist dialog (name + description fields)
   - Watchlist detail view: ticker table with remove button, add ticker input
   - "Scan This Watchlist" button → starts scan with `watchlist_id`
   - **TickerDrawer**: "Add to Watchlist" button (dropdown if multiple watchlists)
   - **Router**: add `/watchlists` route
   - **Nav**: add "Watchlists" link to App.vue navigation

### Tests (~45)

- Repository: all 9 CRUD methods, uniqueness constraint, foreign key cascade
- API: all 7 endpoints, 404 for missing watchlist, 409 for duplicate name
- Pipeline: watchlist mode skips universe fetch, scans only given tickers
- CLI: create/list/show/add/remove/delete commands
- Vue: WatchlistPage renders list, create dialog, ticker management

### Files Created/Modified

| File | Action | Conflict Risk |
|------|--------|---------------|
| `src/options_arena/data/repository.py` | MODIFY (add 9 methods) | MEDIUM — append-only but large |
| `src/options_arena/scan/pipeline.py` | MODIFY (Phase 1, ~20 lines) | MEDIUM — Phase 1 shared with Stream 4 |
| `src/options_arena/api/routes/watchlist.py` | CREATE | NONE |
| `src/options_arena/api/app.py` | MODIFY (add router include, 2 lines) | LOW |
| `src/options_arena/api/schemas.py` | MODIFY (extend ScanRequest) | LOW |
| `src/options_arena/cli/commands.py` | MODIFY (add watchlist subcommands) | LOW |
| `web/src/stores/watchlist.ts` | CREATE | NONE |
| `web/src/pages/WatchlistPage.vue` | CREATE | NONE |
| `web/src/components/WatchlistManager.vue` | CREATE | NONE |
| `web/src/router/index.ts` | MODIFY (add route, 5 lines) | LOW |
| `web/src/App.vue` | MODIFY (add nav link) | LOW |
| `web/src/pages/ScanPage.vue` | MODIFY (add watchlist scan option) | LOW |
| `web/src/components/TickerDrawer.vue` | MODIFY (add "Add to Watchlist" button) | LOW |
| `tests/unit/data/test_repository_watchlist.py` | CREATE | NONE |
| `tests/unit/api/test_watchlist_routes.py` | CREATE | NONE |
| `tests/unit/cli/test_watchlist_commands.py` | CREATE | NONE |

---

## Stream 3: Debate Trend + Quick Wins

**Instance**: C
**Duration**: 4-5 hours
**Branch**: `feat/v2.1-trends-polish`
**Depends on**: Stream 0 merged

### Feature 5: Debate Replay & Trend

**Problem**: Past debates are a flat list. Users can't see how AI conviction evolved over
time, or whether bull/bear scores are converging or diverging.

**Implementation**:

1. **Repository** (`data/repository.py`) — add method:
   - `get_debate_trend_for_ticker(ticker: str, limit: int = 20) -> list[DebateTrendPoint]`
     — SELECT from `ai_theses` WHERE ticker, parse `verdict_json` for direction/confidence/scores
     — ORDER BY created_at ASC (chronological for charting)
     — Return `list[DebateTrendPoint]` (from Stream 0's `models/diff.py`)

2. **API** (`api/routes/debate.py`) — add endpoint:
   - `GET /api/debate/trend/{ticker}?limit=20` → `DebateTrendResponse`
   - 404 if no debates found for ticker

3. **Web UI**:
   - Add `chart.js` and `vue-chartjs` to `web/package.json`
   - New component `DebateTrendChart.vue`:
     - Line chart: X axis = date, Y axis = confidence (0-1)
     - Green line for bullish points, red for bearish, yellow for neutral
     - Bull/bear score as semi-transparent bands
     - Clickable points → navigate to `/debate/{id}`
   - Add chart to `DebateResultPage.vue` below thesis card (if ticker has >= 2 debates)
   - Add chart to `TickerDrawer.vue` in debate history section

4. **CLI**: enhance `options-arena debate AAPL --history`:
   - Add trend indicator (arrows: confidence trending up/down/flat)

### Feature 6: Earnings Proximity Alerts

**Problem**: `next_earnings` exists on MarketContext but is invisible in the UI. Options
traders care deeply — IV crush can destroy positions.

**Implementation**:

1. **TickerDrawer.vue** — add earnings section:
   - Show "Next Earnings: Mar 15, 2026 (7 days)" with countdown
   - Warning badge (orange) when < 7 days
   - "N/A" when `next_earnings` is null

2. **ScanResultsPage.vue** — add earnings column to DataTable:
   - "Earn" column showing days until earnings or "—"
   - Sortable by DTE to earnings
   - Requires passing `next_earnings` through the API — currently not on TickerScore.
   - **Decision**: Add `next_earnings` to the scan results API response as an enrichment
     step, OR accept that this column is only available in the TickerDrawer (which fetches
     TickerInfo on demand). **Recommendation**: TickerDrawer only for v2.1 (no schema change).

### Feature 7: Auto-Refresh Dashboard

**Problem**: Dashboard is static. Users manually refresh to check scan status and health.

**Implementation**:

1. **DashboardPage.vue**:
   - `setInterval` polling: health every 30s, latest scan every 60s
   - "Last updated: 12s ago" timestamp on cards
   - Auto-refresh toggle (saved in localStorage)
   - Pulsing health dots on update

2. **health.ts store**: add `autoRefreshEnabled` ref, `startAutoRefresh()`/`stopAutoRefresh()`

### Tests (~25)

- Repository: get_debate_trend returns chronological points, handles no debates
- API: GET /trend/{ticker} returns points, 404 for unknown ticker
- Vue: DebateTrendChart renders with mock data, handles < 2 points gracefully
- Vue: Earnings badge shows warning when < 7 days
- Vue: DashboardPage auto-refresh polls on interval

### Files Created/Modified

| File | Action | Conflict Risk |
|------|--------|---------------|
| `src/options_arena/data/repository.py` | MODIFY (add 1 method) | LOW — append-only |
| `src/options_arena/api/routes/debate.py` | MODIFY (add trend endpoint) | LOW |
| `web/package.json` | MODIFY (add chart.js, vue-chartjs) | NONE |
| `web/src/components/DebateTrendChart.vue` | CREATE | NONE |
| `web/src/pages/DebateResultPage.vue` | MODIFY (add trend section) | LOW |
| `web/src/stores/debate.ts` | MODIFY (add fetchTrend action) | LOW |
| `web/src/components/TickerDrawer.vue` | MODIFY (add earnings + trend) | LOW |
| `web/src/pages/DashboardPage.vue` | MODIFY (add auto-refresh) | NONE |
| `web/src/stores/health.ts` | MODIFY (add auto-refresh state) | NONE |
| `tests/unit/data/test_repository_trend.py` | CREATE | NONE |
| `tests/unit/api/test_debate_trend.py` | CREATE | NONE |

---

## Stream 4: Sector & Market Cap Filters

**Instance**: D (runs AFTER Stream 2 merges — both modify pipeline.py Phase 1)
**Duration**: 3-4 hours
**Branch**: `feat/v2.1-filters`
**Depends on**: Stream 0 merged AND Stream 2 merged

### Problem

The `--sectors` CLI flag exists but logs a warning and does nothing. No way to focus
scans on specific sectors or market cap tiers from the UI. Users scanning SP500 get 503
tickers and must manually hunt for their sectors.

### Implementation

1. **Config** (`models/config.py`) — extend ScanConfig:
   ```python
   sectors: list[str] | None = None          # GICS sector names
   market_cap_tiers: list[MarketCapTier] | None = None
   ```

2. **Pipeline Phase 1** (`scan/pipeline.py` `_phase_universe()`) — add filtering:
   - After the existing preset filter (SP500/full) and after watchlist filter (from Stream 2):
   ```python
   # Sector filter
   if self._settings.scan.sectors:
       allowed_sectors = set(self._settings.scan.sectors)
       tickers = [t for t in tickers if sp500_sectors.get(t, "") in allowed_sectors]
   ```
   - Market cap filtering requires TickerInfo (expensive to fetch for all).
   - **Decision**: Sector filtering uses already-fetched SP500 sector data (free).
     Market cap filtering deferred to Phase 3 where TickerInfo is already fetched.
     For v2.1, `--cap-tier` filters at Phase 3 (post-liquidity, pre-top-N).

3. **API** — extend ScanRequest in `schemas.py`:
   ```python
   class ScanRequest(BaseModel):
       preset: ScanPreset = ScanPreset.SP500
       watchlist_id: int | None = None          # from Stream 2
       sectors: list[str] | None = None         # NEW
       # market_cap_tiers deferred — requires TickerInfo fetch in Phase 1
   ```
   - Pass sectors through to pipeline config
   - New endpoint: `GET /api/universe/sectors` → list of unique sector names from SP500

4. **CLI** (`cli/commands.py`) — implement `--sectors`:
   - Remove the "not yet implemented" warning
   - Parse comma-separated string into list
   - Pass to pipeline via ScanConfig override

5. **Web UI** — ScanPage.vue:
   - PrimeVue MultiSelect for sectors (populated from `GET /api/universe/sectors`)
   - Chips showing selected sectors
   - Submitted as part of scan start request

### Tests (~20)

- Config: ScanConfig.sectors accepts list, None by default
- Pipeline: sector filter reduces universe correctly
- API: scan request with sectors, universe/sectors endpoint
- CLI: --sectors "Technology,Healthcare" parses and filters
- Vue: ScanPage MultiSelect renders sectors

### Files Created/Modified

| File | Action | Conflict Risk |
|------|--------|---------------|
| `src/options_arena/models/config.py` | MODIFY (add sectors field) | NONE |
| `src/options_arena/scan/pipeline.py` | MODIFY (Phase 1, ~10 lines after watchlist filter) | LOW — runs after Stream 2 |
| `src/options_arena/api/schemas.py` | MODIFY (extend ScanRequest) | LOW |
| `src/options_arena/api/routes/scan.py` | MODIFY (pass sectors to pipeline) | LOW |
| `src/options_arena/api/routes/universe.py` | MODIFY (add sectors endpoint) | LOW |
| `src/options_arena/cli/commands.py` | MODIFY (implement --sectors) | LOW |
| `web/src/pages/ScanPage.vue` | MODIFY (add sector MultiSelect) | LOW |
| `tests/unit/scan/test_pipeline_filters.py` | CREATE | NONE |
| `tests/unit/api/test_scan_filters.py` | CREATE | NONE |

---

## Shared File Conflict Analysis

| File | Streams | Resolution |
|------|---------|------------|
| `repository.py` | 1, 2, 3 | **Append-only** — each adds distinct methods at file end. Merge order: 3→1→2. Git handles cleanly (no line overlap). |
| `pipeline.py` | 1, 2, 4 | **Phase isolation** — Stream 1 touches Phase 4 (~line 530). Stream 2 touches Phase 1 (~line 180). Stream 4 touches Phase 1 (~line 190, after Stream 2's code). Streams 1 and 2 can merge in any order. Stream 4 MUST merge after Stream 2. |
| `schemas.py` | 0, 1, 2, 4 | **Stream 0 creates foundation sections.** Others append to their own section. Low conflict. |
| `scan routes` | 1, 4 | Stream 1 adds diff endpoint + updates ticker detail. Stream 4 passes filters to pipeline. Different code locations. |
| `cli/commands.py` | 1, 2, 4 | **Different subcommands** — Stream 1 adds `--diff` to scan. Stream 2 adds `watchlist` group. Stream 4 implements `--sectors`. No overlap. |
| `router/index.ts` | 2 only | Stream 2 adds `/watchlists` route. No conflict. |
| `TickerDrawer.vue` | 2, 3 | Stream 2 adds "Add to Watchlist" button. Stream 3 adds earnings badge + trend chart. Different sections of the drawer. Merge order: 3→2 or 2→3 both work. |

---

## Schema Migration

**Single migration**: `006_v2_1_features.sql` created by Stream 0.

- `recommended_contracts` table — used by Stream 1
- `ALTER TABLE watchlists ADD COLUMN description` — used by Stream 2
- No new tables needed for scan diff (computed from existing `ticker_scores`)
- No new tables needed for debate trend (queries existing `ai_theses`)

**No breaking changes** to existing tables. All additive.

---

## New Dependencies

| Package | Version | Stream | Purpose | Bundle Impact |
|---------|---------|--------|---------|---------------|
| `chart.js` | ^4.x | 3 | Chart rendering engine | ~50KB gzipped |
| `vue-chartjs` | ^5.x | 3 | Vue 3 wrapper for Chart.js | ~5KB gzipped |

No new Python dependencies. All features use existing packages.

---

## API Changes Summary

| Endpoint | Change | Stream | Breaking? |
|----------|--------|--------|-----------|
| `GET /api/scan/{id}/scores/{ticker}` | `contracts: list[str]` → `list[OptionContract]` | 1 | Yes (type change) but field was always empty |
| `GET /api/scan/{id}/diff` | NEW | 1 | No |
| `POST /api/scan` body | Add `watchlist_id`, `sectors` | 2, 4 | No (additive optional fields) |
| `GET /api/watchlists` | NEW (7 endpoints) | 2 | No |
| `GET /api/debate/trend/{ticker}` | NEW | 3 | No |
| `GET /api/universe/sectors` | NEW | 4 | No |

---

## Success Criteria

### Functional

- Scan diff shows added/removed tickers + score deltas between any two scans
- Recommended contracts persist with greeks and display in TickerDetail
- Watchlist CRUD works via Web UI, CLI, and API
- Watchlist-mode scan scans only watchlist tickers (replace mode)
- Sector filter reduces SP500 universe correctly (e.g., "Technology" → ~80 tickers)
- `--sectors` CLI flag works (no more "not yet implemented" warning)
- Debate trend chart shows confidence over time with >= 2 data points
- Earnings proximity badge shows in TickerDrawer when < 7 days
- Dashboard auto-refreshes health and scan status

### Technical

- All ~155 new tests pass
- Existing 1,577 Python tests pass
- Existing 38 E2E Playwright tests pass
- `ruff check . --fix && ruff format .` — 0 errors
- `mypy src/ --strict` — 0 errors
- No `print()` in library code
- All new datetime fields have UTC validators
- All new confidence fields have [0.0, 1.0] validators
- No raw dicts in public APIs

---

## Verification Plan

After all streams merge, run full verification:

```bash
# Lint + format
uv run ruff check . --fix && uv run ruff format .

# Type checking
uv run mypy src/ --strict

# All Python tests
uv run pytest tests/ -v

# E2E tests (requires built frontend)
cd web && npm run build && cd ..
cd web && npx playwright test && cd ..

# Manual smoke test
options-arena health
options-arena scan --preset sp500 --diff
options-arena watchlist create "Test" --description "Smoke test"
options-arena watchlist add "Test" AAPL MSFT NVDA
options-arena scan --watchlist "Test"
options-arena scan --sectors "Technology,Healthcare"
options-arena debate AAPL --history
options-arena serve   # verify Web UI features in browser
```

---

## Per-Stream Checklist (for each Claude Code instance)

Before starting work on any stream:

1. Read this PRD fully
2. Read the module CLAUDE.md for every module you'll modify
3. `git checkout master && git pull`
4. Verify Stream 0 is merged: check `data/migrations/006_v2_1_features.sql` exists
5. Create feature branch: `git checkout -b feat/v2.1-<stream-name>`
6. Run full test suite before starting: `uv run pytest tests/ -v`

Before creating PR:

1. `uv run ruff check . --fix && uv run ruff format .`
2. `uv run mypy src/ --strict`
3. `uv run pytest tests/ -v` (all tests pass, including new ones)
4. Verify no `print()` in library code
5. Verify all new models follow project conventions (frozen, UTC validators, confidence validators)
6. Commit with conventional prefix: `feat: ...`

### Key files to read before each stream

**Stream 1**: `data/CLAUDE.md`, `scan/CLAUDE.md`, `api/CLAUDE.md`, `models/CLAUDE.md`
**Stream 2**: `data/CLAUDE.md`, `scan/CLAUDE.md`, `api/CLAUDE.md`, `cli/CLAUDE.md`, `web/CLAUDE.md`
**Stream 3**: `data/CLAUDE.md`, `api/CLAUDE.md`, `web/CLAUDE.md`
**Stream 4**: `scan/CLAUDE.md`, `api/CLAUDE.md`, `cli/CLAUDE.md`, `web/CLAUDE.md`, `models/CLAUDE.md`
