---
name: v2-1-0
status: backlog
created: 2026-02-27T19:13:58Z
progress: 0%
prd: .claude/prds/v2-1-0.md
github: https://github.com/jobu711/options_arena/issues/142
---

# Epic: v2.1.0 — Close the Loop

## Overview

Five features that close the **screen -> analyze -> decide -> track** loop: watchlists, scan deltas, quick debate, score history, and earnings awareness. All features leverage existing database schema (`watchlists`, `watchlist_tickers`, `scan_runs`, `ticker_scores`), existing API patterns, and the existing `MarketContext.next_earnings` field. Zero schema migrations. Zero new dependencies.

## Architecture Decisions

- **No charting library**: Score history and sparklines rendered as hand-crafted SVG (avoids d3/chart.js bundle bloat)
- **No new tables**: `watchlists` + `watchlist_tickers` tables exist since `001_initial.sql`; score history queries join existing `ticker_scores` + `scan_runs`
- **`MarketContext.next_earnings` already exists**: Just needs population in Phase 3 and prompt injection in agents
- **Ticker-only debate already works**: `POST /api/debate` accepts `scan_id: null` — Quick Debate is pure frontend
- **Full-stack per feature**: Each task delivers backend + frontend for one feature (except watchlist, split for size)
- **Tests embedded per task**: Each task includes its own unit + integration + E2E tests (no separate test task)

## Technical Approach

### Data Layer (Repository Additions)
- 6 watchlist CRUD methods in `data/repository.py` (async, typed returns, parameterized queries)
- 1 score history query (`get_score_history(ticker, limit)`) joining `ticker_scores` + `scan_runs`
- Scan diff computed in-route via two `get_scores_for_scan()` calls + set operations (no new repo method needed)

### API Layer (New Routes)
- `routes/watchlist.py` — 6 REST endpoints for watchlist CRUD
- `routes/scan.py` — add `GET /api/scan/{id}/diff?base_id=` endpoint
- `routes/ticker.py` — new file, `GET /api/ticker/{ticker}/history` endpoint

### Service Layer
- `MarketDataService.fetch_earnings_date()` — yfinance `Ticker.calendar`, 24h cache TTL, `asyncio.to_thread` wrapping

### Agent Layer
- Conditional earnings warning injected into bull/bear/risk prompts when `next_earnings` < 7 days

### Web Frontend
- `WatchlistPage.vue` — new page at `/watchlist` route
- `ScoreHistoryChart.vue` — reusable SVG line chart component
- `SparklineChart.vue` — inline SVG sparkline for DataTable cells
- Dashboard additions: quick debate input, trending sections
- TickerDrawer additions: watchlist button, score history chart, earnings warning
- ScanResultsPage additions: compare dropdown, delta chips, earnings column
- New Pinia store: `watchlistStore`

### CLI
- `options-arena watchlist` subcommand group (`list`, `create`, `delete`, `add`, `remove`)

## Implementation Strategy

### Development Phases (Recommended Order)
1. **Task 1 — Quick Debate** (S): Immediate UX win, zero backend work
2. **Task 2 — Watchlist Backend** (M): Foundation for tracking loop
3. **Task 3 — Watchlist Frontend** (M): Completes watchlist feature
4. **Task 4 — Scan Delta** (S-M): Enables "what changed?" workflow
5. **Task 5 — Score History Backend** (S): Data foundation for charts
6. **Task 6 — Score History Frontend** (M): SVG charts, sparklines, dashboard trends
7. **Task 7 — Earnings Overlay** (M): Full-stack earnings awareness

### Risk Mitigation
- Quick Debate (Task 1) ships independently with zero risk — validates frontend patterns for remaining tasks
- Watchlist uses existing schema — no migration risk
- yfinance `Ticker.calendar` coverage varies — `None` handling ensures graceful degradation
- SVG charts are simple enough to avoid charting library complexity but may need iteration on visual polish

### Testing Approach
- Each task adds its own unit tests (repository, service, models), API integration tests, and Playwright E2E tests
- Target: ~150-200 new Python tests, ~15-20 new E2E tests across all tasks
- All 1,577 existing Python + 38 E2E tests must continue passing

## Task Breakdown

- [ ] **Task 1: Quick Debate from Dashboard (FR-3)** — Add InputText + Debate button to DashboardPage quick-actions. Call existing `POST /api/debate` with ticker only. Connect to WebSocket for progress, auto-navigate to `/debate/{id}` on completion. ~3 E2E tests.

- [ ] **Task 2: Watchlist Backend (FR-1 backend)** — Add `Watchlist` and `WatchlistTicker` Pydantic models. Add 6 repository methods (`create_watchlist`, `delete_watchlist`, `add_ticker`, `remove_ticker`, `get_watchlists`, `get_tickers_for_watchlist`). Add `routes/watchlist.py` with 6 REST endpoints. Add `options-arena watchlist` CLI subcommand group. ~40 Python tests.

