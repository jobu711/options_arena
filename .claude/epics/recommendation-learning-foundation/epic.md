---
name: recommendation-learning-foundation
status: backlog
created: 2026-03-24T00:09:54Z
progress: 0%
prd: .claude/prds/recommendation-learning.md
parent_epic: recommendation-learning
depends_on: []
github: https://github.com/jobu711/options_arena/issues/758
---

# Epic: recommendation-learning-foundation

## Overview

Create the shared data infrastructure for the prediction ledger: Pydantic models,
database migration, and data access methods. This is the foundation that both sibling
epics (attribution and feedback) depend on. Ships first, merges to master before
siblings begin.

## Scope Boundary

### In Scope
- `PredictionSource` StrEnum and all prediction/report models
- `predictions` table migration with indexes and FK constraints
- `LearningMixin` CRUD methods: save, score, query predictions
- Full unit test coverage for models and data layer

### Out of Scope (handled by sibling epics)
- Prediction recording hooks in scan/orchestrator (attribution epic)
- Scoring logic and attribution computation (attribution epic)
- Strategy mining enhancement (feedback epic)
- Contract guidance computation (feedback epic)
- CLI commands and API endpoints (attribution epic)
- Prompt injection blocks (feedback epic)

## Architecture Decisions

- `PredictionSource` has 8 values: `SCAN_DIRECTION`, 6 desk types, `SYNTHESIS` (no `DESK_RESEARCH` — Research desk is interactive, doesn't produce `DomainAssessment`)
- `Prediction` model is `frozen=True` with `isfinite()` + range validators on `confidence`
- `model_validator` enforces at least one of `recommendation_id` or `scan_run_id` is set
- Context snapshot fields (`adx`, `iv_rank`, `atr_pct`, `rsi`) are `float | None` — lean subset of 27 indicators
- Migration uses `UNIQUE(recommendation_id, source)` and `UNIQUE(scan_run_id, ticker, source)` for idempotent recording
- Data methods follow existing `LearningMixin` pattern: parameterized queries, `Row` factory, `commit: bool = True`

## Technical Approach

### Models (`models/attribution.py`, ~100-120 lines)

```python
class PredictionSource(StrEnum):
    SCAN_DIRECTION = "scan_direction"
    DESK_TREND = "desk_trend"
    DESK_VOLATILITY = "desk_volatility"
    DESK_FLOW = "desk_flow"
    DESK_FUNDAMENTAL = "desk_fundamental"
    DESK_RISK = "desk_risk"
    DESK_CONTRARIAN = "desk_contrarian"
    SYNTHESIS = "synthesis"

class Prediction(BaseModel, frozen=True):
    # Full model per PRD spec with validators

class PredictionAccuracy(BaseModel, frozen=True):
    # Per-source accuracy stats

class ConditionBucketAccuracy(BaseModel, frozen=True):
    # Per-source per-condition accuracy

class ContractGuidance(BaseModel, frozen=True):
    # Learned optimal delta/DTE ranges

class AttributionReport(BaseModel, frozen=True):
    # Full attribution output combining all above
```

### Migration (`data/migrations/041_predictions.sql`)

```sql
CREATE TABLE predictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    recommendation_id INTEGER REFERENCES recommendation_results(id),
    scan_run_id INTEGER REFERENCES scan_runs(id),
    ticker TEXT NOT NULL,
    source TEXT NOT NULL,
    predicted_direction TEXT NOT NULL,
    confidence REAL NOT NULL,
    adx REAL, iv_rank REAL, atr_pct REAL, rsi REAL,
    was_correct INTEGER,
    created_at TEXT NOT NULL,
    UNIQUE(recommendation_id, source),
    UNIQUE(scan_run_id, ticker, source)
);
-- Plus 5 indexes per PRD spec
```

### Data Layer (`data/_learning.py` additions, ~80-100 lines)

New methods on `LearningMixin`:
- `save_prediction(prediction: Prediction) -> int` — INSERT, return id
- `save_predictions_batch(predictions: list[Prediction]) -> list[int]` — batch INSERT
- `score_predictions(recommendation_id: int, was_correct: bool) -> int` — UPDATE, return count
- `score_scan_predictions(scan_run_id: int, ticker: str, was_correct: bool) -> int`
- `get_predictions(window_days: int, source: PredictionSource | None) -> list[Prediction]`
- `get_prediction_accuracy(window_days: int) -> list[PredictionAccuracy]`

## Task Breakdown Preview

- [ ] Task 1: `models/attribution.py` — PredictionSource enum + all 6 models with validators
- [ ] Task 2: Migration 041 — predictions table + indexes + FK constraints
- [ ] Task 3: `data/_learning.py` — save/batch save prediction methods
- [ ] Task 4: `data/_learning.py` — score + query prediction methods
- [ ] Task 5: Unit tests — model validation + data persistence tests

## Dependencies

- **External**: None
- **Internal**: Existing `recommendation_results` and `scan_runs` tables (migration 037+)
- **Sibling epics**: Both attribution and feedback depend on this shipping first

## Success Criteria

- All 6 models pass validation tests including NaN/Inf defense
- Migration creates table with correct schema, indexes, and FK constraints
- CRUD methods work against in-memory SQLite
- Idempotent recording: duplicate prediction raises on UNIQUE constraint
- `was_correct` starts as `None`, updated via score methods
- All tests green, mypy --strict clean, ruff clean

## Tasks Created

- [ ] #759 - Prediction models and enums (parallel: true)
- [ ] #760 - Predictions table migration (parallel: true)
- [ ] #761 - Data layer — save prediction methods (parallel: false, depends: #759, #760)
- [ ] #762 - Data layer — score and query prediction methods (parallel: false, depends: #761)
- [ ] #763 - Comprehensive tests and edge case coverage (parallel: false, depends: #762)

Total tasks: 5
Parallel tasks: 2 (#759, #760)
Sequential tasks: 3 (#761 → #762 → #763)
Estimated total effort: 9-13 hours

## Test Coverage Plan

Total test files planned: 2
- `tests/unit/models/test_attribution.py` (~15-20 test cases)
- `tests/unit/data/test_prediction_persistence.py` (~15-20 test cases)
Total test cases planned: ~30-40
Critical markers: 2 (one model, one data lifecycle)

## Estimated Effort

- ~5 tasks, ~200-250 new lines of production code
- ~30-40 unit tests across 2 test files
- Low risk — follows established patterns in `data/_learning.py` and `models/`
