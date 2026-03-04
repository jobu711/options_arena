# Progress

## Current State

- **Version**: 2.6.0 — Scan from Watchlist (custom tickers through full stack) complete
- **All 9 phases + 19 epics**: Complete and merged to master
- **Tests**: 3,754 Python + 38 E2E
- **GitHub issues**: 13 open, 243+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe`, `debate` (+ `--batch`, `--export`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## In Progress

### Epic 20: Surface V2 Agent Outputs — #248-#256
Extend DebateResult to surface structured v2 agent fields (4 agent theses, risk assessment).
- #249: DebateResult model extension + migration
- #250: Repository layer — persist and load v2 agent outputs
- #251: Orchestrator wiring — populate and persist v2 fields
- #252-#254: API + CLI + frontend rendering
- #255-#256: Frontend cards + export renderers

## Recently Completed

- **Epic 19** (2026-03-04): Scan from Watchlist — custom tickers through full stack, +130 tests. PR #247.
- **Epic 18** (2026-03-03): Scan Filtering — dimensional scores, API filtering, pre-scan narrowing, +110 tests. PR #227.

## Future Work

- Surface v2 agent outputs (in progress — epic 20)
- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
