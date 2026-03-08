# Research: sp500-heatmap

## PRD Summary

Add a Finviz-style treemap heatmap to the Options Arena dashboard. ~500 S&P 500 stocks
grouped by GICS sector, sized by market cap tier weight, colored by daily % change
(green→neutral→red). Backend fetches batch daily changes via `yf.download()`, joins with
`ticker_metadata` for sector/market cap. Frontend renders a squarify treemap with HTML divs.
Click navigates to `/ticker/:ticker`. 5-minute auto-refresh with server-side caching.

## Relevant Existing Modules

| Module | Relevance |
|--------|-----------|
| `services/market_data.py` | Add `fetch_batch_daily_changes()` — new `yf.download()` pattern (existing code uses per-ticker `yf.Ticker().history()`) |
| `services/universe.py` | `fetch_sp500_constituents()` → `list[SP500Constituent]` already provides the ~500-ticker universe |
| `services/cache.py` | `ServiceCache` with `TTL_QUOTE_MARKET = 5*60` matches the 5-min heatmap TTL |
| `data/repository.py` | `get_all_ticker_metadata()` → `list[TickerMetadata]` for sector/market cap join |
| `models/enums.py` | `GICSSector` (11 values), `MarketCapTier` (mega/large/mid/small/micro), `SECTOR_ALIASES` |
| `models/metadata.py` | `TickerMetadata` frozen model (sector, industry_group, market_cap_tier, company_name) |
| `api/schemas.py` | Where `HeatmapTicker` response model goes |
| `api/app.py` | Router registration point (lines 163-181) |
| `api/deps.py` | `get_market_data`, `get_repo`, `get_universe` providers already exist |
| `web/src/pages/DashboardPage.vue` | Integration point — heatmap goes as first content section |
| `web/src/composables/useApi.ts` | `api<T>(path)` composable for all API calls |
| `web/src/types/scan.ts` | Where `HeatmapTicker` TypeScript interface goes |

## Existing Patterns to Reuse

### 1. Service Layer — `_yf_call()` wrapper
`market_data.py` wraps sync yfinance in `asyncio.to_thread()` + `asyncio.wait_for(timeout)`.
The new `fetch_batch_daily_changes()` uses this for `yf.download()`.

### 2. Batch Result Models
`BatchOHLCVResult` / `TickerOHLCVResult` in `market_data.py` — typed models with `.succeeded()`,
`.failed()`, `.get(ticker)`. Template for `BatchDailyChangeResult`.

### 3. Cache-first Service Pattern
Check cache → return if hit → fetch + compute → cache result. Used by `fetch_ohlcv()`, `fetch_quote()`.
Heatmap uses same pattern with `ttl=5*60`.

### 4. API Route Pattern
Thin handler with `Depends()` DI, `@limiter.limit()` rate limiting, response model annotation.
See `routes/universe.py`, `routes/ticker.py`.

### 5. Frontend Data Fetch
`DashboardPage.vue` uses `Promise.all([...])` with `.catch(() => fallback)` for graceful failure.
Heatmap component manages its own lifecycle (`onMounted`/`onUnmounted` for auto-refresh).

### 6. HTML Div Visualization
`DimensionalScoreBars.vue` renders data as HTML divs with CSS-driven widths/colors — same approach
the heatmap uses (`position: absolute` cells inside `position: relative` container).

### 7. Pinia Store with Auto-Refresh
`health.ts` store has `setInterval`-based auto-refresh with `startAutoRefresh()`/`stopAutoRefresh()`.
Heatmap store follows same pattern with 5-minute interval.

### 8. Sector Color Map
`SectorTree.vue` has `SECTOR_COLOR_MAP` for all 11 GICS sectors — reusable for sector labels.

## Existing Code to Extend

| File | What Exists | What Needs Adding |
|------|------------|-------------------|
| `services/market_data.py` | `_yf_call()`, `fetch_batch_ohlcv()`, `BatchOHLCVResult` | `fetch_batch_daily_changes(tickers)` + `BatchQuote` model |
| `api/schemas.py` | 400+ lines of response schemas | `HeatmapTicker` response model |
| `api/app.py` | 8 router registrations | 9th: `market_router` |
| `web/src/types/scan.ts` | `TickerScore`, `ScanRun`, etc. | `HeatmapTicker` interface |
| `web/src/pages/DashboardPage.vue` | Health strip, scan summary, trending, debates | Add `<MarketHeatmap />` as first section |

## Files to Create

| File | Purpose |
|------|---------|
| `src/options_arena/api/routes/market.py` | `GET /api/market/heatmap` — joins service + repo + universe data |
| `web/src/components/MarketHeatmap.vue` | Squarify treemap component (HTML divs, hover/click) |
| `web/src/stores/heatmap.ts` | Pinia store with auto-refresh (follows `health.ts` pattern) |

## Potential Conflicts

### 1. yfinance timeout for 500 tickers
Default `yfinance_timeout` is 15s — may be tight for `yf.download()` with 500 tickers.
**Mitigation**: Use `yf.download(timeout=30)` parameter directly, or add a dedicated config field.
The 5-min cache ensures this heavy call is rare.

