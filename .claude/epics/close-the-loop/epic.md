---
name: close-the-loop
status: backlog
created: 2026-02-27T21:22:01Z
progress: 0%
prd: .claude/prds/close-the-loop.md
github: https://github.com/jobu711/options_arena/issues/132
---

# Epic: close-the-loop

## Overview

v2.1.0 "Close the Loop" adds continuity features so Options Arena becomes a daily-use
tool rather than a one-shot scanner. Seven features across 5 work streams: contract
persistence, scan diffs, watchlists, debate trends, sector filters, earnings alerts,
and auto-refresh. Designed for parallel execution by 4 Claude Code instances.

## Architecture Decisions

1. **Single migration for all streams** — `006_v2_1_features.sql` creates only
   `recommended_contracts` table + `ALTER TABLE watchlists ADD COLUMN description`.
   Watchlist tables already exist from migration 001. Scan diff and debate trend
   require no schema changes (computed from existing `ticker_scores` and `ai_theses`).

2. **Foundation-first for parallel safety** — Stream 0 creates shared Pydantic models
   (`models/watchlist.py`, `models/diff.py`) and API schemas before parallel streams
   begin. This eliminates merge conflicts on shared type files.

3. **Append-only repository extension** — Current `repository.py` (281 lines, 11
   methods) grows by ~14 new methods. Each stream appends to the end of the file.
   No existing method signatures change.

4. **Pipeline accepts optional ticker list** — `ScanPipeline.run()` gains
   `watchlist_tickers: list[str] | None = None`. When set, Phase 1 skips universe
   fetch entirely (replace mode). Sector filter applies after watchlist filter.

5. **Chart.js for trend visualization** — Only new frontend dependencies: `chart.js`
   + `vue-chartjs`. No new Python dependencies.

6. **Earnings in TickerDrawer only** — `next_earnings` is already on MarketContext but
   not on TickerScore. Rather than enriching the scan results schema, surface earnings
   only in the TickerDrawer (which fetches TickerInfo on demand). Avoids schema change.

## Technical Approach

### Backend Changes

| Area | What Changes |
|------|-------------|
| `data/repository.py` | +14 methods: 3 contract, 4 scan-diff, 9 watchlist, 1 debate-trend |
| `scan/pipeline.py` | Phase 1: watchlist mode + sector filter (~30 lines). Phase 4: contract persist (~5 lines) |
| `models/` | 2 new files (`watchlist.py`, `diff.py`), `__init__.py` re-exports +6 symbols |
| `models/config.py` | `ScanConfig.sectors: list[str] \| None` field |
| `api/schemas.py` | +6 request/response classes, `ScanRequest` gains `watchlist_id` + `sectors`, `TickerDetail.contracts` type fix |
| `api/routes/` | New `watchlist.py` router (7 endpoints). Extend `scan.py` (+diff endpoint), `debate.py` (+trend endpoint), `universe.py` (+sectors endpoint) |
| `api/app.py` | Include watchlist router (+2 lines) |
| `cli/commands.py` | New `watchlist` subcommand group. Implement `--sectors`. Add `--diff` flag. |

### Frontend Changes

| Area | What Changes |
|------|-------------|
| `web/package.json` | Add `chart.js`, `vue-chartjs` |
| Pages | New `WatchlistPage.vue`. Modify `ScanResultsPage`, `DebateResultPage`, `DashboardPage`, `ScanPage` |
| Components | New `ScanDiffView.vue`, `DebateTrendChart.vue`, `WatchlistManager.vue`. Modify `TickerDrawer.vue` |
| Stores | New `watchlist.ts`. Modify `scan.ts`, `debate.ts`, `health.ts` |
| Router | Add `/watchlists` route |

### Key Simplifications vs PRD

1. **No new migration for watchlist tables** — they already exist in migration 001.
   Migration 006 only adds `description` column + `recommended_contracts` table.
2. **`get_scan_diff` is a pure SQL query** — LEFT JOIN `ticker_scores` on two scan IDs.
   No new table needed.
3. **`get_debate_trend` queries existing `ai_theses`** — parses `verdict_json` for
   direction/confidence. No new table needed.
