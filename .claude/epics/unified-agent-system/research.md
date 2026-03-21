# Research: unified-agent-system

## PRD Summary

Replace the dual agent architecture (6 debate agents + 7 desk agents) with a unified desk-only system. Each desk gains a "recommendation mode" (structured `DomainAssessment` output) alongside existing interactive Q&A mode (`str` output). A new synthesis agent replaces algorithmic verdict computation, producing a `PositionRecommendation` with specific contract recommendations, entry/exit criteria, and position sizing. This is a clean break — debate agents, orchestrator, and debate prompts are deleted.

4 sequential epics: A (Foundation Models + Synthesis), B (Desk Recommendation Mode), C (Orchestrator + Persistence), D (Big Bang Cutover + Cleanup). ~19-24 issues total.

## Relevant Existing Modules

- `agents/` — 6 debate agents (~374 lines), orchestrator (~2,052 lines), 6 debate prompts (~711 lines), 7 desk agents, `_parsing.py` (~1,162 lines), `_toolsets.py`, `_routing.py`, `_desk_deps.py`, `model_config.py`, `constraints.py`
- `agents/prompts/` — 6 debate prompts (`trend_agent.py`, `volatility.py`, `flow_agent.py`, `fundamental_agent.py`, `risk.py`, `contrarian_agent.py`) + 7 desk prompts (`desk_*.py`)
- `models/analysis.py` — All debate models: `AgentResponse`, `TradeThesis`, `ExtendedTradeThesis`, `VolatilityThesis`, `FlowThesis`, `FundamentalThesis`, `RiskAssessment`, `ContrarianThesis`, `MarketContext`, `AgentPrediction`, `DeskResponse`
- `models/enums.py` — 37 enums including `DeskType`, `SignalDirection`, `SpreadType`, `VolRegime`, `IVTermStructureShape`, `ValuationSignal`, `QueryType`, `LLMProvider`
- `data/_debate.py` — `DebateMixin` with 6 methods: `save_debate()`, `get_debate_by_id()`, `get_recent_debates()`, `get_debates_for_ticker()`, `save_agent_predictions()`, `get_recommended_contract_id()`
- `data/_analytics.py` — `AnalyticsMixin` with agent prediction queries: `get_agent_accuracy()`, `get_agent_calibration()`, `get_latest_auto_tune_weights()`
- `data/repository.py` — 7-mixin composition: `ScanMixin`, `DebateMixin`, `AnalyticsMixin`, `MetadataMixin`, `SpreadsMixin`, `AgencyMixin`, `LearningMixin`
- `cli/commands.py` — `debate` command with `_debate_async()` (single) + `_batch_async()` (batch), both call `run_debate()`
- `api/routes/debate.py` — 6 endpoints: `POST /api/debate`, `GET /api/debate/{id}`, `POST /api/debate/batch`, `GET /api/debate`, `POST /api/debate/{id}/export`
- `reporting/debate_export.py` — Pure functions rendering debate results as markdown
- `learning/weight_tuner.py` — `AGENT_VOTE_WEIGHTS`, `tune_vote_weights()`, queries `agent_predictions` + `contract_outcomes`

## Existing Patterns to Reuse