- [ ] **Task 3: Watchlist Frontend (FR-1 frontend)** — New `WatchlistPage.vue` at `/watchlist` route with PrimeVue DataTable (ticker, latest score, direction, last debate date). Pinia `watchlistStore`. "Add to Watchlist" in TickerDrawer and scan results. Dashboard quick-action link. ~5 E2E tests.

- [ ] **Task 4: Scan Delta View (FR-2)** — Add `TickerDelta` and `ScanDiff` models. Add `GET /api/scan/{id}/diff?base_id=` endpoint (diff computed via two `get_scores_for_scan` calls + set ops). Frontend: "Compare with..." dropdown on ScanResultsPage, delta chips (green/red arrows), "NEW" badges, top movers section. ~25 Python tests + ~3 E2E tests.

- [ ] **Task 5: Score History Backend (FR-4 backend)** — Add `HistoryPoint` model. Add `get_score_history(ticker, limit=20)` repository method. Add `routes/ticker.py` with `GET /api/ticker/{ticker}/history`. Add `get_trending_tickers(direction, min_scans=3)` repository method for dashboard. ~20 Python tests.

- [ ] **Task 6: Score History Frontend (FR-4 frontend)** — New `ScoreHistoryChart.vue` (SVG line chart: dates x-axis, score y-axis, direction-colored dots). New `SparklineChart.vue` (inline SVG for DataTable cells). Integrate into TickerDrawer, new `/ticker/{ticker}` page, and Dashboard "Trending Up/Down" sections. Sparklines in ScanResultsPage DataTable. ~5 E2E tests.

- [ ] **Task 7: Earnings Calendar Overlay (FR-5)** — Add `MarketDataService.fetch_earnings_date()` (yfinance `Ticker.calendar`, 24h cache, `asyncio.to_thread`). Populate `MarketContext.next_earnings` in Phase 3. Inject earnings proximity warning into agent prompts when < 7 days. Frontend: "Earnings" column in scan results table (DTE, red if < 7d), warning banner in TickerDrawer. ~30 Python tests + ~3 E2E tests.

## Dependencies

### Internal (Existing)
- `watchlists` + `watchlist_tickers` tables (001_initial.sql)
- `scan_runs` + `ticker_scores` tables (score history, scan diff)
- `POST /api/debate` ticker-only support (quick debate)
- `MarketContext.next_earnings` field (earnings overlay)
- `MarketDataService`, `ServiceCache` (earnings data fetching)

### External
- **yfinance**: `Ticker.calendar` for earnings dates (already a dependency)
- No new packages (Python or JS)

### Task Dependencies
```
Task 1 (Quick Debate)     → standalone
Task 2 (Watchlist BE)     → standalone
Task 3 (Watchlist FE)     → blocked by Task 2
Task 4 (Scan Delta)       → standalone
Task 5 (Score History BE) → standalone
Task 6 (Score History FE) → blocked by Task 5
Task 7 (Earnings)         → standalone
```
Parallelizable pairs: (1, 2), (4, 5), (6, 7)

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| New Python tests | ~150-200 |
| New E2E tests | ~15-20 |
| Existing test regression | 0 (1,577 Python + 38 E2E all pass) |
| Schema migrations | 0 |
| New npm/pip dependencies | 0 |
| Score history query | < 100ms for 20-scan lookback |
| Earnings cache TTL | 24h (no yfinance rate limit pressure) |

## Estimated Effort

| Task | Effort | Critical Path |
|------|--------|---------------|
| Task 1: Quick Debate | S (0.5 day) | No |
| Task 2: Watchlist Backend | M (2 days) | Yes (blocks Task 3) |
| Task 3: Watchlist Frontend | M (2 days) | No |
| Task 4: Scan Delta | S-M (2 days) | No |
| Task 5: Score History Backend | S (1 day) | Yes (blocks Task 6) |
| Task 6: Score History Frontend | M (2 days) | No |
| Task 7: Earnings Overlay | M (2 days) | No |
| **Total** | **~11.5 days** | Parallelizable to ~7 days |

## Tasks Created

- [ ] #143 - Quick Debate from Dashboard (parallel: true)
- [ ] #144 - Watchlist Backend (parallel: true)
- [ ] #145 - Watchlist Frontend (parallel: false, depends_on: #144)
- [ ] #146 - Scan Delta View (parallel: true)
- [ ] #147 - Score History Backend (parallel: true)
- [ ] #148 - Score History Frontend (parallel: false, depends_on: #147)
- [ ] #149 - Earnings Calendar Overlay (parallel: true)

Total tasks: 7
Parallel tasks: 5 (#143, #144, #146, #147, #149)
Sequential tasks: 2 (#145 blocked by #144, #148 blocked by #147)
Estimated total effort: 90 hours (~11.5 days)
