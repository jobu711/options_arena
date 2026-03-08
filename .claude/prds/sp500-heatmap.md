---
name: sp500-heatmap
description: Finviz-style S&P 500 treemap heatmap on dashboard showing live daily % change by sector
status: planned
created: 2026-03-08T01:36:53Z
---

# PRD: sp500-heatmap

## Executive Summary

Add a Finviz-style treemap heatmap to the Options Arena dashboard that shows the entire
S&P 500 market at a glance. Stocks are grouped by GICS sector, sized by market cap, and
colored by daily % change (green = up, red = down). This gives users an instant visual
snapshot of market conditions before diving into scans or debates.

## Problem Statement

Users currently have no quick visual summary of broad market conditions on the dashboard.
The existing dashboard shows scan summaries, trending tickers, and recent debates — all
project-specific data. There is no "what is the market doing right now?" view. Users must
leave Options Arena to check Finviz or a brokerage for market context.

A treemap heatmap solves this by showing ~500 stocks' daily performance in a single view,
organized by sector, with size encoding market cap importance. This is the most
information-dense market summary possible and a standard tool for active traders.

## User Stories

### US-1: Market Overview at a Glance
**As a** trader opening Options Arena,
**I want to** see a color-coded treemap of the S&P 500 on the dashboard,
**so that** I can instantly understand whether the market is risk-on or risk-off today.

**Acceptance Criteria:**
- Treemap loads automatically on dashboard page load
- Stocks colored green (up) to red (down) based on daily % change
- Stocks grouped visually by GICS sector with sector labels
- Larger companies (mega/large cap) occupy proportionally more area
- Loads within 10 seconds on first visit, <2 seconds on subsequent (cached)

### US-2: Drill into a Ticker
**As a** trader who spots an interesting stock on the heatmap,
**I want to** click on it to see its full detail page,
**so that** I can quickly research and potentially run a debate on it.

**Acceptance Criteria:**
- Clicking a ticker cell navigates to `/ticker/:ticker`
- Hovering shows tooltip with: ticker, company name, daily % change, current price

### US-3: Sector Analysis
**As a** trader evaluating sector rotation,
**I want to** see which sectors are green and which are red,
**so that** I can identify sector-level momentum before running sector-filtered scans.

**Acceptance Criteria:**
- Sector groups are visually distinct with labeled boundaries
- Sectors with mostly green tickers clearly stand out from mostly red sectors
- Sector names are readable without hovering

### US-4: Freshness
**As a** trader monitoring the market during trading hours,
**I want** the heatmap to auto-refresh periodically,
**so that** the data stays reasonably current without manual reloading.

**Acceptance Criteria:**
- Heatmap data auto-refreshes every 5 minutes
- Stale data shows a "last updated" timestamp
- Manual refresh button available

## Requirements

### Functional Requirements

#### FR-1: Backend — Batch Quote Service
- New method `fetch_batch_daily_changes()` on `MarketDataService`
- Uses `yf.download(tickers, period="2d", progress=False)` via `asyncio.to_thread()`
- Computes daily % change: `(today_close - prev_close) / prev_close * 100`
- Returns typed `BatchQuote` model per ticker (price, change_pct, volume)
- Handles partial failures: tickers that fail are omitted from results (no crash)
- `isfinite()` guard on all computed values

#### FR-2: Backend — Heatmap API Endpoint
- `GET /api/market/heatmap` returns `list[HeatmapTicker]`
- Each item: ticker, company_name, sector, industry_group, market_cap_weight, change_pct, price, volume
- Universe: S&P 500 constituents from existing `UniverseService`
- Metadata join: `ticker_metadata` table for sector, industry_group, market_cap_tier
- Market cap tier → weight mapping: mega=100, large=50, mid=20, small=8, micro=3 (default=10)
- Rate limit: 10 requests/minute
- 5-minute cache TTL via existing `ServiceCache`

#### FR-3: Frontend — Treemap Layout
- Squarify treemap algorithm implemented in TypeScript (no external dependency)
- Two-level hierarchy: sector → tickers
- Sector area proportional to sum of market_cap_weights within that sector
- Ticker area proportional to its market_cap_weight within its sector
- Minimum cell size threshold — tickers too small to render are omitted

