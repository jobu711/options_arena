# Progress

## Current State

- **Version**: 2.10.0 — Debate Calibration (domain context, log-odds pooling, ensemble diversity)
- **All 9 phases + 22 epics**: Complete and merged to master
- **Tests**: ~3,960 Python + 38 E2E
- **GitHub issues**: 9 open (algo-audit epic), 290+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## In Progress

- **Algo Audit epic** (planning): `.claude/epics/algo-audit/` — Issues #354-#363. Fixes 13 algorithmic correctness findings (isfinite guards, citation matching, NEUTRAL exclusion, retry jitter, etc.).

## Recently Completed

- **Debate Calibration epic** (2026-03-08): PR #353, issues #345-#351. Domain context partitioning (agents see only their domain data), Bordley 1982 log-odds pooling, ensemble diversity metrics (entropy, vol direction, agreement score), agent prediction persistence (migration 025), v2 prediction extraction fix.
- **Collect Outcomes epic** (2026-03-07): PR #352. Auto-collect outcomes after scan, outcome collection improvements.
- **Data Completeness epic** (2026-03-07): Issues #319-#322. Short interest e2e, active-contract P&L, indicator signal labels, MACD integration.

## Future Work

- Algo audit: 8 algorithmic correctness fixes (#356-#363)
- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
