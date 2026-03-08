<role>
You are a quantitative finance engineer specializing in options market microstructure
and systematic scoring systems. You understand that liquidity is not binary — a contract
with 10,000 OI and a 0.5% spread is fundamentally different from one with 100 OI and
a 25% spread, even though both pass minimum threshold filters. Your job is to design
a liquidity weighting dimension that transforms these gate-level checks into gradient
signals that improve contract recommendation quality.
</role>

<context>
## Current Scoring Architecture

The Options Arena scan pipeline uses a 4-phase approach:
- **Phase 1**: Build ticker universe, fetch 1y OHLCV
- **Phase 2**: Compute 14 OHLCV indicators, percentile-rank normalize, composite score
- **Phase 3**: Liquidity pre-filter → top-N → fetch option chains → compute Greeks → recommend contracts
- **Phase 4**: Persist scan run + scores + contracts to SQLite

### Composite Scoring (scoring/composite.py)

Weighted geometric mean across 19 indicators (6 categories):

```
Oscillators (0.17):    rsi(0.07), stochastic_rsi(0.05), williams_r(0.05)
Trend (0.20):          adx(0.07), roc(0.03), supertrend(0.05), macd(0.05)
Volatility (0.14):     atr_pct(0.05), bb_width(0.05), keltner_width(0.04)
Volume (0.15):         obv(0.05), ad(0.05), relative_volume(0.05)
Moving Avgs (0.12):    sma_alignment(0.07), vwap_deviation(0.05)
Options (0.22):        iv_rank(0.06), iv_percentile(0.06), put_call_ratio(0.05), max_pain_distance(0.05)
```

Formula: `score = exp(sum(w_i * ln(max(x_i, 0.5))) / sum(w_i))` → range [1.0, 100.0]

### Current Liquidity Handling (Binary Gates Only)

**Service layer** (`services/options_data.py`):
- Reject bid=0 AND ask=0 (dead contracts)
- OI >= `min_oi` (default 100), volume >= `min_volume` (default 1)

**Scoring layer** (`scoring/contracts.py`):
- Spread % gate: `spread / mid <= max_spread_pct` (default 30%)
- Zero-bid exemption: bid=0, ask>0 passes without spread check
- Sorts survivors by OI descending

**No gradient scoring** — a contract with OI=101 and 29% spread scores identically to
one with OI=50,000 and 0.3% spread.

### Existing But Unused

`indicators/options_specific.py` has `compute_average_weighted_spread()` — OI-weighted
average bid-ask spread across a chain. Computed but never fed into scoring.

### Contract Model Fields Available

```python
class OptionContract(BaseModel):  # frozen=True
    bid: Decimal
    ask: Decimal
    volume: int
    open_interest: int
    # Computed:
    mid: Decimal     # (bid + ask) / 2
    spread: Decimal  # ask - bid
    dte: int
```

### Normalization System

- **Universe-wide**: Percentile-rank across all tickers (`percentile_rank_normalize`)
- **Single-ticker**: Linear scaling with domain bounds (`normalize_single_ticker`)
- **Inversion**: 3 indicators where higher = worse get flipped (100 - percentile)
- **Stats persistence**: min, max, median, mean, std_dev, p25, p75 per indicator per scan

### Architecture Boundaries

| Layer | Can Access | Cannot Access |
|-------|-----------|---------------|
| `scoring/` | `models/`, `pricing/dispatch` | APIs, services, `pricing/bsm` or `pricing/american` directly |
| `indicators/` | pandas, numpy | APIs, models, I/O |
| `models/` | Nothing | APIs, logic, I/O |

### Project Conventions

- All structured data as Pydantic v2 models, never raw dicts
- `X | None` syntax, never `Optional[X]`
- `math.isfinite()` guard on every numeric validator (NaN passes `v >= 0`)
- Constants as uppercase module-level variables, no magic numbers
- `StrEnum` for categorical fields
- `field_validator` on confidence fields (clamp [0.0, 1.0])

### Config Pattern

```python
class PricingConfig(BaseModel):
    min_oi: int = 100
    min_volume: int = 1
    max_spread_pct: float = 0.30
    delta_target: float = 0.35
    # ... (thresholds passed via DI, never hardcoded)
```
</context>

<task>
Design and specify the implementation plan for adding options liquidity weighting as a
gradient scoring dimension in the composite scoring system. The goal is to differentiate
contract quality beyond binary pass/fail filters, so that tickers with highly liquid
option chains rank higher than those barely passing minimum thresholds.

This is a DESIGN task — produce a specification document, not code. The output will be
used as a PRD for an implementation epic.
</task>

<instructions>
## Phase 1: Assess — Identify Liquidity Signals

Evaluate which raw contract-level metrics best capture liquidity quality. Consider at
minimum: bid-ask spread as percentage of mid, open interest density (OI relative to
universe), volume-to-OI ratio (turnover), and dollar volume of the recommended contract.

For each candidate signal, assess:
- Does it add information beyond the existing gate filters?
- Is it available from the data already fetched in Phase 3 (no new API calls)?
- Can it be meaningfully percentile-ranked across a scan universe?
- Does it have a natural "good" direction (higher = better or lower = better)?

## Phase 2: Design — Integration Architecture

Determine where liquidity scoring fits in the existing pipeline:

**Option A — New indicators in `IndicatorSignals`**: Add 1-3 liquidity fields to the
indicator model, include in composite.py weight table. Pro: uses existing normalization
and persistence. Con: liquidity is contract-level, indicators are ticker-level — requires
aggregation.

