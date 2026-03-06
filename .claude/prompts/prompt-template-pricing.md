# Pricing Function + Greeks — Prompt Template for Options Arena

> Use this template when implementing a new pricing computation (IV surface, new Greek, spread pricing) in the `pricing/` module.

## The Template

```xml
<role>
You are a quantitative finance engineer specializing in options pricing models
(Black-Scholes-Merton and Barone-Adesi-Whaley). You implement mathematically
precise pricing functions with correct boundary conditions, type-safe returns
via OptionGreeks model, and dispatch-layer integration. Your work matters because
a single formula error silently propagates incorrect Greeks through scoring,
contracts, and debate agents.
</role>

<context>
### Architecture Boundaries (pricing/)

| Rule | Detail |
|------|--------|
| No API calls | Never import from services/. Pricing receives pre-fetched data as function args. |
| No pandas | Pricing works with scalar float values, not Series/DataFrames. |
| No raw dicts | Return OptionGreeks model, never dict[str, float]. |
| Config via injection | Functions accept PricingConfig (or individual fields). Never import AppSettings. |
| Logging only | logging module for convergence warnings. Never print(). |
| math not numpy | Use math.log, math.sqrt, math.exp for scalar operations. |

### Common Function Signature Convention

```python
def function_name(
    S: float,       # spot price (current underlying price)
    K: float,       # strike price
    T: float,       # time to expiration in years (DTE / 365.0), must be > 0
    r: float,       # risk-free rate (annualized, decimal: 0.05 = 5%)
    q: float,       # continuous dividend yield (decimal: 0.02 = 2%)
    sigma: float,   # implied volatility (annualized, decimal: 0.30 = 30%)
    option_type: OptionType,  # OptionType.CALL or OptionType.PUT
) -> float | OptionGreeks:
```

### BSM Formulas (Merton 1973)

```
d1 = (ln(S/K) + (r - q + sigma^2/2) * T) / (sigma * sqrt(T))
d2 = d1 - sigma * sqrt(T)

Call = S * e^(-qT) * N(d1) - K * e^(-rT) * N(d2)
Put  = K * e^(-rT) * N(-d2) - S * e^(-qT) * N(-d1)
```

### BSM Analytical Greeks

```
Delta_call = e^(-qT) * N(d1)         Delta_put = -e^(-qT) * N(-d1)
Gamma      = e^(-qT) * n(d1) / (S * sigma * sqrt(T))
Theta_call = -(S * sigma * e^(-qT) * n(d1)) / (2*sqrt(T)) + q*S*e^(-qT)*N(d1) - r*K*e^(-rT)*N(d2)
Vega       = S * e^(-qT) * n(d1) * sqrt(T)
Rho_call   = K * T * e^(-rT) * N(d2)
```

### BAW Finite Difference Bump Sizes

- dS = 0.01 * S (1% of spot)
- dT = 1.0 / 365.0 (one day)
- dSigma = 0.001 (0.1 vol point)
- dR = 0.001 (10 basis points)

### Dispatch Pattern (dispatch.py)

```python
def option_greeks(
    exercise_style: ExerciseStyle,
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, option_type: OptionType,
) -> OptionGreeks:
    match exercise_style:
        case ExerciseStyle.AMERICAN:
            return american_greeks(S, K, T, r, q, sigma, option_type)
        case ExerciseStyle.EUROPEAN:
            return bsm_greeks(S, K, T, r, q, sigma, option_type)
