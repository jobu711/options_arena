---
name: multi-leg-strategies
description: Multi-leg option strategy builder — construction, P&L, Greeks aggregation, and IV-regime-based selection
status: backlog
created: 2026-03-11T01:57:51Z
---

# PRD: multi-leg-strategies

## Executive Summary

Add a multi-leg option strategy builder to Options Arena. The pipeline currently recommends a single contract per ticker. Real options trading uses defined-risk strategies — vertical spreads, iron condors, straddles, strangles — to shape risk/reward profiles. The data models (`SpreadLeg`, `OptionSpread`, `SpreadType`) already exist but have no construction logic, no P&L mechanics, and no strategy selection engine. This PRD covers the `SpreadAnalysis` model, strategy construction functions, Greeks aggregation, an IV-regime-based selection engine, and integration into the scan pipeline, debate agents, and web UI. Zero new dependencies — all implemented with existing numpy/scipy stack.

## Problem Statement

Options Arena recommends single naked long calls or puts. This is the simplest but often worst way to express a directional or neutral view:

- **Undefined risk profile** — a naked long option loses 100% of premium if OTM at expiry. Spreads define max loss upfront.
- **Overpaying for theta** — long options bleed theta daily. Credit spreads and iron condors collect theta.
- **IV regime mismatch** — buying options in high IV environments (IV rank >50) means overpaying for vol. Selling premium via credit spreads or iron condors is the textbook response, but the system cannot recommend them.
- **Missing from debate** — the Volatility Agent and Risk Agent reference strategy types in their analysis (`TradeThesis.recommended_strategy: SpreadType | None`) but there are no actual multi-leg constructions behind the recommendation.

The existing infrastructure is 80% there: `SpreadLeg(contract, side, quantity)`, `OptionSpread(spread_type, legs, ticker)`, and `SpreadType` with 6 variants are defined and frozen. What's missing is the engine that builds, prices, and selects them.

## User Stories

### US-1: Analyst wants defined-risk trade ideas
**As** a trader reviewing debate output, **I want** the system to recommend a specific multi-leg strategy with max profit, max loss, and breakeven levels **so that** I can evaluate the risk/reward before entering a trade.

**Acceptance criteria:**
- `SpreadAnalysis` includes net_premium, max_profit, max_loss, breakevens, risk_reward_ratio, pop_estimate, net_greeks
- Displayed in debate output and web UI debate detail
- Each leg shows contract details and side (LONG/SHORT)

### US-2: Analyst wants IV-aware strategy selection
**As** a trader, **I want** the system to pick the right strategy type based on current IV environment **so that** I'm not buying premium when IV is high or selling premium when IV is low.

**Acceptance criteria:**
- High IV (rank >50) + Neutral → Iron Condor
- High IV + Directional → Vertical Credit Spread
- Low IV (rank <25) + Directional → Vertical Debit Spread
- High IV + Low confidence → Strangle
- Mid IV or unavailable → single contract fallback (current behavior)

### US-3: Analyst wants aggregated Greeks for spreads
**As** a risk-conscious trader, **I want** to see net delta, gamma, theta, vega for the entire spread **so that** I understand my true exposure, not just per-leg Greeks.

**Acceptance criteria:**
- Net Greeks computed as `Σ(quantity * sign(side) * greek)` across all legs
- LONG = +1, SHORT = -1
- Includes second-order Greeks (vanna, charm, vomma) when available
- `pricing_model` taken from first leg

### US-4: Graceful fallback when spreads can't be built
**As** a user, **I want** the system to still recommend a single contract when there aren't enough liquid options to build a spread **so that** I always get an actionable recommendation.

**Acceptance criteria:**
- All construction functions return `None` when insufficient contracts
- Pipeline falls back to single-contract recommendation seamlessly
- No errors or warnings surfaced to user — just the simpler recommendation

## Requirements

### Functional Requirements

#### FR-S1: SpreadAnalysis Model
- Frozen Pydantic model in `models/options.py`
- Fields: `spread: OptionSpread`, `net_premium: Decimal`, `max_profit: Decimal`, `max_loss: Decimal`, `breakevens: list[Decimal]`, `risk_reward_ratio: float`, `pop_estimate: float`, `net_greeks: OptionGreeks`
- Validators: `pop_estimate` in [0.0, 1.0], `risk_reward_ratio` finite, Decimal `field_serializer`

