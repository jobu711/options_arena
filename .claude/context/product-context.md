---
created: 2026-02-17T08:51:05Z
last_updated: 2026-03-03T14:34:21Z
version: 6.2
author: Claude Code PM System
---

# Product Context

## Target Users

- **Options traders** seeking AI-assisted contract analysis on U.S. equities
- **Technical analysts** who want automated multi-indicator screening across thousands of tickers
- **Self-directed investors** who prefer a local, privacy-first tool over cloud-based paid platforms
- **Researchers** exploring multi-agent AI debate systems for financial analysis

## Data Sources

| Source | Data | Required? |
|--------|------|-----------|
| Yahoo Finance (yfinance) | OHLCV, quotes, ticker info, option chains (fallback), dividends | Yes |
| FRED (St. Louis Fed) | 10-year Treasury rate (risk-free rate) | No (5% fallback) |
| CBOE | Optionable ticker universe + option chains (primary provider via OpenBB) | No (24h cached list / yfinance fallback) |
| Wikipedia | S&P 500 constituents + GICS sectors | No (24h cached list) |
| Groq Cloud API | LLM debate agents (Llama 3.3 70B) | No (data-driven fallback) |
| OpenBB SDK | Fundamentals, unusual flow, news sentiment | No (optional enrichment) |

## Core Capabilities

### 1. Universe Scanning (4-phase async pipeline)
- **Phase 1**: Build universe from CBOE/S&P 500/ETFs, filter by sector, fetch 1y OHLCV
- **Phase 2**: Compute 14 OHLCV-based indicators, normalize to percentile ranks (0-100), composite score, direction (bullish/bearish/neutral)
- **Phase 3**: Liquidity pre-filter, top-N by score, fetch option chains, compute Greeks (BSM/BAW locally), recommend contracts, 4 options-specific indicators (IV rank, IV percentile, put/call ratio, max pain distance)
- **Phase 4**: Persist scan run + ticker scores + contracts to SQLite
- **DSE mode**: 40 indicators across 8 dimensions with regime-adjusted weights
- **Presets**: `full` (~5,286), `sp500` (~500), `etfs` (60+ curated)
- **Sector filtering**: 11 GICS sectors with 30+ case-insensitive aliases

### 2. AI Debate Analysis
- **Standard mode**: Bull → Bear → Risk (3 agents)
- **With options**: +Rebuttal (bull counter), +Volatility agent (IV assessment) — run in parallel
- **DSE mode**: Trend, Volatility, Flow, Fundamental → Risk → Contrarian (6 agents)
- **Market context**: Flat `MarketContext` injected into prompts — price, indicators, Greeks, sector, earnings, OpenBB enrichment fields
- **Output**: `TradeThesis` with direction, confidence, summary, scores, risk assessment, recommended strategy
- **Fallback**: On any Groq error → data-driven verdict (`confidence=0.3`, `is_fallback=True`)
- **Batch**: Debate top-N tickers from latest scan sequentially with per-ticker error isolation

### 3. OpenBB Enrichment (Optional)
- Fundamentals: P/E, forward P/E, PEG, price-to-book, debt-to-equity, revenue growth, profit margin
- Unusual flow: net call/put premium, options-specific put/call ratio
- News sentiment: VADER-scored headlines, aggregate sentiment label (bullish/bearish/neutral)
- Guarded imports — system works identically without OpenBB SDK installed
- Enrichment data injected into agent prompt sections for more informed debate

### 4. Options Pricing & Greeks
- **BSM** (Black-Scholes-Merton) for European-style; **BAW** (Barone-Adesi-Whaley) for American-style
- Automatic dispatch by `ExerciseStyle` enum (all U.S. equity = American = BAW)
- Greeks: delta, gamma, theta, vega, rho — all computed locally (yfinance provides no Greeks)
- IV solver: Newton-Raphson on BSM, seeded from yfinance `impliedVolatility`
- Contract filtering: DTE 30-60d, delta 0.20-0.50, OI >= 100, spread <= 10%

