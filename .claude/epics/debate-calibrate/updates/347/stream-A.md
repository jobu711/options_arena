# Task 347: Orchestrator wiring + log-odds pooling — COMPLETE

## Changes Made

### `src/options_arena/agents/orchestrator.py`

1. **Imported domain renderers** from `_parsing.py`:
   - `render_trend_context`, `render_volatility_context`, `render_flow_context`, `render_fundamental_context`

2. **Partitioned context wiring in `_run_v2_agents()`**:
   - Replaced single `context_text = render_context_block(context)` with 5 context strings
   - `trend_context` -> trend agent (Phase 1)
   - `vol_context` -> volatility agent (Phase 1)
   - `flow_context` -> flow agent (Phase 1)
   - `fund_context` -> fundamental agent (Phase 1)
   - `full_context` -> risk agent (Phase 2), contrarian agent (Phase 3), citation density

3. **Added `_log_odds_pool()` pure function** (Bordley 1982):
   - Clamps inputs to [0.01, 0.99] to prevent log(0)/log(inf)
   - Weights are NOT normalized — compounds independent opinions
   - Three agents at 0.9 -> ~0.997 (satisfies NFR-7 > 0.95)
   - Empty list returns 0.5 (neutral prior)

4. **Replaced linear averaging in `synthesize_verdict()`**:
   - Kept existing collection loop for probabilities and weights from `agent_outputs`
   - Replaced `weighted_confidence /= total_weight` with `_log_odds_pool()` call
   - Agreement-based confidence cap preserved unchanged

5. **Removed dead `"risk": 0.15`** from `AGENT_VOTE_WEIGHTS`:
   - Confirmed dead code — `RiskAssessment` is passed separately, never enters confidence loop

### Tests Created

- `tests/unit/agents/test_log_odds_pool.py` — 12 test cases
- `tests/unit/agents/test_orchestrator_wiring.py` — 3 test cases (weight removal, weight completeness, domain context wiring)

## Verification

- `ruff check` + `ruff format`: clean
- `mypy --strict`: no issues
- All 423 agent tests pass (including 15 new tests)