#### FR-S2: Strategy Construction Functions
Implement in `scoring/spreads.py`:

- `build_vertical_spread(contracts, direction, spot, r, q) -> SpreadAnalysis | None`
  - BULLISH → bull call spread (long lower strike call, short higher strike call)
  - BEARISH → bear put spread (long higher strike put, short lower strike put)
  - Select strikes: long leg near target delta, short leg ~1 strike width away
  - Net premium = long premium - short premium (debit spread) or reverse (credit)

- `build_iron_condor(contracts, spot, r, q) -> SpreadAnalysis | None`
  - 4 legs: short OTM put + long further OTM put + short OTM call + long further OTM call
  - Requires puts AND calls at the same expiration with sufficient OI
  - Max profit = net credit received; max loss = wing width - net credit

- `build_straddle(contracts, spot, r, q) -> SpreadAnalysis | None`
  - 2 legs: long ATM call + long ATM put (same strike, same expiration)
  - Max loss = total premium paid; max profit = unlimited (capped for display at 5x premium)
  - Two breakevens: strike ± total premium

- `build_strangle(contracts, spot, r, q) -> SpreadAnalysis | None`
  - 2 legs: long OTM put + long OTM call (different strikes, same expiration)
  - Max loss = total premium; max profit = unlimited (capped)
  - Two breakevens

#### FR-S3: Greeks Aggregation
Implement in `pricing/spreads.py`:

- `aggregate_spread_greeks(legs: list[SpreadLeg]) -> OptionGreeks`
- Sum formula: `Σ(leg.quantity * sign(leg.side) * leg.contract.greeks.field)` for each Greek
- `PositionSide.LONG` = +1, `PositionSide.SHORT` = -1
- `pricing_model` from first leg's Greeks
- Skip legs where `contract.greeks is None` (log warning)

#### FR-S4: Strategy Selection Engine
Implement in `scoring/spreads.py`:

- `select_strategy(iv_rank, direction, confidence, contracts, spot, r, q) -> SpreadAnalysis | None`
- Decision tree:

| IV Rank | Direction | Confidence | Strategy |
|---------|-----------|------------|----------|
| >50 | NEUTRAL | any | Iron Condor |
| >50 | BULLISH/BEARISH | any | Vertical Credit Spread |
| <25 | BULLISH/BEARISH | any | Vertical Debit Spread |
| >50 | any | <0.4 | Strangle |
| 25-50 | any | any | Single contract (return None) |
| None | any | any | Single contract (return None) |

- Falls through strategies in priority order — if iron condor can't be built, try vertical, etc.

#### FR-S5: Pipeline Integration
- Call `select_strategy()` in `scan/phase_options.py` after single-contract recommendation
- Store `SpreadAnalysis` alongside `RecommendedContract` in Phase 4 persistence
- Pass spread data through to debate context via `MarketContext` or separate field

#### FR-S6: Agent Integration
- Volatility Agent: receives recommended strategy type and net Greeks for exposure assessment
- Risk Agent: evaluates max loss, risk/reward ratio, and spread Greeks
- `TradeThesis.recommended_strategy` populated from actual `SpreadAnalysis` (currently always None)

#### FR-S7: P&L Formulas by Strategy Type

**Vertical (Debit)**: max_profit = width - net_debit, max_loss = net_debit, breakeven = long_strike + net_debit (call) or long_strike - net_debit (put)

**Vertical (Credit)**: max_profit = net_credit, max_loss = width - net_credit, breakeven = short_strike + net_credit (call) or short_strike - net_credit (put)

**Iron Condor**: max_profit = net_credit, max_loss = call_wing_width - net_credit (assuming equal wings), breakevens = short_put_strike - net_credit, short_call_strike + net_credit

**Straddle**: max_loss = call_premium + put_premium, breakevens = strike - total_premium, strike + total_premium

**Strangle**: max_loss = call_premium + put_premium, breakevens = put_strike - total_premium, call_strike + total_premium

#### FR-S8: Probability of Profit (PoP) Estimation
- Use BSM-derived probability: `PoP = P(S_T in profit zone)`
- For debit spreads: `PoP = 1 - N(d2_breakeven)` (call) or `N(-d2_breakeven)` (put)
- For credit spreads: `PoP = N(d2_upper) - N(d2_lower)` between breakevens
- For straddles/strangles: `PoP = 1 - [N(d2_upper) - N(d2_lower)]` (probability of moving beyond either breakeven)
- Use current IV for the N(d2) calculation

