---
name: phase-2-pricing
status: backlog
created: 2026-02-22T08:50:13Z
progress: 0%
prd: .claude/prds/options-arena.md
parent: .claude/epics/options-arena/epic.md
github: [Will be updated when synced to GitHub]
---

# Epic 2: Pricing Module

## Overview

Build the `pricing/` package: cherry-pick BSM from v3 (extend with Merton 1973 dividend yield), write the new BAW American pricing approximation, and create a unified dispatch layer. This is the core differentiator — correct American options pricing.

## Scope

### PRD Requirements Covered
FR-P1, FR-P2, FR-P3, FR-P4, FR-P5

### Deliverables

**`src/options_arena/pricing/`:**

- `bsm.py` — Cherry-pick from v3, extend with continuous dividend yield `q`:
  - `bsm_price(S, K, T, r, q, sigma, option_type)` — Merton 1973 (d1/d2 adjusted for `q`)
  - `bsm_greeks(S, K, T, r, q, sigma, option_type) -> OptionGreeks` — all 5 Greeks
  - `bsm_vega(S, K, T, r, q, sigma)` — standalone for Newton-Raphson fprime
  - `bsm_iv(market_price, S, K, T, r, q, option_type, initial_guess) -> float` — Newton-Raphson with analytical vega, bounded [1e-6, 5.0], tolerance from `PricingConfig`
  - Uses `scipy.stats.norm.cdf` and `norm.pdf`

- `american.py` — New code, BAW analytical approximation:
  - `american_price(S, K, T, r, q, sigma, option_type)` — BAW call and put pricing
  - `american_greeks(S, K, T, r, q, sigma, option_type) -> OptionGreeks` — finite-difference bump-and-reprice (bump S for delta/gamma, bump T for theta, bump sigma for vega, bump r for rho)
  - `american_iv(market_price, S, K, T, r, q, option_type) -> float` — `scipy.optimize.brentq` with bracket [1e-6, 5.0], `xtol` and `maxiter` from `PricingConfig`
  - Objective function: `f(sigma) = american_price(sigma, ...) - market_price`

- `dispatch.py` — Unified routing:
  - `option_price(exercise_style, ...)` — dispatches to BSM or BAW
  - `option_greeks(exercise_style, ...)` — dispatches to BSM or BAW
  - `option_iv(exercise_style, ...)` — BSM uses Newton-Raphson, BAW uses brentq
  - Uses `match exercise_style:` (Python 3.13 pattern matching)

- `__init__.py` — Re-export `option_price`, `option_greeks`, `option_iv`

**Tests (`tests/unit/pricing/`):**
- BSM: put-call parity, at-the-money approximation, boundary conditions (T→0, sigma→0)
- BAW: Hull textbook reference values (parametrized)
- BAW identity: `american_call == bsm_call` when `q=0` (FR-P4)
- BAW dominance: `american_put >= bsm_put` always (FR-P5)
- Greeks: sign correctness (delta ∈ [0,1] for calls, [-1,0] for puts), gamma > 0, theta < 0
- IV round-trip: `compute_price(compute_iv(price)) ≈ price`
- Dispatch: correct routing by ExerciseStyle
- ~100 tests total

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (models — `OptionGreeks`, `PricingModel`, `ExerciseStyle`, `PricingConfig`)
- **Blocks**: Epic 4 (scoring — `contracts.py` uses `pricing/dispatch.py`)

## Key Decisions
- BSM IV: manual Newton-Raphson (analytical vega, quadratic convergence)
- BAW IV: `scipy.optimize.brentq` (no analytical vega, bracket-based, guaranteed convergence)
- BAW Greeks: finite-difference (bump-and-reprice) — bump sizes ~0.01 for price, ~0.001 for IV
- All pricing functions accept `PricingConfig` for tolerance/iteration limits

## Estimated Tests: ~100