### 2. MultiIndex DataFrame parsing
`yf.download()` with `group_by="ticker"` returns `data["AAPL"]["Close"]` (MultiIndex columns).
This is different from per-ticker `Ticker.history()` which returns flat columns.
**Mitigation**: Per-ticker extraction with `KeyError` handling for tickers that failed.

### 3. Metadata coverage gaps
Not all S&P 500 tickers have `ticker_metadata` entries (requires `universe index` run).
**Mitigation**: Default to "Unknown" sector and weight=10 when metadata absent (per PRD).

### 4. SP500Constituent.sector is raw string
Needs normalization to `GICSSector` enum via existing `SECTOR_ALIASES` / `build_sector_map()`.
**Mitigation**: Use SP500Constituent sector as display string, ticker_metadata sector as typed enum.

### 5. No breaking changes
All modifications are purely additive. No existing APIs or models are changed.

## Context7 Verification: yfinance.download()

Verified via Context7 (`/ranaroussi/yfinance`):
- `yf.download(tickers, period="2d", group_by="ticker", progress=False, threads=True)`
- Returns `pandas.DataFrame` with MultiIndex columns `(ticker, field)`
- Access: `data["AAPL"]["Close"]` when `group_by="ticker"`
- `multi_level_index=True` is default
- `timeout` parameter available (default 10s)
- `period="2d"` is valid
- `rounding=True` rounds to 2dp (useful for price display)

## Open Questions

1. **Heatmap store vs inline fetch?** PRD doesn't specify. Research suggests a Pinia store
   (`heatmap.ts`) following the `health.ts` auto-refresh pattern is cleaner than inline
   `DashboardPage` fetch. The store owns refresh lifecycle.

2. **Price as Decimal or float?** Existing patterns serialize `Decimal` as string for the API.
   Heatmap prices are display-only (no arithmetic on frontend). Could use `float` for simplicity
   since no P&L computation occurs. PRD says `BatchQuote` has `price` field — follow existing
   `Quote.price: Decimal` pattern for consistency.

3. **Cache layer for heatmap?** The `ServiceCache` two-tier (memory+SQLite) cache could store
   the full batch result. Alternative: simple in-memory dict with timestamp in the service method.
   Recommend: use existing `ServiceCache` with `"heatmap"` data type for consistency.

## Recommended Architecture

```
yf.download(~500 tickers, period="2d")  [via asyncio.to_thread]
    └── MarketDataService.fetch_batch_daily_changes(tickers: list[str])
            Cache: ServiceCache, TTL=5min, key="yf:heatmap:sp500"
            Returns: list[BatchQuote]  (ticker, price, change_pct, volume)

        + UniverseService.fetch_sp500_constituents()
            Returns: list[SP500Constituent]  (existing, cached 24h)

        + Repository.get_all_ticker_metadata()
            Returns: list[TickerMetadata]  (existing)

    ↓ joined in route handler (thin, no business logic)

GET /api/market/heatmap  →  list[HeatmapTicker]
    Rate limit: 10/min, cache: 5min server-side
    Weight mapping: mega=100, large=50, mid=20, small=8, micro=3, unknown=10

    ↓ HTTP JSON via useApi composable

Pinia heatmap store  →  auto-refresh every 5min
    ↓ reactive data

<MarketHeatmap :data="tickers" />
    Squarify layout (TypeScript, ~80 lines, no npm dep)
    Two-level: sector rectangles → ticker cells
    HTML divs, position: absolute, color by change_pct
    Hover tooltip, click → router.push('/ticker/:ticker')
```

## Test Strategy Preview

### Backend Tests
- `tests/unit/services/test_market_data.py` — existing file, add tests for `fetch_batch_daily_changes()`
  - Mock `yf.download()` with synthetic DataFrame
  - Test partial failures (some tickers missing from result)
  - Test `isfinite()` guards (NaN/Inf change_pct rejected)
  - Test cache hit/miss
- `tests/unit/api/test_market_routes.py` — new file for heatmap endpoint
  - Mock service + repo dependencies
  - Test response shape matches `HeatmapTicker` schema
  - Test metadata-missing fallback (Unknown sector, weight=10)
  - Test rate limiting

### Frontend Tests
- E2E: Add Playwright test that dashboard loads heatmap section (skeleton → data)
- No unit tests for squarify algorithm per PRD out-of-scope decision

### Existing Test Patterns
- Fixtures: `@pytest.fixture` with mock services, `AsyncMock` for async methods
- Naming: `test_{method}_{scenario}` (e.g., `test_fetch_batch_daily_changes_partial_failure`)
- Assertions: exact model field checks, `math.isfinite()` on numerics

## Estimated Complexity

**Large (L)** — Justification:
- New `yf.download()` pattern (never used before in codebase)
- Backend: new service method + new API route + new schema (3 files modified, 1 created)
- Frontend: new squarify algorithm + new Vue component + new Pinia store + dashboard integration
  (2 files created, 3 modified)
- Cross-stack feature touching services, API, models, and frontend
- ~500-ticker batch processing with partial failure handling
- However, all patterns have clear precedents in the codebase — no architectural novelty
