# Analysis: #767 — Scan Pipeline Prediction Recording

## Streams

### Stream A: Model extension + phase_scoring changes
**Files:** `src/options_arena/models/scan.py`, `src/options_arena/scan/phase_scoring.py`
**Work:**
1. Add `scan_predictions: list[Prediction] = Field(default_factory=list)` to `ScoringResult` in `scan/models.py` (NOT `models/scan.py` — ScoringResult is in `scan/models.py`)
2. In `phase_scoring.py`, after direction + confidence assignment loop (after line ~161):
   - Build `Prediction` per ticker with `source=SCAN_DIRECTION`, `scan_run_id=0` placeholder
   - Context from `raw_signals[ticker]`: adx, iv_rank (None in Phase 2), atr_pct, rsi
   - Never-raises per-ticker try/except
3. Pass `scan_predictions` to `ScoringResult` constructor

### Stream B: Unit tests
**Files:** `tests/unit/scan/test_phase_scoring_predictions.py` (NEW)
**Work:**
1. Test one Prediction per TickerScore
2. Test direction matches TickerScore.direction
3. Test context from raw_signals
4. Test iv_rank=None expected
5. Test scan_run_id=0 placeholder
6. Test ScoringResult default empty list
7. Test prediction creation failure skipped

## Key Details
- `ScoringResult` is in `src/options_arena/scan/models.py` (NOT frozen, mutable)
- Direction assigned at lines 128-143 in phase_scoring.py
- Direction confidence computed at lines 145-161
- Best insertion point: after line 161 (both direction and confidence are set)
- `IndicatorSignals` has `adx`, `rsi`, `atr_pct` (available Phase 2); `iv_rank` (None until Phase 3)
- `direction_confidence` could be None — use `or 0.5` fallback for Prediction.confidence

## Dependencies
- Foundation epic: MERGED (Prediction, PredictionSource models available)
- No intra-epic dependencies

## Conflicts
- None — different files from #765/#766
