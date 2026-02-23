---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-22T23:58:54Z
version: 1.3
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

### Options Arena Rewrite — Phase 1: Bootstrap & Models (Complete)
- From-scratch rewrite as `options_arena` (PEP 8 compliant)
- 11 enums, 14 Pydantic models, exception hierarchy, AppSettings config
- 220 tests passing, strict UTC enforcement, StrEnum for all categorical fields
- PR #12 merged to master (2026-02-22)

### Options Arena — Phase 2: Pricing Engine (Next)
- BAW (Barone-Adesi-Whaley) for American options pricing
- BSM for European options pricing
- IV solvers: Newton-Raphson (BSM), brentq (BAW)
- Finite-difference Greeks computation

### Web UI (Rolled Back — Deferred to v2)
- Two attempts removed (React SPA, then Jinja2+HTMX) on 2026-02-19
- Will revisit after core pricing + scan pipeline are complete

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
