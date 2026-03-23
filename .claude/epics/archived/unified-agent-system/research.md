# Research: unified-agent-system

## PRD Summary

Replace the dual agent architecture (6 debate agents + 7 desk agents) with a unified desk-only system. Each desk gains a "recommendation mode" (structured `DomainAssessment` output) alongside existing interactive Q&A mode (`str` output). A new synthesis agent replaces algorithmic verdict computation, producing a `PositionRecommendation` with specific contract recommendations, entry/exit criteria, and position sizing. This is a clean break — debate agents, orchestrator, and debate prompts are deleted.

4 sequential epics: A (Foundation Models + Synthesis), B (Desk Recommendation Mode), C (Orchestrator + Persistence), D (Big Bang Cutover + Cleanup). ~19-24 issues total.

## Relevant Existing Modules

- `agents/` — Core agent subsystem (4,880+ LOC). 6 debate agents (~900 LOC total), 7 desk agents (~1,050 LOC), orchestrator (2,052 LOC), _parsing (1,162 LOC), _toolsets (1,666 LOC), _routing (~575 LOC), _desk_deps (34 LOC), model_config (~300 LOC), constraints (~200 LOC)
- `agents/prompts/` — 13 system prompts: 6 debate (`trend_agent.py`, `volatility.py`, `flow_agent.py`, `fundamental_agent.py`, `risk.py`, `contrarian_agent.py`) + 7 desk (`desk_*.py`). Static constants only, < 8000 chars each
- `models/analysis.py` — All debate output models: `AgentResponse`, `TradeThesis`, `ExtendedTradeThesis`, `VolatilityThesis`, `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`, `MarketContext` (225+ fields), `DeskResponse`, `AgentPrediction`
- `models/enums.py` — 37 StrEnums including `DeskType` (7 members), `SignalDirection`, `SpreadType`, `VolRegime`, `IVTermStructureShape`, `ValuationSignal`, `QueryType`, `LLMProvider`, `RiskLevel`, `CatalystImpact`
- `models/config.py` — `DebateConfig` (21 fields) + `AgencyConfig` on `AppSettings`
- `data/_debate.py` — `DebateMixin` (633 LOC): `save_debate()`, `get_debate_by_id()`, `get_recent_debates()`, `get_debates_for_ticker()`, `save_agent_predictions()`, `get_agent_accuracy()`, `get_agent_calibration()`, `save_auto_tune_weights()`, `get_latest_auto_tune_weights()`, `get_weight_history()`
- `data/_analytics.py` — `AnalyticsMixin`: agent prediction accuracy queries, outcome tracking
- `data/repository.py` — 7-mixin composition: `ScanMixin, DebateMixin, AnalyticsMixin, MetadataMixin, SpreadsMixin, AgencyMixin, LearningMixin`
- `cli/commands.py` — `debate` command with `_debate_async()` (single) + `_batch_async()` (batch)
- `cli/rendering.py` — Rich panels for agent responses, thesis rendering
- `api/routes/debate.py` — 5 endpoints: `POST /api/debate`, `GET /api/debate/{id}`, `POST /api/debate/batch`, `GET /api/debate`, `POST /api/debate/{id}/export`
- `reporting/debate_export.py` — Pure functions rendering `DebateResult` as markdown/PDF
- `learning/weight_tuner.py` — `AGENT_VOTE_WEIGHTS` (6 agents, sum=0.85), `tune_vote_weights()`, `compute_auto_tune_weights()`

## Existing Patterns to Reuse

