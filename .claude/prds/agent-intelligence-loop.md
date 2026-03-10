---
name: agent-intelligence-loop
description: Activate auto-tune agent weights from outcome accuracy data + Web UI weight tuning tab + close FinancialDatasets issues
status: planned
created: 2026-03-10T22:00:00Z
effort: M
---

# PRD: Agent Intelligence Loop

## Executive Summary

Make the debate system self-improving by connecting existing pieces that are already
built but never wired together. Three tracks:

1. **Activate auto-tune weights**: `compute_auto_tune_weights()`, `save_auto_tune_weights()`,
   `get_latest_auto_tune_weights()`, and the `auto_tune_weights` DB table (migration 028)
   all exist. `run_debate()` already loads persisted weights when `config.auto_tune_weights=True`.
   The missing piece: **nothing ever calls compute + persist**. Add a CLI command, API endpoint,
   and the single function that connects them.

2. **Web UI weight tuning tab**: New tab on the Analytics page showing manual vs auto-tuned
   weights, a trigger button to recompute, and a history chart of weight evolution over time.

3. **Close FinancialDatasets issues**: Issues #394-#399 and epic #390 describe work that was
   already implemented. Verify and close.

## Problem Statement

### The Auto-Tune Dead Code Problem

The entire auto-tune pipeline is implemented as isolated pieces that nothing connects:

```
get_agent_accuracy()          <- EXISTS in data/_debate.py:234
        |
compute_auto_tune_weights()   <- EXISTS in agents/orchestrator.py:912
        |
save_auto_tune_weights()      <- EXISTS in data/_debate.py:432
        |
get_latest_auto_tune_weights()<- EXISTS in data/_debate.py:393
        |
run_debate() loads weights    <- EXISTS in agents/orchestrator.py:1373
```

Every box exists. **No arrow between boxes 1-2-3 is ever executed in production.**
The `outcomes agent-weights` CLI command and `GET /api/analytics/agent-weights` endpoint
only *read* the latest snapshot -- they cannot *compute* one.

### No Weight History or Visibility

The `auto_tune_weights` table accumulates rows over time (each snapshot shares a
`created_at` timestamp), but `get_latest_auto_tune_weights()` only retrieves the most
recent snapshot. There is no query to retrieve history, no way to see how weights evolve,
and `window_days` is stored but never returned to callers.

### FD Issues Still Open

Issues #394-#399 (models, service, context rendering, wiring, tests) and epic #390 were
implemented in prior work but never formally closed on GitHub.

## User Stories

### US1: Compute and persist auto-tuned weights
**As** a power user with 50+ collected outcomes,
**I want** to run `options-arena outcomes auto-tune` to compute and save tuned weights,
**So that** subsequent debates automatically use accuracy-derived vote weights.

**Acceptance criteria:**
- `outcomes auto-tune [--dry-run] [--window 90]` computes weights from outcome data
- `--dry-run` shows comparison table without persisting
- Without `--dry-run`, weights are saved to `auto_tune_weights` table
- Next `run_debate()` with `auto_tune_weights=True` uses the persisted weights
- Rich table shows: agent | manual | tuned | delta | brier | samples
- Agents with <10 samples keep manual baseline (existing guard)

### US2: API trigger for auto-tune
**As** a web UI user,
**I want** to trigger weight auto-tuning from the browser,
**So that** I don't need CLI access to activate the intelligence loop.

**Acceptance criteria:**
- `POST /api/analytics/weights/auto-tune` computes and persists (with `dry_run` query param)
- `GET /api/analytics/weights/history` returns historical weight snapshots
- Response includes `computed_at`, `window_days`, and per-agent comparison data

### US3: Weight tuning analytics tab
**As** a developer evaluating agent performance,
**I want** a dedicated tab showing weight evolution and a tune button,
**So that** I can visualize how auto-tuning changes agent influence over time.