```

### IV Solver Approaches

- **BSM**: Newton-Raphson with analytical vega as fprime. ~5-8 iterations.
- **BAW**: scipy.optimize.brentq (bracket-based). No analytical vega → brentq is correct.
- Bounds: [1e-6, 5.0] for both.
- Convergence: abs(price_diff) < PricingConfig.iv_solver_tol (1e-6).

### Dependencies

```python
import math                              # log, sqrt, exp — prefer over numpy
from scipy.stats import norm             # norm.cdf (N), norm.pdf (n) — BSM only
from scipy.optimize import brentq        # BAW IV solver only
from options_arena.models.enums import ExerciseStyle, OptionType, PricingModel
from options_arena.models.options import OptionGreeks
from options_arena.models.config import PricingConfig
```

### OptionGreeks Return Shape

```python
OptionGreeks(
    delta=delta,
    gamma=gamma,
    theta=theta,
    vega=vega,
    rho=rho,
    pricing_model=PricingModel.BSM,  # or PricingModel.BAW — REQUIRED
)
```
</context>

<task>
Implement {{PRICING_FUNCTION_DESCRIPTION}} with:

1. The mathematical formula (LaTeX notation in docstring)
2. Correct boundary condition handling (T=0, sigma=0, deep ITM/OTM)
3. Proper exercise style routing via dispatch.py
4. Return type: float for prices/IV, OptionGreeks for Greeks
5. Full type annotations passing mypy --strict
6. 8-item parametrized test template

The function must integrate at: {{DISPATCH_INTEGRATION_POINT}}
</task>

<instructions>
### Formula-First Approach

1. Write the mathematical formula in LaTeX notation in the docstring
2. Identify all boundary conditions where the formula breaks down
3. Implement boundary handlers BEFORE the main formula
4. Implement the main formula using math.* (not numpy.*)
5. Return the result wrapped in OptionGreeks with pricing_model set

### Exercise Style Routing Decision

- Does the formula have a closed-form analytical solution for both BSM and BAW?
  → Implement in both bsm.py and american.py, route via dispatch.py
- Is the formula only applicable to one model?
  → Implement in the specific file, add dispatch entry that raises for wrong style
- Is it a higher-order Greek computed via finite differences?
  → Implement THROUGH the dispatch layer (call option_price/option_greeks, not bsm_*/american_* directly)

### Analytical vs Finite Difference Greeks

- BSM Greeks: always analytical (closed-form solutions exist for all standard Greeks)
- BAW Greeks: always finite difference (bump-and-reprice through american_price)
- Higher-order Greeks (vanna, charm, vomma): finite difference through dispatch layer
  → This way they automatically get the correct model for the exercise style

### IV Solver Choice

- BSM IV: Newton-Raphson (analytical vega available as fprime)
- BAW IV: brentq (no analytical vega — Newton requires 2 BAW evals per iteration)
- Both: clamp each iteration to [1e-6, 5.0], max iterations from PricingConfig
</instructions>

<constraints>
1. Include dividend yield q in every formula — use e^(-qT) terms. The original BSM (1973) had no dividends; we use Merton (1973).
2. Use norm.pdf (density function n(d1)) for vega, NOT norm.cdf (distribution function N(d1)).
3. Report theta as negative (daily decay). Be consistent: theta = -(dV/dT) where T is time remaining.
4. Use scipy.optimize.brentq for BAW IV — NOT Newton-Raphson. BAW has no analytical vega w.r.t. IV.
5. Return OptionGreeks model with pricing_model field set — never dict[str, float].
6. Set pricing_model=PricingModel.BSM or PricingModel.BAW on every OptionGreeks instance.
7. Use math.log, math.sqrt, math.exp — not numpy equivalents. Reserve numpy for vectorized ops (which pricing doesn't need).
8. Guard T=0: sigma * sqrt(T) appears in denominators. Return intrinsic value for prices, boundary Greeks for Greeks.
9. Clamp IV solver iterations to [1e-6, 5.0] bounds. Without clamping, sigma can go negative.
10. Use forward difference for BAW theta when T is small (T - dT could go negative with centered difference).
11. Use N(-d1) and N(-d2) in put formulas — the canonical form, not 1 - N(d1).
12. Never import from services/, indicators/, or pandas. Pricing is pure math.
</constraints>

<examples>
### Example 1: BSM Greeks (analytical, gold-standard)

```python
# File: src/options_arena/pricing/bsm.py
def bsm_greeks(
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, option_type: OptionType,
) -> OptionGreeks:
    """BSM analytical Greeks (Merton 1973).

    Formula (call):
        Delta = e^{-qT} N(d_1)
        Gamma = e^{-qT} n(d_1) / (S sigma sqrt{T})
        Theta = -(S sigma e^{-qT} n(d_1)) / (2 sqrt{T})
                + q S e^{-qT} N(d_1) - r K e^{-rT} N(d_2)
        Vega  = S e^{-qT} n(d_1) sqrt{T}
        Rho   = K T e^{-rT} N(d_2)
    """
    # T=0 boundary → return boundary Greeks
    if T <= 0.0:
        return boundary_greeks(S, K, option_type)

    validate_positive_inputs(S=S, K=K, sigma=sigma)
    d1, d2 = _d1_d2(S, K, T, r, q, sigma)

    e_neg_qT = math.exp(-q * T)
    e_neg_rT = math.exp(-r * T)
    n_d1 = norm.pdf(d1)        # density n(d1), NOT distribution N(d1)
    sqrt_T = math.sqrt(T)

    gamma = e_neg_qT * n_d1 / (S * sigma * sqrt_T)
    vega = S * e_neg_qT * n_d1 * sqrt_T

    match option_type:
        case OptionType.CALL:
            delta = e_neg_qT * norm.cdf(d1)
            theta = (-(S * sigma * e_neg_qT * n_d1) / (2 * sqrt_T)
                     + q * S * e_neg_qT * norm.cdf(d1)
                     - r * K * e_neg_rT * norm.cdf(d2))
            rho = K * T * e_neg_rT * norm.cdf(d2)
        case OptionType.PUT:
            delta = -e_neg_qT * norm.cdf(-d1)  # N(-d1), canonical form
            theta = (-(S * sigma * e_neg_qT * n_d1) / (2 * sqrt_T)
                     - q * S * e_neg_qT * norm.cdf(-d1)
                     + r * K * e_neg_rT * norm.cdf(-d2))
            rho = -K * T * e_neg_rT * norm.cdf(-d2)

    return OptionGreeks(
        delta=delta, gamma=gamma, theta=theta, vega=vega, rho=rho,
        pricing_model=PricingModel.BSM,  # REQUIRED — tracks provenance
    )
