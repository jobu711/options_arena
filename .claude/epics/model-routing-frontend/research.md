# Research: model-routing-frontend

## PRD Summary

Add a collapsible Dashboard panel with two sections: (1) runtime model routing configuration (enable toggle, threshold sliders, model inputs, cost map), and (2) per-recommendation cost breakdown table showing which tier/model each desk used with token counts. Backend uses a session-only `app.state` overlay pattern to avoid mutating `AppSettings`. Requires persisting `DeskMetrics` to the DB (new migration 040).

## Relevant Existing Modules

- `api/routes/config.py` — GET-only config endpoint returning `ConfigResponse` (4 fields). Will add PUT/DELETE for routing overlay.
- `api/routes/analytics.py` — `GET /api/analytics/recommendation-costs` endpoint returning `RecommendationCostSummary` (ticker, tokens, duration). Will expand with per-desk details.
- `api/routes/debate.py` — Calls `run_recommendation()` with `settings` (AppSettings). Integration point for routing override resolution. Single debate at line 257, batch at line 385.
- `api/schemas.py` — ~970 lines. `ConfigResponse` at line 755, `RecommendationCostSummary` at line 954.
- `api/app.py` — `lifespan()` initializes all services on `app.state`. Will add `routing_override = None`.
- `api/deps.py` — 6 dependency providers. Will add `get_routing_override()`.
- `data/_recommendation.py` — `RecommendationRow` dataclass (30 fields, line 23), `save_recommendation()` (29-column INSERT, line 98). No `desk_metrics_json` column.
- `models/recommendation.py` — `DeskMetrics` (line 162, frozen, 7 fields), `RecommendationResult` (line 315, has `desk_metrics: list[DeskMetrics]`), `RecommendationCost` (line 212).
- `models/config.py` — `RoutingConfig` (line 252, 6 fields with validators), nested on `DebateConfig.routing` (line 344).
- `agents/recommendation_orchestrator.py` — `_run_desk()` at line 548, desk metrics built at line 571. `_compute_recommendation_cost()` at line 339.
- `web/src/pages/DashboardPage.vue` — Loads config, trending, recent debates on mount. Will add routing panel and cost table.
- `web/src/types/config.ts` — 7-line `ConfigResponse` interface. Will expand.

## Existing Patterns to Reuse

- **PUT endpoint pattern**: `routes/learning.py` lines 136-148 — `PUT /playbook/{rule_id}` with Path params, Query params, repo DI, rate limiting. Follow this for `PUT /api/config/routing`.
- **Config endpoint pattern**: `routes/config.py` — thin wrapper, safe values only, `Depends(get_settings)`.
- **JSON serialization in persistence**: `save_recommendation()` uses `model_dump(mode="json")` for complex fields (assessments, key_factors). Same pattern for `desk_metrics_json`.
- **Dashboard data loading**: `DashboardPage.vue` lines 48-55 — `Promise.all()` with multiple `api<T>()` calls, `.catch()` fallbacks for optional data.
- **PrimeVue collapsible**: `Panel toggleable` for collapsible cards (Context7-verified).
- **PrimeVue form controls**: `ToggleSwitch` (boolean), `Slider` (ranges), `InputNumber` (with min/max/fractionDigits).
- **`model_copy(update={...})`**: Pydantic v2 method for creating modified copies of BaseModel instances without mutating the original. Context7-verified: update data is NOT validated by model_copy — validate at PUT endpoint.
- **ALTER TABLE ADD COLUMN**: 30+ existing migrations use this pattern. Migration 040 follows the same convention.

## Existing Code to Extend

