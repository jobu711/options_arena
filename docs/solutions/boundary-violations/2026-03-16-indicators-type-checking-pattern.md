---
title: "Threading config into indicators/ without violating architecture boundary"
date: 2026-03-16
module: options_arena.indicators.vol_surface
problem_type: boundary_violation
severity: medium
symptoms:
  - "mypy error: Argument type 'object | None' incompatible with 'MLConfig | None'"
  - "Runtime ImportError if indicators/ imports from models/ directly"
  - "Need to pass MLConfig to indicator functions without adding models/ dependency"
tags:
  - architecture-boundary
  - type-checking
  - indicators
  - models
  - from-future-annotations
root_cause: "indicators/ cannot import models/ at runtime per architecture table; TYPE_CHECKING pattern needed for type hints"
---

## Problem

`indicators/vol_surface.py` needed an `MLConfig` parameter to thread neural surface
configuration through `compute_vol_surface()`. But per the architecture boundary table,
`indicators/` can only access `pandas` and `numpy` — never `models/`.

A naive `from options_arena.models import MLConfig` would violate the boundary. Using
`object | None` as the type caused mypy errors downstream when callers passed `MLConfig | None`.

## Root Cause

The architecture boundary exists because `indicators/` is a pure math layer (pandas in,
pandas out). Adding runtime imports from `models/` would create coupling between the math
layer and the data shape layer.

## Solution

Use `TYPE_CHECKING` + `from __future__ import annotations` for type-only imports:

```python
from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from options_arena.models import MLConfig

def compute_vol_surface(
    chain_df: pd.DataFrame,
    spot: float,
    ml_config: MLConfig | None = None,  # resolved as string at runtime
) -> VolSurfaceResult:
    ...
```

Key details:
- `from __future__ import annotations` makes ALL annotations strings (PEP 563)
- `TYPE_CHECKING` block is only evaluated by mypy/pyright, never at runtime
- At runtime, `MLConfig` is never imported — the annotation is just a string
- mypy sees the full type and validates callers correctly
- The function body accesses config via `getattr()` or passes it opaquely

## Prevention Rule

**When `indicators/` needs a type from `models/` for a function signature, use the
`TYPE_CHECKING` pattern.** Never add a runtime import from `models/` in `indicators/`.
The function can receive the config object and pass it through to other modules that
DO have access to `models/`. Inside `indicators/`, access config attributes via
`getattr(config, "field", default)` if needed.

## Related

- PR #555 (CodeRabbit review — ml_config threading suggestion)
- Architecture boundary table in `CLAUDE.md`
- `indicators/vol_surface.py`, `scan/phase_options.py`
