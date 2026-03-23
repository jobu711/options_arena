# CLAUDE.md -- Analysis Module (`analysis/`)

## Purpose

Pure computation modules for competitive analysis: valuation models, correlation analysis,
risk-adjusted performance metrics, and position sizing. No I/O, no API calls, no database
access. Consumes typed models from `models/` and stdlib/numpy/pandas. Returns typed models.

## Architecture Rules

- **No API calls** -- data comes from `services/` via the caller, never fetched here
- **Typed models everywhere** -- consume and return Pydantic models from `models/`
- **No raw dicts** from public functions
- **Constants, not magic numbers** -- all thresholds, weights, and bounds are module-level uppercase
- Can import from: `models/`, stdlib (`math`, `statistics`, `datetime`, `dataclasses`), `numpy`, `pandas`
- Cannot import from: APIs, services, I/O, `pricing/` directly, `indicators/`, `scoring/`, `data/`

## What Claude Gets Wrong Here

- Don't call APIs from analysis code -- data comes from the caller
- Don't return raw dicts from public functions -- use typed models
- Don't use magic numbers -- reference the named constants
- Don't confuse weighted arithmetic mean with weighted geometric mean
- Don't forget to clamp composite scores to [0, 100]
- Don't forget that theta is per-day (divided by 365), not annual
