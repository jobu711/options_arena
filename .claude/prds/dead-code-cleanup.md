---
name: dead-code-cleanup
description: Remove ~4,300 lines of dead/orphaned/speculative code identified by 2 forensic audits (12 parallel agents)
status: planned
created: 2026-03-23T12:58:31Z
---

# PRD: dead-code-cleanup

## Executive Summary

A full-codebase forensic audit of Options Arena v3.0.0 identified 51 findings across all 13 modules plus the Vue 3 frontend and test suite. A follow-up post-cutover simplification audit validated those findings and discovered 20 additional items — including ~1,000 lines of orphaned intelligence infrastructure, 14 dead API endpoints with zero frontend callers, and an empty eval framework (1,024 lines). Combined, **~4,300 lines** of dead, redundant, or speculative code are removable across 4 waves.

This PRD defines a structured cleanup organized into 4 waves of increasing effort, each leaving the test suite green. No behavioral changes — pure dead code removal and structural simplification.

## Problem Statement

After the v3.0.0 unified agent system cutover, Options Arena carries ~4,300 lines of code with zero production callers or orphaned integration. This dead code:

- **Obscures signal paths**: Developers reading `rendering.py` (1,019 lines) encounter 490 lines of dead debate panel renderers before the live recommendation renderers
- **Inflates test surface**: ~15 test files exercise dead functionality, consuming CI time
- **Creates false architecture signals**: Re-exported symbols in `__init__.py` suggest public APIs that nothing consumes
- **Hides integration gaps**: `constraints.py` (184 lines of tested constraint checking) is fully implemented but never wired into the pipeline — invisible to anyone not auditing call chains
- **Carries optional dependencies**: 734 lines of neural pricing code behind a `[neural]` extra that isn't shipped

## User Stories

### US-1: Developer navigating rendering.py
**As a** developer modifying CLI output,
**I want** `rendering.py` to contain only live rendering functions,
**So that** I don't waste time reading 490 lines of dead debate panel code before finding the active recommendation renderers.
**Acceptance criteria**: `rendering.py` contains only functions with production callers. All dead functions removed. File drops from ~1,019 to ~530 lines.

### US-2: Developer understanding the indicator pipeline
**As a** developer adding a new indicator,
**I want** every function in `indicators/` to be wired into the scan pipeline or clearly marked as optional,
**So that** I know which indicators are active vs. scaffolded-but-unused.
**Acceptance criteria**: 6 dead indicator functions removed or wired. `__init__.py` re-exports match actual usage. No `IndicatorSignals` fields that are defined but never populated (or fields removed).

### US-3: CI pipeline efficiency
**As a** CI system,
**I want** the test suite to not exercise dead production code,
**So that** test runtime and maintenance burden are minimized.
**Acceptance criteria**: ~15 test files updated or removed. 7 unused test fixtures deleted. Stale docstrings corrected. All tests pass after cleanup.

### US-4: Developer understanding module boundaries
**As a** developer reading `agents/__init__.py`,
**I want** every re-exported symbol to have at least one production consumer,
**So that** the public API surface accurately represents what the module provides.
**Acceptance criteria**: Dead re-exports removed from `agents/`, `indicators/`, `scoring/`, `models/`, `learning/` `__init__.py` files.

## Requirements

### Functional Requirements

#### Wave 1 — Quick-wins, zero risk (22 items)

**FR-1.1: agents/ cleanup**
- Delete `should_debate()` from `_context.py` (duplicate of `should_recommend()`)
- Delete `_log_completeness_breakdown()` from `_context.py` (zero callers anywhere)
- Delete `DebateProgressCallback` type alias from `_context.py` (zero imports)
- Delete `extract_agent_predictions()` from `_context.py` (~105 lines, zero production callers — only tests; originally used by deleted debate orchestrator). Update `__init__.py` re-exports
- Delete `constraints.py` entirely (~183 lines, zero callers in `src/`; never wired to recommendation pipeline). Also delete `ConstraintSeverity`, `ConstraintViolationType` enums from `models/enums.py` and `ContractConstraint` from `models/analysis.py`. Delete `test_constraints.py` (~336 lines)
- Delete `_run_unimplemented()` from `_routing.py` (unreachable code)
- Delete `_IMPLEMENTED_DESKS` frozenset from `_routing.py` (test-only, replaceable)
- Replace 7 trivial delegate functions (`_run_vol`, `_run_risk`, etc.) with direct function references in `_desk_runners` dispatch dict (~75 lines)
- Update stale "debate-mode" comments in 7 desk prompt files (`desk_trend.py`, `desk_flow.py`, `desk_risk.py`, `desk_volatility.py`, `desk_fundamental.py`, `desk_contrarian.py`, `desk_research.py`) — ~15 lines of comment cleanup

