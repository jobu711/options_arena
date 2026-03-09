# Progress

## Current State

- **Version**: 2.13.0 — Liquidity-weighted composite scoring
- **All 9 phases + 27 epics**: Complete and merged to master
- **Tests**: ~4,300 Python + 73 E2E
- **GitHub issues**: 10+ open (pipeline-phase-extraction #424-#428, financialdatasets-ai #393-#399), 384+ closed
- **CI**: GitHub Actions (4 gates: lint, typecheck, tests, frontend)
- **CLI**: `options-arena scan`, `health`, `universe` (+ `index`), `debate` (+ `--batch`, `--export`, `--provider`), `serve`, `watchlist`, `outcomes` (collect, summary)
- **Web UI**: Vue 3 SPA served by FastAPI at `http://127.0.0.1:8000`
- **AI providers**: Groq (default, `GROQ_API_KEY`) + Anthropic (`ANTHROPIC_API_KEY`, `--provider anthropic`)

## In Progress

- **Pipeline phase extraction epic** (#423, issues #424-#428): Extract 4 pipeline phases from monolithic `pipeline.py` into `phase_universe.py`, `phase_scoring.py`, `phase_options.py`, `phase_persist.py`
- **FinancialDatasets.ai epic** (#393, issues #394-#399): Integrate Financial Datasets MCP for fundamental data enrichment

## Recently Completed

- **Repository decomposition epic** (2026-03-09): Issues #418-#422. Decomposed `Repository` monolith (1762 lines) into domain-specific mixins: `_base.py`, `_scan.py`, `_debate.py`, `_analytics.py`, `_metadata.py`. 114 new tests verifying mixin composition.
- **Context7 upgrade** (2026-03-09): Upgraded `/context7` command to auto-detecting structural verification engine.
- **Liquidity weighting epic** (2026-03-08): PR #384, issues #375-#383. `chain_spread_pct` and `chain_oi_depth` indicators, liquidity multiplier in `select_by_delta()`, weight redistribution (sum=1.0), 50+ tests across 7 files.
- **Anthropic API epic** (2026-03-08): PR #374, issues #215-#219. `LLMProvider` StrEnum, multi-provider `build_debate_model()` dispatcher (Groq + Anthropic), `--provider` CLI flag, `check_anthropic()` health check, conditional `ModelSettings` for extended thinking, `anthropic>=0.83.0` dependency.

## Future Work
 Real-time market data streaming
- Frontend unit testing (Vitest + Vue Test Utils) — E2E covered by Playwright

## Blockers

- None currently known.
