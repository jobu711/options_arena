# NaN Passes Through min/max Clamp Silently

## Problem

`max(0.0, min(1.0, value))` does NOT catch NaN. NaN comparisons always return False,
so `min(1.0, NaN)` returns `NaN` and `max(0.0, NaN)` returns `NaN`. The clamp appears
to work but silently propagates corrupt data.

## Context

Found in `learning/confidence_decay.py` — `decay_confidence()` clamped output to
`[0.0, 1.0]` but a NaN confidence input would pass through unchanged and be written
to the database, corrupting all downstream consumers.

## Solution

Always check `math.isfinite()` BEFORE any arithmetic or clamping:

```python
# WRONG — NaN passes through
clamped = max(0.0, min(1.0, value))

# RIGHT — guard first
if not math.isfinite(value):
    return 0.0  # or raise
clamped = max(0.0, min(1.0, value))
```

## Applies To

- Any function that clamps float output to a range
- Confidence values, scores, percentages, normalized indicators
- Repository update methods that accept raw floats (add validation at data layer too)

## Related

- `.claude/rules/nan-defense.md` — project-wide NaN defense pattern
- `models/strategy.py` — `StrategyRule.confidence` has model-level `isfinite()` validator
- `data/_learning.py` — `update_rule_confidence()` now validates at data layer entry