**FR-1.2: indicators/ cleanup**
- Delete `compute_vix_term_structure()` from `regime.py`
- Delete `compute_risk_on_off()` from `regime.py`
- Delete `compute_sector_momentum()` from `regime.py`
- Delete `compute_vix_correlation()` from `iv_analytics.py`
- Delete `put_call_ratio_oi()` from `options_specific.py`
- Delete `map_regime_label_to_market_regime()` from `regime_ml.py`
- Remove dead symbols from `indicators/__init__.py` re-exports
- Remove or mark corresponding `IndicatorSignals` fields (`vix_term_structure`, `risk_on_off_score`, `sector_relative_momentum`, `vix_correlation`) — if removing, also update `dimensional.py` `FAMILY_INDICATOR_MAP`

**FR-1.3: models/ + data/ cleanup**
- Delete `DebateConfig.num_ctx` field and its validator
- Delete `MacroSignals` and `MacroRegimeResult` from `models/macro.py`
- Delete `AgentMemory` from `models/strategy.py`
- Delete `save_agent_memory()` and `get_agent_memories()` from `data/_learning.py`
- Delete `get_recommended_contract_id()` from `data/_debate.py`
- Delete `save_debate()` from `data/_debate.py` (~70 lines, zero production callers — only tests)
- Delete `save_agent_predictions()` from `data/_debate.py` (~50 lines, zero production callers — only tests)
- Delete `get_eval_definition()` (singular) from `data/_eval.py`
- Delete `_cached_fetch()` from `services/base.py` (~38 lines, zero callers across entire codebase)
- Remove dead symbols from `models/__init__.py` and `data/__init__.py` re-exports

**FR-1.4: api/ + reporting/ + cli/ cleanup**
- Delete `AgencyQueryStarted` from `api/schemas.py`
- Delete `export_debate_to_file` from `reporting/debate_export.py` and its re-export
- Delete `DebateProgressBridge` class from `api/ws.py` (~32 lines, never instantiated — replaced by `RecommendationProgressBridge`)
- Remove `--no-recon` CLI flag from `debate` command (~15 lines across 3 functions — flag is accepted but silently discarded; `_recommendation_single()` does not accept a `no_recon` parameter)

**FR-1.5: web/ cleanup**
- Delete `web/src/types/agency.ts` entirely (superseded by `api/agency.ts`)
- Remove agency re-exports from `web/src/types/index.ts`
- Delete `getAgencyQuery()` from `web/src/api/agency.ts`
- Delete `debates` ref and `fetchDebates()` action from `web/src/stores/debate.ts`
- Delete `DebateOptions` interface and unused `options` parameter from `startDebate()`
- Delete `IndicatorAttributionResult` from `web/src/types/analytics.ts`
- Delete `SectorOption` from `web/src/types/scan.ts`
- Remove OpenBB enrichment fields from `web/src/types/debate.ts:70-81` (12 fields: `pe_ratio`, `forward_pe`, `peg_ratio`, `price_to_book`, `debt_to_equity`, `revenue_growth`, `profit_margin`, `net_call_premium`, `net_put_premium`, `news_sentiment_score`, `news_sentiment_label`, `enrichment_ratio` — permanently null)
- Remove enrichment rendering sections from `DebateResultPage.vue:236-301` (~60 lines of template + `sentimentColorClass()`, `hasFundamentalEnrichment`, `hasFlowEnrichment` computed properties — always render nothing)

**FR-1.6: tests/ cleanup**
- Delete `mock_debate_config` fixture from `tests/unit/agents/conftest.py`
- Delete 6 unused fixtures from `tests/unit/scoring/conftest.py`
- Fix stale docstrings in `test_benchmarks.py` and performance `conftest.py`
- Delete or update `orchestration_known_values.json`
- Update `api/CLAUDE.md` ConfigResponse example (stale `enable_rebuttal`/`enable_volatility_agent` fields)

#### Wave 2 — Medium effort, low risk (6 items)

**FR-2.1: Delete 10 dead debate rendering functions from `cli/rendering.py`**
- Functions: `render_volatility_panel`, `render_flow_panel`, `render_fundamental_panel`, `render_risk_panel`, `render_contrarian_panel`, `render_spread_panel`, `render_debate_panels`, `_build_agent_panel_text`, `_build_verdict_panel_text`, `render_batch_summary_table`
- ~490 lines removed
- Update/delete 4 test files: `test_rendering.py`, `test_rendering_v2.py`, `test_spread_rendering.py`, `test_batch_debate.py`

