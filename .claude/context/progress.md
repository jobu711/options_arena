# Progress

## Current State

- **Version**: 3.0.0 — dead-code-cleanup complete (2026-03-23)
- **All 9 phases + 42 epics + 4 cleanup epics**: Complete and merged to master
- **Tests**: ~350 files, 16.6K+ passing (27K parametrized + 107 E2E)
- **CI**: GitHub Actions (lint, typecheck, tests, frontend)
- **Stack**: Typer CLI + FastAPI/Vue 3 SPA + SQLite (WAL) + Groq/Anthropic AI
- **Recommendation system**: 6 desk agents -> synthesis -> `PositionRecommendation` (sole analysis path)
- **AI Agency**: 7 desk agents with tool-use, intent routing, learning/weight tuning, strategy mining, confidence decay
- **Model routing**: Complexity-based per-desk tier selection (FAST/STANDARD/PREMIUM)
- **GitHub issues**: 695+ closed

## Recently Completed

- **dead-code-cleanup** (2026-03-23): 4 parallel epics via git worktrees, ~4,300 lines identified, net -1,548 lines after merge
  - **quickwins**: Deleted dead functions (should_debate, constraints.py, 6 indicator functions, MacroSignals, AgentMemory, etc.), removed 4 IndicatorSignals fields, cleaned web types
  - **refactor**: Deleted 490 lines debate rendering, 420 lines context renderers, extracted FiniteFieldsMixin, _check_api_provider, cache serialization helpers
  - **orphans**: Removed IntelligenceService (~997 lines), eval harness (~1,024 lines), 14 dead API endpoints (~330 lines)
  - **sunset**: Refactored process_ticker_options from 353-line monolith to ~50-line coordinator + 4 extracted helpers

## In Progress

- **AI Agency Evolution**: 2 remaining epics: `ai-agency-analysis-tools`, `ai-agency-ml-tools`

## Blockers

- None currently known.
