# Progress

## Current State

- **Version**: 2.10.0 — Release hardening + full audit + math verification
- **All 9 phases + 39 epics**: Complete and merged to master (6/8 AI Agency epics done)
- **Tests**: 355 test files, 27K+ parametrized + 107 E2E (17 spec files)
- **GitHub issues**: 618+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `outcomes` (collect, summary, backtest, equity-curve), `agency` (ask, chat), `learn` (tune-indicators, tune-votes, status, mine, playbook)
- **Web UI**: Vue 3 SPA served by FastAPI — Dashboard, Scan, Debate, Universe, Health, Watchlist, Analytics, Desks, Agency Chat
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)
- **AI Agency**: 7 desk agents (Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research) with tool-use, intent routing, `learning/` weight tuning, and strategy mining playbook
- **Claude Code infra**: 7 audit agents, `/full-audit` parallel orchestration, `/fix-loop` iterative repair, `/compound` knowledge capture, `docs/solutions/` institutional memory

## In Progress

- **AI Agency Evolution**: 6/8 epics complete. 2 remaining epics (not yet decomposed): `ai-agency-analysis-tools`, `ai-agency-ml-tools`.

## Recently Completed

- **ai-agency-strategy-mining epic** (2026-03-20): Issues #614-#617, PR #618. Strategy pattern mining via dimensional grouping (sector x IV x DTE x direction), chi-squared significance testing, human approval workflow. `StrategyRule`/`AgentMemory` models, migration 036, `LearningMixin`, `strategy_book.py`. Learned pattern injection into all 7 desk agent prompts. API: mine, playbook, approve/reject. CLI: `learn mine`, `learn playbook`. 91 new tests.
- **ai-agency-weight-tuning epic** (2026-03-20): Issues #607-#611, PR #612. New `learning/` module with `weight_tuner.py` — indicator weight tuning via P&L correlation, vote weight tuning. Migration 035 for indicator weight columns. Learning API endpoints + `LearningStatus` model. CLI `learn` subcommands (tune-indicators, tune-votes, status).
- **ai-agency-all-desks epic** (2026-03-19): Issues #587-#591, PR #595. 5 new desk agents (Trend, Flow, Fundamental, Contrarian, Research), expanded `_toolsets.py` (574+ lines), all 7 desks wired into routing. `DeskSelector.vue` frontend component. Integration tests for all desk routing.
- **ai-agency-advisor-routing epic** (2026-03-18): Issues #581-#584, PR #580. Intent classification + routing orchestrator (`_routing.py`). `AgencyMixin` + migration 034 for query persistence. Agency API endpoints + CLI `agency` commands. `AgencyChat.vue` frontend component.
- **ai-agency-desk-foundation epic** (2026-03-17): Issues #575-#578, PR #579. Proved desk agent pattern with Volatility + Risk desks. `DeskDeps`, `DeskType`/`QueryType` enums, `DeskResponse`/`QueryIntent` models, `AgencyConfig`, 5 PydanticAI tool wrappers. 99 new tests.
- **v2-release-prep epic** (2026-03-17): Issues #564-#571. Full audit battery (7 agents + math audit, 54 formulas verified), version 2.10.0, CHANGELOG, git tag `v2.10.0`.
- **Dead code audit epic** (2026-03-16): Issues #557-#563. Removed ~1,720 lines dead code across 17 modules.
- **Scientific ML Statistical epic** (2026-03-15): Issues #533-#537, PR #538. GARCH/EGARCH, Markov-switching, FRED macro pipeline, Hurst exponent.

## Future Work

- AI Agency: analysis tools, ML tools (2 remaining epics)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
