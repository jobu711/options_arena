---
epic: pipeline-wiring-fix
verified: 2026-03-25T04:30:00Z
result: PASS
---

# Verification Report: pipeline-wiring-fix

## PRD Success Criteria Traceability

| # | Criterion | Evidence | Tests | Status |
|---|-----------|----------|-------|--------|
| SC-1 | Spread strategy referenced in synthesis output | `SPREAD_ANALYSIS_BLOCK` in `prompts/synthesis.py`, injected by `synthesis_agent.py` when `deps.spread_analysis` present | 8 prompt rendering tests | PASS |
| SC-2 | `prob_profit_neural` reaches `MarketContext` | Unpacked in `recommendation_orchestrator.py:505` via `enrich.prob_profit_neural` → `build_market_context()` | `test_prob_profit_neural_unpacked` | PASS |
| SC-3 | `RecommendationCostTable` renders in Analytics Costs tab | `GET /api/analytics/recommendation-costs` in `analytics.py:189`, Pinia store `costs.ts`, 8th tab in `AnalyticsPage.vue` | 6 endpoint tests | PASS |
| SC-4 | `outcomes agent-weights` CLI no crash | Duplicate `get_prediction_accuracy()` removed; call site in `outcomes.py:432` now passes `window_days=365` | 6 dedup tests | PASS |
| SC-5 | `ARENA_LEARNING__APPLY_TUNED_WEIGHTS=true` uses DB weights | `LearningConfig` in `config.py:147`, `weight_overrides` param on `composite_score()`, scan pipeline loads from DB | 25 scoring/config tests | PASS |
| SC-6 | Future enrichment = add field to `ScanEnrichment` | Envelope pattern: all fields `| None = None`, orchestrator unpacks, callers construct — no `run_recommendation()` signature change needed | 14 model tests | PASS |

## Task-Level Acceptance Criteria

| Task | Title | Code Evidence | Tests | Commit | Status |
|------|-------|--------------|-------|--------|--------|
| #805 | ScanEnrichment model | `class ScanEnrichment` in `models/analysis.py:59`, exported from `__init__.py` | 14 pass | `4250066` | PASS |
| #806 | Refactor run_recommendation() | `enrichment: ScanEnrichment` at lines 399, 498 in orchestrator; `# noqa: ARG001` removed | 6 pass | `b1b2362` | PASS |
| #807 | Spread context in prompts | `SPREAD_ANALYSIS_BLOCK` + `RISK_SPREAD_CONTEXT_BLOCK` templates; conditional injection | 13 pass | `61179e4` | PASS |
| #808 | Build ScanEnrichment at call sites | Construction in `cli/commands.py` and `api/routes/debate.py`; old `spread_analysis=` kwarg gone | 9 pass | `df1c557` | PASS |
| #809 | Spread rendering in CLI | `render_spread_recommendation()` at `rendering.py:473`, called in `commands.py:974` | 12 pass | `766d9a6` | PASS |
| #810 | Fix duplicate function | Single `get_prediction_accuracy` at `_learning.py:490`; `outcomes.py` call site fixed | 6 pass | `4250066` | PASS |
| #811 | SpreadDetail frontend | `SpreadDetail` in `recommendation.ts`, `index.ts`; spread section in `PositionCard.vue` | type-check + build pass | `fb67022` | PASS |
| #812 | Spread deps injection | `spread_analysis` field on `DeskDeps:40` and `SynthesisDeps:48`; orchestrator wires from enrichment | 6 pass | `f0ff0d6` | PASS |
| #813 | Wire costs endpoint | `GET /recommendation-costs` at `analytics.py:189`; Pinia store; 8th tab in AnalyticsPage | 6 pass | `969a94d` | PASS |
| #814 | Tuned weights scoring | `weight_overrides` param on `composite_score()`; `LearningConfig` in `config.py`; scan pipeline integration | 25 pass | `314da71` | PASS |

## Test Summary

- **New tests**: 97 across 11 test files — **97/97 PASS**
- **Full unit suite**: 1081 passed, 1 pre-existing failure (`test_volatility_toolset_has_four_tools` — expects 4 tools, 5 exist, unrelated)
- **Regressions**: 0

## Lint / Type Check

- `ruff check`: 154 errors (pre-existing: 155, reduced by 1)
- `ruff format`: clean
- Frontend: `vue-tsc --noEmit` + `vite build` pass

## Summary

**10/10 tasks PASS. 6/6 PRD success criteria PASS. 0 regressions. 0 FAIL. 0 WARN.**
