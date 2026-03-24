# Analysis: #765 — Prediction Scoring Functions

## Streams

### Stream A: Core scoring module (prediction_ledger.py)
**Files:** `src/options_arena/learning/prediction_ledger.py` (NEW)
**Work:**
1. Create `prediction_ledger.py` with logger, imports
2. Add `_direction_was_correct(predicted: SignalDirection, stock_return_pct: float) -> bool`
3. Add `score_predictions_for_recommendation(repo: Repository, recommendation_id: int) -> int`
4. Add `score_predictions_for_scan(repo: Repository, scan_run_id: int) -> int`
5. Add `run_prediction_scoring(repo: Repository) -> None` (never-raises wrapper)

### Stream B: Unit tests
**Files:** `tests/unit/learning/test_prediction_ledger.py` (NEW)
**Work:**
1. Create test file with fixtures
2. TestDirectionCorrectness — 7 parametrized cases
3. TestScorePredictionsForRecommendation — 3 async tests
4. TestRunPredictionScoring — never-raises test

## Key Patterns
- Follow `strategy_book.py` never-raises pattern (lines 418-439)
- `SignalDirection` enum: BULLISH, BEARISH, NEUTRAL (in `models/enums.py`)
- `ContractOutcome.stock_return_pct` is `float | None` (in `models/analytics.py`)
- CRUD methods available: `repo.score_predictions()`, `repo.score_scan_predictions()`, `repo.get_predictions()`
- Repository uses mixin pattern (`LearningMixin` in `data/_learning.py`)

## Dependencies
- Foundation epic: MERGED (models, migration, CRUD all available)
- No intra-epic dependencies

## Conflicts
- #766 extends the same file — must complete before #766 starts
