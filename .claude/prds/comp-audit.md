---
name: comp-audit
description: Integrate 7 cherry-picked ideas from ai-hedge-fund competitive audit — Hurst exponent, performance metrics, persona framing, constraint pre-checks, position sizing, correlation matrix, multi-methodology valuation
status: planned
created: 2026-03-15T22:00:00Z
---

# PRD: competitive-audit-integration

## Problem Statement

Options Arena's scoring engine uses 22 technical indicators but lacks a regime
classification signal (trending vs. mean-reverting). The Risk agent produces qualitative
assessments without quantitative position sizing. The analytics module has equity curves
and P&L tracking but no standard risk-adjusted metrics (Sharpe, Sortino). Debate agents
occasionally recommend contracts with hard constraint violations (expired, illiquid).
The Fundamental agent receives raw financials without a fair-value framework. And
portfolio-level risk (correlation across holdings) is entirely absent.

## User Stories

### US-A1: Regime-Aware Scoring
**As** a trader reviewing scan results, **I want** to know whether a ticker's price
action is statistically trending or mean-reverting **so that** I can choose appropriate
strategies (momentum plays for trending, contrarian for mean-reverting).

**Acceptance criteria:**
- Hurst exponent computed per ticker in Phase 2 of scan pipeline
- Value displayed in scan detail view (0-1 scale, with regime label)
- Integrated into composite scoring with 0.02 weight in "regime" category

### US-A2: Risk-Adjusted Performance Metrics
**As** a trader evaluating my outcomes, **I want** to see Sharpe ratio, Sortino ratio,
and max drawdown with date tracking **so that** I can assess risk-adjusted performance,
not just raw P&L.

**Acceptance criteria:**
- Proper annualized Sharpe (using FRED risk-free rate, sqrt(252) scaling)
- Sortino using downside deviation only
- Max drawdown with start/end dates
- Available via CLI (`outcomes risk-metrics`), API, and web UI analytics page

### US-A3: Debate Quality via Constraint Pre-Checks
**As** a trader reading debate output, **I want** agents to never recommend contracts
that violate hard constraints (expired, illiquid, wide spread) **so that** I can trust
the recommendations are actionable.

**Acceptance criteria:**
- Pre-check runs before agent invocation on all recommended contracts
- Hard violations injected as "DO NOT recommend" directives into agent prompts
- Soft violations flagged as caution warnings

### US-A4: Quantitative Position Sizing
**As** a risk-conscious trader, **I want** the Risk agent to recommend a specific
position size as a percentage of portfolio based on volatility regime **so that** I
don't overallocate to high-vol names.

**Acceptance criteria:**
- Four-tier vol bucketing with configurable thresholds
- Correlation adjustment when portfolio data available
- Position size displayed in debate output and Risk agent context
- Informational only — does not influence scan ranking

### US-A5: Distinctive Agent Personalities
**As** a user reading debate output, **I want** each agent to have a distinctive
professional persona **so that** the debate feels more engaging and each agent's
perspective is immediately recognizable.

**Acceptance criteria:**
- Each of 6 agents has a named persona (e.g., "Momentum Trader", "Vol Arb Specialist")
- Persona paragraph prepended to system prompt (~80 tokens each)
- No structural changes — prompt-only modification

### US-A6: Fair-Value Estimation
**As** a fundamentals-focused trader, **I want** the system to compute a composite
fair value using multiple valuation methodologies **so that** I can identify mispriced
underlyings with asymmetric options opportunities.

**Acceptance criteria:**
- Four independent valuation models (Owner Earnings DCF, 3-Stage DCF, EV/EBITDA, Residual Income)
- Weighted composite with margin-of-safety signal (undervalued/fairly/overvalued)
- Injected into Fundamental agent context when financial data available
- Graceful degradation — each model independently returns None on insufficient data

## Requirements

### Functional Requirements

#### FR-C1: Hurst Exponent Indicator

**New file**: `src/options_arena/indicators/hurst.py`