- **Dual-instance agent pattern**: PydanticAI enforces single `output_type` per Agent. Each desk file gains a second agent instance (`*_desk_recommend: Agent[DeskDeps, *Assessment]`) alongside the existing interactive one. Both share same toolset via `build_*_toolset()`.
- **Toolset builder pattern**: `build_*_toolset()` functions in `_toolsets.py` return `list[object]`. Same toolsets reused for recommendation agents (both modes share tools). Add `build_synthesis_toolset()` following same pattern.
- **Dynamic system prompt pattern**: `@agent.system_prompt(dynamic=True)` already used by all 7 desk agents for learned pattern injection. Recommendation agents use the same pattern.
- **Output validator pattern**: `@agent.output_validator` with `strip_think_tags()` used by all desk agents. Recommendation agents add `build_cleaned_domain_assessment()` (new helper, follows `build_cleaned_agent_response()` pattern in `_parsing.py`).
- **Never-raises pattern**: All desk query runners return `DeskResponse` on any error. All orchestrator functions catch exceptions → fallback. Recommendation orchestrator follows same pattern.
- **DeskDeps dataclass**: Plain `@dataclass` (PydanticAI convention). Extended with optional fields for recommendation mode. All 37 construction sites use keyword args or `**defaults` dict.
- **Repository mixin composition**: Add `RecommendationMixin` alongside `DebateMixin` — same inheritance pattern.
- **`build_market_context()`**: ~350 LOC function in `orchestrator.py` maps `TickerScore` + `Quote` + `TickerInfo` → `MarketContext`. Must be preserved/moved for new orchestrator.
- **`extract_agent_predictions()`**: ~100 LOC in `orchestrator.py`. Extracts per-agent predictions for accuracy tracking. Must be adapted for desk recommendation outputs.
- **Context rendering functions**: `render_trend_context()`, `render_volatility_context()`, `render_flow_context()`, `render_fundamental_context()` in `_parsing.py` — reusable for recommendation prompts.
- **`PROMPT_RULES_APPENDIX`**: Shared calibration rules appended to all debate prompts. Recommendation agents should use this (unlike interactive desk prompts which don't).
- **Config pattern**: `DebateConfig` on `AppSettings` — add new fields, remove dead ones. Keep name for env var backward compatibility (`ARENA_DEBATE__*`).
- **Discriminated union**: Pydantic v2 `Discriminator("desk")` + `Tag()` enables polymorphic round-trip through SQLite JSON storage (Context7-verified).
- **`asyncio.Semaphore`** for parallelism control: `desk_parallelism` config gates concurrent LLM calls.

## Existing Code to Extend

- **`agents/_desk_deps.py`** (34 LOC) — Add 3 optional fields: `ticker_score: TickerScore | None = None`, `contracts: list[OptionContract] = field(default_factory=list)`, `market_context: MarketContext | None = None`. Current field ordering is valid (all non-defaults before defaults). PRD mentions a field ordering violation but investigation shows `repo: Repository` has no default and correctly precedes `fred: FredService | None = None`. Verify at implementation time.
- **`agents/volatility_desk.py`** (and 5 other desk files) — Add second agent instance (`vol_desk_recommend: Agent[DeskDeps, VolatilityAssessment]`) + `run_vol_desk_recommendation()` function.
- **`agents/_toolsets.py`** (1,666 LOC) — Add `build_synthesis_toolset()` for synthesis agent.
- **`agents/_parsing.py`** (1,162 LOC) — Add `build_cleaned_domain_assessment()` helper + `build_citation_text_from_assessments()`. Preserve all render functions, `PROMPT_RULES_APPENDIX`, `strip_think_tags()`, `compute_citation_density()`. Move reusable functions from `orchestrator.py` here before deletion.
- **`agents/__init__.py`** (114 LOC) — Replace debate exports with recommendation exports. Currently exports: `run_debate`, `build_market_context`, `synthesize_verdict`, `extract_agent_predictions`, `compute_agreement_score`, `should_debate`, `DebateDeps`, `DebateResult`, `DebatePhase`, all 6 debate agents, all 7 desk agents, toolset builders, routing functions.
- **`data/repository.py`** — Add `RecommendationMixin` to 7-mixin composition.
- **`models/__init__.py`** — Re-export new recommendation models.
- **`models/enums.py`** — All needed enums already exist (`DeskType`, `SignalDirection`, `SpreadType`, `VolRegime`, `IVTermStructureShape`, `ValuationSignal`). No new enums required.
- **`cli/commands.py`** — Rewrite `debate` command to use `run_recommendation()` instead of `run_debate()`.
- **`api/routes/debate.py`** — Rewrite 5 routes to use `run_recommendation()`.
- **`reporting/debate_export.py`** — Adapt to `RecommendationResult` shape instead of `DebateResult`.
- **`models/config.py`** — Remove dead fields (`enable_volatility_agent`, `enable_rebuttal`, `phase1_parallelism`, `phase1_batch_delay`), add new fields (`synthesis_timeout`, `recommendation_protocol`, `min_recommendation_score`, `desk_parallelism`, `disabled_desks`).

## Potential Conflicts

- **`_parsing.py` shared code**: Contains both debate-specific code (`DebateDeps`, `DebateResult`, debate-specific cleaners) and reusable code (context renderers, `PROMPT_RULES_APPENDIX`, `strip_think_tags()`). Must carefully preserve reusable code when deleting debate-specific code. **Mitigation**: Epic C moves reusable functions before Epic D deletes debate code.

- **`orchestrator.py` critical functions**: `build_market_context()` (~350 LOC), `extract_agent_predictions()` (~100 LOC), `compute_citation_density()`, `_build_model_settings()`, `should_debate()` are all in `orchestrator.py`. The new recommendation orchestrator needs these. **Mitigation**: Move reusable functions to `_parsing.py` or new `_context.py` module in Epic C before deleting `orchestrator.py` in Epic D.

- **Learning module `agent_predictions` queries**: `tune_vote_weights()` and `get_agent_accuracy()` query `agent_predictions` without protocol filtering. After cutover, new predictions use `recommendation_protocol='unified_v1'` while old ones are `'debate_v1'`. **Mitigation**: Migration 037 adds `recommendation_protocol` column with backfill; learning queries add `WHERE recommendation_protocol = 'unified_v1'` filter.

- **Test suite disruption**: ~2,324 lines of debate-specific tests (9 files) + ~800 lines of orchestrator tests (7+ files) reference `run_debate()`, `DebateDeps`, `DebateResult`, `synthesize_verdict()`. All must be rewritten or removed in Epic D. **Mitigation**: Write new tests in Epics A-C (80-100 new tests) before deleting old tests in Epic D.

- **`DebateMixin` preserved for backward compat**: `GET /api/debate/{id}` must check both `ai_theses` (old IDs) and `recommendation_results` (new IDs). `DebateMixin` stays read-only for old data. **Mitigation**: Separate read paths — don't delete `DebateMixin` methods that read old data.

- **`DeskDeps` field additions**: Adding `ticker_score`, `contracts`, `market_context` as optional fields with defaults is backward-compatible. All 37 construction sites (1 source + 36 tests) use keyword args or `**defaults` dict unpacking. No positional arg breakage.

- **Config field removal**: Removing `enable_volatility_agent`, `enable_rebuttal`, `phase1_parallelism`, `phase1_batch_delay` from `DebateConfig` requires verifying no consumers remain. **Mitigation**: Grep for field usage before removal in Epic D.

- **Frontend adaptation**: `DebateResultPage.vue` renders agent panels (bull, bear, risk, etc.) and needs to render domain assessments + position recommendation instead. WebSocket progress uses `DebatePhase` enum (sequential phases) but new system has parallel desks + synthesis. **Mitigation**: Marked out of scope in PRD — adapt to new data shape but no UX redesign.

## Open Questions

1. **`build_market_context()` relocation**: This ~350-line function lives in `orchestrator.py`. Options: (a) move to `_parsing.py` (already has render functions), (b) new `agents/_context.py` module. Either works — PRD doesn't specify. Recommendation: `_context.py` to avoid `_parsing.py` growing past 1,500 LOC.

2. **`constraints.py` fate**: PRD says "keep as pre-check — inject constraint_warnings into DeskDeps". But `DeskDeps` currently has no `constraint_warnings` field. Should it be added to `DeskDeps` or passed separately to the recommendation orchestrator? PRD leans toward DeskDeps extension.

3. **Frontend `DebateResultPage.vue` adaptation**: PRD marks this out of scope for detailed spec. The frontend renders debate panels — it will need to render domain assessments + position recommendation. Needs a follow-up frontend task.

4. **WebSocket progress events**: Current debate WebSocket uses `DebatePhase` enum (TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN) — sequential phases. New system runs all 6 desks in parallel + synthesis. Progress callback pattern needs adaptation (parallel progress vs sequential).

5. **E2E test impact**: 107 Playwright E2E tests across 17 spec files — some may test debate flow end-to-end. Need to assess which E2E tests break and plan rewrites.

6. **DeskDeps field ordering**: PRD states `repo` before `fred` violates dataclass rules, but investigation shows the current ordering IS valid (non-default `repo` before optional `fred`). Need to verify at implementation time whether this is actually broken or the PRD has a stale observation.

## Recommended Architecture

The PRD's architecture is well-designed and validated against the codebase. Key architectural decisions are sound:

1. **Dual-instance pattern** (per desk) — PydanticAI enforces single `output_type` per Agent. Two instances sharing toolsets is the cleanest solution.
2. **Discriminated union** (`AnyAssessment`) — Pydantic v2 `Discriminator("desk")` enables polymorphic round-trip through SQLite JSON storage.
3. **`asyncio.Semaphore`** for parallelism control — `desk_parallelism` config gates concurrent LLM calls.
4. **Forward-only analytics** — Clean separation avoids fragile normalization between debate and recommendation data.
5. **Migration 037** — Next sequential number confirmed (latest is `036_strategy_mining.sql`).

**Reusable code extraction strategy** (critical for Epic C):
```
orchestrator.py ──extract──> _context.py (new) or _parsing.py:
  - build_market_context()        (~350 LOC)
  - extract_agent_predictions()   (~100 LOC)
  - compute_citation_density()    (~30 LOC)
  - _build_model_settings()       (~30 LOC)
  - should_debate() → should_recommend()  (~5 LOC)
  - _build_fallback_result()      (~100 LOC, adapted)
```

**DeskDeps extension** is safe — all 37 construction sites use keyword args or dict unpacking.

**Data flow**:
```
Current (Debate):
  CLI/API → build_market_context() → DebateDeps (pre-fetched, no tools)
    → Phase 1: Trend + Vol parallel → AgentResponse
    → Phase 2: Risk → RiskAssessment
    → Phase 3: Contrarian → AgentResponse
    → Phase 4: synthesize_verdict() (algorithmic) → TradeThesis
    → DebateResult

New (Recommendation):
  CLI/API → build_market_context() → DeskDeps (pre-fetched + tools)
    → Phase 1: 6 desks parallel → DomainAssessment (each desk uses tools)
    → Phase 2: Synthesis agent → PositionRecommendation (AI-driven)
    → Phase 3: Persist
    → RecommendationResult
```

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/agents/test_*.py` — each debate agent has unit tests using `TestModel` + `models.ALLOW_MODEL_REQUESTS = False`. Desk agents have similar test files (`test_*_desk.py`).
- **Test file naming**: `test_{module_name}.py` convention throughout.
- **Mocking**: `TestModel` for LLM responses (no real API calls), `AsyncMock` for services, in-memory SQLite for persistence.
- **Parametrized tests**: Heavy use of `@pytest.mark.parametrize` for model validation edge cases.
- **Fixture patterns**: `@pytest.fixture` for service instances, `DeskDeps` construction helpers (`_make_deps()` or `**defaults` dicts).
- **Test tiers**: `@pytest.mark.critical` for pre-commit, `@pytest.mark.exhaustive` for nightly.
- **E2E**: Playwright in `tests/e2e/` — 17 spec files, 4 parallel workers, isolated DB per test.

**Existing debate test files** (to be rewritten/removed in Epic D):
- `tests/unit/api/test_debate_routes.py` (252 LOC)
- `tests/unit/api/test_debate_routes_detail.py` (626 LOC)
- `tests/unit/api/test_debate_scan_run_id.py` (64 LOC)
- `tests/unit/cli/test_batch_debate.py` (463 LOC)
- `tests/integration/agents/test_debate_e2e.py` (196 LOC)
- `tests/integration/test_debate_protocol.py` (723 LOC)
- `tests/unit/agents/test_orchestrator*.py` (7+ files, ~800 LOC)

**Existing desk test files** (preserved, minimal changes):
- `tests/unit/agents/test_*_desk.py` (7 files, ~1,360 LOC)
- `tests/unit/agents/test_desk_deps.py` (107 LOC)
- `tests/unit/agents/test_toolsets.py`
- `tests/unit/agents/test_routing_all_desks.py` (93 LOC)

**New test needs** (~80-100 new tests):
- Epic A: Model construction/validation/round-trip (~15-20), synthesis agent with TestModel (~5-10)
- Epic B: 6 desk recommendation agents with TestModel (~18-24), domain assessment cleaning (~6)
- Epic C: Orchestrator success/partial/full-failure/timeout (~12-16), persistence round-trip (~8-10)
- Epic D: CLI rendering (~4-6), API response schemas (~4-6), regression tests

## Estimated Complexity

**XL** — 4 sequential epics, ~19-24 issues, touches 13+ modules, deletes 13 files, creates 12 new files, modifies ~15 files, rewrites CLI + API entry points, migration, 80-100 new tests, 50-80 tests to rewrite/remove.

Justification:
- Scope is large (entire agent subsystem replacement)
- But risk is manageable because: desk agents already work, patterns are established, changes are well-scoped per epic, verification gates between epics
- No new external dependencies
- No new architectural patterns (extends existing ones)
- Strictly sequential epics prevent merge conflicts
- ~7,000+ LOC of source code affected + ~4,900+ LOC of tests affected