**Acceptance criteria:**
- New "Weight Tuning" tab on Analytics page
- Current weights comparison table (manual vs tuned, delta, brier, samples)
- "Auto-Tune" button triggers `POST /api/analytics/weights/auto-tune`
- History chart showing weight evolution across snapshots (line chart, one line per agent)
- Empty state when no tuned weights exist ("Run auto-tune to see results")

### US4: Close FD issues
**As** the project maintainer,
**I want** implemented FD issues formally closed,
**So that** the issue tracker reflects reality.

## Requirements

### FR1: Auto-Tune Orchestration Function

One function that connects the existing pieces:

```python
async def auto_tune_weights(
    repo: Repository,
    window_days: int = 90,
    dry_run: bool = False,
) -> list[AgentWeightsComparison]:
    """Connect the dots: accuracy -> compute -> persist."""
    accuracy = await repo.get_agent_accuracy(window_days=window_days)
    tuned = compute_auto_tune_weights(accuracy)
    comparisons = [
        AgentWeightsComparison(
            agent_name=name,
            manual_weight=AGENT_VOTE_WEIGHTS.get(name, 0.0),
            auto_weight=weight,
            brier_score=next(
                (a.brier_score for a in accuracy if a.agent_name == name), None
            ),
            sample_size=next(
                (a.sample_size for a in accuracy if a.agent_name == name), 0
            ),
        )
        for name, weight in tuned.items()
    ]
    if not dry_run:
        await repo.save_auto_tune_weights(comparisons, window_days=window_days)
    return comparisons
```

**Location**: `agents/orchestrator.py` -- next to `compute_auto_tune_weights()`. Keeps
pure computation and orchestration co-located while respecting boundaries (`agents/`
can access `models/` and `data/`).

### FR2: CLI `outcomes auto-tune` Subcommand

```
options-arena outcomes auto-tune [--dry-run] [--window 90]
```

- Calls `auto_tune_weights()` from FR1
- Renders Rich table: Agent | Manual | Tuned | Delta | Brier | Samples
- Delta column: `tuned - manual` with color (green if positive, red if negative)
- On `--dry-run`: prints table + "[DRY RUN] Weights not saved."
- Without `--dry-run`: prints table + "Weights saved. Next debate will use tuned weights."

### FR3: Weight History Repository Method

```python
async def get_weight_history(
    self,
    limit: int = 20,
) -> list[WeightSnapshot]:
```

New `WeightSnapshot` model:

```python
class WeightSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    computed_at: datetime  # UTC validated
    window_days: int
    weights: list[AgentWeightsComparison]
```

Query groups `auto_tune_weights` rows by `created_at`, orders DESC, limits to N snapshots.
Returns the full history for the weight evolution chart.

### FR4: API Endpoints

```python
# Trigger auto-tune computation
@router.post("/weights/auto-tune")
async def trigger_auto_tune(
    request: Request,
    repo: Repository = Depends(get_repo),
    window: int = Query(90, ge=1, le=365),
    dry_run: bool = Query(False),
) -> list[AgentWeightsComparison]: ...

# Weight history for chart
@router.get("/weights/history")
async def get_weight_history(
    request: Request,
    repo: Repository = Depends(get_repo),
    limit: int = Query(20, ge=1, le=100),
) -> list[WeightSnapshot]: ...
```

### FR5: Web UI -- Weight Tuning Tab

**New files:**
- `web/src/components/analytics/WeightTuningPanel.vue` -- tab content component

**Modified files:**
- `web/src/pages/AnalyticsPage.vue` -- add tab entry + lazy loading
- `web/src/stores/backtest.ts` -- add weight state + fetch/trigger actions

**Panel layout:**

