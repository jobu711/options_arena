---
name: model-routing-frontend
description: Dashboard panel for runtime model routing configuration and per-recommendation cost metrics
status: planned
created: 2026-03-23T12:37:16Z
---

# PRD: model-routing-frontend

## Executive Summary

Add a collapsible dashboard panel that lets users configure model routing settings at runtime and view per-recommendation cost breakdowns. Currently, model routing is configured exclusively via environment variables and has zero frontend visibility. This feature exposes the full `RoutingConfig` (enable/disable, complexity thresholds, model names per tier, cost-per-million-tokens map) in the Dashboard UI and shows a detailed cost table for recent recommendations.

## Problem Statement

### What problem are we solving?

Model routing (`RoutingConfig`) controls which LLM tier (FAST/STANDARD/PREMIUM) each desk agent uses during recommendation analysis. It directly impacts cost and quality. However:

1. **No visibility** — the frontend has zero awareness of model routing. Users can't see which tier each desk used or what it cost.
2. **No runtime control** — changing routing requires setting environment variables and restarting the server. There's no way to experiment with thresholds or toggle routing on/off during a session.
3. **No cost insight** — the existing `/api/analytics/recommendation-costs` endpoint returns only aggregate token counts, not per-desk tier/model/token breakdowns.

### Why is this important now?

