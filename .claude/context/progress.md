# Progress

## Current State

- **Version**: 2.10.0 — pending bump to 3.0.0 after live smoke test
- **All 9 phases + 42 epics**: Complete and merged to master (8/8 AI Agency epics done, 3 agent-infra epics done)
- **Unified agent system**: All 4 sub-epics complete and merged. Debate system fully replaced by recommendation system.
- **Agent infrastructure**: 3 sub-epics complete — tool-response (#693), eval-harness (#694), model-routing (#695)
- **Tests**: ~370 test files, 27K+ parametrized + 107 E2E (17 spec files)
- **GitHub issues**: 695+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`, `--cost-summary`), `serve`, `outcomes` (collect, summary, backtest, equity-curve), `agency` (ask, chat), `learn` (tune-indicators, tune-votes, status, mine, playbook, decay), `eval` (run, list, show)
- **Web UI**: Vue 3 SPA served by FastAPI — Dashboard, Scan, Debate, Universe, Health, Watchlist, Analytics, Desks, Agency Chat
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)
- **AI Agency**: 7 desk agents (Volatility, Risk, Trend, Flow, Fundamental, Contrarian, Research) with tool-use, intent routing, `learning/` weight tuning, strategy mining playbook, and confidence decay
- **Model routing**: Complexity-based per-desk model tier selection (FAST/STANDARD/PREMIUM), per-desk metrics, assessment summary, cost estimation
- **Recommendation system**: `run_recommendation()` is the sole analysis path. 6 desk recommendation agents → synthesis agent → `PositionRecommendation`. 13 old debate files deleted.
- **Eval harness**: `evals/` framework for regression testing agent outputs with pass@k scoring
- **Claude Code infra**: 7 audit agents, `/full-audit` parallel orchestration, `/fix-loop` iterative repair, `/compound` knowledge capture, `docs/solutions/` institutional memory

## In Progress

- **Version 3.0.0 release**: Pending live smoke test before version bump finalization
- **AI Agency Evolution**: 8/8 epics complete. 2 remaining from original roadmap: `ai-agency-analysis-tools`, `ai-agency-ml-tools`.

## Recently Completed

- **agent-infra-model-routing epic** (2026-03-22): Issues #679-#683, PR #695. Complexity-based model routing: `ModelTier` enum, `_assess_complexity()`, `route_model_tier()`, per-desk `DeskMetrics`, `AssessmentSummary`, `RecommendationCost`, `RoutingConfig`. CLI `--cost-summary`, API `/api/analytics/recommendation-costs`. 82 new tests.
- **agent-infra-eval-harness epic** (2026-03-22): PR #694. Eval framework: `EvalDefinition`, `EvalRun`, `EvalBaseline` models, `EvalConfig`, migration 039, `evals/` directory, CLI `eval` subcommand, pass@k scoring.
- **agent-infra-tool-response epic** (2026-03-22): PR #693. Unified `ToolResponse` model with `ToolStatus` enum for all desk agent tool wrappers. Structured tool results replace raw strings.
- **agent-infra-learning-decay epic** (2026-03-22): PR #692. Confidence decay for strategy rules, `learn decay` CLI command, playbook confidence columns.
- **unified-agent-system-cutover epic** (2026-03-22): Issues #664-#671, PR #691. Big bang cutover to recommendation system. Net -7,445 lines. 239 new tests.

## Future Work

- AI Agency: analysis tools, ML tools (2 remaining epics)
- Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright
- Frontend `DebateResultPage.vue` adaptation for recommendation display

## Blockers

- None currently known.
