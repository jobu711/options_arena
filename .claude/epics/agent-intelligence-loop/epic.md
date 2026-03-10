---
name: agent-intelligence-loop
status: backlog
created: 2026-03-10T18:17:25Z
progress: 0%
prd: .claude/prds/agent-intelligence-loop.md
github: https://github.com/jobu711/options_arena/issues/452
---

# Epic: agent-intelligence-loop

## Overview

Activate the auto-tune intelligence loop by connecting existing dead-code primitives
(`compute_auto_tune_weights()`, `save_auto_tune_weights()`, `get_agent_accuracy()`) with
thin entry points (CLI subcommand, 2 API endpoints), add a weight history query for
time-series visibility, build a Weight Tuning tab in the Vue analytics page, and close
the already-implemented FinancialDatasets issues.

~60% of the infrastructure already exists. This epic wires the remaining ~40%.

## Architecture Decisions

1. **`auto_tune_weights()` orchestration function in `agents/orchestrator.py`**: Co-locates
   with `compute_auto_tune_weights()` and `AGENT_VOTE_WEIGHTS`. The `agents/` module can
   access `models/` and `data/` per boundary table. ~20 lines connecting existing pieces.

2. **No new migration**: Migration 028 created `auto_tune_weights` with row-per-agent schema
   storing `window_days` and `created_at`. History query groups by `created_at` to reconstruct
   snapshots. Schema is sufficient.

3. **`WeightSnapshot` model**: New frozen Pydantic model wrapping `computed_at`, `window_days`,
   and `list[AgentWeightsComparison]`. Lives in `models/analytics.py` alongside existing
   `AgentWeightsComparison`.

4. **`get_weight_history()` in `data/_debate.py`**: Groups `auto_tune_weights` rows by
   `created_at` DESC, joins with manual weights, limits to N snapshots. Returns
   `list[WeightSnapshot]`.

5. **Web UI**: New "Weight Tuning" tab on AnalyticsPage with comparison table, Auto-Tune
   trigger button, and Chart.js line chart for weight evolution. Reuses existing PrimeVue
   DataTable + Chart patterns from other analytics tabs.

## Technical Approach

### Backend (Wave 1)

| Component | File | Change |
|-----------|------|--------|
| `WeightSnapshot` model | `models/analytics.py` | +15 lines |
| `auto_tune_weights()` function | `agents/orchestrator.py` | +25 lines |
| `get_weight_history()` method | `data/_debate.py` | +30 lines |
| `outcomes auto-tune` CLI subcommand | `cli/outcomes.py` | +40 lines |
| Unit tests | `tests/unit/agents/`, `tests/unit/cli/` | +140 lines |

### API + Web UI (Wave 2)

| Component | File | Change |
|-----------|------|--------|
| `POST /weights/auto-tune` | `api/routes/analytics.py` | +15 lines |
| `GET /weights/history` | `api/routes/analytics.py` | +10 lines |
| API tests | `tests/unit/api/` | +60 lines |
| `WeightTuningPanel.vue` | `web/src/components/analytics/` | ~120 lines |
| `weights.ts` types | `web/src/types/` | ~20 lines |
| Store additions | `web/src/stores/backtest.ts` | +35 lines |
| Tab integration | `web/src/pages/AnalyticsPage.vue` | +8 lines |

### Housekeeping (Wave 3)

- Verify and close FD issues #394-#399 + epic #390 on GitHub

## Implementation Strategy

- **Wave 1** (backend): Model + orchestration + repo method + CLI + tests. All backend
  pieces land first so API and UI have a stable foundation.
- **Wave 2** (API + UI): API endpoints + Vue tab. Can be parallelized internally (API
  and frontend are independent until integration).
- **Wave 3** (housekeeping): GitHub issue closure. No code changes.
- Run full test suite after each wave.

## Task Breakdown Preview

- [ ] Task 1: `WeightSnapshot` model + `get_weight_history()` repo method + tests
- [ ] Task 2: `auto_tune_weights()` orchestration function + tests
- [ ] Task 3: `outcomes auto-tune` CLI subcommand + tests
- [ ] Task 4: API endpoints (`POST /weights/auto-tune`, `GET /weights/history`) + tests
- [ ] Task 5: Web UI — Weight Tuning tab (types, store, panel, page integration)
- [ ] Task 6: E2E test for Weight Tuning tab
- [ ] Task 7: Verify + close FD issues #394-#399 and epic #390

## Dependencies

- **Internal**: Migration 028 (exists), `compute_auto_tune_weights()` (exists),
  `AgentWeightsComparison` model (exists), `save_auto_tune_weights()` (exists)
- **External**: None — all data sources already wired
- **Prerequisite**: Sufficient outcome data (50+ collected outcomes) for meaningful weights.
  Not a code blocker — auto-tune degrades gracefully with <10 samples per agent.

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| `outcomes auto-tune` produces valid weights | Weights sum to 0.85, each in [0.05, 0.35] |
| `outcomes auto-tune --dry-run` shows table, no DB write | Assert empty after dry run |
| Weight persistence round-trip | Persist -> load in next debate -> weights match |
| History endpoint returns snapshots | Multiple auto-tune runs -> history grows |
| Web UI displays weights | Table renders, chart renders, button triggers POST |
| FD issues closed | #390, #394-#399 all closed |
| Existing tests pass | Zero regressions |
| New test coverage | 20+ tests |

## Tasks Created
- [ ] #453 - WeightSnapshot model + weight history query (parallel: true)
- [ ] #454 - auto_tune_weights() orchestration function (parallel: false, depends: #453)
- [ ] #455 - outcomes auto-tune CLI subcommand (parallel: false, depends: #454)
- [ ] #456 - Auto-tune API endpoints (parallel: true, depends: #453, #454)
- [ ] #457 - Weight Tuning tab (parallel: false, depends: #456)
- [ ] #458 - E2E test for Weight Tuning tab (parallel: false, depends: #457)
- [ ] #459 - Verify and close FinancialDatasets issues (parallel: true)

Total tasks: 7
Parallel tasks: 3 (#453, #456, #459)
Sequential tasks: 4 (#454→#455, #457→#458)
Estimated total effort: 15-17 hours

## Test Coverage Plan
Total test files planned: 6
Total test cases planned: ~35

## Estimated Effort

**M (Medium) — 2-3 days**
- Wave 1: M (1 day) — new function + method + CLI command + tests
- Wave 2: M (1 day) — 2 API endpoints + Vue tab with table + chart
- Wave 3: S (1-2 hours) — GitHub issue verification + closure
