# Research: recommendation-learning

## PRD Summary

Add a prediction ledger that records every intermediate decision in the recommendation
pipeline (scan direction, 7 desk direction calls, synthesis), scores them against outcomes,
and feeds accuracy data back into existing learning infrastructure. Regime awareness emerges
from enriched strategy mining dimensions. Human approval gates on all weight/pattern changes.

## Critical Discovery: `agent_predictions` Table Already Exists

The codebase already has an `agent_predictions` table (migration 025 + 037) that stores
per-agent direction and confidence. However, it has an FK constraint to `ai_theses(id)`
(the old debate system) and cannot currently reference `recommendation_results`. The
orchestrator has a deferred note (lines 724-734) acknowledging this gap.

**Decision**: Create a new `predictions` table rather than retrofitting `agent_predictions`.
The new table has a cleaner schema (dual FK to `recommendation_results` + `scan_runs`,
context snapshot columns) and avoids touching the legacy debate data. The old
`agent_predictions` table can be sunset later.

## Relevant Existing Modules

### Direct Modifications Required

| Module | File | What Changes |
|--------|------|-------------|
| `learning/` | New `prediction_ledger.py` | Core attribution logic: scoring, bucketing, contract guidance |
| `learning/` | `strategy_book.py` | Add condition dimensions (ADX bucket, vol bucket) to `OutcomeWithContext` and mining |
| `learning/` | `weight_tuner.py` | Accept prediction-derived desk accuracy (richer than current `AgentAccuracyReport`) |
| `models/` | New `attribution.py` | `PredictionSource`, `Prediction`, `AttributionReport`, `ContractGuidance` models |
| `data/` | `_learning.py` | New methods: `save_prediction`, `score_predictions`, `get_prediction_accuracy` |
| `data/` | New migration 041 | `predictions` table + indexes |
| `agents/` | `recommendation_orchestrator.py` | Persist `Prediction` per desk after assessments; inject `<<<CONTRACT_GUIDANCE>>>` |
| `scan/` | `phase_scoring.py` | Persist `Prediction` for scan direction after `determine_direction()` |
| `cli/` | `outcomes.py` | Add `learn attribution` subcommand; hook scoring into `outcomes collect` |
| `api/` | `analytics.py` | New `GET /api/analytics/attribution` endpoint |

### Read-Only Dependencies (no changes needed)

| Module | File | Relationship |
|--------|------|-------------|
| `scoring/` | `direction.py` | `determine_direction()` — called in scan, predictions recorded after it returns |
| `models/` | `recommendation.py` | `DomainAssessment` base + 6 subclasses carry `direction` + `confidence` |
| `models/` | `analytics.py` | `AgentAccuracyReport`, `ContractOutcome`, `RecommendedContract` |
| `models/` | `scan.py` | `IndicatorSignals` (source of ADX, IV Rank, ATR%, RSI context) |
| `models/` | `strategy.py` | `StrategyRule`, `StrategyCondition` |
| `services/` | `outcome_collector.py` | Outcome collection flow — prediction scoring hooks in after |

## Existing Patterns to Reuse

### 1. Never-Raises Orchestration (learning/, agents/)
```python
async def run_prediction_scoring(repo: Repository) -> None:
    try:
        await _score_predictions_inner(repo)
    except Exception:
        logger.exception("Prediction scoring failed")
```
All learning orchestration functions follow this. Prediction recording and scoring must too.

### 2. Repository Mixin (data/_learning.py, data/_debate.py)
New prediction CRUD methods go in `LearningMixin`. Pattern: parameterized queries,
`await conn.commit()`, `Row` factory for named access, `commit: bool = True` parameter.

### 3. Prompt Injection Blocks (learning/strategy_book.py:364-410)
```python
def render_learned_patterns(rules: list[StrategyRule]) -> str:
    lines = ["<<<LEARNED_PATTERNS>>>"]
    # ... build content ...
    lines.append("<<<END_LEARNED_PATTERNS>>>")
    text = "\n".join(lines)
    if len(text) > MAX_PATTERN_TEXT_CHARS:
        text = text[:text.rfind("\n", 0, MAX_PATTERN_TEXT_CHARS)]
    return text
```
New `<<<CONTRACT_GUIDANCE>>>` block follows identical pattern. Injected in orchestrator
alongside existing `<<<LEARNED_PATTERNS>>>` and `<<<TUNED_WEIGHTS>>>`.

### 4. IV/DTE Bucket Classification (learning/strategy_book.py:36-48)
```python
IV_BUCKETS = [(0, 25, "low"), (25, 50, "mid_low"), (50, 75, "mid_high"), (75, 100, "high")]
DTE_BUCKETS = [(0, 30, "short"), (30, 60, "medium"), (60, 120, "long"), (120, 365, "extended")]
```
Reuse `_classify_iv()` and `_classify_dte()` for condition bucketing. Add new
`_classify_adx()` and `_classify_vol()` following the same pattern.

