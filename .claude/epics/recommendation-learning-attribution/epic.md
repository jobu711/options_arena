---
name: recommendation-learning-attribution
status: completed
created: 2026-03-24T00:09:54Z
updated: 2026-03-23T13:00:00Z
completed: 2026-03-23T13:00:00Z
progress: 100%
prd: .claude/prds/recommendation-learning.md
parent_epic: recommendation-learning
depends_on:
  - recommendation-learning-foundation
github: https://github.com/jobu711/options_arena/issues/764
---

# Epic: recommendation-learning-attribution

## Overview

Implement prediction recording, scoring, and attribution analysis — the core capture-and-analyze
loop. Records predictions during scan and recommendation pipelines, scores them automatically
during outcome collection, and provides attribution reports via CLI and API. Delivers user
stories US-1, US-2, and US-6.

## Scope Boundary

### In Scope
- Prediction recording hook in scan pipeline (`phase_scoring.py`)
- Prediction recording hook in recommendation orchestrator
- Prediction scoring logic triggered by outcome collection
- Attribution computation (per-source accuracy + condition bucketing)
- `learn attribution` CLI subcommand
- `GET /api/analytics/attribution` API endpoint
- Hook scoring into `outcomes collect` flow
- Unit + integration tests

### Out of Scope (handled by sibling epics)
- Models, migration, data CRUD (foundation epic)
- Strategy mining condition dimensions (feedback epic)
- Contract guidance computation and prompt injection (feedback epic)
- Weight tuner enhancement (feedback epic)

## Architecture Decisions

- **Scoring uses stock return direction** (not contract return) — isolates direction accuracy from contract selection quality. Positive `stock_return_pct` = bullish was correct.
- **Scoring is batch**: all predictions for a recommendation scored in one commit after outcome collection.
- **Scan predictions scored via ticker linkage**: join `predictions(scan_run_id, ticker)` to `recommended_contracts(scan_run_id, ticker)` to `contract_outcomes`.
- **Scan predictions without outcomes stay unscored** (`was_correct=None`) — expected for tickers scanned but not recommended.
- **Attribution minimum thresholds**: 10 for source-level, 20 for condition-level (per PRD).
- **Never-raises contract**: all recording and scoring functions catch exceptions and log, never crash the pipeline.

## Technical Approach

### Prediction Ledger (`learning/prediction_ledger.py`, ~300-400 lines, NEW FILE)

Core computation module with pure functions:

```python
async def score_predictions_for_recommendation(repo: Repository, recommendation_id: int) -> int:
    """Score all predictions for a recommendation based on outcome direction."""

async def score_predictions_for_scan(repo: Repository, scan_run_id: int) -> int:
    """Score scan direction predictions based on outcome direction."""

def compute_attribution(predictions: list[Prediction]) -> AttributionReport:
    """Group by source, compute accuracy, bucket by conditions."""

def _classify_adx(adx: float | None) -> str | None:
    """ADX bucket: weak (<20), moderate (20-30), strong (>30)."""

def _classify_iv_rank(iv_rank: float | None) -> str | None:
    """IV Rank bucket: low (<30), mid (30-70), high (>70)."""
```

### Scan Recording (`scan/phase_scoring.py`, ~15-20 lines added)

After `determine_direction()` in Phase 2:
```python
prediction = Prediction(
    scan_run_id=scan_run_id,
    ticker=ts.ticker,
    source=PredictionSource.SCAN_DIRECTION,
    predicted_direction=ts.direction,
    confidence=ts.direction_confidence,
    adx=raw.adx, iv_rank=raw.iv_rank, atr_pct=raw.atr_pct, rsi=raw.rsi,
)
```

**Open question from research**: `phase_scoring.py` may not have `repo` access in Phase 2.
If not, collect predictions in memory during Phase 2 and persist in Phase 4 (persistence phase).

### Orchestrator Recording (`agents/recommendation_orchestrator.py`, ~30-40 lines added)

After desk execution loop (~line 626), create one `Prediction` per desk from `DomainAssessment`:
```python
predictions = []
for metrics in desk_results:
    predictions.append(Prediction(
        recommendation_id=rec_id,
        ticker=ticker,
        source=PredictionSource(f"desk_{metrics.desk.value}"),
        predicted_direction=metrics.assessment.direction,
        confidence=float(metrics.assessment.confidence),
        adx=market_context.adx, ...
    ))
# Add synthesis prediction after synthesis completes
await repo.save_predictions_batch(predictions)
```

