# CLAUDE.md -- Options Pricing (`pricing/`)

## Purpose

All options pricing math: Black-Scholes-Merton (European), Barone-Adesi-Whaley (American),
implied volatility solvers, Greeks computation, and a unified dispatch layer. This module
is the **sole source of Greeks** for the entire pipeline -- yfinance provides none.

Pure math at the boundary: functions accept primitives (`float`, `OptionType`, `ExerciseStyle`),
return `float` for prices/IV or `OptionGreeks` for Greeks. No API calls. No data fetching.
No pandas. `PricingConfig` supplies solver tolerances and iteration limits.

Use Glob to discover files.

---

## Architecture Boundary

| Rule | Detail |
|------|--------|
| No API calls | Never import from `services/`. Receives pre-fetched data as function args. |
| No pandas | Unlike `indicators/`, pricing works with scalar `float` values, not Series/DataFrames. |
| No raw dicts | `bsm_greeks` and `american_greeks` return `OptionGreeks` model, never `dict[str, float]`. |
| Config via injection | Functions that need solver params accept `PricingConfig`. Never import `AppSettings`. |
| Logging only | Use `logging` for convergence warnings. Never `print()`. |
| Scalar math | Use `math.log`, `math.sqrt`, `math.exp` -- not numpy. |

---

## Common Parameter Convention

All functions share: `S` (spot, float), `K` (strike, float -- converted from Decimal at call site),
`T` (years = DTE/365, must be > 0), `r` (risk-free rate, decimal), `q` (continuous dividend yield,
decimal), `sigma` (annualized IV, decimal, solver bounds [1e-6, 5.0]), `option_type` (CALL/PUT).

---

## BSM -- Black-Scholes-Merton (`bsm.py`)

### Merton 1973 Extension

Standard BSM extended with continuous dividend yield `q`:

```
d1 = (ln(S/K) + (r - q + sigma^2/2) * T) / (sigma * sqrt(T))
d2 = d1 - sigma * sqrt(T)

Call = S * e^(-qT) * N(d1) - K * e^(-rT) * N(d2)
Put  = K * e^(-rT) * N(-d2) - S * e^(-qT) * N(-d1)
```

Uses `scipy.stats.norm.cdf` for N(x) and `scipy.stats.norm.pdf` for n(x).

### Functions

| Function | Returns | Purpose |
|----------|---------|---------|
| `bsm_price(S, K, T, r, q, sigma, option_type)` | `float` | European option price |
| `bsm_greeks(S, K, T, r, q, sigma, option_type)` | `OptionGreeks` | All 5 Greeks, `pricing_model=PricingModel.BSM` |
| `bsm_vega(S, K, T, r, q, sigma)` | `float` | Standalone vega for Newton-Raphson `fprime` |
| `bsm_iv(market_price, S, K, T, r, q, option_type, initial_guess)` | `float` | Newton-Raphson IV solver |

### BSM IV Solver -- Newton-Raphson

- Analytical vega as `fprime` -- quadratic convergence, ~5-8 iterations typical.
- `initial_guess`: use `market_iv` from yfinance when available, else `0.30`.
- Bounded search: clamp each iteration to `[1e-6, 5.0]`.
- Convergence: `abs(price_diff) < PricingConfig.iv_solver_tol`.
- Max iterations: `PricingConfig.iv_solver_max_iter` (default 50).
- Non-convergence: raise `ValueError` with diagnostic info -- never return garbage.

---

## BAW -- Barone-Adesi-Whaley (`american.py`)

Adds early exercise premium to European BSM price. Critical prices found via
Newton-Raphson on boundary condition.

### Key Identities (Tests MUST Verify)

- **FR-P4**: When `q = 0`, `american_call == bsm_call` -- no early exercise premium for
  calls on non-dividend stocks. Mathematical identity.
- **FR-P5**: `american_put >= bsm_put` always -- early exercise premium is non-negative.

### Functions

| Function | Returns | Purpose |
|----------|---------|---------|
| `american_price(S, K, T, r, q, sigma, option_type)` | `float` | American option price via BAW |
| `american_greeks(S, K, T, r, q, sigma, option_type)` | `OptionGreeks` | Finite-difference, `pricing_model=PricingModel.BAW` |
| `american_iv(market_price, S, K, T, r, q, option_type, config)` | `float` | `brentq` IV solver |