### Non-Functional Requirements

#### NFR-S1: No New Dependencies
All implemented with existing numpy, scipy, Decimal. No new packages.

#### NFR-S2: Backward Compatibility
- `SpreadAnalysis` is a new model — no existing code affected
- Pipeline continues to produce single-contract recommendations; spread is additive
- All ~4,400 existing tests pass without modification

#### NFR-S3: Performance
- Strategy construction: <50ms per ticker (simple arithmetic on pre-computed Greeks)
- No additional pricing calls — uses Greeks already computed on contracts

#### NFR-S4: Graceful Degradation
- Every construction function returns `None` when it can't build a valid spread
- Insufficient contracts (< 2 at same expiration) → None
- Missing Greeks on any leg → None
- Zero-width spreads (same strike both legs) → None
- Pipeline falls back to single contract seamlessly

## Success Criteria

| Metric | Target |
|--------|--------|
| Strategy recommendation produced | >50% of debate tickers with liquid chains |
| Correct P&L formulas (verified by tests) | 100% of strategy types |
| Greeks aggregation sign correctness | Verified by BSM cross-check tests |
| Graceful fallback when spread can't build | 100% — never errors, always returns result |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~60 tests across 3 test files |

## Constraints & Assumptions

### Constraints
- `scoring/spreads.py` imports from `models/` and `pricing/dispatch` only — never `pricing/bsm` or `pricing/american` directly
- `pricing/spreads.py` imports from `models/` only
- All Decimal fields need `field_serializer`. `pop_estimate` needs [0,1] validator.
- Frozen models — use `model_copy(update=...)` for modifications

### Assumptions
- All legs in a spread share the same expiration (single-expiration strategies only)
- Strategy builder operates on the filtered contract list from Phase 3 (post-liquidity-filter)
- OI >= 100 and volume >= 1 already guaranteed by `filter_contracts()` upstream
- Second-order Greeks on `OptionGreeks` are available (from native-quant epic) — if not, aggregation skips them

## Out of Scope

- **Calendar spreads** — requires contracts at different expirations (different pricing assumptions)
- **Butterfly spreads** — 3-strike construction adds complexity; defer to future iteration
- **Ratio spreads** — unequal quantities per leg; advanced strategy, defer
- **Strategy backtesting** — historical P&L tracking for spreads (requires chain snapshots)
- **Broker execution** — placing multi-leg orders via IBKR or other APIs
- **Portfolio-level aggregation** — combining spreads across multiple tickers
- **Volatility surface 3D visualization** — covered by native-quant PRD
- **Interactive strategy builder UI** — drag-and-drop leg construction; future UI epic

## Dependencies

### Internal
- **Soft dependency on native-quant**: Second-order Greeks on `OptionGreeks` (vanna, charm, vomma) are used in aggregation when available, but spread builder works without them (skips None fields)
- `OptionGreeks`, `SpreadLeg`, `OptionSpread`, `SpreadType` models already exist in `models/options.py`
- `filter_contracts()`, `compute_greeks()`, `select_by_delta()` in `scoring/contracts.py` provide input data
- `pricing/dispatch.option_greeks()` already populates first-order Greeks on all contracts

### External
- None. All algorithms use existing numpy/scipy/Decimal stack.

## Delivery Issues

| Issue | Description | New Files | Modified Files | Est. Tests |
|-------|-------------|-----------|----------------|------------|
| 1 | `SpreadAnalysis` model + re-exports | 0 | 2 | ~10 |
| 2 | `aggregate_spread_greeks()` in `pricing/spreads.py` | 1 | 1 | ~15 |
| 3 | Strategy construction functions in `scoring/spreads.py` | 1 | 1 | ~25 |
| 4 | Strategy selection engine + pipeline integration | 0 | 3 | ~10 |
| 5 | Agent prompt enrichment + API/UI integration | 0 | 4 | ~5 |
| **Total** | | **2** | **11** | **~65** |

Issues 1-3 can be implemented in parallel. Issue 4 depends on 1-3. Issue 5 depends on 4.

## References

- Natenberg (2015) "Option Volatility and Pricing", Ch. 14-16 — spread strategies and risk profiles
- Hull (2018) "Options, Futures, and Other Derivatives", Ch. 12 — trading strategies involving options
- McMillan (2012) "Options as a Strategic Investment", 5th Edition — strategy selection by IV regime
