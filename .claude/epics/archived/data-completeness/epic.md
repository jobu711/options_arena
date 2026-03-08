---
name: data-completeness
status: backlog
created: 2026-03-06T20:50:42Z
progress: 0%
prd: .claude/prds/data-completeness.md
github: https://github.com/jobu711/options_arena/issues/318
---

# Epic: data-completeness

## Overview

Fill three data gaps: (1) inject `OptionsDataService` into `OutcomeCollector` so active contracts compute P&L from live option chains, (2) extract short interest (`shortRatio`, `shortPercentOfFloat`) from yfinance into `TickerInfo` and thread to debate agents via `MarketContext`, (3) add colored interpretation labels (Overbought, Strong Trend, etc.) to the TickerDrawer indicator grid using PrimeVue `Tag`.

## Architecture Decisions

1. **OptionsDataService as optional DI** — Add as `options_data: OptionsDataService | None = None` to `OutcomeCollector.__init__()`. Backward compatible: without it, behavior is unchanged (active contracts return `None` P&L). No new service classes.

2. **Reuse `MARKET` collection method** — Active contracts with option chain data continue using `OutcomeCollectionMethod.MARKET` (already the method for active contracts). No new enum value needed.

3. **No cache key versioning** — `TickerInfo` cache serves `None` for missing short interest fields on old cached entries. Market-hours-aware TTL handles refresh naturally. Avoids cache invalidation complexity.

4. **No `short_pct_of_float` upper bound** — Allow values >1.0 since short squeezes can exceed 100% of float. Only validate `isfinite()` and `>= 0`.

5. **MarketContext persistence unaffected** — Stored as JSON blob (`market_context_json TEXT`). Pydantic handles missing fields on deserialization with `None` default. No SQL migration.

6. **Frontend-only signal classification** — `classifySignal()` is a pure TypeScript function in TickerDrawer (or shared utility). No backend changes. Thresholds apply to normalized 0-100 percentile values.

## Technical Approach

### Backend (Features 1 & 2)

**Short interest pipeline** (5 files):
- `models/market_data.py`: Add `short_ratio: float | None = None`, `short_pct_of_float: float | None = None` to `TickerInfo` with `field_validator` (isfinite + non-negative)
- `services/market_data.py`: Extract via existing `safe_float(info.get("shortRatio"))` pattern in `fetch_ticker_info()`
- `models/analysis.py`: Add `short_ratio: float | None = None` to `MarketContext`
- `agents/orchestrator.py`: Thread `ticker_info.short_ratio` into `MarketContext(...)` constructor
- `agents/_parsing.py`: Render via `_render_optional("SHORT RATIO", ctx.short_ratio, ".2f")` in Fundamental Profile section

**Active-contract P&L** (3 files):
- `services/outcome_collector.py`: Add `options_data` param, implement chain fetch + contract matching in `_process_active_contract()`. Wrap in `asyncio.wait_for(timeout=10)`, `try/except Exception` for graceful fallback.
- `api/deps.py`: Pass `request.app.state.options_data` to `OutcomeCollector()`
- `cli/outcomes.py`: Create `OptionsDataService`, pass to collector, close in `finally`

### Frontend (Feature 3)

**Indicator signal interpretation** (1 file):
- `web/src/components/TickerDrawer.vue`: Add `classifySignal(key, value)` function returning `{ label, severity } | null`. 6 indicators with thresholds per PRD. Render PrimeVue `<Tag>` alongside value. Expand CSS grid to 3 columns.

## Implementation Strategy

### Waves (Tasks 1-3 are parallelizable)

| Task | Files | Depends On |
|------|-------|------------|
| 1. Short interest end-to-end | 5 Python files | None |
| 2. Active-contract P&L | 3 Python files | None |
| 3. Indicator signal labels | 1 Vue file | None |
| 4. Verification | — | Tasks 1-3 |

All three features are independent — they can be implemented in any order or in parallel.

## Task Breakdown Preview

- [ ] Task 1: Short interest — TickerInfo fields + extraction + MarketContext threading + agent context rendering + tests
- [ ] Task 2: Active-contract P&L — OutcomeCollector OptionsDataService DI + chain fetch logic + deps.py + CLI wiring + tests
- [ ] Task 3: Indicator signal interpretation — classifySignal utility + TickerDrawer Tag rendering + CSS grid update
- [ ] Task 4: Verification — ruff check, ruff format, mypy --strict, pytest (full suite), frontend build

## Dependencies

### Internal (all exist)
- `OptionsDataService` — fully implemented, on `app.state.options_data`
- `safe_float()` helper — in `services/helpers.py`
- `_render_optional()` — in `agents/_parsing.py`
- PrimeVue `Tag` — already imported in `TickerDrawer.vue`
- `compute_short_interest()` — in `indicators/fundamental.py` (validation logic)

### External
- yfinance `Ticker.info["shortRatio"]` / `["shortPercentOfFloat"]` — standard fields, available for liquid equities

## Success Criteria (Technical)

| Criterion | Validation |
|-----------|-----------|
| Active contracts compute `exit_contract_mid` | Unit test: mock `fetch_chain` → mid = (bid+ask)/2 |
| Fallback works without OptionsDataService | Unit test: construct without `options_data` → None P&L |
| Chain fetch failure → graceful None | Unit test: `fetch_chain` raises → log warning, None |
| `TickerInfo.short_ratio` populated | Unit test: yfinance info with shortRatio → extracted |
| NaN/negative short interest rejected | Unit test: validator raises ValueError |
| `MarketContext.short_ratio` threaded | Unit test: orchestrator passes value |
| Context block renders SHORT RATIO | Unit test: render_context_block output contains label |
| Indicator labels shown in TickerDrawer | Manual or E2E: RSI >70 shows "Overbought" red tag |
| `ruff check`, `ruff format`, `mypy --strict` pass | CI gates |
| All existing tests still pass | Full pytest suite |

## Estimated Effort

**Medium** — 9 Python files edited, 1 Vue component edited, ~15-20 new tests. No new files, services, or models. All changes extend existing code using established patterns. 4 tasks, all parallelizable except final verification.

## Tasks Created
- [ ] #319 - Short interest end-to-end (parallel: true)
- [ ] #320 - Active-contract P&L via OptionsDataService DI (parallel: true)
- [ ] #321 - Indicator signal interpretation labels (parallel: true)
- [ ] #322 - Verification and CI gates (parallel: false, depends: #319-#321)

Total tasks: 4
Parallel tasks: 3
Sequential tasks: 1
Estimated total effort: 7-10 hours

## Test Coverage Plan
Total test files planned: 4 (existing files, new tests added)
Total test cases planned: ~18 (8 short interest + 8 outcome collector + 2 context block)

## Research Resolutions

| Open Question | Resolution |
|--------------|-----------|
| MarketContext persistence schema | JSON blob — no migration needed |
| Cache key versioning | Not needed — None default for missing fields, TTL handles refresh |
| short_pct_of_float range | Allow >1.0 (short squeezes exceed 100%). Only validate isfinite + non-negative |
| OutcomeCollectionMethod enum | Reuse `MARKET` — already represents live market data |
