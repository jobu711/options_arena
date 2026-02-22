---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-19T16:03:12Z
version: 1.2
author: Claude Code PM System
---

# Project Vision

## Long-Term Direction

Option Alpha aims to be a comprehensive, locally-run options analysis platform that combines quantitative analysis with AI-driven qualitative reasoning. The system is designed in phases to incrementally add capability.

## Phase Roadmap

### Phase 1 — Core Engine (Complete)
- CLI-based scan-and-debate pipeline
- Ollama-only AI backend (Llama 3.1 8B)
- 18 technical indicators in pure pandas/numpy
- SQLite persistence with repository pattern
- yfinance for market data
- Terminal and markdown reporting

### Phase 2 — Web UI (Complete, Pending Merge)
- Dark-mode server-rendered web interface (Jinja2 + HTMX + Alpine.js)
- FastAPI backend with SSE scan progress streaming
- No Node.js/npm — vendored static JS (HTMX 2.0.4, Alpine.js 3.14.8, Lightweight Charts 4.2.1)
- 7 pages: Dashboard, Scanner, Debate, Universe, Watchlists, Health, Settings
- TradingView Lightweight Charts for candlestick + volume visualization
- HTMX partial page swaps for SPA-like navigation

### Phase 3 — Enhanced AI & Advanced Features (Future)
- Additional LLM provider support (Anthropic Claude, OpenAI)
- Multi-round debate capability
- Real-time market data streaming
- Portfolio integration and position tracking
- Options strategy builder with risk visualization
- Backtesting against historical data

## Strategic Priorities

1. **Local-first**: All core functionality runs without cloud dependencies
2. **Data integrity**: Mathematically correct indicators, proper financial precision
3. **Modularity**: Clean boundaries enable swapping components (different LLMs, data sources)
4. **Transparency**: AI reasoning is visible and auditable through debate transcripts
5. **Safety**: Mandatory disclaimers, no trade execution, educational purpose only

## Guiding Principles

- Correctness over speed — wrong financial math is dangerous
- Typed boundaries over convenience — Pydantic models at every module seam
- Graceful degradation — system works (with reduced capability) when external services are down
- No magic numbers — every constant named and documented
