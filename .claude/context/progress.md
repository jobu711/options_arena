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

- **Backtesting engine epic** (2026-03-10): Issues #430-#436. 7 backtest models (`BacktestResult`, `EquityCurve`, `DrawdownSeries`, etc.), 7 analytics queries in `AnalyticsMixin`, 7 API endpoints on `/api/analytics/backtest`, CLI `outcomes backtest` + `equity-curve` subcommands, Vue analytics dashboard with 5 tabs (Chart.js), E2E tests. Migration 029.
- **Pipeline phase extraction epic** (2026-03-10): Issues #424-#428. Decomposed monolithic `pipeline.py` (1168→352 lines) into 4 phase modules: `phase_universe.py`, `phase_scoring.py`, `phase_options.py`, `phase_persist.py`. Pipeline.py now a thin orchestrator.
- **Repository decomposition epic** (2026-03-09): Issues #418-#422. Decomposed `Repository` monolith into domain-specific mixins.
- **Prompt engineering v2 + agent calibration** (2026-03-09): Prompt extraction to `agents/prompts/`, few-shot golden examples, regression tests, per-agent accuracy tracking, auto-tune weights.

## Future Work

- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
