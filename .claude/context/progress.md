# Progress

## Current State

- **Version**: 3.0.0 — hedge-fund-frontend complete (2026-03-24)
- **All 9 phases + 43 epics + 4 cleanup epics**: Complete and merged to master
- **Tests**: ~370 files, 16.6K+ passing (27K parametrized + 107 E2E + 89 frontend)
- **CI**: GitHub Actions (lint, typecheck, tests, frontend)
- **Stack**: Typer CLI + FastAPI/Vue 3 SPA + SQLite (WAL) + Groq/Anthropic AI
- **Recommendation system**: 6 desk agents -> synthesis -> `PositionRecommendation` (sole analysis path)
- **Frontend**: Single-screen trading desk with masonry grid, real-time WS pipeline, 12 new components
- **AI Agency**: 7 desk agents with tool-use, intent routing, learning/weight tuning, strategy mining, confidence decay
- **Model routing**: Complexity-based per-desk tier selection (FAST/STANDARD/PREMIUM)
- **GitHub issues**: 805+ closed

## Recently Completed

- **hedge-fund-frontend** (2026-03-24): Gut rebuild of Vue 3 frontend as single-screen AI trading desk
  - 12 new components, 1 Pinia state machine store, 1 type module
  - Router collapsed 8→3 routes, 39 old files deleted (-9,018 lines)
  - 3 WebSocket connections (scan, debate, batch) with completion poll safety nets
  - Masonry CSS Grid layout with collapsible DeskCard panels
  - 89 frontend test cases (Vitest + Vue Test Utils)
  - Live testing fixes: scan ID mismatch (counter vs DB), phase revert bug, page_size cap, debate poll
  - CodeRabbit review: 5 fixes applied (race condition, state mutation, UX, test casing)
  - Verification: 31/31 requirements PASS

- **dead-code-cleanup** (2026-03-23): 4 parallel epics via git worktrees, ~4,300 lines identified, net -1,548 lines after merge

## In Progress

- None currently — all epics complete

## Blockers

- **Groq API**: 403 forbidden (key may need refresh). Anthropic works as fallback (`ARENA_DEBATE__PROVIDER=anthropic`).
