---
title: "NaN silently passes numeric range validators like v >= 0"
date: 2026-03-13
module: options_arena.models
problem_type: nan_defense
severity: critical
symptoms:
  - "NaN values accepted by Pydantic validators that check v >= 0"
  - "Downstream computation produces NaN without any validation error"
  - "isfinite() not called before range check in field_validator"
tags:
  - nan
  - NaN
  - isfinite
  - validation
  - pydantic
  - range-check
  - inf
root_cause: "IEEE 754: NaN comparisons always return False, so NaN >= 0 is False but NaN < 0 is also False — range checks silently pass"
---

## Problem

Pydantic field validators that check numeric ranges like `if v < 0: raise ValueError`
silently accept `NaN` values. The corrupted value propagates through the system,
producing incorrect results without any error.

## Root Cause

IEEE 754 floating-point standard: `NaN` compared to anything (including itself) returns
`False`. This means:
- `NaN >= 0` → `False`
- `NaN < 0` → `False`
- `NaN == NaN` → `False`

So a validator like `if v < 0: raise ValueError("must be non-negative")` passes for NaN
because `NaN < 0` is `False`. The NaN slips through undetected.

## Solution

Always check `math.isfinite()` BEFORE any range check:

```python
import math
from pydantic import field_validator

@field_validator("price")
@classmethod
def _validate_price(cls, v: float) -> float:
    if not math.isfinite(v):          # catches NaN AND Inf
        raise ValueError("must be finite")
    if v < 0:
        raise ValueError("must be non-negative")
    return v
```

`math.isfinite()` returns `False` for NaN, +Inf, and -Inf — catching all three.

## Prevention Rule

**Every numeric validator must call `math.isfinite()` before range checks.** This is the
#1 source of subtle bugs in Options Arena. Grep for validators missing `isfinite` with:
`grep -n "field_validator" | grep -v "isfinite"` on model files.

## Related

- CLAUDE.md: "Don't leave numeric validators without `math.isfinite()`"
- `src/options_arena/models/` — all model files should follow this pattern
- Python docs: `math.isfinite(x)` — returns True if x is neither infinity nor NaN
