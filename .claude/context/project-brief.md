---
created: 2026-02-17T08:51:05Z
last_updated: 2026-02-22T23:58:54Z
version: 1.4
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

- **In scope (Phase 1 — Complete)**: CLI tool, yfinance data, Ollama-only AI, SQLite persistence, technical indicators, rich terminal output
- **In scope (Phase 2 — Rolled back)**: Web UI attempts removed (2026-02-19). Deferred to v2.
- **Out of scope**: Cloud AI providers, real-time streaming, portfolio management, trade execution

## Repository

- **GitHub**: jobu711/options_arena
- **Branch**: `master` (Phase 1 Bootstrap & Models merged via PR #12)
- **Rewrite**: Renamed from `Option_Alpha` to `options_arena` (PEP 8 compliant). PRD: `.claude/prds/options-arena.md`