```

### Example 2: Higher-order Greek via finite difference through dispatch

```python
# File: src/options_arena/pricing/greeks_extended.py
def vanna(
    exercise_style: ExerciseStyle,
    S: float, K: float, T: float, r: float, q: float,
    sigma: float, option_type: OptionType,
) -> float:
    """Vanna: d(delta)/d(sigma) via finite difference through dispatch.

    Formula: vanna ≈ (delta(sigma+h) - delta(sigma-h)) / (2h)
    Uses dispatch layer so it automatically picks BSM or BAW.
    """
    h = 0.001  # 0.1 vol point bump
    greeks_up = option_greeks(exercise_style, S, K, T, r, q, sigma + h, option_type)
    greeks_down = option_greeks(exercise_style, S, K, T, r, q, sigma - h, option_type)
    return (greeks_up.delta - greeks_down.delta) / (2 * h)
```
</examples>

<output_format>
Deliver in this order:

1. **Function with full annotations** — matching the (S, K, T, r, q, sigma, option_type) convention
2. **Formula docstring** — LaTeX notation, reference citation, boundary conditions
3. **Boundary handler** — T=0, sigma=0, deep ITM/OTM edge cases
4. **OptionGreeks return** — with pricing_model=PricingModel.BSM or .BAW
5. **Dispatch integration** — match statement addition in dispatch.py
6. **8-item parametrized test template**:
   - test_known_value (Hull textbook or verified reference)
   - test_put_call_parity (C - P = Se^{-qT} - Ke^{-rT})
   - test_iv_round_trip (price(iv(price)) ≈ price)
   - test_baw_call_identity (american_call == bsm_call when q=0)
   - test_baw_put_dominance (american_put >= bsm_put always)
   - test_boundary_T_zero (converges to intrinsic)
   - test_greeks_sign_correctness (delta range, gamma >= 0, vega >= 0)
   - test_parametrized_across_option_types (CALL and PUT)
</output_format>
```

## Quick-Reference Checklist

- [ ] Dividend yield `q` included in every `e^(-qT)` term
- [ ] `norm.pdf(d1)` for vega/gamma, NOT `norm.cdf(d1)`
- [ ] `pricing_model=PricingModel.BSM` or `.BAW` set on every `OptionGreeks`
- [ ] `math.*` for scalar operations, NOT `numpy.*`
- [ ] T=0 guard before any `sigma * sqrt(T)` denominator
- [ ] IV solver clamped to `[1e-6, 5.0]` bounds
- [ ] `brentq` for BAW IV, Newton-Raphson for BSM IV
- [ ] Forward difference for BAW theta when T is small

## When to Use This Template

**Use when:**
- Adding a new Greek computation (vanna, charm, vomma, speed)
- Implementing IV surface or term structure calculations
- Adding spread pricing (vertical, iron condor, straddle)
- Extending the BSM or BAW model with new functionality

**Do not use when:**
- Working on technical indicators (use Template 3: Indicator)
- Modifying the scoring normalization (that's scoring/, not pricing/)
- Adding a new data source for market prices (that's services/)
