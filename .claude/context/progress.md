# Progress

## Current State

- **Version**: 1.5.0 (MVP + AI Debate + Batch Mode + Export + Groq-Only)
- **All 9 phases + 6 epics**: Complete and merged to master (2026-02-25)
- **Branch**: `master` (1402 tests, all phases + epics merged)
- **Tests**: 1402 (220 models + 214 pricing + 172 indicators + 102 scoring + 163 services + 34 data + 156 scan + 40 cli + 235 agents + 14 reporting + 52 misc)
- **GitHub issues**: 1 open (#112), 113 closed
- **CLI**: `options-arena scan`, `health`, `universe`, `debate` (+ `--batch`, `--export`) commands
- **AI provider**: Groq (cloud, `GROQ_API_KEY` env var or `ARENA_DEBATE__API_KEY`)

## Phase Summary

| Phase | Module | Tests | Status |
|-------|--------|-------|--------|
| 1 | Models, enums, config | 220 | Complete |
| 2 | Pricing (BSM + BAW) | 214 | Complete |
| 3 | Technical indicators (18 functions) | 172 | Complete |
| 4 | Scoring (normalize, composite, direction, contracts) | 102 | Complete |
| 5 | Services (market data, options, FRED, universe, health) | 163 | Complete |
| 6 | Data layer (SQLite, migrations, repository) | 34 | Complete |
| 7 | Scan pipeline (4-phase async orchestration) | 156 | Complete |
| 8 | CLI (Typer + Rich, logging, SIGINT) | 25 | Complete |
| 9 | AI debate (PydanticAI agents, Groq) | 197 | Complete |

For detailed phase completion logs, see `progress-archive.md`.

## Recently Completed Epics

### Epic 8: Groq-Only Migration + 12 Debate Improvements (2026-02-25)
Removed Ollama provider entirely, made Groq sole LLM provider. Deleted `DebateProvider`
enum, simplified `DebateConfig` (renamed groq_model→model, groq_api_key→api_key),
added Groq health check, parallel rebuttal+volatility, score-confidence clamping,
citation density scoring, A/B logging (debate_mode, citation_density columns),
list-length validators, IV rank/percentile clarification, Greeks guidance in prompts.
Removed `ollama` dependency.

### Epic 7: Debate Export (2026-02-25) — #107
Markdown and PDF export for debate results via `--export md|pdf` and `--export-dir` flags.
New `reporting/` module with `debate_export.py`. PDF requires optional `weasyprint` dep
(`pip install options-arena[pdf]`). +14 tests. Issues: #109-#113.

### Epic 6: Multi-Ticker Batch Debate (2026-02-25) — #101
`debate --batch` and `--batch-limit N` flags to debate top-scored tickers from the latest
scan sequentially. Extracted `_debate_single()` for reuse, error isolation per ticker,
`render_batch_summary_table()` summary. +11 tests. Issues: #102-#106.

### Epic 5: Bull Rebuttal Round (2026-02-25) — #93
Optional bull rebuttal phase. Config: `enable_rebuttal`. Issues: #94-#99.

### Epic 4: Volatility Agent (2026-02-25) — #82
Optional volatility analysis agent. Config: `enable_volatility_agent`. Issues: #83-#92.

## Future Work (v2)

- Batch export support (`debate --batch --export md`, issue #112)
- Additional LLM providers (Anthropic Claude, OpenAI)
- Options liquidity weighting in composite scoring
- Web UI (deferred from earlier attempts)
- Real-time market data streaming
- Multi-round debate (bear rebuttal, second rounds)

## Blockers

- None currently known.