### BAW Greeks -- Finite Difference (Bump-and-Reprice)

BAW has **no analytical Greeks**. Centered finite differences (11 BAW evaluations per call).
Bump sizes: `dS=1%*S`, `dT=1/365`, `dSigma=0.001`, `dR=0.001`.
Guard: `T - dT <= 0` -> forward difference. Sigma clamp prevents negative in vega bump.

### BAW IV Solver -- `scipy.optimize.brentq`

- **NOT Newton-Raphson** -- BAW has no analytical vega w.r.t. IV, making Newton require
  expensive numerical differentiation.
- `brentq` is bracket-based, guaranteed convergent, no derivative needed.
- Bracket: `[1e-6, 5.0]` (option price is monotonically increasing in sigma).
- Objective: `f(sigma) = american_price(..., sigma, ...) - market_price`
- Tolerances: `xtol=PricingConfig.iv_solver_tol`, `maxiter=PricingConfig.iv_solver_max_iter`
- Typical convergence: ~15-40 function evaluations.
- `ValueError` from `brentq`: market price outside theoretical range.

---

## Dispatch Layer (`dispatch.py`)

Routes by `ExerciseStyle` using Python 3.13 `match`:

| Function | Returns | Routes to |
|----------|---------|-----------|
| `option_price(exercise_style, S, K, T, r, q, sigma, option_type)` | `float` | `bsm_price` or `american_price` |
| `option_greeks(exercise_style, S, K, T, r, q, sigma, option_type)` | `OptionGreeks` | `bsm_greeks` or `american_greeks` |
| `option_iv(exercise_style, market_price, S, K, T, r, q, option_type, config)` | `float` | `bsm_iv` or `american_iv` |
| `option_second_order_greeks(...)` | `SecondOrderGreeks` | Vanna, charm, vomma |

Dispatch functions re-exported from `__init__.py`. Direct `bsm_*`/`american_*` are internal.
Tests may import internals directly.

---

## Edge Cases

- `T = 0`: return intrinsic value. `T` very small: BAW theta uses forward difference.
- `sigma = 0`: discounted intrinsic. `sigma > 3.0`: allow (meme stocks), clamp at 5.0.
- `q > r`: valid (high-dividend). `q = 0`: BAW call == BSM call (FR-P4 identity).
- Market price < intrinsic: IV solver may fail, raise `ValueError`. Price = 0: skip IV.

---

## What Claude Gets Wrong Here (Fix These)

1. **Forgetting dividend yield `q`** -- Every BSM formula must include `e^(-qT)` terms.
   Omitting `q` is the #1 bug. We use Merton (1973), not original BSM.

2. **BSM vega: `norm.cdf` instead of `norm.pdf`** -- Vega uses density `n(d1)`, not CDF `N(d1)`.

3. **Wrong sign on theta** -- Conventionally reported as negative (daily decay). Be consistent.

4. **Newton-Raphson for BAW IV** -- Use `brentq`. BAW has no analytical vega w.r.t. IV.

5. **`dict[str, float]` for Greeks** -- Return `OptionGreeks` with `pricing_model` set.

6. **Forgetting `pricing_model`** -- Every `OptionGreeks` MUST set BSM or BAW.

7. **numpy for scalar math** -- Use `math.log/sqrt/exp`. No numpy needed in pricing.

8. **T=0 division by zero** -- `sigma * sqrt(T)` in denominators. Guard `T <= 0`.

9. **Unclamped IV iterations** -- Must clamp sigma to `[1e-6, 5.0]` each step.

10. **BAW theta forward difference** -- `T - dT` can go negative. Use forward difference fallback.

11. **Mixing up N(d1) vs N(-d1)** -- Put formulas use `N(-d1)`, `N(-d2)`. Use canonical form.

12. **Importing from services/indicators** -- Pricing is pure math. No data fetching. If you
    find yourself importing `httpx`, `yfinance`, `pandas`, stop.
