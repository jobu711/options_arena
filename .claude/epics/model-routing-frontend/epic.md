---
name: model-routing-frontend
status: completed
created: 2026-03-23T13:15:13Z
progress: 100%
prd: .claude/prds/model-routing-frontend.md
github: https://github.com/jobu711/options_arena/issues/696
---

# Epic: model-routing-frontend

## Overview

Add runtime model routing configuration and per-recommendation cost visibility to the Dashboard. Three waves of work: (1) fix token attribution so DeskMetrics has real token counts, (2) persist metrics and expose routing config via API, (3) build frontend components.

## Architecture Decisions

- **Runtime overlay pattern**: Store `RoutingConfig` override on `app.state.routing_override` (session-only). `AppSettings` stays immutable. Overlay resolved at the API layer via `model_copy(update={"routing": override})` before passing `DebateConfig` to the orchestrator.
- **Token attribution via return type change**: Update `_DeskRunner` protocol to return `tuple[DomainAssessment, RunUsage]`. Each desk runner returns `(assessment, result.usage())`. Orchestrator populates `DeskMetrics.input_tokens`/`output_tokens`.
- **Always compute cost**: Remove `enable_model_routing` gate on `_compute_recommendation_cost()`. Cost is meaningful even with default model (map has entry for `llama-3.3-70b-versatile`).
- **JSON persistence for desk metrics**: New `desk_metrics_json TEXT` column (migration 040). Serialized via `model_dump(mode="json")`, matching the existing `assessments_json` pattern.
- **No new Pinia store**: Component-local state in `ModelRoutingPanel.vue` is sufficient for a single dashboard card. No shared config store needed.

## Technical Approach

### Wave 1: Token Attribution + Cost Always-On (agents/)
- Update `_DeskRunner` protocol in orchestrator to expect `tuple[DomainAssessment, RunUsage]`
- Update all 6 desk runner functions (`run_*_desk_recommendation()`) to return `(cleaned_assessment, result.usage())` instead of just the assessment. Fallback paths return `RunUsage()` (empty).
- Update `_run_desk()` to extract `RunUsage`, populate `DeskMetrics(input_tokens=usage.input_tokens, output_tokens=usage.output_tokens)`
- Aggregate per-desk usage into `RecommendationResult.total_usage`
- Remove `if routing_config.enable_model_routing` gate on `_compute_recommendation_cost()` — always compute
- Update existing orchestrator tests

### Wave 2: Persistence + API (data/, api/)
- Migration 040: `ALTER TABLE recommendation_results ADD COLUMN desk_metrics_json TEXT NOT NULL DEFAULT '[]'`
- `_recommendation.py`: serialize `desk_metrics` in `save_recommendation()`, add `desk_metrics_json` to `RecommendationRow`, deserialize in `_row_to_recommendation_row()`
- `schemas.py`: Add `RoutingConfigUpdate`, `RoutingConfigResponse`, `DeskCostDetail`. Expand `ConfigResponse` and `RecommendationCostSummary`.
- `app.py`: Add `app.state.routing_override = None` in `lifespan()`
- `deps.py`: Add `get_routing_override()` provider
- `routes/config.py`: Add PUT (validate, construct `RoutingConfig`, store on `app.state`) and DELETE (clear overlay) handlers
- `routes/analytics.py`: Expand cost endpoint to include `desk_details` from `desk_metrics_json`
- `routes/debate.py`: Resolve override before calling `run_recommendation()`
- Backend tests for all new/modified endpoints and persistence

### Wave 3: Frontend (web/)
- `types/config.ts`: Add `RoutingConfig`, `DeskCostDetail`, `RecommendationCostDetail` interfaces
- `ModelRoutingPanel.vue`: Collapsible `Panel toggleable` with `ToggleSwitch`, `Slider` (thresholds), `InputText` (model names), `InputNumber` (cost map), Apply/Reset buttons
- `RecommendationCostTable.vue`: `DataTable` with expandable rows — top level shows ticker/timestamp/total cost, expanded shows per-desk tier/model/tokens/duration
- `DashboardPage.vue`: Import and render both components
- E2E tests

## Task Breakdown Preview

