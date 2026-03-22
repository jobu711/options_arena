# Progress

## Current State

- **Version**: 2.10.0 — Release hardening + full audit + math verification
- **All 9 phases + 39 epics**: Complete and merged to master (6/8 AI Agency epics done)
- **Unified agent system**: All 4 sub-epics complete and merged. Debate system fully replaced by recommendation system.
- **Tests**: ~350 test files, 27K+ parametrized + 107 E2E (17 spec files)
- **GitHub issues**: 671+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `outcomes` (collect, summary, backtest, equity-curve), `agency` (ask, chat), `learn` (tune-indicators, tune-votes, status, mine, playbook)
- **Web UI**: Vue 3 SPA served by FastAPI — Dashboard, Scan, Debate, Universe, Health, Watchlist, Analytics, Desks, Agency Chat
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)
- **AI Agency**: 7 desk agents (Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research) with tool-use, intent routing, `learning/` weight tuning, and strategy mining playbook
- **Recommendation system**: `run_recommendation()` is the sole analysis path. 6 desk recommendation agents → synthesis agent → `PositionRecommendation`. 13 old debate files deleted.
- **Claude Code infra**: 7 audit agents, `/full-audit` parallel orchestration, `/fix-loop` iterative repair, `/compound` knowledge capture, `docs/solutions/` institutional memory

## In Progress

- **AI Agency Evolution**: 6/8 epics complete. 2 remaining: `ai-agency-analysis-tools`, `ai-agency-ml-tools`.

## Recently Completed

- **unified-agent-system-cutover epic** (2026-03-22): Issues #664-#671, PR #691. Big bang cutover: rewired CLI + API to `run_recommendation()`, deleted 13 debate files (6 agents, 6 prompts, orchestrator), updated DebateConfig (removed 4 dead fields, added 5 new), updated 4 CLAUDE.md files, cleaned 24 old test files. Net -7,445 lines. 239 new tests.
- **unified-agent-system-orchestrator epic** (2026-03-22): Issues #647-#651, PR #646. `run_recommendation()` orchestrator, migration 037 (recommendation_results table), `RecommendationMixin`, extracted reusable code from orchestrator.py to `_context.py`.
- **unified-agent-system-desk-recommend epic** (2026-03-22): Issues #640-#645, PR #639. 6 recommendation agents (one per desk), 6 recommendation prompts, `DeskDeps` extended with recommendation mode, domain assessment cleaners.
- **unified-agent-system-foundation epic** (2026-03-22): Issues #632-#636, PR #638. `DomainAssessment` hierarchy (6 subclasses), `AnyAssessment` discriminated union, `PositionRecommendation`, `RecommendationResult`, synthesis agent, 2 synthesis tools. 125 new tests.
- **ai-agency-strategy-mining epic** (2026-03-20): Issues #614-#617, PR #618. Strategy pattern mining, chi-squared significance testing, human approval workflow. 91 new tests.
- **ai-agency-weight-tuning epic** (2026-03-20): Issues #607-#611, PR #612. Indicator weight tuning via P&L correlation, vote weight tuning. CLI `learn` subcommands.

## Future Work

- AI Agency: analysis tools, ML tools (2 remaining epics)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright
- Frontend `DebateResultPage.vue` adaptation for recommendation display

## Blockers

- None currently known.
