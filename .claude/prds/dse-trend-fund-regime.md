---
name: dse-trend-fund-regime
description: "DSE Epic 3 — 15 trend/fundamental/regime indicators, universe-wide signals, Fundamental Agent"
status: backlog
created: 2026-02-28T10:22:58Z
parent: deep-signal-engine
---

# DSE-3: Trend, Fundamental & Regime

## Objective

Fill three critical analytical gaps: (1) add uncorrelated trend signals to reduce redundancy in the existing 7-indicator trend family, (2) build fundamental catalyst analytics around earnings, dividends, and short interest, (3) create the regime and macro layer that currently has zero coverage. Deploy a new Fundamental Agent. Add shared data fetchers for universe-wide reference tickers (^GSPC, ^VIX, ^VIX3M, sector ETFs).

**Branch**: `epic/dse-3-trend-fund-regime`
**Depends on**: Foundation (Phase 0) merged to master
**Parallel with**: DSE-1, DSE-2, DSE-4

---

## File Ownership

**This epic ONLY creates or modifies these files.**

| File | Action | Notes |
|------|--------|-------|
| `indicators/trend.py` | Extend | Multi-TF Alignment (#41), RSI Divergence (#42), ADX Exhaustion (#43) |
| `indicators/fundamental.py` | **Create** | Earnings EM vs IV (#48), Days to Earnings (#49), Short Interest (#50), Div Impact (#51), IV Crush History (#52) |
| `indicators/regime.py` | **Create** | Market Regime (#53), VIX Term Structure (#54), Risk-On/Off (#55), Sector Momentum (#56), RS vs SPX (#44), Correlation Regime Shift (#57), Volume Profile Skew (#46) |
| `services/market_data.py` | Extend | Shared fetchers for ^GSPC, ^VIX, ^VIX3M, HYG, LQD, sector ETFs |
| `agents/fundamental_agent.py` | **Create** | Fundamental Agent definition + prompt |
| `tests/unit/indicators/test_trend_ext.py` | **Create** | Extended trend indicator tests |
| `tests/unit/indicators/test_fundamental.py` | **Create** | Fundamental indicator tests |
| `tests/unit/indicators/test_regime.py` | **Create** | Regime indicator tests |

**Read-only imports** (do NOT modify):
- `models/enums.py` — `MarketRegime`, `CatalystImpact`
- `models/scan.py` — `IndicatorSignals` (populate fields, don't add fields)
- `models/analysis.py` — `FundamentalThesis`

---

## Indicators

### Trend & Momentum (4 new)

| # | Indicator | Function Name | Module | Formula | Priority |
|---|-----------|--------------|--------|---------|----------|
| 41 | **Multi-TF Trend Alignment** | `compute_multi_tf_alignment` | `trend.py` | Supertrend on weekly resampled data. Score: `daily_supertrend + weekly_supertrend` → {+2, 0, -2}. | P0 |
| 42 | **RSI-Price Divergence** | `compute_rsi_divergence` | `trend.py` | Detect price new high + RSI lower high (bearish) or price new low + RSI higher low (bullish). Rolling 20-bar window. Returns float: -1.0 (bearish), 0.0 (none), +1.0 (bullish). | P1 |
| 43 | **ADX Trend Exhaustion** | `compute_adx_exhaustion` | `trend.py` | `ADX_current - ADX_5_bars_ago`. Negative = trend losing steam. | P1 |
| 44 | **Relative Strength vs SPX** | `compute_rs_vs_spx` | `regime.py` | `ticker_return_20d / SPX_return_20d`. >1.0 = outperforming. Requires ^GSPC data. | P1 |

### Fundamental Context (5 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 48 | **Earnings Expected Move vs IV** | `compute_earnings_em_ratio` | `IV_expected_move / avg_earnings_actual_move` over past 4 quarters. >1.0 = IV overpricing earnings. | P0 |
| 49 | **Days to Earnings Impact** | `compute_earnings_impact` | `max(0, 1 - DTE_to_earnings/30)`. Near 1.0 when imminent. 0.0 when >30 days. | P0 |
| 50 | **Short Interest Ratio** | `compute_short_interest` | `short_interest / avg_daily_volume` — days to cover. From yfinance `info.shortRatio`. | P1 |
| 51 | **Dividend Ex-Date Impact** | `compute_div_impact` | `1.0` if ex-dividend within DTE of contract (early exercise risk for ITM calls), else `0.0`. | P1 |
| 52 | **Earnings IV Crush History** | `compute_iv_crush_history` | Avg IV drop on earnings over past 4 quarters. Uses HV as proxy (yfinance lacks historical IV). | P2 |

### Regime & Macro (5 new)

| # | Indicator | Function Name | Formula | Priority |
|---|-----------|--------------|---------|----------|
| 53 | **Market Regime Classifier** | `classify_market_regime` | SPX-based: `ADX_SPX + HV_20d_SPX + SMA_alignment_SPX` → 4 regimes: `TRENDING`, `MEAN_REVERTING`, `VOLATILE`, `CRISIS`. | P0 |
| 54 | **VIX Term Structure Regime** | `compute_vix_term_structure` | `VIX / VIX3M`. <0.9 = contango (complacency), >1.0 = backwardation (fear). Fallback: VIX absolute thresholds. | P0 |
| 55 | **Risk-On/Risk-Off Score** | `compute_risk_on_off` | Composite: VIX level (inverted) + HY spread proxy (HYG/LQD ratio) + SPX trend. Normalized 0-100. | P1 |
| 56 | **Sector Relative Momentum** | `compute_sector_momentum` | Sector ETF 20-day return vs SPX 20-day return. Uses sector → ETF mapping (XLF, XLK, XLE, etc.). | P1 |
| 57 | **Correlation Regime Shift** | `compute_correlation_regime_shift` | 60-day rolling corr(ticker, SPX) vs 252-day average. Spike = macro-driven. | P2 |

### Microstructure (1 new)

| # | Indicator | Function Name | Module | Formula | Priority |
|---|-----------|--------------|--------|---------|----------|
| 46 | **Volume Profile Skew** | `compute_volume_profile_skew` | `regime.py` | Distribution of equity volume across price range (10-bar). Positive skew = accumulation. | P2 |

**Total: 15 indicators (4 P0, 6 P1, 3 P2, 2 microstructure)**

---

## Key Implementation: Universe-Wide Signals

### Shared Data Fetchers (`services/market_data.py`)

Universe-wide indicators (#53, #54, #55) are computed **once per scan**, not per-ticker. Add cached fetchers:

```python
class UniverseData(BaseModel):
    """Cached reference data for universe-wide indicators. Fetched once per scan."""
    model_config = ConfigDict(frozen=True)

    spx_ohlcv: pd.DataFrame      # ^GSPC daily OHLCV
    vix_close: pd.Series          # ^VIX daily close
    vix3m_close: pd.Series | None # ^VIX3M daily close (may be unavailable)
    hyg_close: pd.Series          # HYG daily close
    lqd_close: pd.Series          # LQD daily close
    sector_etf_returns: dict[str, float]  # 20-day returns by sector ETF

async def fetch_universe_data(period: str = "1y") -> UniverseData:
    """Fetch all universe-wide reference data in one batch."""
    tickers = ["^GSPC", "^VIX", "^VIX3M", "HYG", "LQD",
               "XLF", "XLK", "XLE", "XLV", "XLI", "XLC",
               "XLY", "XLP", "XLB", "XLRE", "XLU"]
    # asyncio.gather all fetches, return UniverseData
```

### Sector ETF Mapping

```python
SECTOR_ETF_MAP: dict[str, str] = {
    "Technology": "XLK",
    "Financial Services": "XLF",
    "Healthcare": "XLV",
    "Energy": "XLE",
    "Industrials": "XLI",
    "Communication Services": "XLC",
    "Consumer Cyclical": "XLY",
    "Consumer Defensive": "XLP",
    "Basic Materials": "XLB",
    "Real Estate": "XLRE",
    "Utilities": "XLU",
}
```

### Compute Budget

- Universe-wide fetch: 16 tickers × 1 yfinance call each = ~5s (async batched)
- Market Regime: arithmetic on ^GSPC data = negligible
- VIX Term Structure: 1 division = negligible
- Risk-On/Off: 3 components combined = negligible
- Per-ticker regime indicators (#44, #56, #57): lightweight arithmetic
- Fundamental indicators: yfinance `info` dict access (already fetched) = negligible
- **Total epic compute impact: ~5-10s for universe fetch (amortized across all tickers)**

---

## IndicatorSignals Fields (populated by this epic)

```
multi_tf_alignment: float | None              # #41 — {-2, -1, 0, 1, 2}
rsi_divergence: float | None                  # #42 — {-1.0, 0.0, 1.0}
adx_exhaustion: float | None                  # #43
rs_vs_spx: float | None                       # #44
volume_profile_skew: float | None             # #46
earnings_em_ratio: float | None               # #48
days_to_earnings_impact: float | None         # #49
short_interest_ratio: float | None            # #50
div_ex_date_impact: float | None              # #51
iv_crush_history: float | None                # #52
market_regime: MarketRegime | None            # #53
vix_term_structure: float | None              # #54
risk_on_off_score: float | None               # #55
sector_relative_momentum: float | None        # #56
correlation_regime_shift: float | None        # #57
```

---

## Fundamental Agent

### Definition (`agents/fundamental_agent.py`)

New agent using `FundamentalThesis` output model (defined in Foundation).

**Role**: Contextualize trades with fundamental catalysts — earnings, dividends, short interest.

**Exclusive Indicators**: Earnings EM vs IV (#48), Days to Earnings Impact (#49), Short Interest (#50), IV Crush History (#52)

**Shared Indicators**: Dividend yield (existing), next earnings date (existing)

**Key Question**: "Are there fundamental catalysts that change the risk profile of this trade?"

**Fallback**: Data-driven: fundamental_score + earnings proximity + short interest thresholds.

### FundamentalThesis Output (defined in Foundation)

```python
class FundamentalThesis(BaseModel):
    model_config = ConfigDict(frozen=True)
    catalyst_impact: CatalystImpact        # POSITIVE / NEGATIVE / NEUTRAL
    confidence: float                      # [0.0, 1.0]
    earnings_risk_assessment: str
    iv_crush_risk: str
    short_squeeze_potential: str
    dividend_impact: str
    key_catalysts: list[str]               # >= 1
    model_used: str
```

### Prompt Structure

- **Earnings Event**: Days to earnings + Expected Move Ratio + IV Crush History
- **IV Crush Risk**: Historical crush magnitude + current IV level
- **Short Interest**: Days to cover + squeeze potential assessment
- **Dividend**: Ex-date proximity + early exercise risk for ITM calls
- **Catalyst Timeline**: When catalysts occur relative to option expiration

---

## Data Reality Checks

### #50 (Short Interest)
yfinance `info` dict includes `shortRatio` and `shortPercentOfFloat` for most tickers. Not guaranteed — needs `None` handling. Access pattern:
```python
info = ticker.info  # already fetched by services/market_data.py
short_ratio = info.get("shortRatio")  # float | None
```

### #52 (IV Crush History)
yfinance lacks historical IV time series. **Use HV as proxy**: compute 5-day HV around each of the past 4 earnings dates. The "crush" signal = HV spike before earnings + HV collapse after. Flag as P2 because the proxy is noisy.

### #54 (VIX3M)
^VIX3M may have sparse data on yfinance. **Fallback**: Use VIX absolute thresholds:
- VIX < 15 → complacency (equivalent to contango)
- 15-25 → normal
- 25-35 → elevated
- \>35 → crisis (equivalent to backwardation)

---

## Testing Requirements

### Unit Tests — Trend Extensions

1. **Multi-TF Alignment**: Weekly resample + Supertrend → verify {+2, 0, -2} output
2. **RSI Divergence**: Known divergence pattern → detect correctly; no divergence → 0.0
3. **ADX Exhaustion**: Rising ADX (positive), falling ADX (negative)

### Unit Tests — Fundamental

1. **Earnings Impact**: 0 days away → 1.0, 30 days → 0.0, 15 days → 0.5
2. **Earnings EM Ratio**: Mock past earnings moves + current IV → verify ratio
3. **Short Interest**: Missing data → None, valid data → correct ratio
4. **Div Impact**: Ex-date within DTE → 1.0, outside → 0.0

### Unit Tests — Regime

1. **Market Regime**: Mock SPX data for each of 4 regimes → correct classification
2. **VIX Term Structure**: Contango (ratio < 0.9), backwardation (> 1.0), fallback thresholds
3. **Risk-On/Off**: Full risk-on scenario → near 100, full risk-off → near 0
4. **Sector Momentum**: Outperforming vs underperforming sector
5. **RS vs SPX**: Ticker outperforming → >1.0, underperforming → <1.0

---

## Merge Boundaries — DO NOT TOUCH

- `indicators/iv_analytics.py` — DSE-1
- `indicators/volatility.py` — DSE-1
- `pricing/iv_surface.py` — DSE-1
- `indicators/flow_analytics.py` — DSE-2
- `pricing/greeks_extended.py` — DSE-2
- `indicators/options_specific.py` — DSE-2
- `scoring/` — DSE-4
- `agents/orchestrator.py` — DSE-4
- `agents/flow_agent.py` — DSE-2
- `agents/trend_agent.py` — DSE-4
- `agents/contrarian_agent.py` — DSE-4
- `models/` — Foundation only

---

## Dependencies

### From Foundation
- `IndicatorSignals` with 15 new optional fields
- `MarketRegime`, `CatalystImpact` enums
- `FundamentalThesis` model
- Config: `enable_fundamental: bool`, `enable_regime: bool`

### From Existing Code
- `indicators/oscillators.py` — existing RSI computation (for divergence detection)
- `indicators/trend.py` — existing ADX, Supertrend (for exhaustion, multi-TF)
- `services/market_data.py` — yfinance ticker info, OHLCV, earnings dates
- Existing earnings date fetch in `MarketContext`

### Cross-Epic (at Integration)
- DSE-4 consumes all 15 indicators for `trend_score`, `fundamental_score`, `regime_score`
- DSE-4 integrates Fundamental Agent into debate protocol Phase 1 (parallel)
- DSE-1 Expected Move (#36) used by Earnings EM Ratio (#48) — use `None` fallback until DSE-1 merges
- Universe data (^GSPC, ^VIX) may also be used by DSE-1 (#29 VIX Correlation) — no conflict since DSE-1 reads from `services/market_data.py`, this epic extends it