Function signature (follows `hv_estimators.py` pattern):
```python
def hurst_exponent(close: pd.Series, max_lag: int = 100) -> float | None:
    """Hurst exponent via rescaled range (R/S) analysis.
    H > 0.5 = trending, H < 0.5 = mean-reverting, H ~ 0.5 = random walk.
    Reference: Mandelbrot & Wallis (1969).
    Returns: float in [0.0, 1.0], or None if insufficient data or poor R^2.
    """
```

Algorithm:
1. Compute log returns from close prices
2. For each lag in `range(10, max_lag + 1)`, subdivide into non-overlapping windows
3. Per window: cumulative deviations from mean, range R, standard deviation S
4. Average R/S across windows per lag
5. OLS regression: `log(avg_R/S) = H * log(lag) + c`
6. Return H clamped to [0.0, 1.0]. Return None if R^2 < 0.5 or insufficient data.

**Modified files:**
- `models/scan.py` — add `hurst_exponent: float | None = None` to `IndicatorSignals`
- `scoring/composite.py` — add `"hurst_exponent": (0.02, "regime")` to `INDICATOR_WEIGHTS`; reduce `roc` 0.03→0.02 and `put_call_ratio` 0.03→0.02 (user-confirmed)
- `scoring/normalization.py` — add domain bounds `"hurst_exponent": (0.0, 1.0)`
- `indicators/__init__.py` — re-export `hurst_exponent`

Not inverted (higher H = trending = generally favorable for directional options).

#### FR-C2: Performance Metrics (Sharpe, Sortino, Max Drawdown)

**New files:**
- `src/options_arena/analysis/__init__.py` — package init
- `src/options_arena/analysis/performance.py` — metric computation

**New model** in `models/analytics.py`:
```python
class RiskAdjustedMetrics(BaseModel):
    model_config = ConfigDict(frozen=True)
    lookback_days: int                      # >= 1
    total_trades: int                       # >= 0
    sharpe_ratio: float | None = None       # None if < 30 trades
    sortino_ratio: float | None = None      # None if no downside deviation
    max_drawdown_pct: float | None = None   # Non-positive or zero
    max_drawdown_date: date | None = None
    annualized_return_pct: float | None = None
    risk_free_rate: float                   # From FRED or fallback
    # validators: isfinite on all floats
```

Formulas:
- **Sharpe**: `sqrt(252 / holding_days) * mean(excess_returns) / std(excess_returns)`
  where `excess_return = contract_return_pct - risk_free_daily`
- **Sortino**: Same numerator, denominator = `std(min(excess_returns, 0))`
- **Max Drawdown**: Walk equity curve chronologically, track running peak, record worst
  trough percentage and date
- Risk-free rate from `PricingConfig.risk_free_rate_fallback` (5%) or FRED service

Computed from existing `contract_outcomes` table — no new migration.

**Modified files:**
- `models/__init__.py` — re-export `RiskAdjustedMetrics`
- `data/_analytics.py` — add `get_risk_adjusted_metrics()` to `AnalyticsMixin`
- `api/routes/analytics.py` — add `GET /api/analytics/risk-metrics` endpoint
- `cli/outcomes.py` — add `outcomes risk-metrics` subcommand

#### FR-C3: Investor Persona Agent Framing

Prompt-only changes to 6 agent system prompts:

| Agent | Persona | Rationale |
|-------|---------|-----------|
| Trend | "Momentum Trader" | Reinforces conviction-based directional analysis |
| Volatility | "Vol Arb Specialist" | Deepens IV-centric analysis perspective |
| Flow | "Institutional Flow Analyst" | Reinforces smart money / institutional lens |
| Fundamental | "Event-Driven Analyst" | Sharpens catalyst timing focus |
| Risk | "Portfolio Risk Manager" | Adds hedging protocol emphasis |
| Contrarian | "Devil's Advocate Strategist" | Formalizes structured disagreement |

Pattern: Prepend ~60-80 token identity paragraph to each prompt constant:
```python
TREND_SYSTEM_PROMPT = (
    """## Your Identity: Momentum Trader
You are a seasoned momentum trader who reads price action on U.S. equity options. \
You trust trend-following indicators and believe strong directional moves confirmed \
by ADX and SMA alignment create the highest-probability entries.

"""
    + _EXISTING_PROMPT_BODY
    + PROMPT_RULES_APPENDIX
)
```

