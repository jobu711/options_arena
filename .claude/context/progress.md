# Progress

## Current State

- **Version**: 2.10.0 — Release hardening + full audit + math verification
- **All 9 phases + 39 epics**: Complete and merged to master (6/8 AI Agency epics done)
- **Unified agent system**: Foundation epic complete (1/4 sub-epics). Synthesis models + agent merged.
- **Tests**: 363 test files, 27K+ parametrized + 107 E2E (17 spec files)
- **GitHub issues**: 638+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `outcomes` (collect, summary, backtest, equity-curve), `agency` (ask, chat), `learn` (tune-indicators, tune-votes, status, mine, playbook)
- **Web UI**: Vue 3 SPA served by FastAPI — Dashboard, Scan, Debate, Universe, Health, Watchlist, Analytics, Desks, Agency Chat
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)
- **AI Agency**: 7 desk agents (Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research) with tool-use, intent routing, `learning/` weight tuning, and strategy mining playbook
- **Claude Code infra**: 7 audit agents, `/full-audit` parallel orchestration, `/fix-loop` iterative repair, `/compound` knowledge capture, `docs/solutions/` institutional memory

## In Progress

- **Unified Agent System**: Parent PRD with 4 sub-epics. Foundation (1/4) complete. Next: `desk-recommend` (decomposed, ready), `orchestrator`, `cutover`.
- **AI Agency Evolution**: 6/8 epics complete. 2 remaining: `ai-agency-analysis-tools`, `ai-agency-ml-tools`.

## Recently Completed

- **unified-agent-system-foundation epic** (2026-03-22): Issues #632-#636, PR #638. `DomainAssessment` hierarchy (6 subclasses), `AnyAssessment` discriminated union, `PositionRecommendation`, `RecommendationResult`, synthesis agent (`Agent[SynthesisDeps, PositionRecommendation]`), `SYNTHESIS_SYSTEM_PROMPT`, 2 synthesis tools. 125 new tests. Audit fixes: `BaseException` check, lock-release guards, `SpreadType` enum, dead `[pdf]` extra removed.
- **ai-agency-strategy-mining epic** (2026-03-20): Issues #614-#617, PR #618. Strategy pattern mining, chi-squared significance testing, human approval workflow. 91 new tests.
- **ai-agency-weight-tuning epic** (2026-03-20): Issues #607-#611, PR #612. Indicator weight tuning via P&L correlation, vote weight tuning. CLI `learn` subcommands.
- **ai-agency-all-desks epic** (2026-03-19): Issues #587-#591, PR #595. 5 new desk agents, all 7 desks wired into routing.
- **ai-agency-advisor-routing epic** (2026-03-18): Issues #581-#584, PR #580. Intent classification + routing orchestrator.
- **ai-agency-desk-foundation epic** (2026-03-17): Issues #575-#578, PR #579. Desk agent pattern with Volatility + Risk desks.
- **v2-release-prep epic** (2026-03-17): Issues #564-#571. Full audit battery, version 2.10.0.
- **Dead code audit epic** (2026-03-16): Issues #557-#563. Removed ~1,720 lines dead code.
- **Scientific ML Statistical epic** (2026-03-15): Issues #533-#537, PR #538. GARCH/EGARCH, Markov-switching.

## Future Work

- Unified Agent System: 3 remaining sub-epics (desk-recommend, orchestrator, cutover)
- AI Agency: analysis tools, ML tools (2 remaining epics)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
