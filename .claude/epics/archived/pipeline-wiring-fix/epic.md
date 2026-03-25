---
name: pipeline-wiring-fix
status: completed
created: 2026-03-25T02:06:19Z
updated: 2026-03-25T06:00:00Z
completed: 2026-03-25T06:00:00Z
progress: 100%
prd: .claude/prds/pipeline-wiring-fix.md
github: https://github.com/jobu711/options_arena/issues/804
---

# Epic: pipeline-wiring-fix

## Overview

Introduce a `ScanEnrichment` frozen envelope model that carries all scan-phase enrichment
data to the recommendation phase, replacing the flat parameter list on `run_recommendation()`.
Wire spread strategies, neural P(profit), and macro context end-to-end. Close remaining
gaps: cost table UI, tuned weights in scoring, duplicate function removal.

This is a one-time architectural fix that prevents the entire class of "computed but
discarded" bugs. Future epics add fields to `ScanEnrichment` instead of extending
function signatures.

## Architecture Decisions

- **Envelope pattern over flat params**: `ScanEnrichment(frozen=True)` in `models/analysis.py`
  alongside `MarketContext`. All fields default to `None` for backward compatibility.
  Future features add fields here, never to `run_recommendation()`.
- **Unpack in orchestrator**: `_run_recommendation_pipeline()` unpacks `ScanEnrichment`
  into `build_market_context()` kwargs. No signature changes needed on `build_market_context()`
  — it already accepts all macro/neural params.
- **Spread injection via deps**: Add `spread_analysis` to `SynthesisDeps` (and optionally
  `DeskDeps`). Orchestrator populates from `enrichment.spread_analysis`.
- **Opt-in tuned weights**: New `LearningConfig(BaseModel)` on `AppSettings` with
  `apply_tuned_weights: bool = False`. Weights only affect scoring when explicitly enabled.
- **PRD correction**: Function is `composite_score()` not `compute_composite_score()`.

## Technical Approach

### Wave 1: Foundation — ScanEnrichment Envelope (blocking)

**Issue 1: Create `ScanEnrichment` model**
- File: `src/options_arena/models/analysis.py`
- Add frozen `ScanEnrichment` model with fields: `spread_analysis`, `prob_profit_neural`,
  `macro_regime`, `macro_yield_spread`, `macro_fed_funds_rate`, `macro_vix_level`,
  `next_earnings`, `fd_package`
- Validators: `prob_profit_neural` needs `isfinite()` + `[0.0, 1.0]` range check;
  macro floats need `isfinite()` checks
- Export from `models/__init__.py`

**Issue 2: Refactor `run_recommendation()` signature**
- File: `src/options_arena/agents/recommendation_orchestrator.py`
- Replace `spread_analysis: SpreadAnalysis | None = None  # noqa: ARG001` with
  `enrichment: ScanEnrichment | None = None`
- In `_run_recommendation_pipeline()`, unpack enrichment into `build_market_context()` call
- Pass `enrichment.spread_analysis` to synthesis deps (Issue 5 dependency)

**Issue 3: Build `ScanEnrichment` at call sites**
- Files: `src/options_arena/cli/commands.py`, `src/options_arena/api/routes/debate.py`
- CLI scan path: construct from `OptionsResult` fields (spread_analyses.get(ticker),
  prob_profit_neural.get(ticker), macro_*, earnings_dates.get(ticker))
- API debate path: same construction pattern
- Single-ticker debate: `enrichment=None` (backward compat)

**Issue 4: Fix duplicate `get_prediction_accuracy()`**
- File: `src/options_arena/data/_learning.py`
- Delete first definition (lines ~285-344, optional `window_days`)
- Keep second definition (lines ~554-599, required `window_days`, validates >= 0)
- Audit all call sites — they already pass `window_days` explicitly

### Wave 2: Wire Spread Data End-to-End (depends on Wave 1)

**Issue 5: Inject spread context into agent deps**
- Files: `src/options_arena/agents/synthesis_agent.py`, `src/options_arena/agents/_desk_deps.py`
- Add `spread_analysis: SpreadAnalysis | None = None` to `SynthesisDeps`
- In orchestrator, populate from `enrichment.spread_analysis`
- Consider adding to `DeskDeps` for risk desk benefit

**Issue 6: Add spread context to synthesis prompt**
- File: `src/options_arena/agents/prompts/synthesis.py`
- Add conditional `<<<SPREAD_ANALYSIS>>>` block with: strategy type, net premium,
  max profit/loss, risk/reward ratio, P(profit), rationale
- Also inject into desk agent prompts (risk desk especially)
- Follow existing `<<<TUNED_WEIGHTS>>>` / `<<<LEARNED_PATTERNS>>>` pattern

**Issue 7: Add spread rendering to CLI**
- File: `src/options_arena/cli/rendering.py`
- Add `render_spread_recommendation()` function using Rich Table
- Display: spread type, legs, P&L profile, risk/reward when spread data present
- Follow existing rendering patterns (Green/Red/Yellow, right-aligned numerics)