- **`api/schemas.py` `ConfigResponse`** (line 755): Add `routing: RoutingConfigResponse` field. Currently 4 fields.
- **`api/schemas.py` `RecommendationCostSummary`** (line 954): Add `desk_details: list[DeskCostDetail]` field. Currently 5 fields.
- **`api/routes/config.py`** (30 lines): Add PUT and DELETE handlers. Currently only GET.
- **`api/app.py` `lifespan()`**: Add `app.state.routing_override = None` initialization.
- **`api/deps.py`**: Add `get_routing_override()` provider.
- **`api/routes/debate.py`**: Resolve routing override before calling `run_recommendation()`.
- **`data/_recommendation.py` `save_recommendation()`** (line 98): Add `desk_metrics_json` to INSERT.
- **`data/_recommendation.py` `RecommendationRow`** (line 23): Add `desk_metrics_json: str` field.
- **`data/_recommendation.py` `_row_to_recommendation_row()`**: Map new column to dataclass.
- **`web/src/types/config.ts`**: Add `RoutingConfig`, `DeskCostDetail`, `RecommendationCostDetail` interfaces.
- **`web/src/pages/DashboardPage.vue`**: Import and render new `ModelRoutingPanel` and `RecommendationCostTable` components.

## Potential Conflicts

### Critical: DeskMetrics tokens are always zero

**Problem**: `recommendation_orchestrator.py` line 571-577 — `DeskMetrics` is constructed with `input_tokens` and `output_tokens` at their default value of 0. The desk runners (`run_trend_desk_recommendation()`, etc.) return only the typed assessment (`TrendAssessment`), discarding the PydanticAI `RunResult` which contains the `RunUsage` with actual token counts.

**Impact**: Even after persisting `desk_metrics_json`, the per-desk token counts will all be zero, making cost breakdown useless.

**Mitigation**: The desk runners need to return `RunUsage` alongside the assessment. Two options:
1. Change desk runner return type to `tuple[Assessment, RunUsage]` — breaks the `_DeskRunner` protocol
2. Have the orchestrator's `_run_desk()` call `agent.run()` directly instead of going through the desk runner wrapper — more invasive

**Recommendation**: Option 1 is cleaner. Update `_DeskRunner` protocol, update each desk's `run_*_desk_recommendation()` to return `(assessment, result.usage())`, update orchestrator to extract usage and populate `DeskMetrics.input_tokens`/`output_tokens`. This is a prerequisite for meaningful cost data.

### Minor: total_usage is always empty

**Problem**: `recommendation_orchestrator.py` line 672 — `total_usage=RunUsage()` creates an empty usage object with zero tokens. The `RecommendationResult.total_usage` field has never had real data.

**Mitigation**: Once per-desk tokens are captured, aggregate them into `total_usage`. This is a natural follow-on from fixing the token attribution gap.

### Minor: Cost computed only when routing enabled

**Problem**: `_compute_recommendation_cost()` is only called when `routing_config.enable_model_routing` is True (line 660-663). When routing is disabled, `RecommendationResult.cost` is `None`.

**Mitigation**: Compute cost always (all runs use a model with a known cost rate). The `cost_per_million_tokens` map already has entries for the default model. Change the condition to always compute cost.

### Minor: ConfigResponse schema change

**Problem**: Expanding `ConfigResponse` with a `routing` field changes the API response shape. Any frontend code reading `GET /api/config` must handle the new field.

