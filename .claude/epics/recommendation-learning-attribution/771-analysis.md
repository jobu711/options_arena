# Analysis: #771 — Integration Tests and Full-Loop Verification

## Streams

### Stream A: Integration test file
**Files:** `tests/integration/test_prediction_lifecycle.py` (NEW)
**Work:**
1. Full lifecycle test: save recommendation → save predictions → save outcomes → score → attribute
2. Cold start test: zero data → empty report, no crash
3. Idempotent scoring test: double-scoring same results
4. Performance test: 1,000 predictions attributed in < 2s
5. Never-raises test: DB error during scoring → logged
6. Mixed outcomes test: some correct, some incorrect → accurate %

## Key Patterns
- Integration tests use in-memory SQLite with all migrations applied
- Check existing tests/integration/ for fixture patterns (DB setup, repo creation)
- Mark with @pytest.mark.critical, @pytest.mark.integration, @pytest.mark.asyncio
- Factory helpers for predictions — check tests/factories.py for make_prediction()
- All functions to test:
  - learning/prediction_ledger.py: run_prediction_scoring(), compute_attribution()
  - data/_learning.py: save_predictions_batch(), get_predictions(), score_predictions()

## Dependencies
- All prior tasks #765-#770 ✅ (completed)
