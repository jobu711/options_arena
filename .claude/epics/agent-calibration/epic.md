---
name: agent-calibration
status: completed
created: 2026-03-09T16:43:07Z
progress: 100%
prd: .claude/prds/agent-calibration.md
github: https://github.com/jobu711/options_arena/issues/407
---

# Epic: agent-calibration

## Overview

Close the feedback loop between agent predictions and real outcomes. Add per-agent accuracy
tracking (direction hit rate, Brier score, confidence calibration), expose via CLI + API, and
auto-tune `AGENT_VOTE_WEIGHTS` from empirical performance. All infrastructure exists:
`AgentPrediction` (migration 025), `OutcomeCollector`, `ContractOutcome`. This epic wires them
together with queries, models, and a weight computation algorithm.

## Architecture Decisions

- **JOIN path**: `agent_predictions.recommended_contract_id` → `contract_outcomes.recommended_contract_id` (direct FK, no intermediate hops). Fallback through `debate_id → ai_theses.id` only if `recommended_contract_id` is NULL.
- **Canonical holding period**: T+10 (`holding_days=10`) for direction accuracy evaluation.
- **Direction accuracy**: Compare `agent_predictions.direction` (`BULLISH`/`BEARISH`) against sign of `contract_outcomes.stock_return_pct`. Positive return = bullish correct, negative = bearish correct.
- **Weight formula**: Normalized inverse Brier score `(1.0 - brier_score)` per agent, with floor=0.05, cap=0.35, risk=0.0, sum normalized to 0.85 (Bordley 1982 constraint).
- **Agent names**: 6 agents stored in DB: `trend`, `volatility`, `flow`, `fundamental`, `contrarian`, `risk`. Note: `extract_agent_predictions()` maps "bull" → "trend" in v2 protocol.
- **Opt-in auto-tune**: `DebateConfig.auto_tune_weights: bool = False`. Manual `AGENT_VOTE_WEIGHTS` remain default. Zero behavior change unless explicitly enabled.
- **Pure function injection**: `synthesize_verdict()` gets `vote_weights` param (optional). Weights injected, not fetched — keeps function pure and testable.

## Technical Approach

### Models (in `models/analytics.py`)

4 new frozen Pydantic models following existing pattern (`frozen=True`, `math.isfinite()` validators):

- `AgentAccuracyReport`: `agent_name`, `direction_hit_rate`, `mean_confidence`, `brier_score`, `sample_size`
- `CalibrationBucket`: `bucket_label`, `bucket_low`, `bucket_high`, `mean_confidence`, `actual_hit_rate`, `count`
- `AgentCalibrationData`: `agent_name | None`, `buckets: list[CalibrationBucket]`, `sample_size`
- `AgentWeightsComparison`: `agent_name`, `manual_weight`, `auto_weight`, `brier_score | None`, `sample_size`

### Migrations

- **026**: Composite index `idx_ap_name_created ON agent_predictions(agent_name, created_at)` — accelerates time-windowed accuracy queries.
- **027**: `auto_tune_weights` table — stores per-agent weight history with Brier scores, sample sizes, window.

### Repository Queries (in `data/repository.py`)

4 new async methods following existing `async with conn.execute(SQL)` pattern:

- `get_agent_accuracy(window_days: int | None) -> list[AgentAccuracyReport]` — JOIN + GROUP BY with 10-sample minimum
- `get_agent_calibration(agent_name: str | None) -> AgentCalibrationData` — 5-bucket binning
- `get_latest_auto_tune_weights() -> list[AgentWeightsComparison]` — most recent weight set
- `save_auto_tune_weights(weights: list[AgentWeightsComparison], window_days: int) -> None`

### Weight Computation

Pure function `compute_auto_tune_weights(accuracy: list[AgentAccuracyReport]) -> dict[str, float]`:
- Input: per-agent accuracy reports (from repository query)
- Agents with < 10 samples: keep manual weight from `AGENT_VOTE_WEIGHTS`
- Agents with ≥ 10 samples: `raw = 1.0 - brier_score`
- Floor each at 0.05, cap at 0.35, risk always 0.0
- Normalize directional weights to sum = 0.85
- Returns `dict[str, float]` suitable for injection into `synthesize_verdict()`

### Orchestrator Integration

- `synthesize_verdict()`: Add `vote_weights: dict[str, float] | None = None` parameter. If provided, use instead of `AGENT_VOTE_WEIGHTS`. If None, backward-compatible behavior.
- `run_debate()`: When `config.auto_tune_weights=True` and `repository` is provided, load auto-tuned weights via `get_latest_auto_tune_weights()`. Pass to `synthesize_verdict()`.