### 5. Outcome Join Query (learning/strategy_book.py:478-513)
```sql
SELECT ... FROM contract_outcomes co
JOIN recommended_contracts rc ON co.recommended_contract_id = rc.id
LEFT JOIN ticker_metadata tm ON rc.ticker = tm.ticker
WHERE co.contract_return_pct IS NOT NULL AND co.is_winner IS NOT NULL
```
Prediction scoring joins similarly: `predictions` → `recommendation_results` → `contract_outcomes`.

### 6. Test Helpers (tests/unit/learning/, tests/unit/data/)
Pattern: `_make_outcome()`, `_make_cell()`, `_make_rule()` helpers construct models with defaults.
In-memory SQLite via `Database(":memory:")`. Async fixtures with `@pytest_asyncio.fixture`.
Markers: `@pytest.mark.critical`, `@pytest.mark.db`, `@pytest.mark.asyncio`.

### 7. API Endpoint Pattern (api/analytics.py)
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

## Existing Code to Extend

### `recommendation_orchestrator.py` — Hook Point for Desk Predictions
**Location**: After Phase 1 (parallel desk execution), ~line 626
- Each desk returns `DomainAssessment` with `direction: SignalDirection` and `confidence: float`
- `DeskMetrics` carries `desk: DeskType`
- `MarketContext` carries indicator values for context snapshot
- **Action**: After loop, create `Prediction` per desk + one for synthesis, batch persist

### `scan/phase_scoring.py` — Hook Point for Scan Direction
**Location**: After `determine_direction()` call, ~line 137
```python
ts.direction = determine_direction(adx=raw.adx or 0.0, rsi=raw.rsi or 50.0, ...)
```
- `raw_signals[ts.ticker]` has all indicator values for context snapshot
- **Action**: Create `Prediction` with `source=SCAN_DIRECTION`, persist with `scan_run_id`

### `cli/outcomes.py` — Hook Point for Prediction Scoring
**Location**: After `collector.collect_outcomes()` returns, ~line 151
- Currently calls `run_confidence_decay(repo)` after outcome collection
- **Action**: Add `await score_predictions(repo)` call before confidence decay

### `learning/strategy_book.py` — Extend `OutcomeWithContext`
**Location**: Lines 61-86
- Currently: `sector`, `iv_level`, `dte_at_entry`, `direction`, `return_pct`, `is_winner`
- **Action**: Add `adx: float | None`, `atr_pct: float | None`, `rsi: float | None`
- Update `_fetch_outcomes_with_context()` SQL to join these from `IndicatorSignals` or `predictions` context

### `learning/weight_tuner.py` — Accept Prediction-Derived Accuracy
**Location**: `compute_auto_tune_weights()` at line 54
- Currently takes `list[AgentAccuracyReport]` from `repo.get_agent_accuracy()`
- **Action**: `get_agent_accuracy()` query can be enhanced to pull from `predictions` table
  instead of `agent_predictions`, providing per-desk accuracy from scored predictions.
  Interface stays the same (`AgentAccuracyReport`), data source changes.

## Potential Conflicts

### 1. `agent_predictions` vs New `predictions` Table
**Risk**: Two tables storing similar data (per-agent direction predictions).
**Mitigation**: New `predictions` table has a cleaner schema and different purpose (attribution
vs. debate tracking). Old `agent_predictions` table stays as-is for backward compatibility
with existing analytics queries. Document that new code uses `predictions` table exclusively.

### 2. Scan Pipeline Doesn't Currently Have `repo` Access in Phase 2
**Risk**: `phase_scoring.py` may not have a `Repository` instance to persist predictions.
**Mitigation**: Check if `repo` is passed through the pipeline. If not, prediction recording
can be deferred to Phase 4 (persistence phase) by collecting predictions in memory during
Phase 2 and persisting them alongside other scan data.

### 3. Outcome Scoring Linkage for Scan Predictions
**Risk**: Scan predictions have `scan_run_id` + `ticker` but no `recommendation_id`. Outcome
data is linked to `recommended_contracts` which has `scan_run_id` + `ticker`. Need a join path.
**Mitigation**: Join via `(ticker, scan_run_id)` — both `predictions` and `recommended_contracts`
share these columns. A scan prediction is "correct" if any recommended contract for that
ticker in that scan run had positive stock return.

### 4. `OutcomeWithContext` Extension
**Risk**: Adding fields to `OutcomeWithContext` may break existing strategy mining if the
SQL query doesn't return the new columns.
**Mitigation**: New fields are `float | None` with defaults. Update the SQL query in
`_fetch_outcomes_with_context()` to LEFT JOIN indicator context. Existing callers unaffected
because new fields default to `None`.