Version bump `# VERSION:` comment in each modified file.

**Modified files** (6 files):
- `agents/prompts/trend_agent.py`
- `agents/prompts/volatility.py`
- `agents/prompts/flow_agent.py`
- `agents/prompts/fundamental_agent.py`
- `agents/prompts/risk.py`
- `agents/prompts/contrarian_agent.py`

#### FR-C4: Deterministic Constraint Pre-Check

**New file**: `src/options_arena/agents/constraints.py`

Functions:
```python
def check_contract_constraints(
    contracts: list[OptionContract],
    filters: OptionsFilters,
) -> list[ContractConstraint]:
    """Check contracts against hard/soft constraints. Returns violations."""

def render_constraint_warnings(violations: list[ContractConstraint]) -> str:
    """Render violations as delimited text block for agent prompt injection."""
```

Constraint rules (thresholds from existing `OptionsFilters` in `models/filters.py`):

| Rule | Condition | Severity |
|------|-----------|----------|
| Expired | `expiration < today` | hard |
| DTE too short | `dte < filters.min_dte` | hard |
| OI too low | `open_interest < filters.min_oi` | hard |
| Spread too wide | `spread_pct > filters.max_spread_pct` | hard |
| Zero bid | `bid == 0 and ask > 0` | soft |
| Volume too low | `volume < filters.min_volume` | soft |

Prompt injection format:
```
<<<CONSTRAINT_WARNINGS>>>
DO NOT recommend these contracts (hard constraint violations):
- AAPL 200C 2026-04-18: Bid-ask spread 42% exceeds 30% maximum
EXERCISE CAUTION with these contracts (soft violations):
- AAPL 210C 2026-05-16: Zero bid price
<<<END_CONSTRAINT_WARNINGS>>>
```

**New model** in `models/analysis.py`:
```python
class ContractConstraint(BaseModel):
    model_config = ConfigDict(frozen=True)
    contract_label: str       # "AAPL 200C 2026-04-18"
    violation_type: ConstraintViolationType
    detail: str               # Human-readable explanation
    severity: ConstraintSeverity  # "hard" or "soft"
```

**New enums** in `models/enums.py`:
- `ConstraintViolationType` (EXPIRED, DTE_TOO_SHORT, OI_TOO_LOW, SPREAD_TOO_WIDE, ZERO_BID, VOLUME_TOO_LOW)
- `ConstraintSeverity` (HARD, SOFT)

**Modified files:**
- `agents/_parsing.py` — add `constraint_warnings: str | None = None` to `DebateDeps`;
  append to `render_context_block()` output
- `agents/orchestrator.py` — call `check_contract_constraints()` before building `DebateDeps`

#### FR-C5: Volatility-Regime Position Sizing

**New file**: `src/options_arena/analysis/position_sizing.py`

```python
def compute_position_size(
    annualized_iv: float,
    correlation_with_portfolio: float | None = None,
    config: PositionSizingConfig | None = None,
) -> PositionSizeResult:
    """Compute position size based on vol regime and correlation."""
```

Vol tier mapping (configurable via `PositionSizingConfig`):

| Tier | IV Range | Base Allocation |
|------|----------|----------------|
| 1 (low) | < 15% | 25% |
| 2 (moderate) | 15-30% | 17.5% (linear interpolation) |
| 3 (elevated) | 30-50% | 10% (linear interpolation) |
| 4 (extreme) | >= 50% | 5% hard cap |

Correlation adjustment: if `correlation > 0.70`, multiply allocation by 0.50.

**New config** in `models/config.py`:
```python
class PositionSizingConfig(BaseModel):
    tier1_iv_max: float = 0.15
    tier1_alloc: float = 0.25
    tier2_iv_max: float = 0.30
    tier2_alloc: float = 0.175
    tier3_iv_max: float = 0.50
    tier3_alloc: float = 0.10
    tier4_alloc: float = 0.05
    high_corr_threshold: float = 0.70
    corr_penalty: float = 0.50
```

