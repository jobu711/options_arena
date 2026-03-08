# Progress

## Current State

- **Version**: 2.12.0 — Multi-provider LLM support (Groq + Anthropic)
- **All 9 phases + 25 epics**: Complete and merged to master
- **Tests**: ~4,185 Python + 73 E2E
- **GitHub issues**: 0 open, 375+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)

## In Progress

- **Liquidity weighting epic** near complete (12/13 tasks, ~50 tests). PR #384 open.

## Recently Completed

- **Anthropic API epic** (2026-03-08): PR #374, issues #215-#219. `LLMProvider` StrEnum, multi-provider `build_debate_model()` dispatcher (Groq + Anthropic), `--provider` CLI flag, `check_anthropic()` health check, conditional `ModelSettings` for extended thinking, `anthropic>=0.83.0` dependency.
- **Housekeeping** (2026-03-08): Archived completed epics, pruned stale branches/stashes, removed cruft, synced docs. Added `daily-audit` command, `tach.toml` boundary enforcement, `tools/bootstrap-dev-env.py`, ast-grep rules.
- **S&P 500 Heatmap epic** (2026-03-08): Issues #366-#372. BatchQuote model, `fetch_batch_daily_changes()`, `GET /api/market/heatmap`, `MarketHeatmap.vue` squarify treemap, Pinia heatmap store, chunked batch download, E2E tests.

## Future Work

- Additional LLM providers (OpenAI) — Groq + Anthropic done
- Options liquidity weighting in composite scoring (PRD drafted)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
