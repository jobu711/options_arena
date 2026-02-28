---
name: dse-flow-risk
description: "DSE Epic 2 — 12 flow/risk/microstructure indicators, second-order Greeks, Flow Agent"
status: backlog
created: 2026-02-28T10:22:58Z
parent: deep-signal-engine
---

# DSE-2: Options Flow & Risk Analytics

## Objective

Build the options flow analysis and risk quantification layers. Detect smart money activity via GEX, unusual activity scoring, and OI concentration. Add second-order Greeks (vanna, charm, vomma) via finite difference on existing pricing infrastructure. Deploy a new Flow Agent that specializes in institutional positioning signals. Extend options-specific indicators with PoP, Optimal DTE, spread quality, and max loss ratio.

**Branch**: `epic/dse-2-flow-risk`
**Depends on**: Foundation (Phase 0) merged to master
**Parallel with**: DSE-1, DSE-3, DSE-4

---

## File Ownership

**This epic ONLY creates or modifies these files.**

| File | Action | Notes |
|------|--------|-------|
| `indicators/flow_analytics.py` | **Create** | GEX, OI Concentration, Unusual Activity, Max Pain Magnet, Dollar Volume Trend |
| `pricing/greeks_extended.py` | **Create** | Vanna, Charm, Vomma via finite difference |
| `indicators/options_specific.py` | Extend | PoP, Optimal DTE, Spread Quality, Max Loss Ratio |
| `agents/flow_agent.py` | **Create** | Flow Agent definition + prompt |
| `tests/unit/indicators/test_flow_analytics.py` | **Create** | Flow indicator tests |
| `tests/unit/pricing/test_greeks_extended.py` | **Create** | Second-order Greek tests |
| `tests/unit/indicators/test_options_specific_ext.py` | **Create** | Extended options indicator tests |

