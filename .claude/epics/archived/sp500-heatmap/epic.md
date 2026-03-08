---
name: sp500-heatmap
status: completed
created: 2026-03-08T02:01:25Z
completed: 2026-03-08T06:30:00Z
progress: 100%
prd: .claude/prds/sp500-heatmap.md
github: https://github.com/jobu711/options_arena/issues/365
---

# Epic: sp500-heatmap

## Overview

Add a Finviz-style S&P 500 treemap heatmap as the first section on the dashboard. Backend
introduces `yf.download()` batch fetching (new pattern) on `MarketDataService`, a thin
`GET /api/market/heatmap` endpoint joining quotes with `ticker_metadata`, and a 5-minute
server-side cache. Frontend implements a squarify treemap algorithm in TypeScript (zero npm
deps), a Pinia store with auto-refresh, and an HTML-div-based `MarketHeatmap.vue` component
with hover tooltips and click-to-navigate.

## Architecture Decisions

1. **`yf.download()` for batch fetching** — Single call for ~500 tickers instead of 500
   individual `yf.Ticker().history()` calls. Uses `group_by="ticker"`, `period="2d"`,
   `timeout=30`. Context7-verified API surface.

2. **Pinia store for heatmap state** — `heatmap.ts` follows `health.ts` auto-refresh pattern
   (`setInterval` 5min). Store owns data lifecycle; component is purely presentational.

3. **Price as `float`** — Heatmap prices are display-only (no P&L computation). Using `float`
   avoids `Decimal` serialization overhead for 500 items. `isfinite()` validators still apply.

4. **Existing `ServiceCache`** — New `"heatmap"` data type with 5-min TTL. Consistent with
   codebase; avoids ad-hoc caching.

5. **Market cap tier → weight mapping in route** — `mega=100, large=50, mid=20, small=8,
   micro=3, unknown=10`. This is API/display concern, not service logic. Lives in route file.

6. **Squarify in TypeScript** — ~80 lines, well-known algorithm. No npm dependency. Two-level
   layout: sectors → tickers within sectors.

7. **HTML divs, not SVG/Canvas** — `position: absolute` cells inside `position: relative`
   container. Follows `DimensionalScoreBars.vue` pattern. Simple, performant for ~500 elements.

## Technical Approach

### Backend

**`services/market_data.py`** — Add `fetch_batch_daily_changes(tickers: list[str])`:
- `yf.download()` via `asyncio.to_thread()` + `asyncio.wait_for(timeout=30)`
- Parse MultiIndex DataFrame: `data[ticker]["Close"]` per ticker, compute `(today - prev) / prev * 100`
- Return `list[BatchQuote]` (ticker, price, change_pct, volume)
- `isfinite()` guard; skip tickers with NaN/missing data
- Cache full result with `ServiceCache`, key `"yf:heatmap:sp500"`, TTL 5min

**`api/schemas.py`** — Add `HeatmapTicker(BaseModel, frozen=True)`:
- Fields: ticker, company_name, sector, industry_group, market_cap_weight, change_pct, price, volume
- `isfinite()` validator on `change_pct` and `price`

**`api/routes/market.py`** — New file, `GET /api/market/heatmap`:
- DI: `Depends(get_market_data)`, `Depends(get_universe)`, `Depends(get_repo)`
- Fetch universe tickers, batch daily changes, ticker metadata
- Join into `list[HeatmapTicker]` with fallback sector/weight for missing metadata
- Rate limit: `@limiter.limit("10/minute")`

**`api/app.py`** — Register `market_router`

### Frontend

**`web/src/types/scan.ts`** — Add `HeatmapTicker` interface

**`web/src/stores/heatmap.ts`** — Pinia setup store:
- `fetchHeatmap()` via `api<HeatmapTicker[]>('/api/market/heatmap')`
- `startAutoRefresh(5 * 60 * 1000)` / `stopAutoRefresh()`
- Reactive: `tickers`, `loading`, `error`, `lastUpdated`

