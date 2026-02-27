---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-27T11:40:38Z
version: 2.0.0
author: Claude Code PM System
---

# Project Brief

## What It Is

**Option Alpha** is an AI-powered options analysis tool that uses a multi-agent debate system to evaluate options contracts. Three AI agents (Bull, Bear, Risk) debate via locally-hosted Ollama models (Llama 3.1 8B), producing a structured verdict with risk assessment.

## Why It Exists

- Provides data-driven options analysis without relying on cloud AI services or paid APIs
- Combines quantitative technical indicators with qualitative AI reasoning
- Runs entirely locally for privacy and cost control
- Educational/research tool — NOT investment advice

## Project Goals

1. **Phase 1 MVP**: Complete CLI-based scan-and-debate pipeline
2. Fetch market data, compute 18 technical indicators, score tickers
3. Run structured single-pass AI debate (Bull -> Bear -> Risk) on selected tickers
4. Persist results in SQLite for historical analysis
5. Generate terminal and markdown reports with mandatory disclaimers

## Success Criteria

- Full universe scan (500 tickers) completes in < 5 minutes
- Zero race conditions, connection leaks, or sync-on-async violations
- `mypy --strict`, `ruff check .`, and all tests pass
- Data-driven fallback produces valid verdict when Ollama is down
- Test count >= 1,000 with >= 80% coverage

## Scope Boundaries

- **In scope (v1.2.0 — Complete)**: CLI tool, yfinance data, BAW/BSM pricing, SQLite persistence, 18 technical indicators, Rich terminal output, scan pipeline, health checks, universe management, AI debate system (Bull/Bear/Risk via PydanticAI + Ollama or Groq cloud)
- **Deferred to v2**: Multi-round debate, web UI, reporting module, additional LLM providers (Anthropic, OpenAI)
- **Out of scope**: Real-time streaming, portfolio management, trade execution

## Repository

- **GitHub**: jobu711/options_arena
- **Branch**: `master` (all 9 phases merged, 1,262 tests, 70 issues closed)
- **Package**: `options_arena` (PEP 8 compliant). PRD: `.claude/prds/options-arena.md`