```
+-------------------------------------------------------------+
|  Weight Tuning                              [Auto-Tune >]   |
+-------------------------------------------------------------+
|                                                             |
|  Current Weights                                            |
|  +------------+--------+--------+--------+-------+-------+ |
|  | Agent      | Manual | Tuned  | Delta  | Brier | N     | |
|  +------------+--------+--------+--------+-------+-------+ |
|  | trend      | 0.250  | 0.284  | +0.034 | 0.182 | 87    | |
|  | volatility | 0.200  | 0.198  | -0.002 | 0.215 | 82    | |
|  | flow       | 0.200  | 0.172  | -0.028 | 0.241 | 75    | |
|  | fundamental| 0.150  | 0.148  | -0.002 | 0.228 | 64    | |
|  | contrarian | 0.050  | 0.048  | -0.002 | 0.312 | 71    | |
|  | risk       | 0.000  | 0.000  |  0.000 |  --   | --    | |
|  +------------+--------+--------+--------+-------+-------+ |
|                                                             |
|  Weight Evolution                                           |
|  +-----------------------------------------------------+   |
|  |  0.30 - - trend ---------------/--                   |   |
|  |  0.25 -                       /                      |   |
|  |  0.20 - - volatility ------------- - -               |   |
|  |  0.15 - - flow ---------\-------- -                  |   |
|  |  0.10 - - fundamental ----------- -                  |   |
|  |  0.05 - - contrarian ------------ -                  |   |
|  |       +------+------+------+------+------+           |   |
|  |       Mar 1  Mar 3  Mar 5  Mar 7  Mar 10            |   |
|  +-----------------------------------------------------+   |
|                                                             |
|  Empty state: "No tuned weights yet. Click Auto-Tune."     |
+-------------------------------------------------------------+
```

- Table: CSS grid matching existing analytics panels
- Chart: PrimeVue `Chart` (Chart.js line chart), one dataset per agent, color-coded
- Button: PrimeVue `Button`, POST to `/api/analytics/weights/auto-tune`, refresh on success
- Loading state during computation, toast on success/error

### FR6: Close FD Issues

Verify each issue against existing code and close:

| Issue | Title | Evidence |
|-------|-------|----------|
| #394 | Models + Config | `models/financial_datasets.py` (173 lines) |
| #395 | FinancialDatasetsService | `services/financial_datasets.py` (344 lines) |
| #396 | MarketContext 16 fd_* fields | `models/analysis.py` |
| #397 | Context rendering + prompt v3.0 | `agents/_parsing.py:617-670` |
| #398 | Integration wiring | CLI, API, orchestrator all pass `fd_package` |
| #399 | Test suite | 998 lines across 2 test files |
| #390 | Epic tracker | All child issues complete |

## Files Changed

### New Files (4)

| File | Purpose | Lines |
|------|---------|-------|
| `web/src/components/analytics/WeightTuningPanel.vue` | Tab content: table + chart + button | ~120 |
| `web/src/types/weights.ts` | `WeightSnapshot`, `AgentWeight` TS interfaces | ~20 |
| `tests/unit/agents/test_auto_tune_orchestration.py` | Tests for `auto_tune_weights()` function | ~80 |
| `tests/unit/cli/test_outcomes_auto_tune.py` | Tests for CLI subcommand | ~60 |

### Modified Files (7)

| File | Change | Lines |
|------|--------|-------|
| `models/analytics.py` | Add `WeightSnapshot` model | +15 |
| `agents/orchestrator.py` | Add `auto_tune_weights()` function (FR1) | +20 |
| `cli/outcomes.py` | Add `auto-tune` subcommand (FR2) | +40 |
| `data/_debate.py` | Add `get_weight_history()` method (FR3) | +30 |
| `api/routes/analytics.py` | Add 2 endpoints (FR4) | +25 |
| `web/src/pages/AnalyticsPage.vue` | Add tab entry + onTabChange branch | +8 |
| `web/src/stores/backtest.ts` | Add weight state + actions | +35 |

### NOT Modified (Confirmed Complete)

