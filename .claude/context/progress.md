# Progress

## Current State

- **Version**: 2.8.0 — Backtesting analytics + pipeline decomposition
- **All 9 phases + 29 epics**: Complete and merged to master
- **Tests**: ~4,400 Python (24K parametrized) + 92 E2E (15 spec files)
- **GitHub issues**: 6+ open (financialdatasets-ai #393-#399), 390+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `watchlist`, `outcomes` (collect, summary, backtest, equity-curve)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)

## In Progress

- **FinancialDatasets.ai epic** (#393, issues #394-#399): Integrate Financial Datasets MCP for fundamental data enrichment

## Recently Completed

- **Service layer unification epic** (2026-03-10): Issues #438-#444. `ServiceBase[ConfigT]` mixin in `base.py` — cache-first fetch, rate-limited retries, yfinance wrapping. All 7 data services migrated. Cleanup PR #450: consolidated dual-logger to `self._log` (`type(self).__module__`), added missing `super().close()`.
- **Backtesting engine epic** (2026-03-10): Issues #430-#436. 7 backtest models, 7 analytics queries, 7 API endpoints, CLI subcommands, Vue analytics dashboard, E2E tests. Migration 029.
- **Pipeline phase extraction epic** (2026-03-10): Issues #424-#428. Decomposed monolithic `pipeline.py` (1168→352 lines) into 4 phase modules.
- **Repository decomposition epic** (2026-03-09): Issues #418-#422. Decomposed `Repository` monolith into domain-specific mixins.

## Future Work

- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