- **Dual-instance agent pattern**: Not yet used — this is new. But the desk agent module-level singleton pattern (`Agent(model=None, ...)`) is directly extensible: add a second agent instance (`vol_desk_recommend`) alongside the existing one.
- **Toolset builder pattern**: `build_*_toolset()` functions in `_toolsets.py` return `list[object]`. Same toolsets reused for recommendation agents (both modes share tools).
- **Dynamic system prompt pattern**: `@agent.system_prompt(dynamic=True)` already used by all 7 desk agents for learned pattern injection. Recommendation agents will use the same pattern.
- **Output validator pattern**: `@agent.output_validator` with `strip_think_tags()` — used by all desk agents. Recommendation agents add `build_cleaned_domain_assessment()` (new helper, follows `build_cleaned_agent_response()` pattern).
- **Never-raises pattern**: All desk query runners return `DeskResponse` on any error. Recommendation runners follow same pattern with fallback `DomainAssessment`.
- **DeskDeps dataclass**: Plain `@dataclass` (PydanticAI convention). Extended with optional fields for recommendation mode.
- **Repository mixin composition**: Add `RecommendationMixin` alongside `DebateMixin` — same inheritance pattern.
- **`run_debate()` orchestrator pattern**: `asyncio.gather(return_exceptions=True)` for parallel agents, sequential synthesis, fallback on any error. Recommendation orchestrator follows same structure.
- **`build_market_context()`**: Reusable function from `orchestrator.py` — must be moved/shared for new orchestrator.
- **`extract_agent_predictions()`**: Reusable — extracts predictions from agent outputs for learning pipeline.
- **Context rendering functions**: `render_trend_context()`, `render_volatility_context()`, etc. in `_parsing.py` — reusable for recommendation prompts.
- **`PROMPT_RULES_APPENDIX`**: Shared calibration rules — recommendation agents should use this (unlike interactive desk prompts which don't).
- **Config pattern**: `DebateConfig` on `AppSettings` — add new fields, remove dead ones.

## Existing Code to Extend

- **`agents/_desk_deps.py`** — Add 3 optional fields: `ticker_score: TickerScore | None = None`, `contracts: list[OptionContract] = field(default_factory=list)`, `market_context: MarketContext | None = None`. Field ordering is already correct (all required before optional).
- **`agents/volatility_desk.py`** (and 5 other desk files) — Add second agent instance (`vol_desk_recommend: Agent[DeskDeps, VolatilityAssessment]`) + `run_vol_desk_recommendation()` function.
- **`agents/_toolsets.py`** — Add `build_synthesis_toolset()` for synthesis agent.
- **`agents/_parsing.py`** — Add `build_cleaned_domain_assessment()` helper. Preserve all render functions and `PROMPT_RULES_APPENDIX`. Move reusable functions (`build_market_context`, `extract_agent_predictions`, context renderers) to survive orchestrator deletion.
- **`agents/__init__.py`** — Replace debate exports with recommendation exports.
- **`data/repository.py`** — Add `RecommendationMixin` to mixin composition.
- **`models/__init__.py`** — Re-export new recommendation models.
- **`models/enums.py`** — All needed enums already exist. No new enums required (DeskType, SignalDirection, SpreadType, VolRegime, IVTermStructureShape, ValuationSignal all present).
- **`cli/commands.py`** — Rewrite `debate` command to use `run_recommendation()` instead of `run_debate()`.
- **`api/routes/debate.py`** — Rewrite routes to use `run_recommendation()`.
- **`reporting/debate_export.py`** — Adapt to `RecommendationResult` shape instead of `DebateResult`.

## Potential Conflicts

- **`_parsing.py` shared code**: Contains both debate-specific code (DebateDeps, DebateResult, debate-specific cleaners) and reusable code (context renderers, PROMPT_RULES_APPENDIX, strip_think_tags). Must carefully preserve reusable code when deleting debate-specific code. **Mitigation**: Epic C moves reusable functions before Epic D deletes debate code.

- **`orchestrator.py` critical functions**: `build_market_context()` (~200 lines), `extract_agent_predictions()`, `compute_citation_density()`, `synthesize_verdict()`, context rendering helper calls are all in orchestrator.py. The new recommendation orchestrator needs `build_market_context` and `extract_agent_predictions`. **Mitigation**: Move reusable functions to `_parsing.py` or a new shared module before deleting orchestrator.py.

- **Learning module `agent_predictions` queries**: `tune_vote_weights()` and `get_agent_accuracy()` query `agent_predictions` without protocol filtering. After cutover, new predictions use `recommendation_protocol='unified_v1'` while old ones are `'debate_v1'`. **Mitigation**: Migration 037 adds `recommendation_protocol` column with backfill; learning queries add `WHERE recommendation_protocol = 'unified_v1'` filter.

- **Test suite disruption**: ~50-80 existing debate tests reference `run_debate()`, `DebateDeps`, `DebateResult`, `synthesize_verdict()` — all must be rewritten or removed in Epic D. **Mitigation**: Write new tests in Epics A-C before deleting old tests in Epic D.

- **`DebateMixin` preserved for backward compat**: `GET /api/debate/{id}` must check both `ai_theses` (old) and `recommendation_results` (new) tables. `DebateMixin` stays read-only. **Mitigation**: Separate concern — don't delete DebateMixin methods that read old data.

- **`DeskDeps` field additions**: Adding `ticker_score`, `contracts`, `market_context` as optional fields with defaults is backward-compatible since all callers use keyword args (verified — 40+ construction sites, ALL keyword args). No conflict.

- **Config field removal**: Removing `enable_volatility_agent`, `enable_rebuttal`, `phase1_parallelism`, `phase1_batch_delay` from `DebateConfig` — must verify no consumers remain after debate code deletion. **Mitigation**: Grep for field usage before removal in Epic D.

## Open Questions

1. **`build_market_context()` relocation**: This ~200-line function lives in `orchestrator.py`. Where does it move? Options: (a) into `_parsing.py` (already has render functions), (b) new `agents/_context.py` module. Either works — PRD doesn't specify.

2. **`constraints.py` fate**: PRD says "keep as pre-check — inject constraint_warnings into DeskDeps". But DeskDeps currently has no `constraint_warnings` field. Should it be added to DeskDeps or passed separately to the recommendation orchestrator? PRD leans toward DeskDeps extension.

3. **Frontend `DebateResultPage.vue` adaptation**: PRD says "adapt to new data shape but no UX redesign" and marks it out of scope for detailed spec. The frontend renders debate panels (bull, bear, risk, etc.) — it will need to render domain assessments + position recommendation instead. This needs a follow-up frontend task.

4. **WebSocket progress events**: Current debate WebSocket uses `DebatePhase` enum (TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN). New system runs all 6 desks in parallel + synthesis. Progress callback pattern needs adaptation (parallel progress vs sequential phases).

5. **E2E test impact**: 107 Playwright E2E tests — some may test debate flow end-to-end. Need to assess which E2E tests break and plan rewrites.

## Recommended Architecture

The PRD's architecture is well-designed and validated against Context7. Key architectural decisions are sound:

1. **Dual-instance pattern** (per desk) — PydanticAI enforces single output_type per Agent. Two instances sharing toolsets is the cleanest solution.
2. **Discriminated union** (`AnyAssessment`) — Pydantic v2 `Discriminator("desk")` enables polymorphic round-trip through SQLite JSON storage.
3. **`asyncio.Semaphore`** for parallelism control — `desk_parallelism` config gates concurrent LLM calls.
4. **Forward-only analytics** — clean separation avoids fragile normalization between debate and recommendation data.
5. **Migration 037** — next sequential number confirmed (latest is 036).

**Reusable code extraction strategy** (critical for Epic C):
```
orchestrator.py ──extract──> _parsing.py or _context.py:
  - build_market_context()
  - extract_agent_predictions()
  - compute_citation_density()
  - _build_model_settings()
  - _format_agent_outputs() (for contrarian context)
```

**DeskDeps extension** is safe — verified all 40+ construction sites use keyword args.

## Test Strategy Preview

- **Existing test patterns**: `tests/unit/agents/test_*.py` — each debate agent has unit tests using `TestModel` + `models.ALLOW_MODEL_REQUESTS = False`. Desk agents have similar test files (`test_*_desk.py`).
- **Test file naming**: `test_{module_name}.py` convention throughout.
- **Mocking**: `TestModel` for LLM responses (no real API calls), `AsyncMock` for services, in-memory SQLite for persistence.
- **Parametrized tests**: Heavy use of `@pytest.mark.parametrize` for model validation edge cases.
- **Fixture patterns**: `@pytest.fixture` for service instances, `DeskDeps` construction helpers (`_make_deps()`).
- **Test tiers**: `@pytest.mark.critical` for pre-commit, `@pytest.mark.exhaustive` for nightly.
- **E2E**: Playwright in `tests/e2e/` — 17 spec files, 4 parallel workers, isolated DB per test.

**New test needs** (~80-100 new tests):
- Epic A: Model construction/validation/round-trip (~15-20), synthesis agent with TestModel (~5-10)
- Epic B: 6 desk recommendation agents with TestModel (~18-24), domain assessment cleaning (~6)
- Epic C: Orchestrator success/partial/full-failure/timeout (~12-16), persistence round-trip (~8-10)
- Epic D: CLI rendering (~4-6), API response schemas (~4-6), regression tests (existing should pass)

## Estimated Complexity

**XL** — 4 sequential epics, ~19-24 issues, touches 13+ modules, deletes 13 files, creates 12 new files, modifies ~15 files, rewrites CLI + API entry points, migration, 80-100 new tests, 50-80 tests to rewrite/remove.

Justification:
- Scope is large (entire agent subsystem replacement)
- But risk is manageable because: desk agents already work, patterns are established, changes are well-scoped per epic, verification gates between epics
- No new external dependencies
- No new architectural patterns (extends existing ones)
- Strictly sequential epics prevent merge conflicts
