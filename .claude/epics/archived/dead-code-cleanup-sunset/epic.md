---
name: dead-code-cleanup-sunset
status: backlog
created: 2026-03-23T13:21:12Z
progress: 0%
prd: .claude/prds/dead-code-cleanup.md
parent_epic: dead-code-cleanup
depends_on: []
worktree: ../wt-sunset
branch: epic/dead-code-cleanup-sunset
github: https://github.com/jobu711/options_arena/issues/710
---

# Epic: dead-code-cleanup-sunset

## Overview

Wave 4: Architectural simplification and old debate backward-compat sunset. Contains
one complexity reduction (refactor `process_ticker_options`) and one deferred item
(sunset old debate data paths after data migration).

## Scope Boundary

### In Scope
- FR-4.1: Refactor `process_ticker_options` (353 lines) into focused helpers
- FR-4.2: Sunset old debate backward-compat paths (deferred — requires data migration)

### Out of Scope (handled by sibling epics)
- All dead code deletion (Waves 1-3)
- All helper extraction and refactoring (Wave 2)
- All orphaned infrastructure removal (Wave 3)

## Technical Approach

### FR-4.1: Refactor process_ticker_options

`scan/phase_options.py:503-855` is a 353-line async function that handles:
- Chain data fetching
- Ticker info lookup + earnings date extraction
- Contract recommendation
- Spread analysis
- Flow analytics indicators
- Fundamental indicators
- ML trajectory computation
- Greeks computation
- Phase 3 indicator merging

Extract into 4-5 focused helpers:
- `_fetch_chain_data(ticker, services, config)` — chain fetch + fallback
- `_compute_flow_indicators(chain_data, ticker_info)` — flow analytics
- `_compute_fundamental_indicators(ticker_info, services)` — fundamental data
- `_build_spread_analysis(contracts, greeks, config)` — spread engine
- `_merge_phase3_results(base_signals, flow, fundamental, spread)` — merge into IndicatorSignals

Each helper is independently testable. The orchestrating function becomes a ~50-line
coordinator that calls each helper in sequence.

**No behavioral change** — pure function extraction. Existing integration tests
validate the full pipeline end-to-end.

### FR-4.2: Sunset old debate backward-compat (DEFERRED)

**Prerequisite**: Data migration script that transforms `ai_theses` rows into
`recommendation_results` format. Do NOT execute until migration is complete.

When ready to execute:
- Remove ~297 lines of dual-table API lookup in `api/routes/debate.py` and `api/routes/export.py`
- Remove ~350 lines of old debate model classes from `models/analysis.py`:
  `AgentResponse`, `TradeThesis`, `VolatilityThesis`, `FlowThesis`, `RiskAssessment`,
  `FundamentalThesis`, `ContrarianThesis`, `ExtendedTradeThesis`
- Remove `DebateResult` from `agents/_parsing.py` and `_context.py`
- Remove old debate sub-renderers from `reporting/debate_export.py` (~260 lines)
- Simplify API routes to only use `recommendation_results` table

**This task is intentionally deferred.** Create the migration script first, verify
all historical data is migrated and accessible via new schema, then execute.

## Tasks Created

- [ ] #723 - Extract `_fetch_ticker_data` helper from process_ticker_options (parallel: false)
- [ ] #727 - Extract `_compute_dse_indicators` helper from process_ticker_options (parallel: false)
- [ ] #734 - Extract `_select_and_score_contracts` and `_build_spread` helpers (parallel: false)
- [ ] #730 - Slim `process_ticker_options` to ~50-line coordinator (parallel: false)
- [ ] #731 - Final verification — lint, typecheck, full test suite (parallel: false)
- [ ] #736 - (DEFERRED) Plan data migration for ai_theses sunset (parallel: true)

Total tasks: 6
Parallel tasks: 1 (#736 only — deferred planning)
Sequential tasks: 5 (#723 → #727 → #734 → #730 → #731)
Estimated total effort: 3.5 hours

## Test Coverage Plan
Total test files planned: 5
Total test cases planned: ~30

## Shared File Conflicts (with sibling epics)

| File | This epic | Conflict with |
|------|-----------|---------------|
| `models/analysis.py` | sunset thesis classes (deferred) | quickwins (del ContractConstraint), refactor (enrichment_ratio) |
| `scan/phase_options.py` | refactor process_ticker_options | — (no other epic touches this file) |

Resolution: rebase onto master after all 3 sibling epics merge. `models/analysis.py`
conflict only arises if FR-4.2 is executed (currently deferred).

## Dependencies

- None for FR-4.1 (process_ticker_options refactor)
- FR-4.2 requires: data migration script (not yet built)

## Success Criteria

- `process_ticker_options` reduced from 353 lines to ~50-line coordinator
- 4-5 extracted helpers with clear single responsibilities
- All existing integration tests pass without modification
- No behavioral change in scan pipeline output

## Estimated Effort

- 5-6 tasks (1 deferred)
- ~2 hours wall-clock for FR-4.1
- FR-4.2 deferred to future epic
- Merges last (rebase after all siblings)
