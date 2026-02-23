---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-22T20:16:37Z
version: 3.2
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

## User Workflows (Phase 1)

1. **Scan**: `option-alpha scan` — scans universe, computes indicators, scores tickers
2. **Debate**: `option-alpha debate AAPL` — runs AI debate on a ticker
3. **History**: `option-alpha debate history AAPL` — shows past debates
4. **Report**: `option-alpha report` — generates markdown report
5. **Health**: `option-alpha health` — checks Ollama, yfinance connectivity
6. **Universe**: `option-alpha universe refresh/list/stats` — manage ticker universe
7. **Watchlist**: `option-alpha watchlist add/remove/list` — manage watchlists

## Options Arena Rewrite (In Progress)

The project is being rewritten from `Option_Alpha` to `options_arena` (PEP 8 compliant). Key product changes:
- **American options pricing** via BAW replaces incorrect European-only BSM (Phase 2 — Complete)
- **MVP scope narrowed** to pricing + scan pipeline only — AI debate, reporting, and web UI deferred to v2
- **Package renamed** from `Option_Alpha` to `options_arena`
- PRD: `.claude/prds/options-arena.md`
- Phase 1 (Models) and Phase 2 (Pricing) both complete and merged to master

## Important Constraints

- **NOT investment advice** — educational/research tool only
- Every output includes a mandatory disclaimer
- No trade execution capability
- No real-time streaming (batch analysis only in Phase 1)
- Ollama must be running locally for AI features (graceful degradation otherwise)