**`web/src/components/MarketHeatmap.vue`** — Composition API `<script setup>`:
- Squarify algorithm: takes weighted items, returns `{x, y, width, height}` rects
- Two-level layout: group by sector → squarify sectors → squarify tickers within each
- Color: interpolate `#ef4444` ↔ `#374151` ↔ `#22c55e` based on `change_pct / 5.0`
- Hover: floating tooltip div with ticker, name, sector, change%, price, volume
- Click: `router.push('/ticker/${ticker}')`
- Sector labels: semi-transparent background at top-left of sector area
- Font scaling: ticker symbol size proportional to cell area; hide text when too small
- Loading skeleton + error state

**`web/src/pages/DashboardPage.vue`** — Add `<MarketHeatmap />` as first content section
with "Market Overview" header, "Last updated X min ago", and refresh button

## Implementation Strategy

### Wave 1: Backend (sequential)
- Task 1: Service method + model + tests
- Task 2: API endpoint + schema + router registration + tests

### Wave 2: Frontend (sequential, depends on Wave 1)
- Task 3: TypeScript types + Pinia store
- Task 4: MarketHeatmap.vue component (squarify, colors, interactivity)
- Task 5: Dashboard integration + E2E test

### Risk Mitigation
- **yfinance timeout**: Use `timeout=30` directly on `yf.download()` call; cache makes repeat calls rare
- **Metadata gaps**: Fallback to `SP500Constituent.sector` string + default weight=10
- **MultiIndex parsing**: `KeyError` handling per ticker; partial results acceptable

## Task Breakdown Preview

- [ ] Task 1: Backend service — `BatchQuote` model + `fetch_batch_daily_changes()` + unit tests
- [ ] Task 2: Backend API — `HeatmapTicker` schema + `GET /api/market/heatmap` route + register router + route tests
- [ ] Task 3: Frontend data layer — `HeatmapTicker` TS type + `heatmap.ts` Pinia store with auto-refresh
- [ ] Task 4: Frontend component — `MarketHeatmap.vue` with squarify algorithm, color encoding, hover/click
- [ ] Task 5: Dashboard integration — Wire component into `DashboardPage.vue` + E2E test

## Dependencies

### Internal (all existing, no new work needed)
- `UniverseService.fetch_sp500_constituents()` — ticker universe
- `MarketDataService._yf_call()` — async yfinance wrapper
- `Repository.get_all_ticker_metadata()` — sector/market cap metadata
- `ServiceCache` — two-tier caching
- `api/deps.py` — `get_market_data`, `get_universe`, `get_repo` providers
- `useApi` composable — frontend API calls

### External
- `yfinance.download()` — batch OHLCV (Context7-verified)
- S&P 500 CSV — GitHub datasets (existing source)

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Backend tests pass | All new unit tests green |
| `fetch_batch_daily_changes()` | Returns >90% of requested tickers |
| Cached response time | <100ms |
| Frontend render | <500ms for ~500 div elements |
| Zero new npm deps | Squarify implemented in TypeScript |
| `ruff check` + `mypy --strict` | Clean |
| E2E test | Dashboard heatmap loads and renders |

## Estimated Effort

- **5 tasks**, **Large (L)** complexity
- **Critical path**: Task 1 → Task 2 → Task 3 → Task 4 → Task 5
- All patterns have clear precedents — no architectural novelty, just cross-stack breadth

## Tasks Created

- [ ] #366 - Backend service — BatchQuote model + fetch_batch_daily_changes() (parallel: false)
- [ ] #367 - Backend API — HeatmapTicker schema + GET /api/market/heatmap route (parallel: false, depends: #366)
- [ ] #368 - Frontend data layer — HeatmapTicker type + Pinia heatmap store (parallel: false, depends: #367)
- [ ] #369 - Frontend component — MarketHeatmap.vue with squarify treemap (parallel: false, depends: #368)
- [ ] #370 - Dashboard integration + E2E test (parallel: false, depends: #369)

Total tasks: 5
Parallel tasks: 0
Sequential tasks: 5
Estimated total effort: 16-24 hours

## Test Coverage Plan

Total test files planned: 2 (backend) + 1 (E2E) = 3
Total test cases planned: 19 backend + 4 E2E = 23