**Read-only imports** (do NOT modify):
- `models/enums.py`, `models/scan.py`, `models/analysis.py` — Foundation-owned
- `pricing/dispatch.py` — existing Greek computation (call, don't modify)
- `pricing/bsm.py`, `pricing/american.py` — pricing functions (call, don't modify)

---

## Indicators

### Options Flow & OI (5 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 30 | **Gamma Exposure (GEX)** | `compute_gex` | `Σ(OI × gamma × 100 × spot)` across all strikes. Net GEX = call_GEX - put_GEX. Positive GEX = dealer hedging dampens moves. | P0 |
| 34 | **OI Concentration Score** | `compute_oi_concentration` | `max_strike_OI / total_OI` — how concentrated OI is at a single strike. High = pinning risk. | P0 |
| 35 | **Unusual Activity Score** | `compute_unusual_activity` | `Σ(volume_i / OI_i)` for strikes where `volume > 2 × OI`. Weighted by premium: `volume × mid × 100`. | P0 |
| 39 | **Max Pain Magnet Strength** | `compute_max_pain_magnet` | `1 - (|spot - max_pain| / spot)` — near 1.0 = strong gravitational pull. | P1 |
| 47 | **Dollar Volume Trend** | `compute_dollar_volume_trend` | 20-day slope of `close × volume`. Rising = increasing institutional participation. | P1 |

### Second-Order Greeks (3 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 31 | **Vanna Exposure** | `compute_vanna` | `d(delta)/d(IV)` — finite difference: `(delta(σ+dσ) - delta(σ-dσ)) / (2*dσ)` where `dσ = 0.01` | P1 |
| 32 | **Charm (Delta Decay)** | `compute_charm` | `d(delta)/d(T)` — `(delta(T-dT) - delta(T)) / dT` where `dT = 1/365` | P1 |
| 33 | **Vomma** | `compute_vomma` | `d(vega)/d(IV)` — `(vega(σ+dσ) - vega(σ-dσ)) / (2*dσ)` | P2 |

### Risk Quantification (4 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 38 | **Probability of Profit (PoP)** | `compute_pop` | `N(d2)` for calls, `N(-d2)` for puts (BSM approximation). | P1 |
| 40 | **Optimal DTE Score** | `compute_optimal_dte` | `(expected_move × delta - theta × DTE) / (theta × DTE)` — theta-normalized expected value. | P2 |
| 45 | **Options Spread Quality** | `compute_spread_quality` | `Σ(spread_pct_i × OI_i) / Σ(OI_i)` — OI-weighted average bid-ask spread. Lower = better. | P0 |
| 58 | **Max Loss Ratio** | `compute_max_loss_ratio` | `contract_cost / account_risk_budget` — % of configurable notional. | P1 |

**Total: 12 indicators (3 P0, 5 P1, 2 P2, 2 P0 microstructure/risk)**

---

## Key Implementation: `pricing/greeks_extended.py`

Second-order Greeks via finite difference on existing `pricing/dispatch.py` functions.

```python
from pricing.dispatch import compute_option_price, compute_option_greeks

async def compute_vanna(
    spot: float, strike: float, time_to_expiry: float,
    risk_free_rate: float, iv: float, option_type: OptionType,
    div_yield: float = 0.0, d_sigma: float = 0.01,
) -> float | None:
    """d(delta)/d(sigma) via central finite difference."""
    greeks_up = await compute_option_greeks(spot, strike, time_to_expiry, risk_free_rate, iv + d_sigma, option_type, div_yield)
    greeks_down = await compute_option_greeks(spot, strike, time_to_expiry, risk_free_rate, iv - d_sigma, option_type, div_yield)
    if greeks_up is None or greeks_down is None:
        return None
    return (greeks_up.delta - greeks_down.delta) / (2 * d_sigma)

# Same pattern for charm (bump time) and vomma (bump sigma on vega)
```

**Cost**: 2-4 additional pricing calls per contract per second-order Greek. At 50 tickers × 3 Greeks = 300 calls. BAW is <1ms per call. Total: <1s.

---

## Key Implementation: `indicators/flow_analytics.py`

### GEX Computation

```python
async def compute_gex(
    chain: OptionChain, spot: float, risk_free_rate: float,
) -> float | None:
    """Net Gamma Exposure across all strikes in the chain.

    Requires computing gamma for each strike. Uses ATM ± 10 strikes
    for performance (captures >95% of GEX).
    """
    # Filter to ATM ± 10 strikes
    # For each strike: gamma = compute_option_greeks(...)
    # call_gex = Σ(OI_call × gamma_call × 100 × spot)
    # put_gex = Σ(OI_put × gamma_put × 100 × spot)  (negative by convention)
    # return call_gex - abs(put_gex)
```

**Compute budget**: ~20 strikes × 3 expirations × 50 tickers = 3,000 gamma computations. BAW gamma via finite difference = ~5 function evaluations each → 15K BAW calls. <1s total CPU, needs async batching with `asyncio.gather()`.

### Unusual Activity Detection

```python
async def compute_unusual_activity(chain: OptionChain) -> float | None:
    """Score unusual options activity based on volume/OI ratio.

    Flags strikes where volume > 2 × OI (fresh positioning).
    Weights by premium (volume × mid × 100) to emphasize big bets.
    """
    # For each contract in chain:
    #   if volume > 2 * open_interest and open_interest > 0:
    #     score += (volume / open_interest) * (mid_price * volume * 100)
    # Normalize by total chain premium volume
```

---

## IndicatorSignals Fields (populated by this epic)

```
gex: float | None                    # #30
vanna: float | None                  # #31
charm: float | None                  # #32
vomma: float | None                  # #33
oi_concentration: float | None       # #34
unusual_activity_score: float | None # #35
pop: float | None                    # #38
max_pain_magnet: float | None        # #39
optimal_dte_score: float | None      # #40
spread_quality: float | None         # #45
dollar_volume_trend: float | None    # #47
max_loss_ratio: float | None         # #58
```

---

## Flow Agent

### Definition (`agents/flow_agent.py`)

New agent using `FlowThesis` output model (defined in Foundation).

**Role**: Detect smart money activity, unusual options flow, and institutional positioning signals.

**Exclusive Indicators** (only this agent interprets): GEX (#30), OI Concentration (#34), Unusual Activity (#35), Max Pain Magnet (#39), Dollar Volume Trend (#47)

**Shared Indicators**: Put/Call Ratio, Max Pain Distance, OBV Trend, A/D Trend, Relative Volume

**Key Question**: "What is smart money doing, and does the options flow confirm or contradict the directional thesis?"

**Fallback**: Data-driven: flow_score + put/call ratio + unusual activity thresholds.

### FlowThesis Output (defined in Foundation)

```python
class FlowThesis(BaseModel):
    model_config = ConfigDict(frozen=True)
    flow_direction: SignalDirection
    confidence: float                    # [0.0, 1.0]
    institutional_signal: str
    unusual_activity_summary: str
    gex_interpretation: str
    key_flow_factors: list[str]          # >= 1
    model_used: str
```

### Prompt Structure

The Flow Agent prompt should organize indicators as:
- **Gamma Positioning**: GEX value + interpretation (positive = dampening, negative = amplifying)
- **Smart Money Activity**: Unusual Activity Score + which strikes flagged
- **OI Analysis**: OI Concentration + Max Pain Magnet + Put/Call Ratio
- **Volume Confirmation**: Dollar Volume Trend + Relative Volume + OBV/AD trends

---

## Testing Requirements

### Unit Tests — Flow Analytics

1. **GEX**: Mock chain with known OI/gamma → verify net GEX calculation
2. **OI Concentration**: Chain with concentrated vs distributed OI → verify score
3. **Unusual Activity**: Chain with normal vs unusual volume/OI ratios → verify scoring and threshold
4. **Max Pain Magnet**: Spot at max pain (=1.0), far from max pain (→0.0)
5. **Dollar Volume Trend**: Rising, falling, flat volume trends

### Unit Tests — Second-Order Greeks

1. **Vanna**: Known BSM inputs → verify against analytical vanna (BSM has closed-form)
2. **Charm**: Verify sign (delta decays for OTM options as time passes)
3. **Vomma**: Verify positive for OTM options, near-zero for ATM
4. **Edge cases**: Zero time to expiry, deep ITM/OTM, zero IV

### Unit Tests — Extended Options

1. **PoP**: ATM option ≈ 50%, deep ITM > 80%, deep OTM < 20%
2. **Spread Quality**: Tight spreads → low score, wide spreads → high score
3. **Max Loss Ratio**: Long call max loss = premium paid, verify ratio

---

## Merge Boundaries — DO NOT TOUCH

- `indicators/iv_analytics.py` — DSE-1
- `indicators/volatility.py` — DSE-1
- `pricing/iv_surface.py` — DSE-1
- `indicators/trend.py` — DSE-3
- `indicators/fundamental.py` — DSE-3
- `indicators/regime.py` — DSE-3
- `scoring/` — DSE-4
- `agents/orchestrator.py` — DSE-4
- `agents/trend_agent.py` — DSE-4
- `agents/contrarian_agent.py` — DSE-4
- `models/` — Foundation only

---

## Dependencies

### From Foundation
- `IndicatorSignals` with 12 new optional fields
- `FlowThesis` model
- Config: `enable_flow_analytics: bool`

### From Existing Code
- `pricing/dispatch.py` — `compute_option_greeks()`, `compute_option_price()`
- `pricing/bsm.py` — `norm.cdf` for PoP N(d2) calculation
- `services/market_data.py` — yfinance chain data
- `indicators/options_specific.py` — existing Put/Call Ratio, Max Pain Distance

### Cross-Epic (at Integration)
- DSE-4 consumes all 12 indicators for `flow_score` and `risk_score` in DimensionalScores
- DSE-4 integrates Flow Agent into debate protocol Phase 1 (parallel)
- DSE-1 Expected Move (#36) needed by Optimal DTE (#40) — use `None` fallback until DSE-1 merges
