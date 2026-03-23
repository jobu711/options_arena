# Product Context

## Target Users

Options traders, technical analysts, and self-directed investors seeking AI-assisted
options analysis on U.S. equities. Also researchers exploring multi-agent AI systems.

## Core Capabilities

- **Universe Scanning**: 4-phase async pipeline -- build universe (CBOE/S&P 500/ETFs), compute 27 indicators with percentile normalization, fetch option chains + compute Greeks (BSM/BAW), persist to SQLite. Presets: full (~5,286), sp500 (~500), etfs (60+). Sector filtering via 11 GICS sectors.
- **AI Recommendation**: 6 desk recommendation agents (Trend, Volatility, Flow, Fundamental, Risk, Contrarian) + synthesis agent produce `PositionRecommendation`. Groq (Llama 3.3 70B) or Anthropic. Data-driven fallback on LLM failure.
- **AI Agency**: 7 interactive desk agents with tool-use, intent routing, and query persistence. Natural language queries dispatched to domain-specific desks.
- **Options Pricing**: BSM (European) + BAW (American) via `pricing/dispatch.py`. All Greeks computed locally (yfinance provides none). IV solver seeded from yfinance `impliedVolatility`.
- **Persistence & History**: SQLite (WAL, 40 migrations). Scan runs, ticker scores, contracts with entry prices, recommendations, outcome tracking (P&L at T+1/T+5/T+10/T+20), score history, scan deltas.
- **Learning**: Indicator weight tuning (P&L correlation), vote weight tuning (agent accuracy), strategy mining with playbook and confidence decay.
- **Reporting**: Rich terminal tables, markdown/PDF export, Greeks tables with dollar-impact.
- **OpenBB Enrichment** (optional): Fundamentals, unusual flow, news sentiment. Guarded imports -- works without SDK.

## CLI Commands

| Command | Purpose |
|---------|---------|
| `scan` | Run scan pipeline (presets, sector filter, top-n, min-score) |
| `debate TICKER` | AI recommendation (single, batch, export md/pdf, cost-summary) |
| `health` | Check all external service connectivity + latency |
| `universe` | Manage ticker universe (refresh, list, stats, sectors, index) |
| `watchlist` | Personal ticker watchlist (add, remove, list) |
| `outcomes` | Contract outcome tracking (collect, summary, backtest, equity-curve) |
| `agency` | Interactive AI desk queries (ask, chat) |
| `learn` | Weight tuning (tune-indicators, tune-votes, status, mine, playbook, decay) |
| `serve` | Launch FastAPI + Vue 3 SPA (loopback-only) |
| `audit` | Code audit tools |

## REST API Surface

- **Scan**: CRUD + start + diff (delta badges)
- **Debate**: Single + batch + result + export
- **Universe**: Stats, tickers, refresh, metadata
- **Health**: Service status + latency
- **Watchlist**: CRUD
- **Analytics**: Win-rate, calibration, holding-period, delta-performance, backtest (equity curve, drawdown, sector, DTE, IV)
- **Agency**: Ask (single query), chat (conversation)
- **Config**: Routing config, model tiers
- *Removed*: 14 dead API endpoints (indicator-attribution, risk-metrics, correlation, recommendation-costs, all learning/*, all eval/*, 3 universe admin endpoints) — CLI equivalents retained
- **WebSocket**: `WS /ws/scan/{id}` (4-phase progress), `WS /ws/debate/{id}` (agent steps)
- **Operation mutex**: One scan or batch at a time (409 if busy)

## Web UI

Vue 3 SPA (TypeScript, Pinia, PrimeVue Aura dark theme). Pages: Dashboard, Scan (list + detail), Debate result, Universe, Health, Watchlist, Analytics (5 tabs), Desks, Agency Chat. Vite dev mode (:5173) proxies to FastAPI (:8000). Production: FastAPI serves `web/dist/`.

## Constraints

- NOT investment advice -- educational/research tool; mandatory disclaimer on all output
- No trade execution -- analysis only, no broker integration
- No real-time streaming -- batch analysis; quotes cached 1m (market hours) / 5m (after hours)
- 200+ bars required -- tickers with < 200 trading days excluded from scanning
- American options only -- all U.S. equity options use BAW; European (SPX) would use BSM
- Loopback-only web server -- `serve` rejects non-loopback hosts for security