**New model** in `models/analysis.py`:
```python
class PositionSizeResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    vol_regime_tier: int           # 1-4
    vol_regime_label: str          # "low", "moderate", "elevated", "extreme"
    annualized_iv: float
    base_allocation_pct: float     # [0.0, 1.0]
    correlation_adjustment: float  # [0.5, 1.0]
    final_allocation_pct: float    # base * adjustment
    rationale: str
```

Scope: **Informational only** (user-confirmed). Appears in debate output and Risk agent
context. Does not influence scan ranking.

Data flow: IV from `MarketContext.atm_iv_30d` or `hv_yang_zhang`. Correlation from FR-C7
(defaults to no adjustment until correlation is built).

**Modified files:**
- `models/config.py` — add `PositionSizingConfig`, add to `AppSettings`
- `models/analysis.py` — add `PositionSizeResult`; replace existing
  `recommended_position_size: str | None` on `MarketContext` with structured fields:
  `position_size_pct: float | None` and `position_size_rationale: str | None`
- `agents/orchestrator.py` — call `compute_position_size()` in `build_market_context()`
- `agents/_parsing.py` — render position size in `render_context_block()`

#### FR-C6: Multi-Methodology Valuation

**New files:**
- `src/options_arena/analysis/valuation.py` — 4 models + combiner
- `src/options_arena/models/valuation.py` — result models

**Models:**
```python
class ValuationModelResult(BaseModel):
    model_config = ConfigDict(frozen=True)
    methodology: str           # "owner_earnings_dcf", "three_stage_dcf", etc.
    fair_value: float | None   # Per-share, None if data insufficient
    margin_of_safety: float | None  # (fair - price) / fair
    confidence: float          # [0.0, 1.0] data quality score
    data_quality_notes: list[str]

class CompositeValuation(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker: str
    current_price: float
    composite_fair_value: float | None
    composite_margin_of_safety: float | None
    valuation_signal: ValuationSignal | None
    models: list[ValuationModelResult]
    weights_used: dict[str, float]
    computed_at: datetime      # UTC validated
```

**New enum**: `ValuationSignal(StrEnum)` — UNDERVALUED (>15% margin), FAIRLY_VALUED (±15%), OVERVALUED (<-15%)

Four valuation models (each returns None independently):

| Model | Weight | Key Inputs | Safety Margin |
|-------|--------|-----------|---------------|
| Owner Earnings DCF | 35% | net_income, D&A, capex | 25% haircut |
| 3-Stage DCF | 35% | FCF, growth rate | Scenario-weighted |
| EV/EBITDA Relative | 20% | ev_to_ebitda | Sector comparison |
| Residual Income | 10% | book_value, ROE | 20% haircut |

Data sources:
- `MarketContext.fd_*` fields (Financial Datasets MCP): existing `fd_net_income`,
  `fd_ev_to_ebitda`, `fd_revenue_growth`, `fd_earnings_growth`
- `TickerInfo`: current_price, market_cap
- `PricingConfig.risk_free_rate_fallback`: discount rate

