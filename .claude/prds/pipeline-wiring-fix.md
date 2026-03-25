---
name: pipeline-wiring-fix
description: Close the scan-to-recommendation gap by introducing ScanEnrichment envelope and wiring computed features end-to-end
status: planned
created: 2026-03-25T01:56:17Z
---

# PRD: Pipeline Wiring Fix — Close the Scan→Recommendation Gap

## Problem Statement

A comprehensive audit of 34 merged epics revealed that multiple features were
implemented but never fully wired. The root cause is architectural: the
`run_recommendation()` function uses a flat parameter list that nobody extends
when new scan-phase features are added. Data is computed, stored on
`OptionsResult`, then silently discarded at the scan→recommendation boundary.

**Affected features:**
- Multi-leg spread strategies (computed, persisted, never reach agents or UI)
- Neural trajectory P(profit) (computed, discarded before agents)
- `RecommendationCostTable.vue` (built, never imported)
- Duplicate `get_prediction_accuracy()` (runtime crash on CLI path)
- Tuned indicator weights (advisory text only, never affect scoring math)

## Design Principle — The Elegant Fix

Instead of patching each broken wire individually, introduce a **single envelope
model** (`ScanEnrichment`) that carries ALL enrichment data from scan to
recommendation. Future epics add fields to this model instead of extending
function signatures. This is a one-time architectural fix that prevents the
entire class of "computed but discarded" bugs permanently.

---

## Epic Structure — 3 Waves

### Wave 1: Foundation — ScanEnrichment Envelope (blocking)

**Issue 1: Create `ScanEnrichment` model**

Add to `src/options_arena/models/analysis.py`:

```python
class ScanEnrichment(BaseModel):
    """Envelope carrying all scan-phase enrichment to the recommendation phase.

    Instead of growing run_recommendation()'s parameter list, new scan features
    add fields here. The orchestrator unpacks what it needs.
    """
    model_config = ConfigDict(frozen=True)

    # Multi-leg strategies (epic: multi-leg-strategies)
    spread_analysis: SpreadAnalysis | None = None

    # Neural trajectory (epic: scientific-ml-neural)
    prob_profit_neural: float | None = None

    # Macro context (epic: scientific-ml-statistical) — already fixed in pipeline,
    # migrate here for consistency
    macro_regime: MacroRegime | None = None
    macro_yield_spread: float | None = None
    macro_fed_funds_rate: float | None = None
    macro_vix_level: float | None = None

    # Earnings date from Phase 3
    next_earnings: date | None = None

    # FinancialDatasets package
    fd_package: FinancialDatasetsPackage | None = None
```

Every field defaults to `None` so the model is always constructible, even when
features are disabled. Future epics add fields here instead of touching
`run_recommendation()`.

**Issue 2: Refactor `run_recommendation()` signature**

Replace the flat parameters with:

```python
async def run_recommendation(
    ticker: str,
    ticker_score: TickerScore,
    contracts: list[OptionContract],
    quote: Quote,
    ticker_info: TickerInfo,
    settings: AppSettings,
    repo: Repository,
    market_data: MarketDataService,
    options_data: OptionsDataService,
    fred: FredService | None = None,
    scan_run_id: int | None = None,
    enrichment: ScanEnrichment | None = None,       # NEW — replaces spread_analysis
    scan_predictions: list[Prediction] | None = None,
    progress_callback: RecommendationProgressCallback | None = None,
) -> RecommendationResult:
```

Remove `spread_analysis: SpreadAnalysis | None = None  # noqa: ARG001`.
The `enrichment` parameter replaces it and is actually consumed.

Inside `_run_recommendation_pipeline()`, unpack enrichment into
`build_market_context()`:

```python
enrich = enrichment or ScanEnrichment()
context = build_market_context(
    ticker_score, quote, ticker_info, contracts,
    next_earnings=enrich.next_earnings,
    fd_package=enrich.fd_package,
    macro_regime=enrich.macro_regime,
    macro_yield_spread=enrich.macro_yield_spread,
    macro_fed_funds_rate=enrich.macro_fed_funds_rate,
    macro_vix_level=enrich.macro_vix_level,
    prob_profit_neural=enrich.prob_profit_neural,
)
```