### CLI Commands (in `cli/outcomes.py`)

3 new subcommands, sync Typer + `asyncio.run()`:
- `outcomes agent-accuracy [--window DAYS]` — Rich table: Agent, Hit Rate, Confidence, Brier, Samples
- `outcomes calibration [--agent NAME]` — Rich table: calibration buckets per agent
- `outcomes agent-weights` — Rich table: manual vs auto-tuned comparison

### API Endpoints (in `api/routes/analytics.py`)

3 new GET endpoints, rate-limited 60/min, `Depends(get_repo)`:
- `GET /api/analytics/agent-accuracy?window=90` → `list[AgentAccuracyReport]`
- `GET /api/analytics/agent-calibration?agent=trend` → `AgentCalibrationData`
- `GET /api/analytics/agent-weights` → `list[AgentWeightsComparison]`

## Task Breakdown Preview

- [ ] Task 1: Foundation — models, config field, migrations 026+027, model exports
- [ ] Task 2: Repository queries — 4 new async methods with JOIN logic and 10-sample minimum
- [ ] Task 3: Weight computation + orchestrator integration — pure weight function, `synthesize_verdict()` param, `run_debate()` loading
- [ ] Task 4: CLI commands — 3 outcomes subcommands with Rich tables
- [ ] Task 5: API endpoints — 3 GET endpoints under `/api/analytics/`
- [ ] Task 6: Tests — repository, weight computation, orchestrator, CLI, API coverage (35+ tests)

## Dependencies

### Internal (all shipped)
- `AgentPrediction` model + migration 025 — per-agent predictions
- `ContractOutcome` model + migration 012 — outcome records with `stock_return_pct`, `is_winner`
- `OutcomeCollector` — collects T+1/T+5/T+10/T+20 P&L
- `extract_agent_predictions()` — extracts predictions from `DebateResult`
- `AGENT_VOTE_WEIGHTS` — existing manual weights (sum=0.85)
- Repository layer, CLI outcomes app, API analytics router

### External
- None — all data is local SQLite

## Success Criteria (Technical)

| Metric | Target |
|--------|--------|
| Per-agent accuracy | All 6 agents reported after 10+ outcomes |
| Calibration buckets | 5 buckets populated per agent |
| Auto-tune constraints | sum=0.85, each in [0.05, 0.35], risk=0.0 |
| 10-sample guard | No stats for <10 outcomes |
| Backward compatibility | All existing orchestrator tests pass unchanged |
| `isfinite()` guards | Every computed float validated |
| Test coverage | 35+ new tests |
| Query performance | <500ms for 1000 predictions |

## Estimated Effort

**L (5-6 days)** — 6 tasks across 4 waves

- Wave 1 (Task 1): S — models, config, migrations. No logic.
- Wave 2 (Task 2): L — complex JOIN queries, Brier score, calibration buckets, 10-sample logic.
- Wave 3 (Tasks 3-5, parallel): M — weight computation, orchestrator, CLI, API. Tasks 4+5 parallel with 3.
- Wave 4 (Task 6): M — test suite for all new paths.

## Tasks Created

- [ ] #411 - Foundation — Models, Config, Migrations (parallel: true)
- [ ] #413 - Repository Queries — Accuracy, Calibration, Weight CRUD (parallel: false, depends: #411)
- [ ] #415 - Weight Computation + Orchestrator Integration (parallel: false, depends: #413)
- [ ] #410 - CLI Commands — agent-accuracy, calibration, agent-weights (parallel: true, depends: #413)
- [ ] #412 - API Endpoints — agent-accuracy, agent-calibration, agent-weights (parallel: true, depends: #413)
- [ ] #414 - Integration Tests — End-to-End Calibration Pipeline (parallel: false, depends: #415, #410, #412)

Total tasks: 6
Parallel tasks: 3 (#411, #410, #412)
Sequential tasks: 3 (#413, #415, #414)
Estimated total effort: 30-40 hours

## Test Coverage Plan

Total test files planned: 7
Total test cases planned: ~50

| Test File | Task | Cases |
|-----------|------|-------|
| `tests/unit/models/test_agent_calibration_models.py` | #411 | 12 |
| `tests/unit/data/test_agent_calibration_queries.py` | #413 | 12 |
| `tests/unit/agents/test_weight_computation.py` | #415 | 8 |
| `tests/unit/agents/test_orchestrator_weights.py` | #415 | 3 |
| `tests/unit/cli/test_outcomes_calibration.py` | #410 | 8 |
| `tests/unit/api/test_agent_calibration_routes.py` | #412 | 8 |
| `tests/integration/test_calibration_pipeline.py` | #414 | 8 |