**Issue 8: Add `SpreadDetail` TypeScript type and frontend rendering**
- Files: `web/src/types/recommendation.ts`, `web/src/components/PositionCard.vue`
- Add `SpreadDetail` interface (spread_type, net_premium, max_profit, max_loss,
  risk_reward_ratio, pop_estimate, strategy_rationale)
- Render spread details in `PositionCard.vue` when present
- Use existing `spread_detail_from_analysis()` in `api/schemas.py` (lines 377-404)

### Wave 3: Close Remaining Gaps (parallel with Wave 2)

**Issue 9: Wire `RecommendationCostTable.vue` into AnalyticsPage**
- Files: `web/src/pages/AnalyticsPage.vue`, `web/src/stores/costs.ts` (new),
  `src/options_arena/api/routes/analytics.py`
- Add `GET /api/analytics/recommendation-costs` endpoint querying `RecommendationCost` records
- Align TypeScript types with backend response (fix schema mismatch)
- Create Pinia `costs` store
- Add 8th "Costs" tab to AnalyticsPage importing existing `RecommendationCostTable.vue`

**Issue 10: Make tuned weights affect scoring (opt-in)**
- Files: `src/options_arena/scoring/composite.py`, `src/options_arena/scan/phase_scoring.py`,
  `src/options_arena/models/config.py`
- Add `weight_overrides: dict[str, float] | None = None` param to `composite_score()`
- Validate overrides sum ≈ 1.0 when provided
- Add `LearningConfig(BaseModel)` to `AppSettings` with `apply_tuned_weights: bool = False`,
  `min_confidence: float = 0.7`
- In scan Phase 2, load approved weights from DB when flag is `True`

## Task Breakdown Preview

- [ ] Issue 1: `ScanEnrichment` model in `models/analysis.py`
- [ ] Issue 2: Refactor `run_recommendation()` signature
- [ ] Issue 3: Build `ScanEnrichment` at CLI + API call sites
- [ ] Issue 4: Fix duplicate `get_prediction_accuracy()`
- [ ] Issue 5: Inject spread context into `SynthesisDeps` / `DeskDeps`
- [ ] Issue 6: Add spread block to synthesis + desk prompts
- [ ] Issue 7: Spread rendering in CLI (`render_spread_recommendation()`)
- [ ] Issue 8: `SpreadDetail` TypeScript type + `PositionCard.vue` rendering
- [ ] Issue 9: Wire `RecommendationCostTable.vue` + costs endpoint + store
- [ ] Issue 10: Tuned weights in `composite_score()` + `LearningConfig`

## Dependencies

- **Wave 1 (Issues 1-4)**: No dependencies. Foundation work.
- **Wave 2 (Issues 5-8)**: Depends on Wave 1 (needs `ScanEnrichment` and refactored signature).
- **Wave 3 (Issues 9-10)**: No dependency on Waves 1-2. Can run in parallel with Wave 2.
- **External**: No new package dependencies. All libraries already in `pyproject.toml`.

## Success Criteria (Technical)

1. Single-ticker scan with spreads → synthesis output references the spread strategy
2. `prob_profit_neural` reaches `MarketContext` when neural deps installed + enabled
3. `RecommendationCostTable` renders real data in Analytics "Costs" tab
4. `get_prediction_accuracy()` has single definition, no runtime crash
5. `ARENA_LEARNING__APPLY_TUNED_WEIGHTS=true` causes scoring to use DB weights
6. Future enrichment = add field to `ScanEnrichment`, touch nothing else
7. All existing tests pass with no regressions
8. `enrichment=None` works identically to current behavior (backward compat)

## Estimated Effort

- **Total**: 10 issues across 3 waves
- **Critical path**: Wave 1 (4 issues) → Wave 2 (4 issues). Wave 3 parallel.
- **Highest risk**: Issue 2 (signature change touches 37 files including tests)
- **Lowest risk**: Issue 4 (delete duplicate, keep better version)

## Tasks Created

### Wave 1: Foundation (blocking)
- [ ] [P] #805 - Create ScanEnrichment model (parallel: true, S, 2h)
- [ ] #806 - Refactor run_recommendation() signature (depends on #805, M, 4h)
- [ ] #808 - Build ScanEnrichment at call sites (depends on #806, S, 3h)
- [ ] [P] #810 - Fix duplicate get_prediction_accuracy() (parallel: true, XS, 1h)

### Wave 2: Wire Spread Data (depends on Wave 1)
- [ ] [P] #812 - Inject spread context into agent deps (depends on #806, S, 2h)
- [ ] #807 - Add spread context to synthesis prompt (depends on #812, S, 3h)
- [ ] [P] #809 - Add spread rendering to CLI (depends on #806, S, 2h)
- [ ] [P] #811 - Add SpreadDetail TypeScript type and frontend rendering (depends on #806, S, 2h)

### Wave 3: Close Remaining Gaps (parallel with Wave 2)
- [ ] [P] #813 - Wire RecommendationCostTable into AnalyticsPage (parallel: true, M, 5h)
- [ ] [P] #814 - Make tuned weights affect scoring opt-in (parallel: true, M, 5h)

Total tasks: 10
Parallel tasks: 7
Sequential tasks: 3
Estimated total effort: 29 hours

## Test Coverage Plan

Total test files planned: 10
Total test cases planned: ~48
