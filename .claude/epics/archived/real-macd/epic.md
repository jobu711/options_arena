---
name: real-macd
status: backlog
created: 2026-03-06T20:34:02Z
progress: 0%
prd: .claude/prds/real-macd.md
github: https://github.com/jobu711/options_arena/issues/311
---

# Epic: real-macd

## Overview

Replace the fake `_derive_macd_signal()` in `orchestrator.py` — which simply echoes the overall direction back as a MACD crossover — with a real MACD histogram computation. Add `macd()` to `indicators/trend.py`, register it in the pipeline, add the field to `IndicatorSignals`, integrate into composite scoring with rebalanced weights, and derive `MacdSignal` from the actual computed value so agents receive honest crossover data.

## Architecture Decisions

- **Single histogram value**: MACD function returns the histogram series (MACD line - signal line) as a `pd.Series`. The registry takes `iloc[-1]` as the normalized float. No multi-column DataFrame — follows existing indicator pattern.
- **Field name `macd`**: Matches PRD specification. Added to `IndicatorSignals` Trend section after `supertrend`.
- **`classify_macd_signal()` replaces `_derive_macd_signal()`**: New helper in `orchestrator.py` takes the raw (un-normalized) MACD histogram float and returns the appropriate `MacdSignal` enum value. Positive → BULLISH_CROSSOVER, negative → BEARISH_CROSSOVER, None/NaN → NEUTRAL.
- **Weight redistribution**: Add MACD at ~0.05 weight in "trend" category. Reduce existing trend weights by small amounts to keep sum = 1.0. Trend category goes from 0.18 to ~0.21 total, offset by minor reductions elsewhere.
- **Raw MACD value access**: `build_market_context()` needs the raw (un-normalized) MACD histogram to classify crossover signal. The `TickerScore.signals.macd` field holds the **normalized** value (0-100 percentile). We need raw signals from Phase 2's `raw_signals` dict, which is already available via `TickerScore` or passed through the pipeline. We'll source it from `IndicatorSignals` on the raw signals copy.

## Technical Approach

### Indicators Module (`indicators/trend.py`)
- Add `macd()` function following existing pattern (roc, adx, supertrend)
- Signature: `def macd(close: pd.Series, *, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.Series`
- Uses `pd.Series.ewm(span=N, adjust=False).mean()` for EMA
- Returns histogram (MACD line - signal line) as `pd.Series`
- Raises `InsufficientDataError` if insufficient data
- NaN for warmup bars
- Re-export from `indicators/__init__.py`

### Models (`models/scan.py`)
- Add `macd: float | None = None` to `IndicatorSignals` in the Trend section after `supertrend`
- Existing `_normalize_non_finite` validator handles NaN/Inf automatically

### Pipeline Registration (`scan/indicators.py`)
- Add `IndicatorSpec("macd", macd, InputShape.CLOSE)` to `INDICATOR_REGISTRY` in Trend section
- Registry count: 14 → 15

### Scoring (`scoring/composite.py`)
- Add `"macd": (0.05, "trend")` to `INDICATOR_WEIGHTS`
- Redistribute: reduce 3 weights by ~0.017 each (e.g., `rsi` 0.08→0.07, `sma_alignment` 0.08→0.07, `adx` 0.08→0.07) to free 0.03, plus reduce one 0.05→0.04 to free another 0.02 = 0.05 total
- Verify sum == 1.0 (enforced at import time)

### Orchestrator (`agents/orchestrator.py`)
- Delete `_derive_macd_signal(direction)` function
- Add `classify_macd_signal(macd_value: float | None) -> MacdSignal`
- Update `build_market_context()` to source raw MACD from `TickerScore.signals` (raw copy) instead of direction

### No Frontend Changes
- MACD value already flows through `IndicatorSignals` → API → frontend as a normalized float
- No new UI components needed per PRD (out of scope)

## Implementation Strategy

### Wave 1 — Foundation (parallelizable)
- Implement `macd()` function + unit tests
- Add `IndicatorSignals.macd` field

### Wave 2 — Pipeline Integration
- Register in `INDICATOR_REGISTRY`
- Add weight to `INDICATOR_WEIGHTS` (rebalance)
- Re-export from `__init__.py`

### Wave 3 — Orchestrator Fix
- Replace `_derive_macd_signal()` with `classify_macd_signal()`
- Update `build_market_context()` to use real MACD value

### Wave 4 — Validation
- Run full test suite, fix any regressions
- Verify MACD can disagree with overall direction (key acceptance criterion)

## Tasks Created
- [ ] #312 - Implement macd() function in indicators/trend.py (parallel: true)
- [ ] #314 - Add macd field to IndicatorSignals model (parallel: true)
- [ ] #316 - Register MACD in INDICATOR_REGISTRY and add scoring weight (parallel: false, depends: #312, #314)
- [ ] #313 - Replace fake MACD derivation in orchestrator (parallel: false, depends: #314, #316)
- [ ] #315 - Update existing tests for MACD integration (parallel: false, depends: #316, #313)
- [ ] #317 - Final validation and CLAUDE.md updates (parallel: false, depends: #315)

Total tasks: 6
Parallel tasks: 2 (Wave 1: #312, #314)
Sequential tasks: 4 (Waves 2-4: #316 → #313 → #315 → #317)
Estimated total effort: 6 hours

## Test Coverage Plan
Total test files planned: 4
Total test cases planned: ~24

## Dependencies

### Internal
- `indicators/trend.py` — add `macd()` alongside existing trend functions
- `models/scan.py` — `IndicatorSignals` field addition
- `scan/indicators.py` — `INDICATOR_REGISTRY` addition
- `scoring/composite.py` — `INDICATOR_WEIGHTS` rebalancing
- `agents/orchestrator.py` — `_derive_macd_signal()` removal
- `indicators/__init__.py` — re-export
- `models/enums.py` — `MacdSignal` (already exists, no changes needed)

### External
- `pandas` `pd.Series.ewm()` — already a dependency, no new packages

## Success Criteria (Technical)

| Criterion | Verification |
|-----------|-------------|
| `macd()` computes real 12/26/9 EMA histogram | Unit test with known values |
| `IndicatorSignals.macd` populated in pipeline | Integration test |
| `INDICATOR_REGISTRY` has 15 entries | Assertion in test |
| `_derive_macd_signal()` deleted | grep confirms removal |
| `classify_macd_signal()` uses real values | Unit test: bullish direction + negative MACD → BEARISH_CROSSOVER |
| Weights sum to 1.0 | Import-time validation (existing) |
| All existing tests pass | Full test suite |
| MACD can disagree with direction | Test case where direction=BULLISH but MACD=BEARISH_CROSSOVER |

## Estimated Effort

- **8 tasks**, ~2-3 hours implementation
- **Critical path**: Wave 1 (function + model) → Wave 2 (registry + weights) → Wave 3 (orchestrator) → Wave 4 (validation)
- **Risk**: Weight rebalancing may cause minor score shifts; PRD allows ±5 points
- **No new dependencies** required
