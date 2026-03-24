# Analysis: #769 — Hook Scoring into Outcomes Collect

## Streams

### Stream A: Wire scoring hook
**Files:** `src/options_arena/cli/outcomes.py` (MODIFY ~5 lines)
**Work:**
1. Import run_prediction_scoring from learning.prediction_ledger
2. After collector.collect_outcomes() returns, before run_confidence_decay():
   - Call `await run_prediction_scoring(repo)`
3. run_prediction_scoring is already never-raises, no extra try/except needed

### Stream B: Unit test
**Files:** `tests/unit/cli/test_outcomes_scoring_hook.py` (NEW)
**Work:**
1. Test scoring called after collection
2. Test scoring called before confidence decay (order)
3. Test scoring failure doesn't block decay

## Key Details
- Hook location: _outcomes_collect_async() in cli/outcomes.py
- Order: collect → score predictions → confidence decay
- run_prediction_scoring() already catches all exceptions internally
- XS-size task — minimal code changes

## Dependencies
- #765: run_prediction_scoring() must exist ✅ (completed)
