# Progress

## Current State

- **Version**: 2.11.0 — S&P 500 Heatmap (squarify treemap on dashboard)
- **All 9 phases + 24 epics**: Complete and merged to master
- **Tests**: ~3,949 Python + 73 E2E
- **GitHub issues**: 0 open, 370+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## In Progress

- Uncommitted changes across orchestrator, scoring, services, tests — likely follow-up refinements

## Recently Completed

- **S&P 500 Heatmap epic** (2026-03-08): Issues #366-#372. BatchQuote model, `fetch_batch_daily_changes()`, `GET /api/market/heatmap`, `MarketHeatmap.vue` squarify treemap, Pinia heatmap store, chunked batch download, E2E tests.
- **Algo Audit epic** (2026-03-08): PR #364, issues #354-#363. 13 algorithmic correctness fixes: isfinite guards, citation matching, NEUTRAL exclusion from agreement, retry jitter, composite floor, expired P&L with historical close, single-ticker normalization, rate-limiter slot starvation fix, ETF 404 retry waste elimination.
- **Debate Calibration epic** (2026-03-08): PR #353, issues #345-#351. Domain context partitioning, Bordley 1982 log-odds pooling, ensemble diversity metrics, agent prediction persistence (migration 025).

## Future Work

- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