**FR-2.2: Delete 5 dead domain-specific context renderers from `agents/_parsing.py`**
- Functions: `render_trend_context`, `render_volatility_context`, `render_flow_context`, `render_fundamental_context`, `render_macro_context`, `_render_identity_block`
- ~420 lines removed
- Remove re-exports from `agents/__init__.py`
- Update/delete ~5 test files

**FR-2.3: De-duplicate `_contracts_to_cache_bytes`/`_cache_bytes_to_contracts`**
- Extract from `options_data.py` and `cboe_provider.py` into `services/helpers.py`
- ~15 lines net reduction

**FR-2.4: Extract `_check_api_provider()` in `services/health.py`**
- Consolidate `check_groq()`/`check_anthropic()` boilerplate
- ~80 lines reduced

**FR-2.5: Extract `FiniteFieldsMixin` for config validators**
- Replace 9 identical `validate_all_finite` model validators in `config.py`
- ~80 lines reduced

**FR-2.6: Fix `enrichment_ratio()` dead code path**
- `MarketContext.enrichment_ratio()` hardcodes `return 0.0`
- `_parsing.py:915` has always-true conditional — remove dead branch or make ratio functional

#### Wave 3 — Orphaned infrastructure removal (4 items)

**FR-3.1: Remove `IntelligenceService` + models (~997 lines)**
- `services/intelligence.py` (583 lines) + `models/intelligence.py` (414 lines) = orphaned pipeline
- Post-cutover audit confirmed: `recommendation_orchestrator.py` calls `build_market_context()` without `intelligence=` kwarg — data NEVER reaches any analysis path
- The service is instantiated in API lifespan when `settings.intelligence.enabled=True` (the default), consuming memory and a rate limiter slot for zero value
- Remove service, models, `IntelligenceConfig` from settings, lifespan instantiation
- Remove `intelligence=` kwarg from `build_market_context()` signature

**FR-3.2: Remove 14 dead API endpoints (~330 lines)**
- Zero frontend callers confirmed by grep across `web/src/`:
  - `GET /api/analytics/indicator-attribution/{indicator}` (~15 lines)
  - `GET /api/analytics/risk-metrics` (~12 lines)
  - `GET /api/analytics/correlation` (~50 lines — note: the `analysis/correlation.py` function stays, used by agent toolsets)
  - `GET /api/analytics/recommendation-costs` (~20 lines)
  - `GET /api/analytics/scan/{scan_id}/contracts` (~15 lines)
  - All 7 `GET/POST /api/learning/*` endpoints (~120 lines — learning remains CLI-only)
  - All 4 `GET/POST /api/eval/*` endpoints (~60 lines — eval remains CLI-only)
  - `POST /api/universe/refresh`, `POST /api/universe/index`, `GET /api/universe/metadata/stats` (~40 lines)
- CLI commands that duplicate this functionality are unaffected

**FR-3.3: Remove eval harness framework (~1,024 lines)**
- `evals/runner.py` (400 lines), `evals/graders.py` (465 lines), `models/eval.py` (159 lines), `data/_eval.py` (persistence)
- Zero eval definitions exist anywhere in the project — no `.json` or `.yaml` eval files
- `get_eval_definitions()` returns `[]`; the framework cannot produce value
- "ModelGrader" name is misleading — runs keyword counting, not LLM-as-judge
- Also remove `eval` CLI subcommand, `EvalConfig` from settings, migration 039 table
- If eval harness is needed later, rebuild with actual eval definitions first

**FR-3.4: Decide on neural pricing modules**
- `trajectory.py` (408 lines) + `neural_surface.py` (326 lines) = 734 lines
- Behind optional `[neural]` extra that isn't shipped
- Decision: keep with documentation, or remove until `[neural]` is productionized

#### Wave 4 — Architectural simplification, needs migration (2 items)

**FR-4.1: Refactor `process_ticker_options` (353 lines)**
- Extract into 4-5 focused helpers: `_fetch_chain_data`, `_compute_flow_indicators`, `_compute_fundamental_indicators`, `_build_spread_analysis`, `_merge_phase3_results`
- No behavioral change — pure extraction

**FR-4.2: Sunset old debate backward-compat paths (future, after data migration)**
- ~297 lines of dual-table API lookup across `debate.py` and `export.py`
- ~350 lines of old debate model classes (`AgentResponse`, `TradeThesis`, `VolatilityThesis`, `FlowThesis`, `RiskAssessment`, `FundamentalThesis`, `ContrarianThesis`, `ExtendedTradeThesis`) in `models/analysis.py`
- Prerequisite: data migration script that transforms `ai_theses` rows into `recommendation_results` format
- Only execute after confirming all historical data is migrated and accessible via new schema