**Mitigation**: Adding a new field is backward-compatible (extra fields are ignored by consumers that don't use them). Frontend already reads `config` and destructures only what it needs.

## Open Questions (Resolved)

1. **Token attribution scope**: RESOLVED — included in this epic as Wave 1. Desk runners will return `(assessment, RunUsage)`, orchestrator populates `DeskMetrics` tokens.

2. **Cost computation when routing is disabled**: RESOLVED — always compute cost. The `cost_per_million_tokens` map has entries for the default model, so cost is meaningful regardless of routing state.

3. **Migration numbering**: Agent 2 confirmed 039 is the latest migration. Confirm no 040 file exists from another in-progress branch before creating it.

## Recommended Architecture

### Backend (5 files modified + 1 new migration)

1. **Migration 040**: `ALTER TABLE recommendation_results ADD COLUMN desk_metrics_json TEXT NOT NULL DEFAULT '[]'`
2. **`_recommendation.py`**: Serialize `desk_metrics` in `save_recommendation()`, add field to `RecommendationRow`, deserialize in `_row_to_recommendation_row()`
3. **`schemas.py`**: Add `RoutingConfigUpdate`, `RoutingConfigResponse`, `DeskCostDetail`. Expand `ConfigResponse` and `RecommendationCostSummary`.
4. **`routes/config.py`**: Add PUT (validate → construct `RoutingConfig` → store on `app.state`) and DELETE (clear overlay) handlers
5. **`routes/analytics.py`**: Expand cost endpoint to deserialize `desk_metrics_json` into `DeskCostDetail` list
6. **`routes/debate.py`**: Resolve `app.state.routing_override` → `model_copy(update={"routing": override})` before calling `run_recommendation()`
7. **`app.py`**: Add `app.state.routing_override = None` in `lifespan()`
8. **`deps.py`**: Add `get_routing_override()` provider

### Frontend (2 new components + 2 modified files)

1. **`ModelRoutingPanel.vue`**: Collapsible `Panel` with `ToggleSwitch`, `Slider` (thresholds), `InputText` (models), `InputNumber` (costs), Apply/Reset buttons
2. **`RecommendationCostTable.vue`**: `DataTable` with expandable rows — top level shows ticker/timestamp/total, expanded shows per-desk breakdown
3. **`DashboardPage.vue`**: Import and render both new components
4. **`types/config.ts`**: Add TypeScript interfaces

### Wave 1: Token Attribution (included in epic)

- Update `_DeskRunner` protocol to return `tuple[DomainAssessment, RunUsage]`
- Update all 6 desk runner functions to return `(assessment, result.usage())`
- Update orchestrator `_run_desk()` to populate `DeskMetrics.input_tokens`/`output_tokens`
- Aggregate into `total_usage` on `RecommendationResult`
- Remove `enable_model_routing` gate on `_compute_recommendation_cost()` — always compute cost

## Test Strategy Preview

### Existing Test Patterns

- **API route tests**: `tests/unit/api/` — use `httpx.AsyncClient` with `ASGITransport`, mock repos via `app.dependency_overrides`
- **Schema tests**: `tests/unit/api/test_schemas.py` — construction, validation, serialization
- **Data layer tests**: `tests/unit/data/` — in-memory SQLite (`:memory:`), real migrations, round-trip fidelity
- **Frontend E2E**: `tests/e2e/` — Playwright, 17 spec files, 4 parallel workers

### New Tests Needed

| Test File | Type | Coverage |
|-----------|------|----------|
| `tests/unit/api/test_config_routing_routes.py` | Unit | PUT validation, DELETE reset, GET with/without override |
| `tests/unit/api/test_routing_override_integration.py` | Integration | Override resolution in debate route |
| `tests/unit/data/test_desk_metrics_persistence.py` | Unit | Save/read desk_metrics_json round-trip |
| `tests/unit/api/test_recommendation_costs_expanded.py` | Unit | Cost endpoint with desk_details |
| `tests/e2e/model-routing.spec.ts` | E2E | Toggle, sliders, apply, reset, cost table |

### Mocking Strategy

- Config route tests: mock `app.state.routing_override` directly
- Cost endpoint tests: mock `repo.get_recent_recommendations()` to return rows with/without `desk_metrics_json`
- Frontend E2E: MSW or API intercept for `/api/config` and `/api/analytics/recommendation-costs`

## Estimated Complexity

**M (Medium)** — 8 backend files, 2 new Vue components, 1 migration, ~5 test files. The core logic is straightforward (overlay pattern, JSON persistence, UI form). The token attribution gap is the only complex part, and it can be scoped as a prerequisite sub-epic or included as Wave 1.