## Open Questions

1. **Scan pipeline `repo` access**: Does `phase_scoring.py` receive a `Repository` instance?
   If not, prediction recording needs to be deferred to Phase 4 or passed through the
   pipeline context. (Implementation detail, not a blocker.)

2. **Direction correctness definition**: For desk predictions, is `was_correct` based on
   `stock_return_pct` direction (price went up = bullish was correct) or
   `contract_return_pct` (the option made money)? Stock return is cleaner for direction
   attribution; contract return conflates direction with contract selection quality.
   **Recommendation**: Use `stock_return_pct` for direction correctness.

3. **Research desk**: The Research desk (`DeskType.RESEARCH`) is an interactive agent, not
   a recommendation desk. It doesn't produce `DomainAssessment` during recommendations.
   Should `DESK_RESEARCH` be in `PredictionSource`? **Recommendation**: Remove it — only
   the 6 recommendation desks + scan + synthesis generate predictions.

## Recommended Architecture

### Layer Structure
```
models/attribution.py          — PredictionSource, Prediction, report models (frozen)
data/_learning.py              — LearningMixin additions (save, score, query predictions)
data/migrations/041_*.sql      — predictions table
learning/prediction_ledger.py  — Pure computation: scoring, bucketing, attribution, guidance
scan/phase_scoring.py          — Record scan direction prediction (1 line + helper)
agents/recommendation_orch.py  — Record desk + synthesis predictions (batch persist)
cli/outcomes.py                — Hook scoring into collect; add attribution subcommand
api/analytics.py               — GET /api/analytics/attribution endpoint
```

### Data Flow
```
CAPTURE (during scan/recommendation):
  scan direction → Prediction(source=SCAN_DIRECTION, scan_run_id=X)
  desk assessment → Prediction(source=DESK_TREND, recommendation_id=Y)
  synthesis → Prediction(source=SYNTHESIS, recommendation_id=Y)

SCORE (during outcomes collect):
  outcomes collected → score_predictions(repo) marks was_correct on all linked predictions

ANALYZE (on demand):
  learn attribution → compute_attribution() → AttributionReport
  learn tune-votes → get_agent_accuracy() now uses predictions table → better weights
  learn mine → OutcomeWithContext now has condition dimensions → richer patterns

FEEDBACK (into next recommendation):
  <<<LEARNED_PATTERNS>>> — now includes condition-aware patterns
  <<<CONTRACT_GUIDANCE>>> — optimal delta/DTE from outcome data
  <<<TUNED_WEIGHTS>>> — prediction-informed desk weights
```

## Test Strategy Preview

### Existing Test Patterns to Follow
- **Location**: `tests/unit/learning/` for learning module tests
- **Location**: `tests/unit/data/` for DB/migration tests
- **Fixtures**: In-memory SQLite, `@pytest_asyncio.fixture`, pre-created scan runs for FK refs
- **Helpers**: `_make_*()` functions that construct models with sensible defaults
- **Markers**: `@pytest.mark.critical` (pre-commit), `@pytest.mark.db`, `@pytest.mark.asyncio`

### New Test Files
| File | Tests |
|------|-------|
| `tests/unit/learning/test_prediction_ledger.py` | Scoring logic, bucketing, attribution, contract guidance |
| `tests/unit/models/test_attribution.py` | Model validation: confidence range, isfinite, source enum |
| `tests/unit/data/test_prediction_persistence.py` | Save, score, query predictions via LearningMixin |
| `tests/unit/data/test_migration_041.py` | Table creation, indexes, FK constraints |

### Key Test Scenarios
- Score predictions: bullish prediction + positive return → correct
- Score predictions: bullish prediction + negative return → incorrect
- Attribution with < 10 samples → `sample_sufficient=False`
- Condition bucketing with `None` indicator values → excluded from that dimension
- Contract guidance with < 30 outcomes → returns `None`
- Full loop: scan → recommend → persist predictions → collect outcome → score → attribution

## Estimated Complexity

**L (Large)** — 3-4 epics estimated

Justification:
- 1 new model file, 1 new learning module file, 1 migration — moderate new code (~600-800 lines)
- 5-6 existing files need modification — moderate integration work
- 60-70 new unit tests + 10-15 integration tests — significant test coverage
- Touches scan pipeline, recommendation orchestrator, learning, CLI, API — wide surface area
- No new external dependencies — reduces risk
- Heavy reuse of existing patterns — reduces implementation uncertainty

Suggested epic decomposition:
1. **Foundation**: Models + migration + prediction CRUD in data layer + basic tests
2. **Capture**: Hook prediction recording into scan pipeline + recommendation orchestrator
3. **Score + Attribute**: Scoring logic, attribution computation, CLI command
4. **Feedback**: Strategy mining enhancement, contract guidance, prompt injection, weight tuner integration