**Issue 3: Build `ScanEnrichment` at call sites**

CLI (`cli/commands.py`) and API (`api/routes/debate.py`) construct the envelope
from `OptionsResult` and pass it:

```python
enrichment = ScanEnrichment(
    spread_analysis=options_result.spread_analyses.get(ticker),
    prob_profit_neural=options_result.prob_profit_neural.get(ticker),
    macro_regime=options_result.macro_regime,
    macro_yield_spread=options_result.macro_yield_spread,
    macro_fed_funds_rate=options_result.macro_fed_funds_rate,
    macro_vix_level=options_result.macro_vix_level,
    next_earnings=options_result.earnings_dates.get(ticker),
)
```

For the single-ticker `debate` command (no prior scan), `enrichment=None`
is fine — everything defaults to `None` and agents use their tools on-demand.

**Issue 4: Fix duplicate `get_prediction_accuracy()`**

In `src/options_arena/data/_learning.py`, delete the first definition (~lines
285-344). Keep the second definition (~lines 554-599) which has the required
`window_days: int` parameter and better validation. Audit all call sites to
ensure they pass `window_days` explicitly (they already do).

**Tests:**
- Unit test: `ScanEnrichment` construction from `OptionsResult` fields
- Unit test: `run_recommendation()` with `enrichment=None` (backward compat)
- Unit test: `run_recommendation()` with full `ScanEnrichment` — verify
  `MarketContext` fields populated
- Integration test: Full scan→recommend pipeline passes enrichment through
- Unit test: `get_prediction_accuracy()` has single definition, callable with int

---

### Wave 2: Wire Spread Data End-to-End (depends on Wave 1)

**Issue 5: Inject spread context into agent deps**

Add `spread_analysis: SpreadAnalysis | None = None` to `SynthesisDeps` and
`DeskDeps`. In the orchestrator, populate from `enrichment.spread_analysis`.

**Issue 6: Add spread context to synthesis prompt**

In `agents/prompts/synthesis.py`, add a conditional `<<<SPREAD_ANALYSIS>>>`
block that renders when spread data is present:

```
{%- if spread_analysis %}
<<<SPREAD_ANALYSIS>>>
Strategy: {{ spread_analysis.spread.spread_type.value }}
Net Premium: ${{ spread_analysis.net_premium }}
Max Profit: ${{ spread_analysis.max_profit }}
Max Loss: ${{ spread_analysis.max_loss }}
Risk/Reward: {{ spread_analysis.risk_reward_ratio }}
P(Profit): {{ spread_analysis.pop_estimate | pct }}
Rationale: {{ spread_analysis.strategy_rationale }}
<<</SPREAD_ANALYSIS>>>
{%- endif %}
```

Also inject into desk agent prompts so they can reference spread data in their
assessments. The risk desk especially benefits from seeing max loss / P(profit).

**Issue 7: Add spread rendering to CLI**

In `cli/rendering.py`, add a `render_spread_recommendation()` function that
displays spread type, legs, P&L profile, and risk/reward when spread data
is present on the recommendation result.

**Issue 8: Add `SpreadDetail` TypeScript type and frontend rendering**

In `web/src/types/recommendation.ts`, add:

```typescript
export interface SpreadDetail {
  spread_type: string
  net_premium: string       // Decimal as string
  max_profit: string
  max_loss: string
  risk_reward_ratio: number
  pop_estimate: number
  strategy_rationale: string
}
```

In `PositionCard.vue`, render spread details when present on the recommendation.

**Tests:**
- Unit test: Synthesis prompt includes spread block when `spread_analysis` present
- Unit test: Synthesis prompt omits spread block when `None`
- Unit test: CLI rendering shows spread table
- E2E test: Frontend renders spread card (if E2E infra exists)

---

### Wave 3: Close Remaining Gaps (parallel, independent)