- [ ] Task 1: Token attribution — update desk runners to return RunUsage (6 desk files + orchestrator protocol)
- [ ] Task 2: Orchestrator — populate DeskMetrics tokens, aggregate total_usage, always compute cost
- [ ] Task 3: Token attribution tests — verify desk runners return real usage, orchestrator populates metrics
- [ ] Task 4: Migration 040 + persistence — desk_metrics_json column, save/read in _recommendation.py
- [ ] Task 5: API schemas — RoutingConfigUpdate, RoutingConfigResponse, DeskCostDetail, expand ConfigResponse + RecommendationCostSummary
- [ ] Task 6: API routes — PUT/DELETE /api/config/routing, expand GET /api/config, expand cost endpoint, routing override resolution in debate route
- [ ] Task 7: API + persistence tests — config routes, override integration, desk metrics round-trip, expanded costs
- [ ] Task 8: Frontend types + ModelRoutingPanel component
- [ ] Task 9: Frontend RecommendationCostTable component + DashboardPage integration
- [ ] Task 10: E2E tests + rebuild web/dist

## Dependencies

- **Internal (all exist)**: `RoutingConfig` (models/config.py:252), `DeskMetrics` (models/recommendation.py:162), `RecommendationResult.desk_metrics` (models/recommendation.py:327), `_compute_recommendation_cost()` (agents/recommendation_orchestrator.py:339), `ConfigResponse` (api/schemas.py:755), `RecommendationCostSummary` (api/schemas.py:954), `save_recommendation()` (data/_recommendation.py:98)
- **External**: None — no new packages

## Success Criteria (Technical)

1. `DeskMetrics.input_tokens`/`output_tokens` are non-zero for real LLM calls (verified in tests with `TestModel`)
2. `RecommendationResult.total_usage` aggregated from desk usage (not empty `RunUsage()`)
3. `RecommendationResult.cost` always populated (not gated on `enable_model_routing`)
4. `desk_metrics_json` round-trips through SQLite (save → read → deserialize → matching models)
5. PUT/DELETE `/api/config/routing` stores/clears overlay; GET returns resolved config with `is_override` flag
6. Routing override applied to `run_recommendation()` in debate route
7. Cost endpoint returns per-desk breakdown from stored metrics
8. Dashboard panel toggles routing, adjusts thresholds/models/costs, shows cost table
9. All existing tests pass (no regressions from desk runner return type change)
10. `ruff check`, `ruff format`, `mypy --strict` all clean

## Estimated Effort

- **10 tasks** across 3 waves
- **Critical path**: Wave 1 (token attribution) must complete before Wave 2 (persistence depends on real token data for meaningful tests). Wave 3 (frontend) depends on Wave 2 APIs.
- **Wave 1**: 3 tasks (desk runners + orchestrator + tests)
- **Wave 2**: 4 tasks (migration + schemas + routes + tests)
- **Wave 3**: 3 tasks (types + components + E2E)

## Tasks Created

- [ ] #697 - Update desk runners to return RunUsage (parallel: false)
- [ ] #699 - Orchestrator token attribution and always-compute cost (parallel: false, depends: #697)
- [ ] #700 - Wave 1 verification — token attribution integration tests (parallel: false, depends: #697, #699)
- [ ] #702 - Migration 040 + desk metrics persistence (parallel: true, depends: #699)
- [ ] #704 - API schemas for routing config and cost details (parallel: true, depends: #699)
- [ ] #698 - API routes — config routing overlay + expanded cost endpoint (parallel: false, depends: #702, #704)
- [ ] #701 - Wave 2 verification — API + persistence integration tests (parallel: false, depends: #698)
- [ ] #703 - Frontend types + ModelRoutingPanel component (parallel: true, depends: #698)
- [ ] #705 - Frontend RecommendationCostTable + DashboardPage integration (parallel: false, depends: #703)
- [ ] #706 - E2E tests + rebuild web/dist (parallel: false, depends: #701, #705)

Total tasks: 10
Parallel tasks: 3 (004+005 in Wave 2, 008 in Wave 3)
Sequential tasks: 7
Estimated total effort: 28-35 hours

## Test Coverage Plan

Total test files planned: 8
Total test cases planned: ~40

| Test File | Task | Cases |
|-----------|------|-------|
| tests/unit/agents/test_desk_runner_usage.py | #697 | 8 |
| tests/unit/agents/test_orchestrator_token_attribution.py | #699 | 6 |
| tests/unit/agents/test_token_attribution_integration.py | #700 | 4 |
| tests/unit/data/test_desk_metrics_persistence.py | #702 | 5 |
| tests/unit/api/test_routing_schemas.py | #704 | 11 |
| tests/unit/api/test_config_routing_routes.py | #698 | 6 |
| tests/unit/api/test_recommendation_costs_expanded.py | #698 | 3 |
| tests/unit/api/test_routing_override_integration.py | #701 | 4 |
| tests/e2e/model-routing.spec.ts | #706 | 6 |
