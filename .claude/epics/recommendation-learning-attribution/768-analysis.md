# Analysis: #768 — Orchestrator Prediction Persistence

## Streams

### Stream A: Orchestrator changes
**Files:** `src/options_arena/agents/recommendation_orchestrator.py` (MODIFY)
**Work:**
1. Add _desk_type_to_prediction_source(desk: DeskType) -> PredictionSource mapping
2. Add _build_desk_predictions() helper
3. In _persist_recommendation(), after save_recommendation returns rec_id:
   - Build desk + synthesis predictions
   - Update scan predictions with real scan_run_id
   - Call repo.save_predictions_batch()
   - All wrapped in try/except (never-raises)

### Stream B: Unit tests
**Files:** `tests/unit/agents/test_orchestrator_predictions.py` (NEW)
**Work:**
1. TestDeskTypeToPredictionSource — parametrized mapping
2. TestBuildDeskPredictions — one per desk, context, skips failed
3. TestOrchestratorPredictionPersistence — async tests with mocked repo

## Key Details
- DeskType enum values: TREND, VOLATILITY, FLOW, FUNDAMENTAL, RISK, CONTRARIAN (+ RESEARCH which is NOT mapped)
- PredictionSource enum: DESK_TREND, DESK_VOLATILITY, etc. + SYNTHESIS
- _persist_recommendation() has access to rec_id, ticker, desk_results, MarketContext
- Need to pass ScoringResult through to get scan_predictions
- Scan predictions have scan_run_id=0 placeholder — replace with real ID

## Dependencies
- #767: ScoringResult.scan_predictions field ✅ (completed)