Model routing was built in the agent-infra-model-routing epic (PR #695) but shipped with `enable_model_routing: bool = False` as default. The infrastructure is fully wired in the orchestrator but there's no user-facing way to activate it, tune it, or observe its effects. This is the natural next step to make routing usable.

## User Stories

### US-1: Toggle model routing on/off
**As a** user on the Dashboard, **I want to** enable or disable model routing with a toggle switch **so that** I can experiment with cost-optimized vs uniform model selection without restarting the server.
**Acceptance criteria**: Toggle sends `PUT /api/config/routing`, next recommendation run uses the new setting. Toggle state reflects current server state on page load.

### US-2: Configure routing thresholds and models
**As a** user, **I want to** adjust complexity thresholds (FAST/PREMIUM cutoffs), model names per tier, and cost-per-million-tokens values **so that** I can fine-tune the cost/quality tradeoff.
**Acceptance criteria**: Sliders for thresholds (0.0-1.0), text inputs for model names, editable cost map. "Apply" button sends `PUT /api/config/routing`. Validation prevents `fast >= premium` threshold.

### US-3: Reset routing to defaults
**As a** user, **I want to** reset routing config to the server's startup defaults (env vars / hardcoded) **so that** I can undo runtime experiments.
**Acceptance criteria**: "Reset to Defaults" button sends `DELETE /api/config/routing`. UI refreshes to show base config with `is_override: false`.

### US-4: View per-recommendation cost breakdown
**As a** user, **I want to** see a table of recent recommendations showing which tier and model each desk used, token counts, duration, and estimated cost **so that** I can understand the cost impact of my routing settings.
**Acceptance criteria**: Table shows ticker, timestamp, per-desk rows (tier badge, model, input/output tokens, duration, status), total estimated cost. Empty state when no recommendations exist.

## Architecture & Design

### Chosen Approach: Runtime Config Overlay (Approach B)

A lightweight `RoutingConfig` overlay stored on `app.state.routing_override` (separate from `AppSettings`). The base `AppSettings` stays immutable as designed. The overlay is explicitly session-scoped — it resets on server restart. The recommendation orchestrator resolves "overlay or base config" at call time via the API layer, not in the orchestrator itself.

### Module Changes

| Module | Change | Files Affected |
|--------|--------|----------------|
| `api/routes/config.py` | Add `PUT /api/config/routing`, `DELETE /api/config/routing`, expand `GET /api/config` response | `routes/config.py` |
| `api/schemas.py` | Add `RoutingConfigUpdate`, `RoutingConfigResponse`, `DeskCostDetail` schemas | `schemas.py` |
| `api/deps.py` | Add `get_routing_override()` dependency provider | `deps.py` |
| `api/app.py` | Initialize `app.state.routing_override = None` in `lifespan()` | `app.py` |
| `api/routes/analytics.py` | Expand `RecommendationCostSummary` with `desk_details` | `routes/analytics.py` |
| `api/routes/debate.py` | Resolve routing override when building `DebateConfig` for `run_recommendation()` | `routes/debate.py` |
| `data/migrations/` | New migration `040_desk_metrics_json.sql` — adds `desk_metrics_json TEXT` column to `recommendation_results` | New file |
| `data/_recommendation.py` | Persist `desk_metrics` list as JSON in new column; deserialize on read | `_recommendation.py` |
| `data/_recommendation.py` | Update `save_recommendation()` to serialize `desk_metrics` to JSON; update `_row_to_recommendation_row()` and `RecommendationRow` dataclass to include `desk_metrics_json` | `_recommendation.py` |
| `agents/recommendation_orchestrator.py` | Update `_DeskRunner` protocol and `_run_desk()` to capture `RunUsage` from desk agents, populate `DeskMetrics` tokens, aggregate into `total_usage`, always compute cost | `recommendation_orchestrator.py` |
| `agents/trend_desk.py` | Return `(assessment, result.usage())` from `run_trend_desk_recommendation()` | `trend_desk.py` |
| `agents/volatility_desk.py` | Return `(assessment, result.usage())` from `run_vol_desk_recommendation()` | `volatility_desk.py` |
| `agents/flow_desk.py` | Return `(assessment, result.usage())` from `run_flow_desk_recommendation()` | `flow_desk.py` |
| `agents/fundamental_desk.py` | Return `(assessment, result.usage())` from `run_fundamental_desk_recommendation()` | `fundamental_desk.py` |
| `agents/risk_desk.py` | Return `(assessment, result.usage())` from `run_risk_desk_recommendation()` | `risk_desk.py` |
| `agents/contrarian_desk.py` | Return `(assessment, result.usage())` from `run_contrarian_desk_recommendation()` | `contrarian_desk.py` |
| `web/src/types/config.ts` | Add `RoutingConfig`, `DeskCostDetail`, `RecommendationCostDetail` interfaces | `types/config.ts` |
| `web/src/pages/DashboardPage.vue` | Add `ModelRoutingPanel` and `RecommendationCostTable` components | `DashboardPage.vue` |
| `web/src/components/ModelRoutingPanel.vue` | New — routing settings form in collapsible card | New file |
| `web/src/components/RecommendationCostTable.vue` | New — per-recommendation cost breakdown table | New file |

**Boundary compliance**: Changes span `api/` (top-of-stack), `web/` (presentation), `data/` (persistence — new column + serialization), and `agents/` (token attribution + cost computation). No changes to `models/` (DeskMetrics and RecommendationResult already have the needed fields). The overlay is resolved at the API layer before passing `DebateConfig` to the orchestrator.

### Data Models

**Backend — `api/schemas.py`**:

```python
class RoutingConfigUpdate(BaseModel):
    """Request body for PUT /api/config/routing."""
    enable_model_routing: bool
    complexity_threshold_fast: float
    complexity_threshold_premium: float
    fast_model: str
    premium_model: str
    cost_per_million_tokens: dict[str, float]
    # Validators: thresholds in [0.0, 1.0], fast < premium, costs non-negative + finite

class RoutingConfigResponse(BaseModel):
    """Current resolved routing config with override indicator."""
    enable_model_routing: bool
    complexity_threshold_fast: float
    complexity_threshold_premium: float
    fast_model: str
    premium_model: str
    cost_per_million_tokens: dict[str, float]
    is_override: bool  # True = runtime override active

class DeskCostDetail(BaseModel):
    """Per-desk cost breakdown within a recommendation."""
    desk: str
    tier: str         # FAST / STANDARD / PREMIUM
    model_used: str
    input_tokens: int
    output_tokens: int
    duration_ms: int
    status: str       # SUCCESS / FALLBACK
```

Expand `ConfigResponse` with `routing: RoutingConfigResponse`.
Expand `RecommendationCostSummary` with `desk_details: list[DeskCostDetail]`.

**Frontend — `web/src/types/config.ts`**:

```typescript
interface RoutingConfig {
  enable_model_routing: boolean
  complexity_threshold_fast: number
  complexity_threshold_premium: number
  fast_model: string
  premium_model: string
  cost_per_million_tokens: Record<string, number>
  is_override: boolean
}

interface DeskCostDetail {
  desk: string
  tier: string
  model_used: string
  input_tokens: number
  output_tokens: number
  duration_ms: number
  status: string
}

interface RecommendationCostDetail {
  ticker: string
  created_at: string
  duration_ms: number
  total_tokens: number
  is_fallback: boolean
  desk_details: DeskCostDetail[]
}
```

### Core Logic

**Override resolution** (in debate route handler, before calling `run_recommendation()`):

```python
routing_override = request.app.state.routing_override
if routing_override is not None:
    config = settings.debate.model_copy(update={"routing": routing_override})
else:
    config = settings.debate
```

This keeps the orchestrator unchanged — it receives a `DebateConfig` with the correct `routing` field already set.

**PUT validation**: Reuse the same validators as `RoutingConfig` (threshold ordering, finite costs, non-negative values). Construct a `RoutingConfig` from the request body to leverage existing validation, then store it on `app.state`.

**Token attribution (prerequisite)**: Currently `DeskMetrics.input_tokens` and `output_tokens` are always 0. The desk runners (`run_*_desk_recommendation()`) return only the typed assessment, discarding the PydanticAI `RunResult` that contains `RunUsage` with actual token counts. This PRD fixes that:
1. Update `_DeskRunner` protocol to return `tuple[DomainAssessment, RunUsage]` instead of just `DomainAssessment`
2. Update all 6 desk runner functions to return `(assessment, result.usage())` from the `RunResult`
3. Update orchestrator `_run_desk()` to extract `RunUsage` and populate `DeskMetrics.input_tokens`/`output_tokens`
4. Aggregate per-desk usage into `RecommendationResult.total_usage` (currently `RunUsage()` empty)

**Cost always computed**: `_compute_recommendation_cost()` is currently gated on `routing_config.enable_model_routing`. This PRD removes that gate — cost is always computed using the `cost_per_million_tokens` map (which has entries for the default model). This makes the cost table useful even when routing is disabled.

**Cost detail persistence**: `DeskMetrics` is currently computed in the orchestrator but NOT persisted. This PRD adds:
1. A `desk_metrics_json TEXT` column to `recommendation_results` (migration 040)
2. Serialization in `save_recommendation()` — `json.dumps([m.model_dump(mode="json") for m in metrics])`
3. The cost endpoint deserializes `desk_metrics_json` to populate `DeskCostDetail` in the response

**Pre-existing data**: Recommendations saved before this migration will have `desk_metrics_json = NULL`. The cost endpoint returns `desk_details: []` for these rows.

## Requirements

### Functional Requirements

| ID | Requirement |
|----|-------------|
| FR-1 | `GET /api/config` returns current routing config (resolved: override or base) with `is_override` flag |
| FR-2 | `PUT /api/config/routing` validates and stores a `RoutingConfig` overlay on `app.state` |
| FR-3 | `DELETE /api/config/routing` clears the overlay, reverting to env var / default values |
| FR-4 | `GET /api/analytics/recommendation-costs` includes per-desk `DeskCostDetail` list |
| FR-5 | Dashboard shows collapsible "Model Routing" panel with enable toggle, threshold sliders, model inputs, cost map editor |
| FR-6 | Dashboard shows "Recommendation Costs" table with per-recommendation per-desk breakdown |
| FR-7 | "Apply" button sends PUT, "Reset to Defaults" sends DELETE, both refresh panel state |
| FR-8 | Validation: `complexity_threshold_fast < complexity_threshold_premium`, costs non-negative, thresholds in [0.0, 1.0] |
| FR-9 | Desk runners return `RunUsage` alongside assessments; `DeskMetrics` populated with actual `input_tokens`/`output_tokens` |
| FR-10 | Cost is always computed (even when `enable_model_routing=False`) using `cost_per_million_tokens` map |
| FR-11 | `RecommendationResult.total_usage` aggregated from per-desk `RunUsage` data |

### Non-Functional Requirements

| ID | Requirement |
|----|-------------|
| NFR-1 | Session-only persistence — override resets on server restart |
| NFR-2 | One new migration (`040_desk_metrics_json.sql`) — additive column only, no destructive changes |
| NFR-3 | No changes to `AppSettings` or `RoutingConfig`. No changes to `models/` (existing fields sufficient). Changes to `agents/` are internal (runner return types, orchestrator logic) |
| NFR-4 | Rate limiting on PUT/DELETE: 10/minute (prevents accidental spam) |
| NFR-5 | Frontend validates thresholds client-side before sending PUT |

## API / CLI Surface

### New Endpoints

| Method | Path | Request Body | Response | Rate Limit |
|--------|------|-------------|----------|------------|
| `PUT` | `/api/config/routing` | `RoutingConfigUpdate` | `RoutingConfigResponse` | 10/min |
| `DELETE` | `/api/config/routing` | None | `RoutingConfigResponse` (base config) | 10/min |

### Modified Endpoints

| Method | Path | Change |
|--------|------|--------|
| `GET` | `/api/config` | Add `routing: RoutingConfigResponse` to response |
| `GET` | `/api/analytics/recommendation-costs` | Add `desk_details: list[DeskCostDetail]` to each item |

### No CLI Changes

The CLI already has `--cost-summary` flag and env var configuration. No new commands needed.

## Testing Strategy

### Backend Tests

- **`test_config_routing_routes.py`** (new):
  - PUT with valid config → 200, overlay stored, GET returns `is_override: true`
  - PUT with `fast >= premium` thresholds → 422
  - PUT with negative cost → 422
  - PUT with non-finite values → 422
  - DELETE → overlay cleared, GET returns `is_override: false` with base values
  - GET when no override → base config with `is_override: false`
  - Rate limiting: 11th PUT within a minute → 429

- **`test_routing_override_integration.py`** (new):
  - Verify debate route handler resolves override when present
  - Verify debate route handler uses base config when no override

- **Expand `test_recommendation_costs.py`**:
  - Verify `desk_details` populated from stored `DeskMetrics` JSON
  - Verify empty `desk_details` when recommendation has no metrics (pre-routing data)

### Frontend Tests (Playwright E2E)

- Toggle routing on → verify PUT called with `enable_model_routing: true`
- Adjust thresholds → Apply → verify PUT body contains new values
- Reset to Defaults → verify DELETE called → panel shows base values
- Cost table renders columns: ticker, desk, tier, model, tokens, duration
- Cost table empty state when no recommendations exist

### Edge Cases

- Server restart clears override — user sees base config on reload
- Concurrent PUT requests — last write wins (acceptable for session-only config)
- Recommendations made before routing was enabled — `desk_details` is empty list
- Override set but no recommendations run yet — settings panel shows config, cost table empty

## Success Criteria

1. Users can toggle model routing on/off from the Dashboard without server restart
2. Users can adjust all routing parameters (thresholds, models, costs) via the UI
3. Users can see per-desk tier/model/token/cost breakdown for each recommendation
4. Override is explicitly session-scoped — no accidental persistence across restarts
5. Minimal changes to `models/` (one field on `RecommendationResult`) and `data/` (persistence). No changes to `scoring/`, `pricing/`, `indicators/`, or `services/`

## Constraints & Assumptions

- **Session-only**: Override lives in `app.state`, not persisted to DB or disk
- **Single-user**: No auth or multi-user conflict resolution (loopback-only server)
- **No model validation**: Model name strings are not validated against Groq's model catalog — invalid names will fail at recommendation time with the existing error handling
- **DeskMetrics population**: The orchestrator already builds `desk_metrics: list[DeskMetrics]` and passes it to `RecommendationResult` in memory. This PRD adds the persistence layer (migration 040, serialization in `save_recommendation()`, deserialization in `_row_to_recommendation_row()`, updated `RecommendationRow` dataclass) so that per-desk data is available for the cost endpoint.

## Out of Scope

- Persisting routing config across server restarts (SQLite or file-based)
- Aggregate cost analytics (total spend, trend lines, tier distribution charts)
- Model name dropdowns validated against Groq's available models API
- CLI commands for runtime config changes
- Multi-user config isolation or auth
- A/B testing between routing configurations

## Dependencies

- **Internal**: `RoutingConfig` model (exists in `models/config.py`), `DeskMetrics` model (exists in `models/recommendation.py`), recommendation cost endpoint (exists in `routes/analytics.py`), `RecommendationResult` model (exists in `models/recommendation.py` — needs `desk_metrics` field), `save_recommendation()` (exists in `data/_recommendation.py` — needs metrics serialization)
- **External**: None — no new packages required

## Migration Details

### Migration 040: `desk_metrics_json`

```sql
-- Migration 040: Add desk_metrics_json column to recommendation_results
-- Stores per-desk DeskMetrics (tier, model, tokens, duration) for cost analytics

ALTER TABLE recommendation_results ADD COLUMN desk_metrics_json TEXT NOT NULL DEFAULT '[]';
```

Additive-only. Existing rows get `'[]'` (empty JSON array). No data backfill needed — pre-routing recommendations have no per-desk metrics.
