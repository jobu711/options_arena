# Pricing Module — Core Business Logic

## What This Module Does

The pricing module is the **sole source of options prices, Greeks, and implied volatility**
for the entire pipeline. It answers three questions for any option contract:

1. **What is this option worth?** (`option_price`)
2. **How sensitive is its price to market changes?** (`option_greeks`)
3. **What volatility does the market imply?** (`option_iv`)

It handles both **European** options (index options like SPX) and **American** options
(all U.S. equity options), which is the core differentiator of this project — most tools
misapply European BSM to American options.

---

## Architecture: Three Layers

```
Consumers (services, scoring, agents)
        │
        ▼
┌─────────────────────────────────────────┐
│  dispatch.py  — routing by ExerciseStyle │
│  option_price / option_greeks / option_iv│
└────────┬──────────────────┬─────────────┘
         │                  │
    AMERICAN            EUROPEAN
         │                  │
         ▼                  ▼
┌────────────────┐  ┌───────────────┐
│  american.py   │  │   bsm.py      │
│  BAW 1987      │  │   Merton 1973 │
│  approximation │──│   (base)      │
└────────────────┘  └───────────────┘
```

**`dispatch.py`** is the only public interface. Consumers import from `options_arena.pricing`
and never call `bsm_*` or `american_*` directly. Dispatch uses Python `match` on
`ExerciseStyle` to route to the correct engine.

**`bsm.py`** is the foundation — BAW builds on top of it by calling `bsm_price` internally.

---

## BSM: Black-Scholes-Merton (European Options)

### The Core Formula — Merton 1973

BSM prices a European option by modeling the stock as a geometric Brownian motion with
continuous dividend yield `q`. The key insight: you can construct a riskless hedge, and
its price must equal the discounted expected payoff under the risk-neutral measure.

```
d1 = (ln(S/K) + (r - q + σ²/2) × T) / (σ × √T)
d2 = d1 - σ × √T

Call = S × e^(-qT) × N(d1) - K × e^(-rT) × N(d2)
Put  = K × e^(-rT) × N(-d2) - S × e^(-qT) × N(-d1)
```

Where:
- `S` = current stock price, `K` = strike price
- `T` = time to expiration in years
- `r` = risk-free rate, `q` = continuous dividend yield
- `σ` = implied volatility
- `N(x)` = cumulative standard normal distribution