### Non-Functional Requirements

**NFR-1: Zero behavioral regression**
- Every wave must leave `uv run pytest -m "not exhaustive" -n auto -q` green
- No user-visible output changes
- No API contract changes (response shapes unchanged)

**NFR-2: Architecture boundary preservation**
- All changes respect module boundaries defined in `CLAUDE.md`
- No new cross-module imports introduced
- Re-export pattern maintained for remaining symbols

**NFR-3: Backward compatibility for old debate data**
- `DebateResult` (defined in `_parsing.py`, imported by `_context.py`), `AgentResponse`, `TradeThesis` (in `models/analysis.py`) MUST be retained — they parse old debate data from SQLite
- `export_debate_markdown()` in `reporting/` MUST be retained — API uses it for old debate export
- Old debate sub-renderers in `reporting/debate_export.py` (~260 lines) are backward-compat — mark as legacy but do NOT delete

**NFR-4: CI gate compliance**
- `uv run ruff check . --fix && uv run ruff format .` passes
- `uv run mypy src/ --strict` passes
- All 4 CI gates green (lint, typecheck, tests, frontend)

## Success Criteria

| Metric | Target |
|--------|--------|
| Lines of dead code removed | >= 3,500 |
| Test files updated/removed | >= 20 |
| Dead `__init__.py` re-exports removed | >= 25 |
| Dead API endpoints removed | >= 14 |
| Unused test fixtures deleted | >= 7 |
| Orphaned services removed | >= 2 (IntelligenceService, eval harness) |
| CI suite still green after each wave | 100% |
| New bugs introduced | 0 |

## Constraints & Assumptions

### Constraints
- Each wave must be independently mergeable (atomic commits per wave)
- Wave 1 has no dependencies on Waves 2-4
- Wave 2 items are independent of each other (parallelizable)
- Wave 3 removes orphaned infrastructure and dead endpoints — verify no external consumers before removing API routes
- Wave 4 requires data migration before execution — do not proceed without migration script
- No changes to SQLite schema or migrations (except eval migration 039 removal in Wave 3)
- No changes to API response contracts for active endpoints (dead endpoint removal is acceptable)

### Assumptions
- The `[neural]` extra will not ship in the near term (Wave 3 decision)
- Old debate data in SQLite must remain readable via API for at least one more release (Wave 4 handles sunset)
- `constraints.py` has zero callers and is confirmed dead — removal, not wiring (moved to Wave 1)
- `IntelligenceService` pipeline is fully orphaned — `build_market_context()` never receives intelligence data (moved to Wave 3 as removal)
- Eval harness has zero eval definitions — framework cannot produce value; removal is reversible if definitions are created later
- Learning/eval API endpoints are CLI-only features — removing API routes has no frontend impact
- Backtesting suite is fully utilized (7/7 endpoints have frontend callers) — do NOT remove
- DSE dimensional scores are actively computed every scan — do NOT remove
- Strategy mining is actively wired into recommendation pipeline via `render_learned_patterns()` — do NOT remove
- Confidence decay has a design contradiction (`auto_promote_demote` bypasses documented "human approval required") — fix, don't remove

## Out of Scope

- **Backtest validation of low-alpha indicators** (`smile_curvature` weight 0.0096, `regime_transition_prob` weight 0.01) — needs production data to validate; tracked separately
- **Wiring unpopulated `IndicatorSignals` fields** — if the functions are dead, the fields are removed; wiring them as live indicators is a feature addition
- **Frontend unit testing** (Vitest) — separate initiative
- **`process_ticker_options` refactor** is included in Wave 4 but is a complexity reduction, not dead code removal — could be deferred
- **Performance optimization** — this epic is about correctness and maintainability, not speed
- **Documentation updates** beyond stale CLAUDE.md fixes — `tools/docgen.py` regeneration handles API docs automatically
- **Strategy mining removal** — actively wired into recommendation pipeline (`render_learned_patterns()`); assessed and confirmed KEEP
- **Confidence decay removal** — small footprint, piggybacked on outcome collection; design contradiction needs fixing (auto-promote vs human approval), not removal
- **Model routing removal** — cleanly gated behind `enable_model_routing=False`, costs nothing when off; assessed and confirmed KEEP
- **CBOE chain provider removal** — provides native Greeks, clean abstraction, graceful degradation; assessed and confirmed KEEP
- **Backtesting suite removal** — pre-research flagged as low-value but audit confirmed 7/7 endpoints have active frontend callers; confirmed KEEP
- **DSE dimensional scores removal** — pre-research flagged as speculative but audit confirmed actively computed every scan; confirmed KEEP
- **`analysis/` module removal** — all 4 functions (`compute_composite_valuation`, `compute_correlation_matrix`, `compute_position_size`, `compute_risk_adjusted_metrics`) have production callers via agent toolsets; confirmed KEEP