**Option B — Contract-level adjustment**: Apply a liquidity multiplier to the recommended
contract's rank/selection in `contracts.py`. Pro: stays at the right abstraction level.
Con: doesn't influence ticker-level composite score (which determines top-N cutoff).

**Option C — Hybrid**: Aggregate chain-level liquidity into ticker-level indicators for
composite scoring, PLUS use contract-level liquidity as a tiebreaker in `select_by_delta`.

Evaluate each option against the architecture boundary table. The chosen approach must
not violate module boundaries.

## Phase 3: Specify — Weight Calibration

Propose initial weights for any new indicators added to the composite. The current 19
indicators sum to 1.0. Adding new indicators requires redistributing weights. Consider:
- How much influence should liquidity have relative to technicals, options metrics, etc.?
- Should liquidity be its own category or folded into the existing "Options" category?
- What are sensible domain bounds for single-ticker linear normalization?

## Phase 4: Verify

Before finalizing, verify the design against these criteria:
- No new API calls or external dependencies
- No violations of module boundaries (scoring cannot import services)
- All new fields have `math.isfinite()` guards
- Inverted indicators (lower = better) are explicitly flagged
- NormalizationStats persistence covers new indicators
- Single-ticker normalization has domain bounds for new indicators
- Backward compatible: existing scans without liquidity data still work
</instructions>

<constraints>
1. All new data structures use Pydantic v2 models with `X | None` union syntax.
2. New indicators added to `IndicatorSignals` must have corresponding entries in normalization domain bounds, composite weights, and inversion flags.
3. The scoring module accesses contract data only through typed models — never raw dicts or pandas DataFrames.
4. Every numeric field validator includes `math.isfinite()` before any range check.
5. New config thresholds go in `PricingConfig` or `ScanConfig` (whichever is semantically correct), never hardcoded.
6. Liquidity metrics use `float` type (not `Decimal`) — these are ratios and scores, not prices.
7. Backward compatibility: `None` defaults on new `IndicatorSignals` fields ensure old scans still load.
8. The composite score formula (geometric mean) tolerates missing indicators via `active_indicators` filtering — new fields participate only when populated.
9. No changes to the service layer data fetching — work with data already available in Phase 3.
10. Contract-level aggregation to ticker-level must handle edge cases: zero contracts passing filters, single contract only, all contracts having identical metrics.
</constraints>

<examples>
### Example: Evaluating a Liquidity Signal Candidate

**Signal**: Bid-ask spread percentage of recommended contract
**Raw value**: `float(contract.spread / contract.mid) * 100` → e.g., 2.5%
**Direction**: Lower is better (inverted indicator)
**Domain bounds (single-ticker)**: (0.0, 30.0) — matches existing `max_spread_pct` gate
**Universe normalization**: Percentile rank across all tickers with recommended contracts
**Composite weight**: 0.04 (moderate, within new "Liquidity" category)
**isfinite guard**: Required — mid can be zero (handled by zero-bid exemption upstream)
**Edge case**: If no contract recommended, field is `None`, skipped in composite

<thinking>
This signal adds gradient information beyond the 30% gate. A ticker whose best contract
has a 1% spread should rank higher than one at 28%. The data is already computed in
`filter_contracts()` — no new fetches needed. It can be percentile-ranked since every
ticker in Phase 3 has a recommended contract (or is excluded). Direction is "lower is
better" so it needs inversion like `bb_width` and `atr_pct`.
</thinking>

**Verdict**: Include — high signal, zero cost, clean integration.

---

### Example: Rejecting a Signal Candidate

**Signal**: Historical option volume trend (30-day moving average of daily option volume)
**Issue**: Requires 30 days of historical option volume data — not available in current
Phase 3 data. Would require new API calls to yfinance for historical option volume.

<thinking>
This violates constraint #9 (no new API calls). While it would be a valuable signal,
it's out of scope. The current pipeline fetches a single snapshot of the option chain,
not historical option data. Flag for future consideration.
</thinking>

**Verdict**: Exclude — requires new data source.
</examples>

<output_format>
## Liquidity Weighting Design Specification

### 1. Selected Signals
For each signal (2-4 recommended):
- **Name**: indicator field name (snake_case)
- **Formula**: exact computation from available fields
- **Direction**: higher-is-better or lower-is-better (inverted?)
- **Domain bounds**: (lo, hi) for single-ticker normalization
- **Justification**: why this signal adds value beyond existing gates

### 2. Architecture Decision
- **Chosen approach**: A, B, C, or hybrid (with rationale)
- **Files modified**: list of production files touched
- **New fields**: additions to `IndicatorSignals`, `PricingConfig`, etc.
- **Data flow**: how liquidity metrics flow from contract → ticker → composite

### 3. Weight Allocation
- Updated weight table (all 19 + N new indicators, sum = 1.0)
- Category breakdown showing where liquidity fits
- Rationale for weight magnitudes

### 4. Edge Cases & Backward Compatibility
- How each edge case is handled (zero contracts, single contract, missing data)
- Migration path for existing scans
- Default behavior when liquidity data is absent

### 5. Task Breakdown
- Ordered list of implementation tasks with effort estimates (S/M/L)
- Dependencies between tasks
- Estimated total effort

### 6. Verification Checklist
- Confirm each constraint from the constraints section is satisfied
</output_format>
