---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-24T16:42:16Z
version: 4.1
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
- Compute 18 technical indicators per ticker
- Score and rank tickers using percentile normalization and weighted geometric mean
- Filter by configurable thresholds (composite score >= 50)

### 2. AI Debate Analysis
- Three-agent single-pass debate: Bull -> Bear -> Risk
- Each agent receives flat `MarketContext` with current market data
- Agents must cite specific contracts, strikes, Greeks, and indicators
- Risk agent synthesizes bull/bear cases into a final verdict
- Data-driven fallback when Ollama is unreachable

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

## User Workflows (v1.1.0)

1. **Scan**: `options-arena scan --preset sp500` — scans universe, computes indicators, scores tickers, recommends contracts
2. **Debate**: `options-arena debate AAPL` — runs Bull/Bear/Risk AI debate on a ticker, renders Rich panels
3. **Debate History**: `options-arena debate AAPL --history` — view past debates for a ticker
4. **Debate Fallback**: `options-arena debate AAPL --fallback-only` — data-driven analysis without Ollama
5. **Health**: `options-arena health` — checks yfinance, FRED, Ollama, CBOE connectivity
6. **Universe Refresh**: `options-arena universe refresh` — re-fetch CBOE + S&P 500 tickers
7. **Universe List**: `options-arena universe list --sector "Information Technology"` — list tickers by sector
8. **Universe Stats**: `options-arena universe stats` — sector breakdown and counts

### Deferred to v2
- **Multi-round debate**: Rebuttal phases between agents
- **Reporting**: Markdown/PDF report generation
- **Watchlists**: CRUD watchlist management
- **Web UI**: Browser-based interface
- **Additional LLM providers**: Anthropic Claude, OpenAI

## Options Arena Rewrite (Complete — v1.1.0)

Rewritten from `Option_Alpha` to `options_arena` (PEP 8 compliant). All 9 phases complete:
- **American options pricing** via BAW replaces incorrect European-only BSM
- **Full scan pipeline**: universe → indicators → scoring → options → persist → CLI output
- **AI debate system**: Bull/Bear/Risk agents via PydanticAI + Ollama with data-driven fallback
- **1,212 tests**, `mypy --strict`, `ruff check` all green
- PRDs: `.claude/prds/options-arena.md`, `.claude/prds/ai-debate.md`

## Important Constraints

- **NOT investment advice** — educational/research tool only
- Every output includes a mandatory disclaimer
- No trade execution capability
- No real-time streaming (batch analysis only in Phase 1)
- Ollama must be running locally for AI features (graceful degradation otherwise)
