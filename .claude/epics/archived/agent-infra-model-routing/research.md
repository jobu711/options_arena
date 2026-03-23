# Research: agent-infra-model-routing

## PRD Summary

Route each desk agent to an appropriate LLM model tier (FAST/STANDARD/PREMIUM) based on
task complexity. Simple tickers (clear trend, high liquidity) use cheaper/faster models;
complex tickers (ambiguous signals, earnings proximity, low liquidity) use more capable
models. Track per-desk timing, token usage, and cost for pipeline observability. Parent
PRD: `agent-infrastructure-evolution`. Epic C of 5 sub-epics.

## Relevant Existing Modules

- `agents/model_config.py` — Current provider-based dispatch: `build_debate_model(config)` routes on `LLMProvider` enum (GROQ vs ANTHROPIC). Returns PydanticAI `Model`. Single model for all desks. Key functions: `_build_groq_model()`, `_build_anthropic_model()`, API key resolution.
- `agents/recommendation_orchestrator.py` — 4-phase pipeline: Phase 0 (context build), Phase 1 (6 desks in parallel via `asyncio.gather`), Phase 2 (synthesis), Phase 3 (persist). Currently calls `build_debate_model()` once, passes same model to all agents.
- `agents/orchestrator.py` — Debate orchestrator (legacy path). Same single-model pattern. Both orchestrators are integration targets.
- `models/recommendation.py` — `RecommendationResult` (7 fields: context, assessments, recommendation, total_usage, duration_ms, is_fallback, citation_density). `DomainAssessment` hierarchy (6 subclasses). `PositionRecommendation` (21 frozen fields).
- `models/config.py` — `DebateConfig` (22 fields including provider, model names, timeouts, parallelism). `AgencyConfig` (per-desk tool budgets). `AppSettings` root with nested configs.
- `models/enums.py` — `LLMProvider(StrEnum)`, `DeskType(StrEnum)` (7 members), `SignalDirection`.
- `models/analysis.py` — `MarketContext` (~65 fields, ~50 optional). `completeness_ratio()` already exists for debate gating (<0.4 → fallback).
- `models/scan.py` — `TickerScore` with `composite_score`, `direction`, `signals: IndicatorSignals` (75 indicator fields).

## Existing Patterns to Reuse

### 1. Provider-Based Model Dispatch
`model_config.py` already has `match config.provider:` dispatch. Extend with tier parameter:
```python
def build_model_for_tier(tier: ModelTier, config: DebateConfig) -> Model:
    # Select model name based on tier, then dispatch on provider
```

### 2. RunUsage Token Accumulation
PydanticAI `RunUsage` already tracks `input_tokens`, `output_tokens`, `requests`, `tool_calls`. Orchestrator accumulates via `result1.usage() + result2.usage()`. Ready for cost calculation.

### 3. Per-Desk Config Pattern
`AgencyConfig` already supports per-desk tool budgets (`risk_tool_budget=8`, `research_tool_budget=13`). Same pattern for model tier overrides.

### 4. Frozen Assessment Hierarchy
`DomainAssessment` base + 6 subclasses with discriminated union. Same pattern for `DeskMetrics`.

### 5. Never-Raises Orchestration
Both `run_debate()` and `run_recommendation()` catch all exceptions → fallback. Cost tracking must survive error paths.

### 6. Completeness Ratio
`MarketContext.completeness_ratio()` already scores data quality (0.0-1.0). Direct input to complexity assessment.

## Existing Code to Extend

- `agents/model_config.py` — Add `route_model_tier()`, `build_model_for_tier()`, `_assess_complexity()`. Current `build_debate_model()` becomes fallback for non-routed calls.
- `models/recommendation.py` — Add `DeskMetrics` and `RecommendationCost` frozen models. Extend `RecommendationResult` with `desk_metrics: list[DeskMetrics] = []` and optional cost.
- `models/config.py` — Add `RoutingConfig(BaseModel)` nested on `DebateConfig` with `enable_model_routing`, thresholds, tier model names, cost-per-million-tokens map.
- `models/enums.py` — Add `ModelTier(StrEnum)` with FAST, STANDARD, PREMIUM.
- `agents/recommendation_orchestrator.py` — Wire per-desk model selection before `asyncio.gather` in Phase 1. Accumulate `DeskMetrics` per desk. Compute `RecommendationCost` after Phase 2.
- `api/routes/debate.py` — Include cost breakdown in recommendation result response.
- `cli/commands.py` — Add `--cost-summary` flag to debate command.

## Potential Conflicts

### 1. RecommendationResult is Frozen
Adding fields to `RecommendationResult` requires including them at construction time. The model uses `ConfigDict(frozen=True)` indirectly (via `arbitrary_types_allowed=True` for `RunUsage`). New `desk_metrics` field must have default (empty list) for backward compatibility with existing construction sites.

### 2. Orchestrator Not Yet Wired to CLI Debate
The `debate` CLI command currently runs `run_debate()` (debate orchestrator), not `run_recommendation()` (recommendation orchestrator). Model routing primarily targets the recommendation path. Cutover epic will switch CLI to recommendation path. For now, routing integrates into recommendation orchestrator; debate orchestrator gets routing as optional enhancement.

### 3. Groq Model Tier Availability
Groq's model catalog changes. FAST tier assumes a cheaper model (e.g., `llama-3.1-8b-instant`). Config-driven model names avoid hardcoding, but tier availability should be validated at startup.