- `models/financial_datasets.py` -- FDPackage model
- `services/financial_datasets.py` -- FinancialDatasetsService
- `agents/_parsing.py` -- context rendering for fd_* fields
- `models/config.py` -- `DebateConfig.auto_tune_weights` flag + `FinancialDatasetsConfig`
- `data/migrations/028_auto_tune_weights.sql` -- table exists
- `agents/orchestrator.py:compute_auto_tune_weights()` -- pure computation, no changes
- `agents/orchestrator.py:run_debate()` -- weight loading already wired
- `data/_debate.py:save_auto_tune_weights()` -- persistence method exists
- `data/_debate.py:get_latest_auto_tune_weights()` -- read method exists
- `scan/` -- scan pipeline doesn't debate; no FD wiring needed

## Design Decisions

### Why no new migration?

Migration 028 created `auto_tune_weights` with a row-per-agent schema that stores
`window_days` and `created_at`. The history query groups by `created_at` to reconstruct
snapshots. The schema is sufficient -- adding `is_active` or `weights_json` would be a
parallel structure for the same data.

### Why no FD scan wiring?

Research confirmed the scan pipeline (`scan/`) is a pure 4-phase scoring pipeline that
never invokes `run_debate()`. Debates are always triggered separately via CLI
(`debate --scan-id N`) or API (`POST /api/debate/batch`). Both paths already wire
`FinancialDatasetsService`. There is no gap to fix.

### Why `auto_tune_weights()` lives in orchestrator?

It imports `compute_auto_tune_weights()` and `AGENT_VOTE_WEIGHTS` (already in orchestrator)
and calls `repo.get_agent_accuracy()` + `repo.save_auto_tune_weights()`. The `agents/`
module can access `models/` and `data/` per the boundary table. Placing it here avoids
creating a new module and keeps the auto-tune logic co-located.

## Success Criteria

| Metric | Target |
|--------|--------|
| `outcomes auto-tune` produces valid weights | Weights sum to 0.85, each in [0.05, 0.35] |
| `outcomes auto-tune --dry-run` shows table, no DB write | Assert empty `auto_tune_weights` after dry run |
| Weight persistence round-trip | Persist -> load in next debate -> weights match |
| History endpoint returns snapshots | Multiple auto-tune runs -> history grows |
| Web UI displays weights | Table renders, chart renders, button triggers POST |
| FD issues closed | #390, #394-#399 all closed |
| Existing tests pass | Zero regressions |
| New test coverage | 20+ tests |

## Non-Functional Requirements

- **Safety**: `--dry-run` flag for preview. Manual `AGENT_VOTE_WEIGHTS` always available as reset.
- **Backward compatibility**: `auto_tune_weights=False` is the default. Debates without the flag behave identically.
- **Minimum samples**: Agents with <10 outcomes keep manual weights (existing guard in `compute_auto_tune_weights`).
- **Weight clamp**: [0.05, 0.35] per agent prevents any single agent from dominating (existing guard).

## Out of Scope

- Per-sector weight tuning (insufficient samples)
- Automatic auto-tune scheduling (manual trigger only)
- Weight A/B testing (parallel manual vs tuned debates)
- FD scan pipeline wiring (confirmed unnecessary -- see Design Decisions)
- New FD data sources beyond existing `fetch_package()`

## Implementation Phases

### Wave 1: Backend -- Auto-Tune Activation (4 issues)
1. `WeightSnapshot` model in `models/analytics.py`
2. `auto_tune_weights()` function in `agents/orchestrator.py`
3. `get_weight_history()` method in `data/_debate.py`
4. `outcomes auto-tune` CLI subcommand in `cli/outcomes.py`

### Wave 2: API + Web UI (3 issues)
5. POST + GET endpoints in `api/routes/analytics.py`
6. Weight Tuning tab: store, types, panel component
7. AnalyticsPage integration + E2E test

### Wave 3: Housekeeping (1 issue)
8. Verify and close FD issues #394-#399 + epic #390

## Effort Estimate

**Total: M (2-3 days)**
- Wave 1: M (1 day) -- new function + method + CLI command + tests
- Wave 2: M (1 day) -- 2 API endpoints + Vue tab with table + chart
- Wave 3: S (1-2 hours) -- GitHub issue verification + closure
