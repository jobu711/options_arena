# Research: pipeline-wiring-fix

## PRD Summary

Introduce a `ScanEnrichment` frozen envelope model to carry all scan-phase enrichment
data to the recommendation phase, replacing the flat parameter list on
`run_recommendation()`. Wire spread strategies, neural P(profit), and macro context
end-to-end. Close remaining gaps: cost table UI, tuned weights in scoring, duplicate
function removal.

## Relevant Existing Modules

- `models/analysis.py` — `MarketContext` (lines 56-232) already has `macro_regime`, `yield_spread`, `fed_funds_rate`, `vix_level`, `prob_profit_neural` fields. `ScanEnrichment` belongs here alongside it.
- `agents/recommendation_orchestrator.py` — `run_recommendation()` (lines 387-402) has unused `spread_analysis` param (`# noqa: ARG001`). Inner pipeline at line 484.
- `agents/_context.py` — `build_market_context()` (lines 130-142) already accepts `macro_*` and `prob_profit_neural` kwargs — just never called with them from the recommendation path.
- `agents/_desk_deps.py` — `DeskDeps` dataclass (lines 19-39), has `market_context` field.
- `agents/synthesis_agent.py` — `SynthesisDeps` dataclass (lines 35-47), has `context: MarketContext` but no `spread_analysis`.
- `agents/prompts/synthesis.py` — Static prompt with `<<<TUNED_WEIGHTS>>>` / `<<<LEARNED_PATTERNS>>>` dynamic blocks (lines 33-45).
- `scan/models.py` — `OptionsResult` (lines 82-116) already carries `spread_analyses`, `macro_*`, `prob_profit_neural`, `earnings_dates`.
- `scoring/composite.py` — Function is `composite_score()` (lines 86-132), NOT `compute_composite_score()` as PRD states.
- `data/_learning.py` — Duplicate `get_prediction_accuracy()` at lines 285-344 (old, optional window) and 554-599 (new, required window, validates >= 0).
- `cli/rendering.py` — Rich Table rendering patterns (lines 63-100+). Pure data→display.
- `api/routes/debate.py` — `_run_recommendation_background()` (lines 258-308) is the API call site.
- `api/routes/analytics.py` — 15 endpoints (lines 44-265), no cost endpoint yet.
- `models/config.py` — `AppSettings` sole `BaseSettings` (line 674+). No `LearningConfig` class exists yet.
- `learning/` — Middle-stack module, accesses `models/`, `data/`, `scoring/`. Never-raises pattern.

## Existing Patterns to Reuse

- **Frozen envelope**: `ConfigDict(frozen=True)` on all point-in-time snapshots (`SpreadAnalysis`, `OptionContract`, `OptionGreeks`, `FinancialDatasetsPackage`). `ScanEnrichment` follows this pattern.
- **Optional-all-fields**: `OptionsResult` defaults everything to `None` or `Field(default_factory=dict)`. `ScanEnrichment` does the same for backward compat.
- **Dynamic prompt blocks**: `<<<BLOCK_NAME>>>` pattern in synthesis prompt (lines 33-45). Spread block follows this convention.
- **NaN defense**: `math.isfinite()` before range checks on all numeric validators (see `OptionGreeks`, `SpreadAnalysis`).
- **SpreadDetail conversion**: `spread_detail_from_analysis()` in `api/schemas.py` (lines 377-404) converts Decimal→string for JSON.
- **Pinia setup store**: All stores in `web/src/stores/` use `defineStore` with setup function syntax.
- **Analytics tab pattern**: Each tab in `AnalyticsPage.vue` loads data via store or direct API call with watchers.

## Existing Code to Extend

- `src/options_arena/models/analysis.py` — Add `ScanEnrichment` model (new class, ~30 lines).
- `src/options_arena/agents/recommendation_orchestrator.py` — Replace `spread_analysis` param with `enrichment: ScanEnrichment | None = None`. Unpack in `_run_recommendation_pipeline()` before `build_market_context()` call.
- `src/options_arena/cli/commands.py` — Build `ScanEnrichment` from `OptionsResult` at scan call site.
- `src/options_arena/api/routes/debate.py` — Build `ScanEnrichment` from `OptionsResult` at API call site (line ~276).
- `src/options_arena/agents/synthesis_agent.py` — Add `spread_analysis: SpreadAnalysis | None = None` to `SynthesisDeps`.
- `src/options_arena/agents/prompts/synthesis.py` — Add `<<<SPREAD_ANALYSIS>>>` conditional block.
- `src/options_arena/cli/rendering.py` — Add `render_spread_recommendation()` function.
- `src/options_arena/scoring/composite.py` — Add `weight_overrides` param to `composite_score()`.
- `src/options_arena/api/routes/analytics.py` — Add `GET /api/analytics/recommendation-costs` endpoint.
- `src/options_arena/models/config.py` — Add `LearningConfig` nested model in `AppSettings`.
- `web/src/pages/AnalyticsPage.vue` — Add 8th "Costs" tab importing existing `RecommendationCostTable.vue`.
- `web/src/stores/costs.ts` — New Pinia store for cost data (new file).
- `web/src/types/recommendation.ts` — Add `SpreadDetail` interface.