### 4. Cost Estimation Accuracy
Groq has no per-request cost API. Cost is estimated from token counts × config-driven pricing. Estimates may drift from actual billing. Mitigation: pricing map is config-driven and user-updatable.

### 5. Migration Numbering
Latest migration is 037 (`recommendation_results`). Migration numbers assigned across sibling epics: 038 (learning-decay), 039 (eval-harness), **040 reserved for model-routing** (cost tracking, if needed).

## Open Questions

1. **FAST tier model**: Which Groq model for FAST tier? `llama-3.1-8b-instant` is fast but less capable. Is quality acceptable for simple tickers? (Requires eval harness to measure — chicken-and-egg with Epic A.)
2. **Anthropic PREMIUM tier**: Should PREMIUM use Anthropic Claude when available, or a larger Groq model? Cost difference is significant. Config should support either.
3. **Per-desk tier overrides**: Should individual desks have hardcoded tier floors (Risk=STANDARD+, Synthesis=PREMIUM), or should this be fully config-driven?
4. **Cost persistence**: Should per-recommendation cost be stored in SQLite for analytics? If so, migration 040 is reserved. Or add cost columns to existing `recommendation_results` table.
5. **Routing in debate orchestrator**: Should `run_debate()` (legacy path) also get routing, or only `run_recommendation()`? Cutover will eliminate debate path, but timing is uncertain.

## Recommended Architecture

### New Module Structure
```
agents/model_routing.py         # NEW: _assess_complexity(), route_model_tier(), build_model_for_tier()
models/enums.py                 # EXTEND: ModelTier(StrEnum)
models/config.py                # EXTEND: RoutingConfig on DebateConfig
models/recommendation.py        # EXTEND: DeskMetrics, RecommendationCost
agents/recommendation_orchestrator.py  # MODIFY: per-desk routing + metrics
api/routes/debate.py            # MODIFY: cost in response
cli/commands.py                 # MODIFY: --cost-summary flag
```

### Complexity Assessment Design
```python
def _assess_complexity(context: MarketContext, ticker_score: TickerScore | None) -> float:
    """0.0 = simple (clear signals, high data), 1.0 = complex (ambiguous, sparse data)."""
    score = 0.0
    # Low data completeness = more inference needed
    if context.completeness_ratio() < 0.6:
        score += 0.3
    # Earnings within 7 days = event uncertainty
    if context.next_earnings and (context.next_earnings - date.today()).days <= 7:
        score += 0.2
    # Conflicting indicators (overbought but no trend)
    if context.rsi_14 and context.adx:
        if context.rsi_14 > 70 and context.adx < 20:
            score += 0.2
    # Extreme IV regime
    if context.iv_rank is not None and context.iv_rank > 80:
        score += 0.15
    # Low liquidity from chain spread
    if ticker_score and ticker_score.signals.chain_spread_pct is not None:
        if ticker_score.signals.chain_spread_pct > 10.0:
            score += 0.15
    return min(score, 1.0)
```

### Model Tier Flow
```
MarketContext + TickerScore
    ↓
_assess_complexity() → float (0.0-1.0)
    ↓
route_model_tier(desk, complexity, config) → ModelTier
    ↓  (Risk floor: STANDARD, Synthesis: PREMIUM)
build_model_for_tier(tier, config) → PydanticAI Model
    ↓
agent.run(model=model, ...)
    ↓
Accumulate DeskMetrics (timing, tokens, tier, status)
    ↓
Compute RecommendationCost from accumulated metrics
```

## Test Strategy Preview

### Existing Test Patterns
- `tests/unit/agents/` — Agent tests use `TestModel` from PydanticAI. Model construction tested separately.
- `tests/unit/models/` — Pydantic model validation tests (frozen, validators, serialization).
- `tests/unit/agents/test_model_config.py` — Tests for `build_debate_model()`, API key resolution.
- Parametrized tests for enum values, config defaults, threshold boundaries.

### Planned Test Files
1. `tests/unit/agents/test_model_routing.py` — Complexity scenarios, tier selection, desk overrides
2. `tests/unit/models/test_desk_metrics.py` — DeskMetrics/RecommendationCost validation, frozen, serialization
3. `tests/unit/models/test_routing_config.py` — RoutingConfig defaults, threshold validation
4. `tests/unit/agents/test_recommendation_orchestrator_routing.py` — Integration: per-desk model selection in pipeline
5. `tests/unit/api/test_cost_analytics.py` — Cost endpoint response format

### Mocking Strategy
- `TestModel` for PydanticAI agent calls (no real LLM)
- Mock `MarketContext` with parametrized completeness ratios
- Mock `TickerScore` with parametrized indicator combinations
- Config fixtures with routing enabled/disabled

## Estimated Complexity

**Medium** — 4 tasks, ~300-500 LOC new, ~200 LOC modified.

Justification:
- Core routing logic is straightforward (complexity heuristics → tier → model dispatch)
- Existing patterns (`build_debate_model`, `RunUsage`, `DebateConfig`) provide strong foundation
- No new external dependencies
- Primary risk is integration with recommendation orchestrator pipeline (must not break never-raises contract)
- Secondary risk is Groq model tier availability (config-driven mitigation)
- Config-driven design means no hardcoded model names
