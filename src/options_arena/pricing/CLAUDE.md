# CLAUDE.md — Options Pricing (`pricing/`)

## Purpose
All options pricing math: Black-Scholes-Merton (European), Barone-Adesi-Whaley (American),
implied volatility solvers, Greeks computation, and a unified dispatch layer. This module
is the **sole source of Greeks** for the entire pipeline — yfinance provides none.

Pure math at the boundary: functions accept primitives (`float`, `OptionType`, `ExerciseStyle`),
return `float` for prices/IV or `OptionGreeks` for Greeks. No API calls. No data fetching.
No pandas. `PricingConfig` supplies solver tolerances and iteration limits.

## Files

| File | Contents |
|------|----------|
| `bsm.py` | `bsm_price`, `bsm_greeks`, `bsm_vega`, `bsm_iv` — Merton 1973 European BSM with continuous dividend yield |
| `american.py` | `american_price`, `american_greeks`, `american_iv` — BAW analytical approximation for American options |
| `dispatch.py` | `option_price`, `option_greeks`, `option_iv` — unified routing by `ExerciseStyle` |
| `__init__.py` | Re-exports `option_price`, `option_greeks`, `option_iv` (dispatch-level only) |

---

## Architecture Boundary

| Rule | Detail |
|------|--------|
| No API calls | Never import from `services/`. Pricing receives pre-fetched data as function args. |
| No pandas | Unlike `indicators/`, pricing works with scalar `float` values, not Series/DataFrames. |
| No raw dicts | `bsm_greeks` and `american_greeks` return `OptionGreeks` model, never `dict[str, float]`. |
| Config via injection | Functions that need solver params accept `PricingConfig` (or its individual fields). Never import `AppSettings` directly. |
| Logging only | Use `logging` module for convergence warnings. Never `print()`. |
| Type-annotate everything | `mypy --strict` — full annotations on every function, no exceptions. |

---

## Common Function Signature

All pricing functions share a standard parameter convention:

```python
def bsm_price(
    S: float,       # spot price (current underlying price)
    K: float,       # strike price
    T: float,       # time to expiration in years (DTE / 365.0)
    r: float,       # risk-free rate (annualized, decimal: 0.05 = 5%)
    q: float,       # continuous dividend yield (decimal: 0.02 = 2%)
    sigma: float,   # implied volatility (annualized, decimal: 0.30 = 30%)
    option_type: OptionType,  # OptionType.CALL or OptionType.PUT
) -> float:
```

- **S, K**: always `float` in pricing functions (not `Decimal` — converted at call site).
- **T**: `DTE / 365.0` — caller computes this. Must be > 0 (T=0 is expiration boundary).
- **r**: annualized risk-free rate as decimal fraction. Fallback `0.05` from `PricingConfig`.
- **q**: continuous dividend yield as decimal fraction. From `TickerInfo.dividend_yield`.
- **sigma**: annualized IV as decimal. Range `[1e-6, 5.0]` for solver bounds.
- **option_type**: `OptionType.CALL` or `OptionType.PUT` — use `match` for dispatch.

---

## BSM — Black-Scholes-Merton (`bsm.py`)

### FR-P1: Merton 1973 Extension

Standard BSM extended with continuous dividend yield `q` (Merton 1973):

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

### BSM Greeks (Analytical)

All have closed-form solutions — compute directly, no finite differences:

```
Delta_call = e^(-qT) * N(d1)         Delta_put = -e^(-qT) * N(-d1)
Gamma      = e^(-qT) * n(d1) / (S * sigma * sqrt(T))
Theta_call = -(S * sigma * e^(-qT) * n(d1)) / (2*sqrt(T)) + q*S*e^(-qT)*N(d1) - r*K*e^(-rT)*N(d2)
Theta_put  = -(S * sigma * e^(-qT) * n(d1)) / (2*sqrt(T)) - q*S*e^(-qT)*N(-d1) + r*K*e^(-rT)*N(-d2)
Vega       = S * e^(-qT) * n(d1) * sqrt(T)
Rho_call   = K * T * e^(-rT) * N(d2)      Rho_put = -K * T * e^(-rT) * N(-d2)
```

