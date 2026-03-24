# Analysis: #766 — Attribution Computation and Condition Classifiers

## Streams

### Stream A: Attribution logic in prediction_ledger.py
**Files:** `src/options_arena/learning/prediction_ledger.py` (EXTEND existing)
**Work:**
1. Add bucket constants (ADX_BUCKETS, IV_RANK_BUCKETS, ATR_PCT_BUCKETS, RSI_BUCKETS)
2. Add _classify_adx(), _classify_iv_rank(), _classify_atr_pct(), _classify_rsi()
3. Add _compute_source_accuracy(predictions) -> list[PredictionAccuracy]
4. Add _compute_condition_accuracy(predictions) -> list[ConditionBucketAccuracy]
5. Add compute_attribution(predictions, contract_guidance=None) -> AttributionReport

### Stream B: Unit tests (extend existing test file)
**Files:** `tests/unit/learning/test_prediction_ledger.py` (EXTEND)
**Work:**
1. TestClassifiers — parametrized cases for all 4 classifiers
2. TestComputeAttribution — empty, source accuracy, thresholds, condition bucketing, multiple sources

## Key Patterns
- Bucket pattern from strategy_book.py: list[tuple[float, float, str]]
- Pure function compute_attribution() — no DB access, takes pre-fetched list
- MIN_SOURCE_SAMPLES = 10, MIN_CONDITION_SAMPLES = 20
- Filter to scored predictions (was_correct is not None) for accuracy
- Models: PredictionAccuracy, ConditionBucketAccuracy, AttributionReport from models/attribution.py

## Dependencies
- #765: prediction_ledger.py must exist ✅ (completed)
