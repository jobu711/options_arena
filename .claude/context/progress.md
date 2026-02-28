# Progress

## Current State

- **Version**: 2.1.0 (Close the Loop — watchlists, debates, history, earnings, delta)
- **All 9 phases + 11 epics**: Complete and merged to master (2026-02-28)
- **Branch**: `master` (1,752 tests, all phases + epics merged)
- **Tests**: 1,752 Python + 38 E2E
- **GitHub issues**: 8 open (#142-#149), 124 closed
- **CLI**: `options-arena scan`, `health`, `universe`, `debate` (+ `--batch`, `--export`), `serve`, `watchlist`
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## Phase Summary

| Phase | Module | Tests | Status |
|-------|--------|-------|--------|
| 1 | Models, enums, config | 293 | Complete |
| 2 | Pricing (BSM + BAW) | 214 | Complete |
| 3 | Technical indicators (18 functions) | 172 | Complete |
| 4 | Scoring (normalize, composite, direction, contracts) | 110 | Complete |
| 5 | Services (market data, options, FRED, universe, health) | 181 | Complete |
| 6 | Data layer (SQLite, migrations, repository) | 42 | Complete |
| 7 | Scan pipeline (4-phase async orchestration) | 131 | Complete |
| 8 | CLI (Typer + Rich, logging, SIGINT) | 40 | Complete |
| 9 | AI debate (PydanticAI agents, Groq) | 241 | Complete |
| 10 | Web UI (FastAPI + Vue 3 SPA) | 82 | Complete |

For detailed phase/epic completion logs, see `progress-archive.md`.

## Recently Completed

### Epic 11: v2.1.0 Close the Loop (2026-02-28) — #142, PR #150
7 features merged to master. Quick debate from dashboard (#143), watchlist backend
(#144) + frontend (#145), scan delta view (#146), score history backend (#147) +
frontend (#148), earnings calendar overlay (#149). New models: `WatchlistItem`,
`TickerDelta`, `ScanDiff`, `HistoryPoint`, `TrendingTicker`. New pages: WatchlistPage,
TickerDetailPage. New components: ScoreHistoryChart, SparklineChart. New CLI subcommand:
`watchlist`. 2 new migrations (006, 007). +175 tests over v2.0.0.

## Future Work

- Close v2.1.0 epic issues (#142-#149) now merged
- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Real-time market data streaming
- Multi-round debate (bear rebuttal, second rounds)
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
