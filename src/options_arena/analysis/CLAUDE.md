# CLAUDE.md — Analysis Module (`analysis/`)

## Purpose

Pure computation modules for competitive analysis: valuation models, correlation analysis,
risk-adjusted performance metrics, and position sizing. No I/O, no API calls, no database
access. Consumes typed models from `models/` and stdlib/numpy/pandas. Returns typed Pydantic
models or dataclasses.

## Files

| File | Purpose |
|------|---------|
| `__init__.py` | Re-exports `compute_composite_valuation` |
| `valuation.py` | Multi-methodology equity valuation: Owner Earnings DCF, Three-Stage DCF, EV/EBITDA Relative, Residual Income Model. Composite combiner renormalizes weights across valid estimates. |
| `correlation.py` | Portfolio correlation matrix via log daily returns (Markowitz 1952). Pairwise Pearson coefficients with minimum overlap threshold. |
| `performance.py` | Risk-adjusted metrics: Sharpe, Sortino, max drawdown. Pure computation from returns and holding days. |
| `position_sizing.py` | Volatility-regime-aware position sizing: IV-to-allocation tier mapping with linear interpolation, optional correlation penalty. |

## Architecture Rules
- **No API calls** — data comes from `services/` via the caller, never fetched here
- **Typed models everywhere** — consume and return Pydantic models from `models/`
- **No raw dicts** from public functions (normalization internals use `dict[str, dict[str, float]]`
  for indicator data interchange, but final output is always `TickerScore` or other typed models)
- **Constants, not magic numbers** — all thresholds, weights, and bounds are module-level uppercase

## Import Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (valuation, correlation, analytics, enums) | APIs, services, I/O |
| stdlib: `math`, `statistics`, `datetime`, `dataclasses` | `pricing/` directly |
| `numpy`, `pandas` | `indicators/`, `scoring/`, `data/` |

## What Claude Gets Wrong Here (Fix These)
- Don't call APIs from analysis code — data comes from the caller
- Don't return raw dicts from public functions — use typed models
- Don't use magic numbers — reference the named constants
- Don't confuse weighted arithmetic mean with weighted geometric mean
- Don't forget to clamp composite scores to [0, 100]
- Don't use `ddof=1` anywhere — this module doesn't compute standard deviations
- Don't forget that theta is per-day (divided by 365), not annual
- Don't mix up IV Rank and IV Percentile weights

