---
created: 2026-02-17T08:51:05Z
last_updated: 2026-03-01T09:14:06Z
version: 3.0
author: Claude Code PM System
---

# Project Brief

## What It Is

**Options Arena** is an AI-powered options analysis tool that uses a multi-agent debate system to evaluate options contracts. AI agents debate via Groq cloud API (Llama 3.3 70B), producing a structured verdict with risk assessment. Includes CLI, web UI, and deep signal analysis.

## Why It Exists

- Provides data-driven options analysis with AI-powered reasoning
- Combines quantitative technical indicators with qualitative AI debate
- Multiple analysis modes: standard 3-agent and deep 6-agent protocols
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

- **In scope (v2.1.0 — Complete)**: CLI + Web UI, yfinance data, BAW/BSM pricing, SQLite persistence, 40+ indicators (18 core + DSE), Rich terminal output, scan pipeline, health checks, universe management, AI debate (standard + DSE 6-agent), rebuttal, batch debate, markdown/PDF export, watchlists, score history/trending, CI/CD
- **Future**: Additional LLM providers (Anthropic Claude, OpenAI), real-time streaming, frontend unit tests
- **Out of scope**: Portfolio management, trade execution

## Repository

- **GitHub**: jobu711/options_arena
- **Branch**: `master` (all phases + 12 epics merged, 2,328 tests, 158 issues closed)
- **Package**: `options_arena` (PEP 8 compliant). PRD: `.claude/prds/options-arena.md`