### BSM IV Solver — Newton-Raphson

- Analytical vega as `fprime` — quadratic convergence, ~5-8 iterations typical.
- `initial_guess`: use `market_iv` from yfinance when available, else `0.30`.
- Bounded search: clamp each iteration to `[1e-6, 5.0]`.
- Convergence: `abs(price_diff) < PricingConfig.iv_solver_tol`.
- Max iterations: `PricingConfig.iv_solver_max_iter` (default 50).
- If non-convergence, raise `ValueError` with diagnostic info — never return garbage.

---

## BAW — Barone-Adesi-Whaley (`american.py`)

### FR-P2: BAW Analytical Approximation

The BAW approximation adds an early exercise premium to the European BSM price:

```
American_Call = BSM_Call + A2 * (S/S*)^q2     when S < S*
American_Call = S - K                          when S >= S* (immediate exercise)

American_Put  = BSM_Put  + A1 * (S/S**)^q1    when S > S**
American_Put  = K - S                          when S <= S** (immediate exercise)
```

Where `S*` and `S**` are the critical stock prices (exercise boundaries) found by
iterative root-finding. `q1`, `q2`, `A1`, `A2` are auxiliary parameters derived from
`r`, `q`, `sigma`, `T`.

**Key implementation details:**
- Critical price solver: Newton-Raphson iteration on the early exercise boundary condition.
- Seed critical price with BSM-derived estimate.
- Handle edge cases: `T → 0` (converge to intrinsic value), `sigma → 0`, `q = 0`.

### FR-P4: BAW Call Identity
When `q = 0` (no dividends), `american_call == bsm_call` — there is never an early exercise
premium for calls on non-dividend-paying stocks. This is a mathematical identity that tests MUST verify.

### FR-P5: BAW Put Inequality
`american_put >= bsm_put` **always** — the early exercise premium is non-negative.
Tests MUST verify this for all parameter combinations.

### Functions

| Function | Returns | Purpose |
|----------|---------|---------|
| `american_price(S, K, T, r, q, sigma, option_type)` | `float` | American option price via BAW |
| `american_greeks(S, K, T, r, q, sigma, option_type)` | `OptionGreeks` | Finite-difference bump-and-reprice, `pricing_model=PricingModel.BAW` |
| `american_iv(market_price, S, K, T, r, q, option_type, config)` | `float` | `scipy.optimize.brentq` IV solver |

### BAW Greeks — Finite Difference (Bump-and-Reprice)

BAW has **no analytical Greeks**. Use centered finite differences:

```python
# Delta: bump S
delta = (american_price(S + dS, ...) - american_price(S - dS, ...)) / (2 * dS)

# Gamma: second derivative of price w.r.t. S
gamma = (american_price(S + dS, ...) - 2 * american_price(S, ...) + american_price(S - dS, ...)) / (dS ** 2)

# Theta: bump T (note: theta is negative of time derivative)
theta = (american_price(..., T - dT, ...) - american_price(..., T, ...)) / dT

# Vega: bump sigma
vega = (american_price(..., sigma + dSigma, ...) - american_price(..., sigma - dSigma, ...)) / (2 * dSigma)

# Rho: bump r
rho = (american_price(..., r + dR, ...) - american_price(..., r - dR, ...)) / (2 * dR)
```

**Bump sizes:**
- `dS = 0.01 * S` (1% of spot for price-based Greeks)
- `dT = 1.0 / 365.0` (one day)
- `dSigma = 0.001` (0.1 vol point)
- `dR = 0.001` (10 basis points)

Guard against `T - dT <= 0` — use forward difference for theta when `T` is very small.

### BAW IV Solver — `scipy.optimize.brentq`

- **NOT Newton-Raphson** — BAW has no analytical vega w.r.t. IV, making Newton require
  expensive numerical differentiation (2 BAW evaluations per iteration).
