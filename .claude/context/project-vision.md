---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-24T16:42:16Z
version: 2.1
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

### Options Arena — Phases 2–8 (All Complete — 2026-02-23)
- **Phase 2**: BAW + BSM pricing engine, IV solvers, Greeks, dispatch (214 tests)
- **Phase 3**: 18 technical indicators across 6 modules (172 tests)
- **Phase 4**: Scoring — normalization, composite, direction, contract selection (102 tests)
- **Phase 5**: Services — yfinance, FRED, CBOE, Wikipedia, health, cache, rate limiting (163 tests)
- **Phase 6**: Data layer — SQLite persistence, migrations, repository pattern (34 tests)
- **Phase 7**: Scan pipeline — 4-phase async orchestration with cancellation (156 tests)
- **Phase 8**: CLI — Typer commands, Rich rendering, logging, SIGINT handler (25 tests)
- **Total**: 1,086 tests, 51 source files, 54 GitHub issues closed

### Phase 9: AI Debate System (Complete — 2026-02-24)
- Three PydanticAI agents (Bull, Bear, Risk) with Ollama (Llama 3.1 8B)
- Single-pass debate: Bull argues → Bear counters → Risk adjudicates into TradeThesis
- Data-driven fallback when Ollama unreachable (confidence=0.3)
- Rich panel rendering, debate history, `--fallback-only` mode
- 126 new tests (agents, orchestrator, parsing, config, repository, e2e)
- **Total**: 1,212 tests, 58 source files, 67 GitHub issues closed

### v2 — Enhanced AI & Advanced Features (Future)
- Additional LLM provider support (Anthropic Claude, OpenAI)
- Multi-round debate with rebuttal phases
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
