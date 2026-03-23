---
name: agent-infra-model-routing
status: backlog
created: 2026-03-22T16:13:36Z
progress: 0%
prd: .claude/prds/agent-infrastructure-evolution.md
parent_epic: agent-infrastructure-evolution
branch: epic/agent-infrastructure-evolution
depends_on:
  - unified-agent-system
github: https://github.com/jobu711/options_arena/issues/673
---

# Epic: agent-infra-model-routing

## Overview

Route each desk agent to an appropriate LLM model tier based on task complexity.
Simple tickers (clear trend, high liquidity) use cheaper/faster models; complex
tickers (ambiguous signals, earnings proximity, low liquidity) use more capable
models. Track per-desk timing, token usage, and cost for pipeline observability.

## Scope Boundary

### In Scope
- `ModelTier` StrEnum (FAST, STANDARD, PREMIUM)
- `route_model_tier()` — complexity-based model selection per desk
- `_assess_complexity()` — score from MarketContext + TickerScore fields
- `build_model_for_tier()` — construct PydanticAI model for tier
- `DeskMetrics` frozen model (desk, status, duration_ms, model_used, token_usage)
- `AssessmentSummary` frozen model (direction_votes, avg_confidence, disagreement_desks, risk_flags, data_completeness)
- `RecommendationCost` frozen model (total_tokens, total_cost_usd, per_desk breakdown)
- Extend `RecommendationResult` with `desk_metrics`, `assessment_summary`, and cost fields
- Config: `RoutingConfig` (enable_model_routing, thresholds, tier model names)
- Cost estimation via token count x config-driven pricing map
- CLI: `--cost-summary` flag on debate command
- API: cost analytics endpoint

### Out of Scope (handled by sibling epics)
- Eval framework (agent-infra-eval-harness)
- Structured tool responses (agent-infra-tool-response)
- Strategy rule confidence decay (agent-infra-learning-decay)

## Architecture Decisions

- **Opt-in routing**: `enable_model_routing: bool = False` on config — default is uniform model (backward compatible)
- **Risk desk always STANDARD+**: Safety-critical assessment never uses FAST tier
- **Synthesis always PREMIUM**: Final recommendation warrants most capable model
- **Complexity heuristics from MarketContext**: completeness_ratio, earnings proximity, conflicting indicators, extreme IV, low liquidity
- **Cost is estimated, not billed**: Groq has no per-request cost API — use token counts x published pricing from config

## Technical Approach

### Model Routing (`agents/model_routing.py`)
- `ModelTier` enum: FAST (reduced budget), STANDARD (full budget), PREMIUM (extended thinking)
- `_assess_complexity(context, ticker_score)` → float 0.0-1.0
- `route_model_tier(desk, context, config)` → ModelTier
- `build_model_for_tier(tier, config)` → PydanticAI Model

### Observability Models (`models/recommendation.py`)
- `DeskMetrics`: desk, status, duration_ms, model_used, token_usage
- `AssessmentSummary`: direction_votes, avg_confidence, disagreement_desks, risk_flags, data_completeness — computed between Phase 1 (desks) and Phase 2 (synthesis), injected into synthesis prompt
- `RecommendationCost`: total_tokens, total_cost_usd, per_desk costs, tier distribution
- Extend `RecommendationResult` with `desk_metrics: list[DeskMetrics]`, `assessment_summary: AssessmentSummary | None`

### Config (`models/config.py`)
- `RoutingConfig` nested on `DebateConfig`:
  - `enable_model_routing: bool = False`
  - `complexity_threshold_fast: float = 0.3`
  - `complexity_threshold_premium: float = 0.7`
  - `cost_per_million_tokens: dict[str, float]` — pricing map

### Orchestrator Integration
- Per-desk model selection before `asyncio.gather` in recommendation orchestrator
- Accumulate `DeskMetrics` during pipeline execution
- Compute `RecommendationCost` after all desks complete

### CLI + API
- `options-arena debate AAPL --cost-summary` — show per-desk cost breakdown
- `GET /api/analytics/recommendation-costs` — cost trend over time

## Task Breakdown Preview
- [ ] Models + enums: `ModelTier`, `DeskMetrics`, `RecommendationCost`, `RoutingConfig`
- [ ] Complexity assessment: `_assess_complexity()` with MarketContext heuristics
- [ ] Model routing: `route_model_tier()` + `build_model_for_tier()`
- [ ] Orchestrator integration: per-desk model selection + metrics accumulation
- [ ] CLI + API: cost-summary flag, analytics endpoint
- [ ] Tests: complexity scenarios, tier selection, cost computation

## Dependencies
- unified-agent-system (recommendation orchestrator must exist for integration)

## Success Criteria
- `route_model_tier()` correctly routes 3 tiers based on complexity score
- Batch recommendations show measurable cost reduction (>30%) with routing enabled
- `RecommendationResult` includes per-desk `DeskMetrics` with timing and status
- `--cost-summary` shows per-desk cost breakdown in CLI
- All tests pass: `ruff check`, `pytest`, `mypy --strict`

## Tasks Created
- [ ] #679 - Models, Enums, and Config for Model Routing (parallel: true)
- [ ] #681 - Complexity Assessment and Model Routing Logic (parallel: false, depends: #679)
- [ ] #682 - Orchestrator Integration — Per-Desk Routing and Metrics (parallel: false, depends: #679, #681)
- [ ] #683 - CLI Cost Summary and API Cost Analytics Endpoint (parallel: false, depends: #682)

Total tasks: 4
Parallel tasks: 1 (#679 only)
Sequential tasks: 3 (#681 → #682 → #683)
Estimated total effort: 12-16 hours

## Test Coverage Plan
Total test files planned: 5
Total test cases planned: ~40

## Estimated Effort
- 4 tasks
- ~300-500 LOC new