- `brentq` is bracket-based, guaranteed convergent on monotonic functions, no derivative needed.
- Option price is monotonically increasing in sigma — the bracket `[1e-6, 5.0]` is always valid.
- Objective: `f(sigma) = american_price(S, K, T, r, q, sigma, option_type) - market_price`.
- `xtol=PricingConfig.iv_solver_tol`, `maxiter=PricingConfig.iv_solver_max_iter`.
- Typical convergence: ~15-40 function evaluations.
- If `brentq` raises `ValueError` (bracket doesn't contain root), the market price is
  outside the theoretical range — log a warning and raise.

---

## Dispatch Layer (`dispatch.py`)

### FR-P3: Unified Routing

Routes by `ExerciseStyle` using Python 3.13 `match`:

```python
def option_price(
    exercise_style: ExerciseStyle,
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, option_type: OptionType,
) -> float:
    match exercise_style:
        case ExerciseStyle.AMERICAN:
            return american_price(S, K, T, r, q, sigma, option_type)
        case ExerciseStyle.EUROPEAN:
            return bsm_price(S, K, T, r, q, sigma, option_type)
```

Same pattern for `option_greeks` and `option_iv`.

### Dispatch Functions

| Function | Returns | Routes to |
|----------|---------|-----------|
| `option_price(exercise_style, S, K, T, r, q, sigma, option_type)` | `float` | `bsm_price` or `american_price` |
| `option_greeks(exercise_style, S, K, T, r, q, sigma, option_type)` | `OptionGreeks` | `bsm_greeks` or `american_greeks` |
| `option_iv(exercise_style, market_price, S, K, T, r, q, option_type, config)` | `float` | `bsm_iv` or `american_iv` |

---

## Re-Export Pattern (`__init__.py`)

```python
"""Options Arena — Options pricing (BSM, BAW) and Greeks computation."""

from options_arena.pricing.dispatch import option_greeks, option_iv, option_price

__all__ = ["option_greeks", "option_iv", "option_price"]
```

Only the dispatch-level functions are public. Direct `bsm_*` and `american_*` functions
are internal — consumers always go through dispatch. Tests may import them directly for
unit-level verification.

---

## Edge Cases & Boundary Conditions

| Condition | Expected Behavior |
|-----------|-------------------|
| `T = 0` (at expiration) | Return intrinsic value: `max(S - K, 0)` for call, `max(K - S, 0)` for put |
| `T` very small (< 1 day) | BAW theta: use forward difference, not centered (avoid `T - dT <= 0`) |
| `sigma = 0` | Price = discounted intrinsic value. Greeks: delta = 0 or 1 (deep ITM/OTM), others = 0 |
| `sigma` very large (> 3.0) | Allow — some meme stocks have extreme IV. Clamp at solver bounds `5.0` |
| `S = K` (ATM) | Normal case. No special handling needed |
| `S >> K` (deep ITM call) | Delta → 1.0, gamma → 0, theta → small negative |
| `S << K` (deep OTM call) | Delta → 0, gamma → 0, price → 0 |
| `q > r` | Valid — high-dividend stocks. BSM formula handles naturally |
| `q = 0` | BAW call == BSM call (FR-P4 identity). No early exercise premium for calls |
| Market price < intrinsic | IV solver may fail (no valid IV). Raise `ValueError` |
| Market price = 0 | Skip IV computation. Log warning |

---

## Dependencies

### Internal Imports
```python
from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel
from options_arena.models.options import OptionGreeks
from options_arena.models.config import PricingConfig
```

### External Libraries
```python
import math                              # log, sqrt, exp
from scipy.stats import norm             # norm.cdf, norm.pdf (BSM only)
from scipy.optimize import brentq        # BAW IV solver only
```

- `scipy.stats.norm.cdf` — cumulative normal distribution N(x)
- `scipy.stats.norm.pdf` — standard normal density n(x)
- `scipy.optimize.brentq` — bracket-based root finder (BAW IV solver)
- `math.log`, `math.sqrt`, `math.exp` — prefer `math` over `numpy` for scalar operations

---

## Test Requirements (~100 tests in `tests/unit/pricing/`)

### BSM Tests (`test_bsm.py`)
- **Put-call parity**: `C - P = S*e^(-qT) - K*e^(-rT)` within tolerance.
- **ATM approximation**: ATM call price ≈ `0.4 * S * sigma * sqrt(T)` for small T, q=0, r≈0.
- **Boundary T→0**: price converges to intrinsic value.
- **Boundary sigma→0**: price = discounted intrinsic.
- **Greeks sign correctness**: delta ∈ [0,1] for calls, [-1,0] for puts; gamma > 0; theta < 0 (typical); vega > 0.
- **IV round-trip**: `bsm_price(bsm_iv(price)) ≈ price` within tolerance.
- **Known values**: Hull textbook or verified reference values (parametrized).

### BAW Tests (`test_american.py`)
- **Hull textbook reference values**: parametrized test with known inputs/outputs.
- **FR-P4 identity**: `american_call == bsm_call` when `q = 0`, within tight tolerance.
- **FR-P5 dominance**: `american_put >= bsm_put` for all parameter combinations.
- **Early exercise premium**: `american_put - bsm_put > 0` for deep ITM puts with dividends.
- **Greeks via finite difference**: sign correctness, same ranges as BSM Greeks.
- **IV round-trip**: `american_price(american_iv(price)) ≈ price`.
- **Convergence**: `american_iv` converges within `maxiter` for reasonable inputs.
- **Edge cases**: T→0, sigma→0, deep ITM/OTM, q=0, q>r.

### Dispatch Tests (`test_dispatch.py`)
- **Correct routing**: AMERICAN → `american_*`, EUROPEAN → `bsm_*`.
- **Consistent interface**: dispatch functions accept same args, return same types.
- **Exhaustive match**: all `ExerciseStyle` variants covered (no unmatched cases).

### Test Conventions
- Use `pytest.approx(rel=1e-6)` for floating-point comparisons.
- Parametrize across `OptionType.CALL` / `OptionType.PUT`.
- Parametrize across multiple `(S, K, T, r, q, sigma)` tuples.
- No mocking — these are pure math functions with deterministic output.

---

## What Claude Gets Wrong Here (Fix These)

1. **Forgetting dividend yield `q`** — Every BSM formula must include `e^(-qT)` terms. Omitting `q` is the #1 bug. The original BSM (1973) had no dividends; we use Merton (1973).
2. **BSM vega: using `norm.cdf` instead of `norm.pdf`** — Vega uses the density function `n(d1)`, not the distribution function `N(d1)`.
3. **Wrong sign on theta** — Theta is the derivative w.r.t. time *remaining* (positive T direction), but conventionally reported as negative (daily decay). Be consistent with the formula.
4. **Newton-Raphson for BAW IV** — Use `scipy.optimize.brentq`, not Newton-Raphson. BAW has no analytical vega w.r.t. IV. This is the core design decision.
5. **Returning `dict[str, float]` for Greeks** — Return `OptionGreeks` model with `pricing_model` set. Never a raw dict.
6. **Forgetting `pricing_model` on `OptionGreeks`** — Every `OptionGreeks` instance MUST set `pricing_model=PricingModel.BSM` or `PricingModel.BAW`.
7. **Using numpy for scalar math** — Use `math.log`, `math.sqrt`, `math.exp` for single-value operations. Reserve numpy for vectorized array operations (which pricing doesn't need).
8. **T=0 division by zero** — `sigma * sqrt(T)` appears in denominators. Guard against `T <= 0`.
9. **Forgetting to clamp IV iterations** — Each Newton-Raphson step must clamp sigma to `[1e-6, 5.0]`. Without clamping, sigma can go negative and blow up.
10. **BAW theta forward difference** — When `T` is small, `T - dT` can go negative. Use forward difference `(price(T+dT) - price(T)) / dT` as fallback.
11. **Mixing up N(d1) vs N(-d1)** — Put formulas use `N(-d1)` and `N(-d2)`, not `1 - N(d1)`. While mathematically equivalent for exact arithmetic, use the canonical form for clarity.
12. **Importing from services or indicators** — Pricing is pure math. It never fetches data. If you find yourself importing `httpx`, `yfinance`, `pandas`, or anything from `services/`, stop.