### Outcome Scoring Hook (`cli/outcomes.py` / `services/outcome_collector.py`)

After `collector.collect_outcomes()` returns, before `run_confidence_decay()`:
```python
await score_predictions(repo)  # batch score all newly-linked predictions
```

### CLI (`cli/outcomes.py`, ~40-50 lines added)

```python
@learn_app.command("attribution")
def attribution_cmd(
    window_days: int = typer.Option(90, min=7, max=365),
    source: PredictionSource | None = typer.Option(None),
) -> None:
    report = asyncio.run(_run_attribution(window_days, source))
    # Rich table output: per-source accuracy + condition breakdown
```

### API (`api/analytics.py`, ~15-20 lines added)

```python
@router.get("/attribution")
@limiter.limit("60/minute")
async def get_attribution(
    request: Request,
    window_days: int = Query(default=90, ge=7, le=365),
    source: PredictionSource | None = Query(default=None),
    repo: Repository = Depends(get_repo),
) -> AttributionReport:
```

## Task Breakdown Preview

- [ ] Task 1: `learning/prediction_ledger.py` — scoring functions (score by recommendation_id, by scan_run_id)
- [ ] Task 2: `learning/prediction_ledger.py` — attribution computation (per-source accuracy + condition bucketing)
- [ ] Task 3: `scan/phase_scoring.py` — record scan direction prediction after determine_direction()
- [ ] Task 4: `agents/recommendation_orchestrator.py` — record desk + synthesis predictions after assessments
- [ ] Task 5: `cli/outcomes.py` + `services/outcome_collector.py` — hook scoring into outcomes collect
- [ ] Task 6: `cli/outcomes.py` + `api/analytics.py` — attribution CLI command + API endpoint
- [ ] Task 7: Unit + integration tests (scoring logic, attribution, full loop)

## Dependencies

- **Foundation epic**: Must be merged — provides `Prediction` model, `PredictionSource` enum, data CRUD methods, migration
- **Sibling (feedback)**: No dependency — zero shared modified files
- **Existing**: `outcome_collector.py` (read-only), `determine_direction()` (read-only), `DomainAssessment` (read-only)

## Success Criteria

- Predictions persisted for every scan direction + desk assessment + synthesis in test recommendation
- Scoring correctly marks predictions based on stock return direction
- Attribution report computes in < 2s for 1,000 predictions
- Minimum sample thresholds enforced (10 source-level, 20 condition-level)
- `learn attribution` displays Rich table with per-source accuracy + condition breakdown
- API endpoint returns `AttributionReport` JSON
- Recording adds < 50ms to pipeline; scoring adds < 100ms to outcome collection
- All tests green, mypy --strict clean, ruff clean

## Tasks Created

- [ ] #765 - Prediction scoring functions (parallel: true)
- [ ] #766 - Attribution computation and condition classifiers (parallel: false, depends: #765)
- [ ] #767 - Scan pipeline prediction recording (parallel: true)
- [ ] #768 - Orchestrator prediction persistence (parallel: false, depends: #767)
- [ ] #769 - Hook scoring into outcomes collect (parallel: true, depends: #765)
- [ ] #770 - Attribution CLI command and API endpoint (parallel: false, depends: #766)
- [ ] #771 - Integration tests and full-loop verification (parallel: false, depends: #768, #769, #770)

Total tasks: 7
Parallel tasks: 3 (#765, #767, #769)
Sequential tasks: 4 (#766, #768, #770, #771)
Estimated total effort: 18-24 hours

## Test Coverage Plan

Total test files planned: 6
- `tests/unit/learning/test_prediction_ledger.py` (~15 test cases)
- `tests/unit/scan/test_phase_scoring_predictions.py` (~7 test cases)
- `tests/unit/agents/test_orchestrator_predictions.py` (~10 test cases)
- `tests/unit/cli/test_outcomes_scoring_hook.py` (~3 test cases)
- `tests/unit/cli/test_learn_attribution.py` + `tests/unit/api/test_attribution_endpoint.py` (~8 test cases)
- `tests/integration/test_prediction_lifecycle.py` (~7 test cases)
Total test cases planned: ~50
Critical markers: 2 (lifecycle integration, attribution CLI)

## Estimated Effort

- ~7 tasks, ~450-550 new lines of production code
- ~50 unit + integration tests across 6 test files
- Medium risk — scan pipeline hook resolved (collect in memory, persist in orchestrator)
