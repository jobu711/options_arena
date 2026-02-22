---
name: phase-5-services
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 5: Services Layer

## Overview

Build the `services/` package: cherry-pick cache, rate limiter, helpers, health, and FRED from v3. Add dividend yield extraction waterfall to market data. Pass `impliedVolatility` through as `market_iv`. Rewrite universe service with `pd.read_html()` and `MarketCapTier` classification.

## Scope

### PRD Requirements Covered
FR-SV1, FR-SV2, FR-SV3, FR-SV4, FR-SV5, FR-SV6, FR-SV7, FR-M7.1 (implementation)

### Deliverables

**`src/options_arena/services/`:**

- `cache.py` — Cherry-pick: two-tier caching (in-memory for quotes/chains, SQLite for OHLCV/fundamentals), market-hours-aware TTL from `ServiceConfig`

- `rate_limiter.py` — Cherry-pick: token bucket + `asyncio.Semaphore`, `rate_limit_rps` and `max_concurrent_requests` from `ServiceConfig`

- `helpers.py` — Cherry-pick: `fetch_with_retry()` with exponential backoff (1s→16s, max 5 retries)

- `market_data.py` — Cherry-pick + extend:
  - yfinance OHLCV, quotes, ticker info via `asyncio.to_thread()` with `asyncio.wait_for(timeout)`
  - **New: Dividend yield extraction** (FR-M7.1 waterfall):
    1. `info.get("dividendYield")` — if not `None`, source = `FORWARD`
    2. `info.get("trailingAnnualDividendYield")` — if not `None`, source = `TRAILING`
    3. `Ticker.get_dividends(period="1y")` sum / price — source = `COMPUTED`
    4. `0.0` — source = `NONE`
  - Fall-through on `value is None` only (NOT falsy — `0.0` is valid)
  - Cross-validation: warn if yield vs dollar-rate divergence > 20%
  - Audit fields: `dividend_rate`, `trailing_dividend_rate` on `TickerInfo`
  - All yfinance `.info` keys are camelCase — translate to snake_case in model

- `options_data.py` — Cherry-pick + extend:
  - Option chain fetching with basic liquidity filters (OI >= 100, volume >= 1, reject both-zero bid/ask)
  - Pass `impliedVolatility` through as `market_iv` on `OptionContract`
  - yfinance chain columns (Context7-verified): `contractSymbol`, `lastTradeDate`, `strike`, `lastPrice`, `bid`, `ask`, `change`, `percentChange`, `volume`, `openInterest`, `impliedVolatility`, `inTheMoney`, `contractSize`, `currency`
  - No Greeks extraction (yfinance provides none)

- `universe.py` — **Rewrite**:
  - CBOE optionable ticker universe (CSV download)
  - S&P 500 constituents: `pd.read_html(url, attrs={"id": "constituents"})` (Context7-verified)
  - Columns needed: `Symbol`, `GICS Sector`
  - Ticker translation: `.` → `-` for yfinance (`BRK.B` → `BRK-B`)
  - Column validation at parse time to catch schema drift
  - `MarketCapTier` classification via yfinance `marketCap`

- `fred.py` — Cherry-pick + extend:
  - FRED 10yr Treasury for risk-free rate via httpx
  - Fallback to `PricingConfig.risk_free_rate_fallback` (default 5%)

- `health.py` — Cherry-pick + extend:
  - Service health checks (yfinance, FRED, CBOE, Ollama)
  - Configurable Ollama model ID from `ServiceConfig`

- `__init__.py` — Re-export public API

**Tests (`tests/unit/services/`):**
- Market data: dividend waterfall (all 4 tiers), cross-validation warning, timeout handling
- Options data: liquidity filtering, `market_iv` passthrough, both-zero bid/ask rejection
- Universe: S&P 500 parsing, ticker translation, column validation, CBOE CSV parsing
- FRED: success, timeout, fallback to default rate
- Cache: TTL expiry, market-hours-aware behavior
- Rate limiter: token bucket depletion, semaphore limiting
- Health: all service checks
- ~100 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models — `TickerInfo`, `OptionContract`, `ServiceConfig`, `DividendSource`)
- **Blocks**: Epic 7 (scan pipeline — Phase 1 universe + OHLCV, Phase 3 options chain)
- **Parallelizable**: Can run in parallel with Epics 2, 3, 6 after Epic 1 completes

## Key Decisions
- All sync yfinance calls wrapped in `asyncio.to_thread()` + `asyncio.wait_for(timeout)`
- Dividend waterfall: fall-through on `is None`, NOT falsy
- Wikipedia table: `attrs={"id": "constituents"}` not positional `[0]`
- Mock yfinance/FRED/CBOE in tests — no live API calls in unit tests

## Estimated Tests: ~100
