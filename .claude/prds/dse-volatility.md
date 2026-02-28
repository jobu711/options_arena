---
name: dse-volatility
description: "DSE Epic 1 — 13 IV/HV indicators, IV surface utilities, Volatility Agent expansion"
status: backlog
created: 2026-02-28T10:22:58Z
parent: deep-signal-engine
---

# DSE-1: Volatility & IV Analytics

## Objective

Build the IV modeling layer that Options Arena completely lacks. Compute 13 indicators spanning IV term structure, skew, vol regime, expected moves, and HV forecasting. Expand the existing Volatility Agent with rich IV context. All indicators are computable from yfinance chains + existing BSM/BAW infrastructure.

**Branch**: `epic/dse-1-volatility`
**Depends on**: Foundation (Phase 0) merged to master
**Parallel with**: DSE-2, DSE-3, DSE-4

---

## File Ownership

**This epic ONLY creates or modifies these files. Do NOT touch files owned by other epics.**

| File | Action | Notes |
|------|--------|-------|
| `indicators/iv_analytics.py` | **Create** | All 13 indicator functions |
| `indicators/volatility.py` | Extend | Add `compute_hv_20d()` and `compute_ewma_vol_forecast()` helpers |
| `pricing/iv_surface.py` | **Create** | Batch IV solving, ATM IV extraction, term structure utilities |
| `agents/prompts/volatility_agent.py` | Extend | Updated prompt template with new IV indicator context |
| `tests/unit/indicators/test_iv_analytics.py` | **Create** | Full coverage for all 13 indicators |
| `tests/unit/pricing/test_iv_surface.py` | **Create** | IV surface utility tests |

