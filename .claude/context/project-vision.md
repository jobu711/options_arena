---
created: 2026-02-17T08:51:05Z
last_updated: 2026-03-03T14:34:21Z
version: 4.1
author: Claude Code PM System
---

# Project Vision

## Long-Term Direction

Options Arena is a comprehensive options analysis platform that combines quantitative analysis with AI-driven qualitative reasoning via multi-agent debate. The system was built in phases and is now feature-complete at v2.4.0.

## Completed Phases

### Phases 1–9: Core Engine (Complete — 2026-02-24)
- From-scratch rewrite as `options_arena` (PEP 8 compliant)
- BAW + BSM pricing, 18 technical indicators, scoring, scan pipeline
- Services: yfinance, FRED, CBOE, Wikipedia, health, cache, rate limiting
- SQLite persistence, CLI (Typer + Rich), AI debate (PydanticAI + Groq)
- Data-driven fallback when Groq unreachable

### v2.0.0 Epics (Complete — 2026-02-28)
- **Groq migration**: Ollama removed, Groq cloud-only (llama-3.3-70b-versatile)
- **Debate enhancements**: Bull rebuttal, volatility agent, batch debate, export (md/pdf)
- **Web UI**: FastAPI REST + WebSocket backend, Vue 3 SPA (PrimeVue Aura dark)
- **Watchlist**: SQLite-backed CRUD, CLI + API + frontend
- **Score history/trending**: Historical score charts, trending tickers
- **Scan delta**: Compare successive scans, show movers
- **Earnings calendar**: yfinance earnings dates, 7-day debate warnings

### v2.1.0: Deep Signal Engine (Complete — 2026-03-01)
- 40 DSE indicators across 8 analytical dimensions
- 6-agent parallel debate protocol (trend, volatility, flow, fundamental → risk → contrarian)
- Multi-dimensional scoring with regime-adjusted weights
- Extended Greeks (charm, vanna, vomma, speed), IV surface utilities
- CI workflow (GitHub Actions), +576 tests
- **Total**: 2,328 tests, 158 GitHub issues closed

### v2.2.0: OpenBB Integration + Chain Migration (Complete — 2026-03-02)
- OpenBB enrichment: fundamentals, unusual flow, news sentiment (guarded imports, config-gated)
- `ChainProvider` protocol: CBOE via OpenBB (primary) + yfinance (fallback)
- Three-tier Greeks: CBOE native → local BAW/BSM → exclude
- Provider orchestration with timeout + broad exception fallback
- DI wiring at 5 call sites, CBOE health check, validation mode
- **Total**: 2,917 tests, 169 GitHub issues closed, 15 epics complete

### v2.3.0: Market Recon (Complete — 2026-03-03)
- IntelligenceService: multi-source market intelligence aggregation
- DSE wiring: intelligence data injected into debate agent prompts
- **Total**: 3,238 tests, 173 GitHub issues closed, 16 epics complete

### v2.4.0: Analytics Persistence (Complete — 2026-03-03)
- Contract persistence: scan recommendations saved with entry prices and Greeks
- Outcome tracking: P&L computation at T+1/T+5/T+10/T+20 holding periods
- 6 analytics queries: win rate, score calibration, indicator attribution, holding period, delta performance, summary
- 9 API endpoints on `/api/analytics`, CLI `outcomes collect|summary`
- **Total**: 3,376 tests, 176 GitHub issues closed, 17 epics complete

### Future
- Additional LLM providers (Anthropic Claude, OpenAI)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils)
- Options liquidity weighting in composite scoring

## Strategic Priorities

1. **Data integrity**: Mathematically correct indicators, proper financial precision
2. **Modularity**: Clean boundaries enable swapping components (different LLMs, data sources)
3. **Transparency**: AI reasoning is visible and auditable through debate transcripts
4. **Safety**: Mandatory disclaimers, no trade execution, educational purpose only
5. **Accessibility**: Both CLI and web UI for different user preferences

## Guiding Principles

- Correctness over speed — wrong financial math is dangerous
- Typed boundaries over convenience — Pydantic models at every module seam
- Graceful degradation — system works (with reduced capability) when external services are down
- No magic numbers — every constant named and documented