**Issue 9: Wire `RecommendationCostTable.vue` into AnalyticsPage**

Add a "Costs" tab (8th tab) to `AnalyticsPage.vue`. Create a cost store
(`web/src/stores/costs.ts`) that fetches from a new API endpoint.

Backend: Add `GET /api/analytics/recommendation-costs` endpoint to
`api/routes/analytics.py` that queries recent `RecommendationResult` records
and maps to `RecommendationCostDetail` response shape. Align the TypeScript
`RecommendationCostDetail` type with the actual backend response (fix the
schema mismatch: backend uses `total_input_tokens`/`total_output_tokens`,
frontend expects `total_tokens`/`desk_details`).

**Issue 10: Make tuned weights affect scoring (opt-in)**

Add a `weight_overrides: dict[str, float] | None = None` parameter to
`compute_composite_score()` in `scoring/composite.py`. When provided, merge
overrides into `INDICATOR_WEIGHTS` for that invocation (validate sum ≈ 1.0).

In the scan pipeline (`scan/phase_scoring.py`), load approved tuned weights
from the DB and pass as overrides when `settings.learning.apply_tuned_weights`
is `True` (new config flag, default `False`). This makes the learning loop
closed: mine → tune → score → validate → promote.

Add a `LearningConfig` section to `AppSettings` if one doesn't exist:

```python
class LearningConfig(BaseModel):
    apply_tuned_weights: bool = False   # Opt-in: use DB weights in scoring
    min_confidence: float = 0.7         # Only apply weights above this confidence
```

**Tests:**
- Unit test: `compute_composite_score()` with `weight_overrides` produces
  different scores than without
- Unit test: `weight_overrides` validation rejects weights that don't sum to ~1.0
- Integration test: Scan with `apply_tuned_weights=True` loads from DB
- E2E test: Costs tab renders in analytics page

---

## Out of Scope

- **`DeskSelector.vue` / `AgencyChat.vue`**: The hedge-fund-frontend epic
  replaced the SPA architecture. Agency interaction is CLI/API-only by design.
  Building a chat UI is a separate product decision, not a wiring fix.

- **Neural deps installation** (`torch`/`lightning`): These are optional extras
  that users install deliberately. The wiring is correct — it just needs deps.
  Document in README that `uv install .[neural]` activates the feature.

- **ML regime classifier training**: The training script exists but needs data.
  Document the training workflow in a HOWTO, don't auto-train in the pipeline.

## Success Criteria

1. A single-ticker scan with spreads enabled produces a recommendation that
   references the spread strategy in the synthesis output
2. `prob_profit_neural` reaches `MarketContext` when neural deps are installed
   and the flag is enabled
3. `RecommendationCostTable` renders real data in the Analytics "Costs" tab
4. `outcomes agent-weights` CLI command executes without crash
5. `ARENA_LEARNING__APPLY_TUNED_WEIGHTS=true` causes scoring to use DB weights
6. Future epics can add scan enrichment by adding a field to `ScanEnrichment`
   without touching `run_recommendation()` or any call site

## Risk Assessment

| Risk | Mitigation |
|------|-----------|
| Changing `run_recommendation()` signature breaks callers | All callers updated in Wave 1; `enrichment=None` is backward-compatible |
| Tuned weights degrade scoring quality | Opt-in flag (default off), confidence threshold, weights validated to sum ≈ 1.0 |
| Spread prompt injection bloats token count | Conditional block; only appended when spread data exists (~150 tokens) |
| Schema mismatch between backend cost model and frontend type | Aligned in Wave 3 Issue 9; single source of truth in backend |

## Effort Estimate

| Wave | Issues | Complexity | Dependencies |
|------|--------|-----------|-------------|
| Wave 1 | 4 issues | Medium — model + signature refactor + call site updates | None (foundation) |
| Wave 2 | 4 issues | Medium — prompt + rendering + TypeScript type | Wave 1 |
| Wave 3 | 2 issues | Medium — new endpoint + config + scoring param | None (parallel) |

**Total: 10 issues across 3 waves.**
