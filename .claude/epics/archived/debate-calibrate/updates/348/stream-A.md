---
task: 348
stream: A
status: complete
updated: 2026-03-07T23:15:00Z
---

# Task 348 — Stream A: Ensemble diversity

## Completed

All 3 FRs (FR-5, FR-6, FR-7) implemented and tested.

### FR-5: Vote Entropy
- Added `ensemble_entropy: float | None = None` to `ExtendedTradeThesis` with `isfinite()` validator
- Added `_vote_entropy()` pure function to orchestrator (Shannon entropy of vote distribution)
- Entropy computed in `synthesize_verdict()` and set on `ExtendedTradeThesis`

### FR-6: Volatility Direction
- Added `direction: SignalDirection = SignalDirection.NEUTRAL` to `VolatilityThesis` (backward-compat default)
- Updated `build_cleaned_volatility_thesis()` to pass `direction=output.direction`
- Removed `isinstance(output, VolatilityThesis): continue` skip from direction voting
- Updated volatility prompt (v2.0 -> v3.0) with IV regime calibration anchors for directional output
- Updated JSON schema in prompt to include `direction` field

### FR-7: Relaxed Contrarian Gate
- Changed `phase1_failures < 2` to `phase1_failures < 3` in `_run_v2_agents()`
- Updated log message accordingly

## Tests Added (31 tests)

### `tests/unit/models/test_ensemble_fields.py` (15 tests)
- `TestExtendedTradeThesisEntropy`: default_none, valid_entropy, zero, nan, inf, neg_inf, backward_compat, roundtrip
- `TestVolatilityThesisDirection`: default_neutral, explicit_bullish, explicit_bearish, backward_compat, roundtrip, frozen_rejects, string_deser

### `tests/unit/agents/test_vote_entropy.py` (8 tests)
- unanimous_zero, two_way_split, three_way_split, empty_dict, single_agent, three_vs_one, all_neutral, non_negative

### `tests/unit/agents/test_volatility_direction.py` (8 tests)
- vol_included_in_directions, vol_bearish_swings_majority, vol_neutral_counted, entropy_set_on_thesis
- iv_regime_calibration_in_prompt, direction_in_json_schema, direction_values_documented, prompt_version_updated

## Verification
- ruff check: clean
- ruff format: clean
- mypy --strict: clean (4 source files)
- All 31 new tests pass
- All 439 existing agent tests pass
- All 1004 existing model tests pass

## Files Modified
- `src/options_arena/models/analysis.py` — added fields + validator
- `src/options_arena/agents/orchestrator.py` — added `_vote_entropy()`, wired entropy, removed vol skip, relaxed gate
- `src/options_arena/agents/_parsing.py` — updated `build_cleaned_volatility_thesis()` to pass direction
- `src/options_arena/agents/volatility.py` — updated prompt v2.0 -> v3.0 with directional output

## Files Created
- `tests/unit/models/test_ensemble_fields.py`
- `tests/unit/agents/test_vote_entropy.py`
- `tests/unit/agents/test_volatility_direction.py`