## Dependencies

### Internal
- All 7 audit agent reports (completed 2026-03-23) — findings are the input to this PRD
- Existing test coverage — tests that exercise dead code will be deleted alongside the dead code
- `tools/docgen.py` — must be run after each wave to regenerate `docs/technical-reference.md`

### External
- None — this is a pure internal cleanup with no external service or API changes

## Risk Assessment

| Risk | Likelihood | Impact | Mitigation |
|------|-----------|--------|------------|
| Removing code that has a dynamic caller (string import, reflection) | Low | High | Grep verified all findings; no dynamic imports in this codebase |
| Breaking old debate data rendering | Low | Medium | `DebateResult` and `export_debate_markdown` explicitly preserved; dual-table API kept until Wave 4 |
| Removing planned infrastructure prematurely | Low | Low | Post-cutover audit validated each finding with call-chain tracing; speculative features (strategy mining, model routing, CBOE, decay) explicitly confirmed KEEP |
| Test suite false-green after removing tests | Low | Medium | Verify coverage of remaining code doesn't drop |
| Dead API endpoint removal breaks external consumer | Low | Medium | Only remove endpoints with zero frontend callers; CLI equivalents remain for all removed endpoints |
| IntelligenceService removal blocks future enrichment | Low | Low | Removal is reversible; service was never connected to analysis path; can be rebuilt when enrichment is prioritized |
| Eval harness removal blocks future regression testing | Low | Low | Framework had zero definitions; rebuild with actual eval content when needed |

## Audit Source Data

### Audit 1: Full-codebase forensic audit (7 parallel agents, 2026-03-23)

| Agent | Scope | Findings | Key items |
|-------|-------|----------|-----------|
| Indicators + Scoring | 25 files | 16 | 6 dead functions, 2 low-alpha weights, sort key duplication |
| Services + Pricing | 23 files | 17 | IntelligenceService unwired, cache duplication, health boilerplate, neural modules |
| Agents + Prompts | 33 files | 12 | 5 dead renderers, should_debate duplicate, routing dead code, constraints unwired |
| Models + Data + Utils | 41 files | 12 | Dead models/methods, enrichment_ratio always 0, config validator duplication |
| Scan + CLI + API + Reporting + Analysis + Learning | 42 files | 12 | 490 lines dead rendering, export_debate_to_file, dead schema |
| Web Frontend | 60 files | 10 | Duplicate types/agency.ts, dead store members, unused TS types |
| Tests | 389 files | 6 | Dead fixtures, stale JSON reference data, stale docstrings |

### Audit 2: Post-cutover simplification audit (5 parallel agents, 2026-03-23)

Validated all pre-researched findings against actual source and grep-confirmed call chains. Key additions:

| Category | New Items | Lines | Key discoveries |
|----------|-----------|-------|-----------------|
| Dead code (agents) | 3 | ~340 | `extract_agent_predictions()` (105 lines), `DebateProgressBridge` (32 lines), `constraints.py` upgraded from "decide" to confirmed REMOVE (519 lines incl tests) |
| Dead code (data) | 2 | ~120 | `save_debate()`, `save_agent_predictions()` — zero production callers |
| Dead code (services) | 1 | ~38 | `_cached_fetch()` in ServiceBase — zero callers |
| Dead code (cli) | 1 | ~15 | `--no-recon` flag accepted but silently discarded |
| Orphaned infra | 1 | ~997 | `IntelligenceService` + models — instantiated but never queried; `build_market_context()` never receives intelligence data |
| Dead API endpoints | 14 | ~330 | Zero frontend callers: 5 analytics, 7 learning, 4 eval, 3 universe |
| Empty framework | 1 | ~1,024 | Eval harness: 4 files, zero eval definitions, cannot produce value |
| Dead frontend | 1 | ~72 | OpenBB enrichment fields in DebateResultPage.vue — permanently null |
| Corrections | 3 | 0 | Backtesting (7/7 endpoints ACTIVE), DSE scores (ACTIVE), strategy mining (ACTIVE) — do NOT remove |