4. **Auto-refresh is frontend-only** — `setInterval` polling existing endpoints.
   Zero backend changes.
5. **Earnings alert is UI-only** — `next_earnings` already exists on MarketContext.
   Just render it in TickerDrawer with a badge.

## Task Breakdown

- [ ] **Task 1: Foundation** — Migration 006, `models/watchlist.py`, `models/diff.py`,
      re-exports, API schema stubs. ~30 tests. (Stream 0, blocking)
- [ ] **Task 2: Contract Persistence + Scan Diff** — Repository methods for contract
      CRUD + scan diff query. Pipeline Phase 4 persist. API endpoints. CLI `--diff`.
      Vue `ScanDiffView`. ~35 tests. (Stream 1, depends on Task 1)
- [ ] **Task 3: Watchlists** — Repository CRUD (9 methods). API router (7 endpoints).
      Pipeline watchlist mode. CLI `watchlist` subcommands. Vue `WatchlistPage` +
      `WatchlistManager` + store. TickerDrawer "Add to Watchlist". ~45 tests.
      (Stream 2, depends on Task 1)
- [ ] **Task 4: Debate Trend + Earnings + Auto-Refresh** — Repository trend query.
      API trend endpoint. `DebateTrendChart.vue` with Chart.js. Earnings badge in
      TickerDrawer. Dashboard auto-refresh polling. CLI `--history` trend arrows.
      ~25 tests. (Stream 3, depends on Task 1)
- [ ] **Task 5: Sector Filters** — `ScanConfig.sectors` field. Pipeline Phase 1
      sector filter. Implement CLI `--sectors`. API sectors endpoint + ScanRequest
      extension. Vue ScanPage MultiSelect. ~20 tests. (Stream 4, depends on Tasks 1+3)
- [ ] **Task 6: Integration & Release** — Merge all streams. Run full verification
      (ruff, mypy, pytest, Playwright). Manual smoke test. Tag v2.1.0.

## Dependencies

- **External**: None new. All features use existing yfinance, Groq, SQLite stack.
- **Frontend**: `chart.js` ^4.x + `vue-chartjs` ^5.x (Task 4 only).
- **Internal**: Stream 0 (Task 1) must merge before Tasks 2-4 begin. Task 5 must
  wait for Task 3 (both modify `pipeline.py` Phase 1).

## Success Criteria (Technical)

- ~155 new tests pass (30 + 35 + 45 + 25 + 20)
- Existing 1,577 Python + 38 E2E tests pass
- `ruff check . --fix && ruff format .` — 0 errors
- `mypy src/ --strict` — 0 errors
- No `print()` in library code
- All new datetime fields have UTC validators
- All new confidence fields have `[0.0, 1.0]` validators
- No raw dicts in public APIs

## Estimated Effort

- **Task 1 (Foundation)**: 2-3 hours — models + migration + schemas
- **Tasks 2-4 (Parallel)**: 4-6 hours each — run simultaneously across 3 instances
- **Task 5 (Filters)**: 3-4 hours — after Task 3 merges
- **Task 6 (Integration)**: 1-2 hours — merge + verify
- **Total wall-clock**: ~13 hours with 4 parallel instances
- **Total effort**: ~25 hours of implementation

## Tasks Created

- [ ] #133 - Foundation — Models, Migration, Schemas (parallel: false, blocking)
- [ ] #135 - Contract Persistence + Scan Diff (parallel: true, depends: #133)
- [ ] #137 - Watchlists (parallel: true, depends: #133)
- [ ] #134 - Debate Trend + Earnings Alerts + Auto-Refresh (parallel: true, depends: #133)
- [ ] #136 - Sector & Market Cap Filters (parallel: false, depends: #133+#137)
- [ ] #138 - Integration & Release v2.1.0 (parallel: false, depends: #135+#137+#134+#136)

Total tasks: 6
Parallel tasks: 3 (#135, #137, #134 — run simultaneously after #133)
Sequential tasks: 3 (#133, #136, #138)
Estimated total effort: ~25 hours
