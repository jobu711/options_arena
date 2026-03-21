# Falsy Check vs `is not None` Guard

## Problem

Using truthiness checks (`if value:`) on numeric fields that can legitimately be `0.0`
treats zero as falsy, skipping valid data. This is the same anti-pattern documented for
`dividend_yield` (waterfall fall-through must use `is None`, not falsy).

## Example (Bug)

```python
# WRONG — 0.0 is a valid fair_value but treated as "missing"
if model_result.fair_value:
    lines.append(f"  Fair Value: ${model_result.fair_value:.2f}")
```

## Fix

```python
# RIGHT — only skip when actually None
if model_result.fair_value is not None:
    lines.append(f"  Fair Value: ${model_result.fair_value:.2f}")
```

## Where This Applies

- Any `float | None` field where `0.0` is a valid value
- `dividend_yield` waterfall (documented in CLAUDE.md)
- `fair_value`, `margin_of_safety`, `correlation`, `spread` fields
- Display formatting in tool wrappers and CLI output

## Detection

Search for: `if variable_name:` where `variable_name` is typed `float | None`.
The pattern `if x:` on a `float | None` is almost always a bug.

## References

- `_toolsets.py:943` — fixed in epic ai-agency-analysis-tools
- CLAUDE.md: "dividend_yield: float = 0.0 never None; waterfall fall-through is `is None` not falsy"
