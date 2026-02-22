# CLAUDE.md — Analysis & Scoring

## Purpose
Scoring engine that normalizes indicator outputs, computes composite scores, determines
directional signals, recommends contracts. Consumes
typed models from `models/` and indicator output. No direct API calls.

## Files


## Architecture Rules
- **No API calls** — data comes from `services/` via the caller, never fetched here
- **Typed models everywhere** — consume and return Pydantic models from `models/`
- **No raw dicts** from public functions (normalization internals use `dict[str, dict[str, float]]`
  for indicator data interchange, but final output is always `TickerScore` or other typed models)
- **Constants, not magic numbers** — all thresholds, weights, and bounds are module-level uppercase

## Key Constants

## Data Flow

## What Claude Gets Wrong Here (Fix These)
- Don't call APIs from analysis code — data comes from the caller
- Don't return raw dicts from public functions — use typed models
- Don't use magic numbers — reference the named constants
- Don't confuse weighted arithmetic mean with weighted geometric mean
- Don't forget to clamp composite scores to [0, 100]
- Don't use `ddof=1` anywhere — this module doesn't compute standard deviations
- Don't forget that theta is per-day (divided by 365), not annual
- Don't mix up IV Rank and IV Percentile weights

