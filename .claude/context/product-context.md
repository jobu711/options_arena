---
created: 2026-02-17T08:51:05Z
last_updated: 2026-03-01T09:14:06Z
version: 5.0
author: Claude Code PM System
---

# Product Context

## Target Users

- **Options traders** who want AI-assisted analysis of options contracts
- **Technical analysts** looking for automated indicator computation across many tickers
- **Developers/researchers** interested in multi-agent AI debate systems
- **Self-directed investors** who prefer local tools over cloud-based paid services

## Core Functionality

### 1. Universe Scanning
- Scan up to 500 optionable tickers from the CBOE universe
- Compute 18+ technical indicators per ticker (40 DSE indicators across 8 dimensions in v2.1.0)
- Score and rank tickers using percentile normalization and weighted geometric mean
- Multi-dimensional scoring with regime-adjusted weights (DSE)
- Filter by configurable thresholds (composite score >= 50)

### 2. AI Debate Analysis
- **Standard mode**: Three-agent single-pass debate: Bull -> Bear -> Risk
- **DSE mode**: 6-agent parallel protocol: Trend, Volatility, Flow, Fundamental -> Risk -> Contrarian
- Each agent receives flat `MarketContext` with current market data
- Agents must cite specific contracts, strikes, Greeks, and indicators
- Risk agent synthesizes all cases into a final verdict
- Optional bull rebuttal phase
- **Provider**: Groq cloud API (llama-3.3-70b-versatile)
- Data-driven fallback when LLM provider is unreachable

### 3. Options Chain Analysis
- Fetch and display options chains with bid/ask spreads
- Greeks computation (delta, gamma, theta, vega, rho)
- Contract filtering: OI >= 100, spread <= 30%, delta 0.30-0.40
- Mid-price calculation as fair value estimate

### 4. Persistence & History
- SQLite storage for scan runs, ticker scores, AI debate theses
- Watchlist management (CRUD)
- Historical debate lookup per ticker

### 5. Reporting
- Rich terminal output (colored, compact)
- Markdown report generation
- Mandatory disclaimer on all user-facing output
- Greeks table with dollar-impact, indicator summary by category

## User Workflows (v2.1.0)

1. **Scan**: `options-arena scan --preset sp500` — scans universe, computes indicators, scores tickers, recommends contracts
2. **Debate**: `options-arena debate AAPL` — runs AI debate on a ticker, renders Rich panels
3. **Batch Debate**: `options-arena debate --batch` — debates top N tickers from latest scan
4. **Debate Export**: `options-arena debate AAPL --export md` — export as markdown or PDF
5. **Debate History**: `options-arena debate AAPL --history` — view past debates for a ticker
6. **Debate Fallback**: `options-arena debate AAPL --fallback-only` — data-driven analysis without Groq
7. **Health**: `options-arena health` — checks yfinance, FRED, Groq, CBOE connectivity
8. **Universe**: `options-arena universe refresh|list|stats` — manage ticker universe
9. **Watchlist**: `options-arena watchlist add|remove|list` — manage personal watchlist
10. **Web UI**: `options-arena serve` — launch browser-based SPA at `http://127.0.0.1:8000`

## Important Constraints

- **NOT investment advice** — educational/research tool only
- Every output includes a mandatory disclaimer
- No trade execution capability
- No real-time streaming (batch analysis only)
- Groq API key required for AI features (`GROQ_API_KEY` or `ARENA_DEBATE__API_KEY`); graceful data-driven fallback otherwise