The `e^(-qT)` terms (Merton's extension) discount the stock price for dividends paid
during the option's life. Without `q`, this reduces to the original Black-Scholes 1973.

### BSM Greeks — Analytical Closed-Form

Each Greek measures how the option price changes when one input moves:

| Greek | What it measures | Call formula | Put formula |
|-------|-----------------|-------------|------------|
| **Delta** | Price sensitivity to stock move | `e^(-qT) × N(d1)` ∈ [0, 1] | `-e^(-qT) × N(-d1)` ∈ [-1, 0] |
| **Gamma** | Delta acceleration (curvature) | `e^(-qT) × n(d1) / (S × σ × √T)` | Same as call |
| **Theta** | Time decay per day | Complex (see below) | Complex (see below) |
| **Vega** | Sensitivity to volatility | `S × e^(-qT) × n(d1) × √T` | Same as call |
| **Rho** | Sensitivity to interest rates | `K × T × e^(-rT) × N(d2)` | `-K × T × e^(-rT) × N(-d2)` |

Where `n(x)` is the standard normal **density** (PDF), not the distribution (CDF).

Theta formulas:
```
Theta_call = -(S × σ × e^(-qT) × n(d1)) / (2√T)
             + q × S × e^(-qT) × N(d1)
             - r × K × e^(-rT) × N(d2)

Theta_put  = -(S × σ × e^(-qT) × n(d1)) / (2√T)
             - q × S × e^(-qT) × N(-d1)
             + r × K × e^(-rT) × N(-d2)
```

### BSM IV Solver — Newton-Raphson

Given a market price, find the volatility `σ` that makes BSM produce that price.
This is a root-finding problem: `f(σ) = bsm_price(σ) - market_price = 0`.

**Why Newton-Raphson?** BSM has an analytical derivative of price w.r.t. σ — that's vega.
This gives quadratic convergence (doubles correct digits each iteration), typically
converging in 5-8 iterations.

```python
# Each iteration:
σ_new = σ - (bsm_price(σ) - market_price) / bsm_vega(σ)
σ_new = clamp(σ_new, 1e-6, 5.0)  # prevent blow-up
```

Convergence check: `|price_diff| < 1e-6` (configurable via `PricingConfig`).

---

## BAW: Barone-Adesi-Whaley (American Options)

### Why European BSM Is Wrong for American Options

American options can be **exercised early**. This right has value — especially for:
- **Puts**: deep ITM puts are worth exercising early to invest the proceeds at the risk-free rate
- **Calls with dividends**: exercising before ex-dividend captures the dividend

BSM assumes no early exercise. For American puts, BSM **underprices** every time.
The BAW approximation corrects this by adding an **early exercise premium**.

### The BAW Algorithm

BAW decomposes the American price into two parts:

```
American Price = European BSM Price + Early Exercise Premium
```

The premium depends on finding the **critical stock price** — the boundary where
it becomes optimal to exercise immediately rather than hold.

#### For Calls:
```
American_Call = BSM_Call + A2 × (S/S*)^q2    when S < S*
American_Call = S - K                         when S >= S*  (exercise now)
```

#### For Puts:
```
American_Put = BSM_Put + A1 × (S/S**)^q1     when S > S**
American_Put = K - S                          when S <= S** (exercise now)
```

Where `S*` (calls) and `S**` (puts) are the critical stock prices, and `q1`, `q2`, `A1`, `A2`
are auxiliary parameters derived from the inputs.

#### Auxiliary Parameters

```
M       = 2r / σ²
N_param = 2(r - q) / σ²
K_param = 1 - e^(-rT)

q2 = (-(N_param - 1) + √((N_param - 1)² + 4M / K_param)) / 2   [calls, q2 > 0]
q1 = (-(N_param - 1) - √((N_param - 1)² + 4M / K_param)) / 2   [puts, q1 < 0]
```

#### Finding the Critical Price (Newton-Raphson)

The critical price satisfies a boundary condition where exercise value equals continuation value.
For calls at `S*`:

```
S* - K = bsm_call(S*) + (1 - e^(-qT) × N(d1(S*))) × S* / q2
```

This is solved iteratively with Newton-Raphson on the boundary residual, seeded with a
perpetual option approximation. Convergence tolerance: `1e-8`, max 200 iterations.

### Two Key Identities

**FR-P4 (Call Identity):** When `q = 0` (no dividends), there is **never** an early exercise
premium for calls. The implementation returns `bsm_price` directly to guarantee exact equality,
not just numerical approximation.

**FR-P5 (Put Dominance):** `american_put >= bsm_put` **always**. The early exercise premium
is mathematically non-negative. If the implementation ever violated this, it would indicate a bug.

### BAW Greeks — Finite Difference (Bump-and-Reprice)

BAW has **no closed-form Greeks**. Instead, each Greek is computed by bumping one input,
repricing, and computing the numerical derivative:

```
Delta = (price(S+dS) - price(S-dS)) / (2 × dS)           [centered]
Gamma = (price(S+dS) - 2×price(S) + price(S-dS)) / dS²   [second derivative]
Theta = (price(T-dT) - price(T)) / dT                     [backward]
Vega  = (price(σ+dσ) - price(σ-dσ)) / (2 × dσ)           [centered]
Rho   = (price(r+dr) - price(r-dr)) / (2 × dr)            [centered]
```

Bump sizes: `dS = 1% of S`, `dT = 1 day`, `dσ = 0.001`, `dr = 0.001`.

This requires **11 BAW price evaluations per Greeks call** (each involving its own critical
price solve), making it significantly more expensive than analytical BSM Greeks.

**Theta edge case:** When `T` is very small (`T <= dT`), backward difference would make
`T - dT <= 0`. The implementation switches to forward difference as a fallback.

### BAW IV Solver — Brentq (NOT Newton-Raphson)

**Why not Newton-Raphson?** BAW has no analytical vega w.r.t. σ. Computing numerical
vega requires 2 BAW evaluations per iteration (each with its own critical price solve),
making Newton expensive and unreliable.

**Why Brentq?** It's a bracket-based root finder that:
- Needs no derivative
- Is **guaranteed** to converge (given a valid bracket)
- Works because option price is monotonically increasing in σ

The bracket `[1e-6, 5.0]` always contains the root for valid market prices.
Typical convergence: 15-40 function evaluations.

---

## Edge Cases and Boundary Conditions

| Condition | Behavior |
|-----------|----------|
| `T = 0` (at expiration) | Return intrinsic value: `max(S-K, 0)` for calls, `max(K-S, 0)` for puts |
| `σ = 0` (no volatility) | BSM: discounted intrinsic. BAW: intrinsic value |
| `σ × √T ≈ 0` | Same as σ = 0 (prevents division by zero in d1/d2) |
| `r ≈ 0` (K_param < 1e-12) | BAW falls back to BSM (early exercise premium vanishes) |
| `q = 0, call` | BAW returns BSM exactly (FR-P4 identity, no approximation) |
| `S >> K` (deep ITM call) | Delta → 1, gamma → 0, price → intrinsic |
| `S << K` (deep OTM call) | Delta → 0, gamma → 0, price → 0 |
| Market price < intrinsic | IV solver fails (no valid σ exists) — raises `ValueError` |
| Market price = 0 | IV solver refuses (`ValueError`) — can't solve for σ |
| Negative discriminant | BAW falls back to BSM with a warning |

---

## Data Flow: How Pricing Connects to the Pipeline

```
OptionContract (from services/)
    │
    ├── market_iv (yfinance impliedVolatility — used as IV solver seed)
    ├── exercise_style (AMERICAN for equities, EUROPEAN for indices)
    ├── strike, expiration, bid, ask
    │
    ▼
dispatch.option_iv(exercise_style, mid_price, spot, strike, T, r, q, option_type)
    │   → Computes implied volatility from market mid price
    │   → Uses market_iv as initial guess for BSM Newton-Raphson
    │
    ▼
dispatch.option_greeks(exercise_style, spot, strike, T, r, q, computed_iv, option_type)
    │   → Computes all 5 Greeks using the locally computed IV
    │   → Returns OptionGreeks(pricing_model=BSM or BAW)
    │
    ▼
OptionContract.greeks = computed_greeks
    │   → Attached to the contract for downstream consumption
    │
    ▼
scoring/ and agents/ use the Greeks for analysis
```

Key insight: **yfinance provides NO Greeks**. Only `impliedVolatility` comes from market data.
All delta, gamma, theta, vega, rho values are computed locally by this module.

---

## Performance Characteristics

| Operation | Cost | Typical Time |
|-----------|------|-------------|
| `bsm_price` | 1 evaluation (closed-form) | ~1 μs |
| `bsm_greeks` | 1 evaluation (closed-form) | ~2 μs |
| `bsm_iv` | 5-8 BSM evaluations (Newton) | ~10 μs |
| `american_price` | 1 BSM + critical price solve (~50 iterations) | ~100 μs |
| `american_greeks` | 11 × `american_price` (bump-and-reprice) | ~1 ms |
| `american_iv` | 15-40 × `american_price` (brentq) | ~5 ms |

BAW Greeks and IV are ~100-500x slower than BSM equivalents due to the iterative nature
of both the critical price solver and the finite-difference/brentq approach. This is
acceptable for the scan pipeline (processing hundreds of contracts), but would need
optimization for real-time applications.

---

## Configuration

All solver parameters come from `PricingConfig` (injected, never imported directly):

```python
class PricingConfig(BaseModel):
    iv_solver_tol: float = 1e-6        # IV convergence tolerance
    iv_solver_max_iter: int = 50       # IV max iterations
    risk_free_rate_fallback: float = 0.05  # Used when FRED rate unavailable
    # ... other fields for delta targeting, DTE range, etc.
```

Internal constants (not configurable):
- Critical price tolerance: `1e-8`
- Critical price max iterations: `200`
- IV bracket: `[1e-6, 5.0]`
- Finite-difference bump sizes: `dS=1%`, `dT=1/365`, `dσ=0.001`, `dr=0.001`