## Potential Conflicts

- **PRD names `compute_composite_score()` but function is `composite_score()`** — PRD Issue 10 must target the correct function name. All references to `compute_composite_score` should be `composite_score`.
- **`spread_analysis` removal from `run_recommendation()`** — 37 files reference `run_recommendation`. All callers and test mocks passing `spread_analysis=` must be updated to `enrichment=`.
- **`get_prediction_accuracy()` duplicate** — First definition (lines 285-344) is a method on the `LearningRepository` class. Deletion must not break the class. Second definition (lines 554-599) is the replacement. Verify no caller depends on the optional `window_days=None` behavior.
- **AnalyticsPage tab count** — Currently 7 tabs. Adding "Costs" as 8th must preserve existing tab indices if any code references tabs by index.
- **`LearningConfig` naming** — No existing `LearningConfig` class. Must be added as nested `BaseModel` on `AppSettings` with env prefix `ARENA_LEARNING__`.

## Open Questions

- **`fd_package` population**: `ScanEnrichment` includes `fd_package: FinancialDatasetsPackage | None` but the current pipeline does not populate this on `OptionsResult`. Is this aspirational or does another code path provide it? (Answer: aspirational — `FinancialDatasetsConfig` exists but enrichment happens in debate path, not scan. Field exists for future use.)
- **Weight override validation**: PRD says "validate sum ≈ 1.0" but `composite_score()` uses a geometric mean. Do overrides replace the existing `INDICATOR_WEIGHTS` dict? What tolerance for "approximately 1.0"?
- **Cost table schema mismatch**: PRD says "backend uses `total_input_tokens`/`total_output_tokens`, frontend expects `total_tokens`/`desk_details`". Need to verify the actual `RecommendationCost` model fields vs `RecommendationCostTable.vue` props.

## Recommended Architecture

1. **ScanEnrichment in `models/analysis.py`** — Frozen, all-optional fields, alongside `MarketContext`. Single import path for both scan and recommendation modules.
2. **Envelope unpacking in orchestrator** — `_run_recommendation_pipeline()` unpacks `ScanEnrichment` into `build_market_context()` kwargs. No changes to `build_market_context()` signature needed (it already accepts all params).
3. **Spread injection via deps** — Add `spread_analysis` to `SynthesisDeps` and optionally `DeskDeps`. Orchestrator populates from `enrichment.spread_analysis`.
4. **Prompt conditional block** — `<<<SPREAD_ANALYSIS>>>` block appended when `deps.spread_analysis is not None`.
5. **Cost endpoint** — Simple read-only endpoint querying `RecommendationCost` records, mapping to response schema aligned with `RecommendationCostTable.vue` props.
6. **Learning config** — `LearningConfig(BaseModel)` with `apply_tuned_weights: bool = False`, `min_confidence: float = 0.7`. Added to `AppSettings` as `learning: LearningConfig`.

## Test Strategy Preview

- **Existing patterns**: `pytest` + `pytest-asyncio`, mocks via `unittest.mock.patch`, Pydantic model construction in fixtures.
- **Test locations**: `tests/unit/models/`, `tests/unit/agents/`, `tests/unit/scoring/`, `tests/unit/cli/`, `tests/unit/api/`, `tests/integration/`.
- **Key tests needed**:
  - `ScanEnrichment` construction and frozen immutability
  - `run_recommendation()` backward compat with `enrichment=None`
  - `run_recommendation()` with full enrichment → verify `MarketContext` fields
  - `composite_score()` with `weight_overrides` param
  - `get_prediction_accuracy()` single definition, required `window_days`
  - Spread prompt rendering (present and absent)
  - Cost API endpoint response schema
  - `RecommendationCostTable.vue` integration (if E2E infra exists)

## Estimated Complexity

**Medium** — All infrastructure exists. The work is primarily wiring (connecting existing models/fields/params), not building new capabilities. Key risks are the 37-file `run_recommendation()` signature change and ensuring test coverage across all call sites. The 3-wave structure is appropriate: foundation first, then feature wiring, then independent gaps.
