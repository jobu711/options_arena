# Progress

## Current State

- **Version**: 2.9.0 — Data Completeness (MACD, short interest, v1 elimination)
- **All 9 phases + 21 epics**: Complete and merged to master
- **Tests**: 3,921 Python + 38 E2E
- **GitHub issues**: 2 open, 280+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## In Progress

- **Data Completeness epic** (active): `.claude/epics/data-completeness/` — branch `epic/data-completeness`. Issues #319-#322. Short interest e2e (#319), active-contract P&L (#320), indicator signal labels (#321) done. Issue #322 (verification) pending.

## Recently Completed

- **MACD integration** (2026-03-06): feat(#312-#317) — real `macd()` in indicators/trend.py, registered in INDICATOR_REGISTRY, `IndicatorSignals.macd` field, `classify_macd_signal()` replaces fake derivation. 4 commits.
- **V1 debate elimination** (2026-03-06): `run_debate_v2` → `run_debate`, removed v1 code path, cleaned up orchestrator (~500 lines removed).
- **UI polish v29** (2026-03-06): Merge of formatter consolidation, timezone date fixes, NaN guards, recommended contracts in TickerDrawer, score filter fix, View All debates link.
- **UI cosmetic fixes** (2026-03-05): fix(#266) — visual polish across AgentCard, DirectionBadge, RegimeBanner, TickerDrawer, DashboardPage, HealthPage, ScanResultsPage.
- **Epic 21** (2026-03-05): Metadata Index — persistent SQLite ticker classification cache. PR #278.

## Future Work

- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
