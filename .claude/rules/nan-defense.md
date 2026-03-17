# NaN/Inf Defense

`NaN` silently passes range checks like `v >= 0`. Every numeric validator MUST
check `math.isfinite()` BEFORE any range check.

```python
# WRONG - NaN passes silently
@field_validator("score")
@classmethod
def _check(cls, v: float) -> float:
    if v < 0:
        raise ValueError("negative")
    return v

# RIGHT - catch non-finite first
@field_validator("score")
@classmethod
def _check(cls, v: float) -> float:
    if not math.isfinite(v):
        raise ValueError("non-finite")
    if v < 0:
        raise ValueError("negative")
    return v
```

Also applies to:
- Confidence fields: `isfinite()` then `0.0 <= v <= 1.0`
- Pricing/scoring entry points: guard non-finite inputs
- Division results: return `float("nan")` for 0/0, not `0.0`
- Display: check `isfinite()` before formatting, fall back to `"--"`