**Read-only imports** (do NOT modify):
- `models/enums.py` — `VolRegime`, `IVTermStructureShape`
- `models/scan.py` — `IndicatorSignals` (populate fields, don't add fields)
- `pricing/dispatch.py` — `compute_option_iv()` for IV solving
- `pricing/bsm.py` — Newton-Raphson IV solver (called via dispatch)

---

## Indicators

### IV-Based Volatility (11 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 19 | **IV vs HV Spread** | `compute_iv_hv_spread` | `ATM_IV_30d - HV_20d` where HV = annualized stddev of log returns over 20 days | P0 |
| 20 | **HV 20-day** | `compute_hv_20d` | `std(ln(close[t]/close[t-1])) * sqrt(252)` annualized | P0 |
| 21 | **IV Term Structure Slope** | `compute_iv_term_slope` | `(IV_60d - IV_30d) / 30` — positive = contango, negative = backwardation. IV_Nd = ATM IV at nearest expiry to N days. | P0 |
| 22 | **IV Term Structure Shape** | `compute_iv_term_shape` | Enum: `CONTANGO` / `BACKWARDATION` / `FLAT` based on slope thresholds (±0.001/day) | P0 |
| 23 | **Put Skew Index** | `compute_put_skew` | `IV_25d_put / IV_ATM` — ratio of 25-delta put IV to ATM IV. >1.0 = demand for downside protection. | P1 |
| 24 | **Call Skew Index** | `compute_call_skew` | `IV_25d_call / IV_ATM` — >1.0 = demand for upside. | P1 |
| 25 | **Skew Ratio** | `compute_skew_ratio` | `IV_25d_put / IV_25d_call` — symmetry of smile. >1.0 = put skew dominant. | P1 |
| 26 | **Vol Regime** | `classify_vol_regime` | `LOW` (IV_rank<20), `NORMAL` (20-50), `ELEVATED` (50-80), `CRISIS` (>80). Uses IV Rank. | P0 |
| 27 | **EWMA Volatility Forecast** | `compute_ewma_vol_forecast` | `σ²_t = λσ²_{t-1} + (1-λ)r²_t`, lambda=0.94. 20-day forward forecast. | P1 |
| 28 | **Vol Cone Percentile** | `compute_vol_cone_pctl` | `percentile_rank(HV_20d, [HV_20d values over past year])` | P2 |
| 29 | **VIX Correlation** | `compute_vix_correlation` | 60-day rolling correlation between ticker daily returns and VIX daily changes | P2 |

### Options-Specific (2 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 36 | **Expected Move** | `compute_expected_move` | `spot × ATM_IV × sqrt(DTE/365)` — ±1σ expected move | P0 |
| 37 | **Expected Move Ratio** | `compute_expected_move_ratio` | `IV_expected_move / avg_actual_move_at_same_DTE` over past year. >1.0 = IV overpricing. | P0 |

**Total: 13 indicators (6 P0, 3 P1, 2 P2, 2 P0 options)**

---

## Key Implementation: `pricing/iv_surface.py`

This is the core utility module enabling IV analytics. The BSM/BAW IV solver already exists in `pricing/dispatch.py` — this module builds batch operations on top.

### Required Functions

```python
async def extract_atm_iv(
    chain: OptionChain, spot: float, risk_free_rate: float
) -> float | None:
    """Find ATM strike, solve IV from mid price using dispatch.compute_option_iv()."""

async def extract_atm_iv_by_dte(
    chains: list[OptionChain], spot: float, risk_free_rate: float,
    target_dte: int,
) -> float | None:
    """ATM IV at the expiration nearest to target_dte days."""

async def compute_iv_at_delta(
    chain: OptionChain, spot: float, risk_free_rate: float,
    target_delta: float, option_type: OptionType,
) -> float | None:
    """Solve IV for the strike closest to target_delta. Used for 25-delta skew."""

async def batch_iv_solve(
    chain: OptionChain, spot: float, risk_free_rate: float,
    strikes: list[float],
) -> dict[float, float | None]:
    """Batch IV solve across multiple strikes. Returns strike → IV mapping."""
```

### Data Flow

```
yfinance chain data
    → pricing/iv_surface.py (batch IV solving, ATM extraction)
        → indicators/iv_analytics.py (indicator computation)
            → IndicatorSignals fields (populated by scan pipeline)
```

### Compute Budget

- IV solving for term structure: ~20 IV solves per ticker × 50 tickers = 1,000 solves × <1ms = <1s
- Skew (#23-25): 4-8 IV solves per ticker for 25-delta strikes × 50 = 200-400 solves = <1s
- EWMA forecast: trivial arithmetic per ticker
- VIX correlation (#29): 1 shared ^VIX fetch + per-ticker correlation = negligible
- **Total epic compute impact: ~5-10s additional on scan pipeline**

---

## IndicatorSignals Fields (populated by this epic)

These fields are defined in Foundation on `IndicatorSignals`. This epic populates them:

```
iv_hv_spread: float | None          # #19
hv_20d: float | None                # #20
iv_term_slope: float | None         # #21
iv_term_shape: IVTermStructureShape | None  # #22
put_skew_index: float | None        # #23
call_skew_index: float | None       # #24
skew_ratio: float | None            # #25
vol_regime: VolRegime | None        # #26
ewma_vol_forecast: float | None     # #27
vol_cone_percentile: float | None   # #28
vix_correlation: float | None       # #29
expected_move: float | None         # #36
expected_move_ratio: float | None   # #37
```

---

## Volatility Agent Expansion

The existing Volatility Agent (disabled by default) is expanded with rich IV context. **This epic updates the prompt template only** — the agent definition already exists.

### New Context for Prompt

The Volatility Agent prompt receives all 13 new indicators plus existing IV Rank, IV Percentile, BB Width, ATR%. The prompt template should structure these as:

- **IV Regime**: Vol Regime + IV Rank + IV Percentile
- **IV vs Realized**: IV-HV Spread + HV 20d + EWMA Forecast
- **Term Structure**: Slope + Shape (contango/backwardation)
- **Skew**: Put Skew + Call Skew + Skew Ratio
- **Expected Moves**: Expected Move + Expected Move Ratio
- **Correlation**: VIX Correlation + Vol Cone Percentile

Enable by default: `enable_volatility_agent: bool = True` (config change in Foundation).

---

## Testing Requirements

### Unit Tests (`test_iv_analytics.py`)

Each indicator function needs:
1. **Happy path**: Known input → expected output (use hand-calculated values)
2. **Insufficient data**: Short price series → returns `None`
3. **Edge cases**: Zero IV, NaN handling, empty chains
4. **Boundary values**: Vol Regime thresholds (19.9 vs 20.1), Term Structure Shape thresholds

### Unit Tests (`test_iv_surface.py`)

1. **ATM extraction**: Verify correct strike selection and IV solve
2. **Delta-based IV**: Verify 25-delta strike identification
3. **Batch solve**: Multiple strikes, some failing → partial results
4. **Missing data**: Empty chain, no ATM strike → graceful None

### Integration Points (tested during Integration Merge)

- IV indicators plugged into scan pipeline Phase 3
- Volatility Agent receives new indicators in MarketContext
- DimensionalScores `iv_vol_score` computed from these indicators

---

## Merge Boundaries — DO NOT TOUCH

- `indicators/flow_analytics.py` — DSE-2
- `indicators/fundamental.py` — DSE-3
- `indicators/regime.py` — DSE-3
- `pricing/greeks_extended.py` — DSE-2
- `scoring/` — DSE-4
- `agents/orchestrator.py` — DSE-4
- `agents/flow_agent.py` — DSE-2
- `agents/fundamental_agent.py` — DSE-3
- `agents/trend_agent.py` — DSE-4
- `agents/contrarian_agent.py` — DSE-4
- `models/` — Foundation only (read-only for this epic)

---

## Dependencies

### From Foundation
- `IndicatorSignals` with 13 new optional fields
- `VolRegime`, `IVTermStructureShape` enums
- `VolatilityThesis` model (existing, extended)

### From Existing Code
- `pricing/dispatch.py` — `compute_option_iv()` for IV solving
- `pricing/bsm.py` — BSM pricing functions
- `pricing/american.py` — BAW pricing functions
- `services/market_data.py` — yfinance chain data, OHLCV data
- `indicators/volatility.py` — existing BB Width, ATR%, Keltner Width

### Cross-Epic (at Integration)
- DSE-4 consumes all 13 indicators for `iv_vol_score` in DimensionalScores
- DSE-4 passes indicators to expanded Volatility Agent in debate