### 5. Persistence & History
- SQLite (WAL mode) with sequential migrations (13 migrations)
- Scan runs, ticker scores, recommended contracts (with entry prices), AI debate theses, watchlist
- Contract outcome tracking: P&L at T+1/T+5/T+10/T+20 holding periods
- Score history + trending tickers (consecutive scans, score changes)
- Scan deltas: movers up/down, new entries, dropped tickers
- Normalization metadata: per-indicator distribution stats per scan

### 6. Reporting & Export
- Rich terminal: colored tables, progress bars, styled agent panels
- Markdown export for debate results
- PDF export via optional `weasyprint` dependency
- Greeks table with dollar-impact, indicator summary by category
- Mandatory disclaimer on all user-facing output

## CLI Commands

| Command | Key Flags | Purpose |
|---------|-----------|---------|
| `scan` | `--preset {full,sp500,etfs}`, `--sector S` (repeatable), `--top-n`, `--min-score` | Run scan pipeline |
| `debate TICKER` | `--batch`, `--batch-limit`, `--export {md,pdf}`, `--fallback-only`, `--history` | AI debate (single or batch) |
| `health` | — | Check all external service connectivity + latency |
| `universe refresh\|list\|stats\|sectors` | `--sector`, `--preset` | Manage ticker universe |
| `watchlist add\|remove\|list` | `--notes` | Personal ticker watchlist |
| `outcomes collect\|summary` | `--holding-days`, `--lookback-days` | Contract outcome tracking + analytics |
| `serve` | `--host`, `--port`, `--verbose` | Launch FastAPI + Vue 3 SPA (loopback-only) |

## Web UI Pages

| Route | Purpose |
|-------|---------|
| `/` | Dashboard: latest scan summary, health strip, quick actions |
| `/scan` | Launch scans, view past scans with pagination |
| `/scan/:id` | Sortable/filterable DataTable: scores, direction, indicators, contracts, delta badges |
| `/debate/:id` | Full debate render: agent panels, thesis, export buttons |
| `/universe` | Stats + scrollable ticker list with sector/market cap |
| `/health` | Service status cards with latency |
| `/watchlist` | Add/remove tickers, view scores and debate history |

## REST API

- **Scan**: `POST /api/scan` (start), `GET /api/scan` (list), `GET /api/scan/{id}/scores` (results), `GET /api/scan/{id}/diff` (delta)
- **Debate**: `POST /api/debate` (single), `POST /api/debate/batch` (batch), `GET /api/debate/{id}` (result), `POST /api/debate/{id}/export`
- **Universe**: `GET /api/universe/stats`, `GET /api/universe/tickers`, `POST /api/universe/refresh`
- **Health**: `GET /api/health`
- **Watchlist**: `GET/POST/DELETE /api/watchlist`
- **Analytics**: `GET /api/analytics/{win-rate,score-calibration,holding-period,delta-performance,summary,indicator-attribution/{name}}`, `POST /api/analytics/collect-outcomes`, `GET /api/analytics/{scan,ticker}/*/contracts`
- **WebSocket**: `WS /ws/scan/{id}` (4-phase progress), `WS /ws/debate/{id}` (agent steps)
- **Operation mutex**: one scan or batch debate at a time (409 if busy)

## Constraints

- **NOT investment advice** — educational/research tool; mandatory disclaimer on all output
- **No trade execution** — analysis only, no broker integration
- **No real-time streaming** — batch analysis; quotes cached 1m (market hours) / 5m (after hours)
- **Groq-only LLM** — no provider abstraction; `GROQ_API_KEY` required for AI features
- **200+ bars required** — tickers with < 200 trading days of OHLCV are excluded from scanning
- **American options only** — all U.S. equity options use BAW pricing; European (SPX) would use BSM
- **Loopback-only web server** — `serve` rejects non-loopback hosts for security