**New `fd_*` fields required on `MarketContext`** (must be added to `models/analysis.py`
and populated by the FinancialDatasets integration epic #393):
- `fd_free_cash_flow: float | None` — absolute FCF (existing `fd_free_cash_flow_yield` is a ratio, not absolute)
- `fd_capex: float | None` — capital expenditures (for Owner Earnings DCF)
- `fd_depreciation_amortization: float | None` — D&A (for Owner Earnings DCF)
- `fd_book_value_per_share: float | None` — book value per share (for Residual Income)
- `fd_roe: float | None` — return on equity (for Residual Income)
- `fd_shares_outstanding: float | None` — for per-share fair value calculation

Combiner renormalizes weights across models that produced values. All four fail → None.

**Modified files:**
- `models/enums.py` — add `ValuationSignal` StrEnum
- `models/analysis.py` — add `valuation_signal`, `valuation_margin_of_safety`,
  `valuation_fair_value` fields to `MarketContext`
- `models/__init__.py` — re-export
- `agents/orchestrator.py` — compute in `build_market_context()` when FD data available
- `agents/_parsing.py` — render valuation in `render_context_block()`
- `agents/prompts/fundamental_agent.py` — add valuation guidance section

#### FR-C7: Portfolio Correlation Matrix

**New files:**
- `src/options_arena/analysis/correlation.py` — pairwise correlation computation
- `src/options_arena/models/correlation.py` — result models

**Models** in `models/correlation.py`:
```python
class PairwiseCorrelation(BaseModel):
    model_config = ConfigDict(frozen=True)
    ticker_a: str
    ticker_b: str
    correlation: float         # Pearson correlation coefficient [-1.0, 1.0]
    overlapping_days: int      # Number of days used in computation
    computed_at: datetime      # UTC validated

class CorrelationMatrix(BaseModel):
    model_config = ConfigDict(frozen=True)
    tickers: list[str]
    pairs: list[PairwiseCorrelation]
    computed_at: datetime      # UTC validated
```

Algorithm:
1. Accept list of tickers + OHLCV DataFrames (daily close prices)
2. Align on common trading dates (inner join on date index)
3. Compute log daily returns per ticker
4. For each pair, compute Pearson correlation on overlapping returns
5. Skip pairs with < 30 overlapping days (return `float("nan")`)
6. Return `CorrelationMatrix` with all valid pairs

```python
def compute_correlation_matrix(
    price_data: dict[str, pd.DataFrame],
    min_overlap: int = 30,
) -> CorrelationMatrix:
    """Compute pairwise Pearson correlation from daily close prices.
    Reference: standard portfolio theory (Markowitz 1952).
    """
```

Data source: OHLCV prices from existing `market_data.fetch_daily_prices()` for
watchlist tickers (accessed via `Repository.get_watchlist()`).

**Modified files:**
- `models/__init__.py` — re-export `CorrelationMatrix`, `PairwiseCorrelation`
- `api/routes/analytics.py` — add `GET /api/analytics/correlation` endpoint
- `cli/outcomes.py` — add `outcomes correlation` subcommand

Feeds into FR-C5 position sizing: `correlation_with_portfolio` parameter uses the
average correlation of the candidate ticker with existing watchlist positions.

### Non-Functional Requirements

#### NFR-C1: No New Dependencies
All 7 items use only numpy, pandas, scipy, and existing project dependencies.

#### NFR-C2: No License Violation
Source repo (`virattt/ai-hedge-fund`) has no open-source license. All implementations
are written from scratch. Algorithms are reimplemented from textbook references, not
copied from source code.

#### NFR-C3: Backward Compatibility
- All items are additive — no existing behavior changed
- Weight redistribution for Hurst (FR-C1) changes scoring balance marginally
- All existing ~4,500 tests must pass without modification

#### NFR-C4: Graceful Degradation
- Hurst: returns None on insufficient data; scoring skips and renormalizes
- Performance metrics: returns None for ratios when < 30 trades
- Position sizing: defaults to Tier 4 (safest) on NaN/Inf IV
- Valuation: each model independently returns None; all four fail → omitted
- Correlation: NaN for pairs with < 30 overlapping days
- Constraints: empty violations list when all contracts are valid

#### NFR-C5: Architecture Compliance
- `indicators/hurst.py`: pandas in/out, no models, no API calls
- `analysis/performance.py`, `analysis/position_sizing.py`, `analysis/correlation.py`,
  `analysis/valuation.py`: imports `models/` only, no API calls, no I/O
- `agents/constraints.py`: imports `models/` only
- All agent prompt changes in `agents/prompts/` only

#### NFR-C6: No New Migration
All new data is computed on the fly or derived from existing tables.

## Success Criteria

| Metric | Target |
|--------|--------|
| Hurst exponent computed | >95% of tickers with 200+ bars |
| Sharpe/Sortino available | When >= 30 closed outcomes exist |
| Constraint violations caught | 100% of expired/illiquid contracts |
| Position size displayed | 100% of debate outputs (when IV available) |
| Correlation matrix computable | Any 2+ tickers with 30+ overlapping days |
| Valuation signal produced | >50% of tickers with FD data |
| Existing test suite passes | 100% (zero regressions) |
| New test count | ~100 tests across 10 test files |

## Constraints & Assumptions

### Constraints
- All implementations from scratch (no license on source repo)
- `analysis/` module: no API calls, typed models in/out
- Agent prompts: <1500 tokens system prompt + appendix
- Weight sum in `INDICATOR_WEIGHTS` must equal 1.0 (import-time guard)

### Assumptions
- OHLCV data for Hurst computation already available in Phase 2 pipeline
- `MarketContext.atm_iv_30d` or `hv_yang_zhang` available for position sizing
- Financial Datasets fields (`fd_*`) available on `MarketContext` for valuation — 6 new
  `fd_*` fields required (see FR-C6); depends on FinancialDatasets epic #393
- Watchlist tickers accessible via existing `Repository` for correlation

## Out of Scope

- **VaR computation** — position sizing is vol-regime bucketing, not full VaR
- **Real-time correlation streaming** — batch computation only
- **Valuation backtesting** — historical fair value tracking over time
- **Multi-provider LLM expansion** — identified in audit but deferred to separate epic
- **Visual workflow builder** — identified in audit (React Flow pattern) but massive effort; deferred
- **LLM cost tracking** — identified in audit but lower priority than these 7 items

## Delivery Issues

| Issue | Description | Wave | New Files | Modified Files | Est. Tests |
|-------|-------------|------|-----------|----------------|------------|
| 1 | Hurst Exponent Indicator (FR-C1) | 1 | 1 | 4 | ~10 |
| 2 | Performance Metrics (FR-C2) | 1 | 2 | 4 | ~10 |
| 3 | Persona Agent Framing (FR-C3) | 1 | 0 | 6 | ~6 |
| 4 | Constraint Pre-Check (FR-C4) | 2 | 1 | 4 | ~12 |
| 5 | Position Sizing Algorithm (FR-C5) | 2 | 1 | 4 | ~12 |
| 6 | Multi-Methodology Valuation (FR-C6) | 3 | 2 | 6 | ~20 |
| 7 | Portfolio Correlation Matrix (FR-C7) | 3 | 2 | 3 | ~15 |
| **Total** | | | **9** | **31** | **~85** |

### Wave Structure

**Wave 1 (Foundation)** — Issues 1, 2, 3 (parallel, ~2 days)
All three are independent with zero internal dependencies.

**Wave 2 (Analysis Core)** — Issues 4, 5 (after Wave 1, ~3 days)
Both modify `agents/orchestrator.py` and `agents/_parsing.py`. Issue 5 benefits from
the `analysis/` package init created in Issue 2.

**Wave 3 (Data-Heavy)** — Issues 6, 7 (after Wave 2, ~5 days)
Issue 6 (Valuation) depends on Financial Datasets data availability and has the largest
surface area. Issue 7 (Correlation) feeds correlation data into Issue 5's position sizing.

### Dependency Graph

```
Wave 1 (parallel):
  Issue 1 (Hurst)         ── standalone
  Issue 2 (Perf Metrics)  ── standalone
  Issue 3 (Personas)      ── standalone

Wave 2 (after Wave 1):
  Issue 4 (Constraints)   ── standalone
  Issue 5 (Pos Sizing)    ── standalone (Issue 6 enhances later)

Wave 3 (after Wave 2):
  Issue 6 (Valuation)     ── standalone (depends on FD data availability)
  Issue 7 (Correlation)   ── feeds into Issue 5 (correlation param)
```

## References

- Mandelbrot, B. & Wallis, J. (1969) — Rescaled range analysis for Hurst exponent
- Sharpe, W. (1966) "Mutual Fund Performance" — Sharpe ratio
- Sortino, F. & van der Meer, R. (1991) — Sortino ratio (downside deviation)
- Damodaran, A. (2012) "Investment Valuation" — DCF, residual income, relative valuation
- Buffett, W. — Owner earnings concept (annual letters)
- Hull, J. (2018) "Options, Futures, and Other Derivatives" — risk-neutral pricing
