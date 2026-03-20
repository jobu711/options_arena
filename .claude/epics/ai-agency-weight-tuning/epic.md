---
name: ai-agency-weight-tuning
status: completed
created: 2026-03-17T14:37:45Z
updated: 2026-03-20T15:20:34Z
completed: 2026-03-20T15:20:34Z
progress: 100%
prd: .claude/prds/ai-agency-evolution.md
parent_epic: ai-agency-evolution
epic_number: 4
dependencies: [ai-agency-desk-foundation, ai-agency-advisor-routing]
parallelizable_with: [ai-agency-analysis-tools, ai-agency-ml-tools]
github: https://github.com/jobu711/options_arena/issues/606
---

# Epic 4: Self-Improvement P1 — Weight Tuning

## Overview

Create the `learning/` module and implement Phase 1 of self-improvement: extended auto-tune for both vote and indicator weights. Relocate `compute_auto_tune_weights()` from `orchestrator.py`, extend `WeightSnapshot` model, and add weight history tracking with API/CLI visibility.

## Architecture Decisions

- `learning/` is middle-stack: accesses `models/`, `data/`, `scoring/`, `agents/prompts/` (text only). Never imports agent instances or services.
- Existing `compute_auto_tune_weights()` (inverse-Brier scoring, clamped [0.05, 0.35], risk=0.0) relocates verbatim, then extended for indicator weights
- `WeightType` enum distinguishes vote vs indicator weights in same table
- Weight tuning triggers inline after `collect_outcomes()` (min 50 samples)
- Never-raises contract: learning errors logged, not propagated

## Technical Approach

### New Module: `learning/`
- `learning/__init__.py` — re-exports
- `learning/weight_tuner.py` — relocated `compute_auto_tune_weights()` + new `compute_indicator_tune_weights()` using outcome P&L correlation with indicator signals
- `learning/CLAUDE.md` — module boundary rules

### Model Extensions
- `WeightType` StrEnum (vote, indicator) in `enums.py`
- Extend `WeightSnapshot` with `weight_type: WeightType` and `accuracy_at_time: float | None`
- `WeightHistory` model for API response

### Data Layer
- Migration 037: ALTER `auto_tune_weights` — add `weight_type TEXT DEFAULT 'vote'`, `accuracy_at_time REAL`
- New repository methods in `AgencyMixin` or `AnalyticsMixin`: `get_weight_history()`, `save_indicator_weights()`

### API & CLI
- `api/routes/learning.py`: `GET /api/learning/weights`, `GET /api/learning/weights/history`
- CLI: `agency learn status`, `agency learn weights`
- LearningDashboard.vue — weight evolution tab (Chart.js line chart)

### Backward Compatibility
- `orchestrator.py` re-exports `compute_auto_tune_weights` from `learning.weight_tuner` (or update imports)
- Existing callers unaffected

## Task Breakdown Preview

- [ ] Create `learning/` module + relocate auto-tune weights + tests
- [ ] Extend indicator weight tuning + WeightSnapshot model + migration 037
- [ ] Weight history API/CLI endpoints + LearningDashboard weight tab

## Dependencies

- Epics 1-2 (desks + advisor exist for end-to-end testing)
- Existing `compute_auto_tune_weights()` in `orchestrator.py`
- Existing outcome tracking (`OutcomeCollector`, `AnalyticsMixin`)

## Success Criteria

- `compute_auto_tune_weights()` works identically from new location
- Indicator weight tuning produces measurably different weights after 100+ outcomes
- Weight history viewable via API and CLI
- Existing auto-tune tests continue passing
- ~20+ new tests

## Estimated Effort

5 issues, ~2-3 implementation sessions

## Tasks Created
- [ ] #608 - Create learning/ module and relocate vote weight tuning (parallel: false)
- [ ] #610 - Implement indicator weight tuning via outcome P&L correlation (parallel: false)
- [ ] #611 - Migration 035 and data layer for indicator weight persistence (parallel: false)
- [ ] #607 - Indicator weight tuning orchestration and outcome collection trigger (parallel: false)
- [ ] #609 - Weight history API endpoints and LearningDashboard frontend tab (parallel: false)

Total tasks: 5
Parallel tasks: 0
Sequential tasks: 5 (dependency chain: #608 → #610 → #611 → #607 → #609)
Estimated total effort: 18-25 hours

## Test Coverage Plan
Total test files planned: 7 (5 Python unit + 1 Python integration + 1 E2E)
Total test cases planned: ~40+