#### FR-4: Frontend — Visual Encoding
- Color gradient: red (#ef4444) for negative change → neutral (#374151) at 0% → green (#22c55e) for positive
- Color intensity scales with magnitude (±5% is full saturation, ±0% is neutral)
- Ticker symbol displayed in each cell (font size scales with cell area)
- Change % displayed below ticker symbol when cell is large enough
- Sector labels at top-left of each sector group with semi-transparent background

#### FR-5: Frontend — Interactivity
- Hover: tooltip with ticker, company name, sector, change %, price, volume
- Click: navigates to `/ticker/:ticker` via Vue Router
- Loading state: skeleton placeholder while data fetches
- Error state: friendly message if endpoint fails

#### FR-6: Frontend — Dashboard Integration
- Placed as the first content section on `DashboardPage.vue`
- Section header: "Market Overview" with "Last updated: X min ago" + refresh button
- Responsive: fills container width, height ~500px (or configurable)
- Renders with HTML divs (position: absolute) inside a relative container

### Non-Functional Requirements

#### NFR-1: Performance
- Backend: batch yfinance download completes in <15 seconds for ~500 tickers
- Backend: cached responses return in <100ms
- Frontend: treemap renders in <500ms for ~500 tickers (HTML divs, no complex drawing)
- Frontend: no layout thrashing — compute positions once, batch DOM updates

#### NFR-2: Reliability
- Partial data is acceptable — if 50 tickers fail to fetch, show the other 450
- If the entire endpoint fails, show an error card (don't break the rest of the dashboard)
- NaN/Inf guard on all change_pct values before sending to frontend

#### NFR-3: Caching
- 5-minute server-side cache for heatmap data
- During market hours (9:30am–4:00pm ET), cache is sufficient for near-real-time feel
- After hours, cache prevents unnecessary API calls for stale data

## Success Criteria

| Metric | Target |
|--------|--------|
| Heatmap loads on dashboard | 100% of page loads (with error fallback) |
| Data freshness | Within 5 minutes of real market data during market hours |
| Tickers displayed | >90% of S&P 500 constituents visible |
| First load time | <15 seconds (uncached), <2 seconds (cached) |
| Interaction responsiveness | Hover tooltip appears in <100ms, click navigates immediately |
| Zero new npm dependencies | Squarify algorithm implemented in-house |

## Constraints & Assumptions

### Constraints
- **yfinance rate limits**: batch download for 500 tickers may be throttled; 5-min cache mitigates
- **No real market cap values**: we have `MarketCapTier` enum (mega/large/mid/small/micro) but not
  dollar values; use approximate weights per tier for sizing
- **Metadata coverage**: not all S&P 500 tickers may have `ticker_metadata` entries; fallback to
  "Unknown" sector and default weight
- **No new npm dependencies**: frontend team prefers zero new dependencies; squarify is small enough
  to implement directly

### Assumptions
- S&P 500 constituent list is available via existing `UniverseService.get_sp500_tickers()`
- `ticker_metadata` table has reasonable coverage for S&P 500 tickers (most should be indexed)
- yfinance `download()` supports batch multi-ticker fetching in a single call
- Daily % change is computed from the last 2 trading days of OHLCV data

## Out of Scope

- **Real-time streaming** — not WebSocket-streamed; poll-refreshed every 5 minutes
- **Multiple preset views** — only S&P 500; no NASDAQ 100, Russell 2000, or custom universes (future enhancement)
- **Zoom/drill-down** — no zooming into sectors or sub-industry groups (single flat treemap)
- **Historical comparison** — no "compare to yesterday" or time-travel features
- **Custom color modes** — no toggle between % change, volume, volatility, etc. (daily % change only)
- **Mobile-optimized layout** — responsive width but not redesigned for small screens
- **Unit tests for squarify algorithm** — algorithm is well-known; visual verification sufficient for v1

## Dependencies

### Internal
- `UniverseService` — S&P 500 ticker list (`services/universe.py`)
- `MarketDataService` — yfinance wrapper, `asyncio.to_thread` pattern (`services/market_data.py`)
- `ServiceCache` — server-side caching (`services/cache.py`)
- `Repository` — `ticker_metadata` table access (`data/repository.py`)
- `GICSSector`, `MarketCapTier` enums (`models/enums.py`)
- `DashboardPage.vue` — integration point (`web/src/pages/DashboardPage.vue`)

### External
- **yfinance** `download()` API — batch OHLCV data for multiple tickers
- **S&P 500 constituents CSV** — from GitHub datasets repo (existing source)

## Technical Implementation Notes

### Files to Create
| File | Purpose |
|------|---------|
| `src/options_arena/api/routes/market.py` | Heatmap API endpoint |
| `web/src/components/MarketHeatmap.vue` | Treemap component |

### Files to Modify
| File | Change |
|------|--------|
| `src/options_arena/services/market_data.py` | Add `fetch_batch_daily_changes()` + `BatchQuote` model |
| `src/options_arena/api/schemas.py` | Add `HeatmapTicker` response model |
| `src/options_arena/api/app.py` | Register market router |
| `web/src/types/scan.ts` | Add `HeatmapTicker` TypeScript interface |
| `web/src/pages/DashboardPage.vue` | Import + render `<MarketHeatmap />` |

### Architecture Boundary Compliance
- `services/market_data.py` owns the yfinance call (services layer = external API access)
- `api/routes/market.py` is a thin wrapper (joins service data + repo metadata)
- `api/schemas.py` defines the API-only response model
- Frontend component fetches via `useApi` composable (no direct fetch)
