# CLAUDE.md — Scoring Module

## Purpose

Percentile-rank normalization, composite scoring, direction classification, and
contract filtering with Greeks dispatch. Receives pre-fetched data from services
layer and indicator output — **no API calls**.

## Files

| File | Purpose | Pattern |
|------|---------|---------|
| `normalization.py` | Percentile-rank normalize raw indicators across universe | Cherry-pick from v3 |
| `composite.py` | Weighted geometric mean composite score per ticker | Cherry-pick from v3 |
| `direction.py` | BULLISH / BEARISH / NEUTRAL classification | Cherry-pick from v3 |
| `contracts.py` | Greeks dispatch, delta targeting, contract selection | **Rewrite** (not cherry-pick) |
| `__init__.py` | Re-exports public API with `__all__` | Standard |

## Architecture Rules

- `normalization.py` and `composite.py` operate on `IndicatorSignals` typed model — NOT `dict[str, float]`
- `direction.py` returns `SignalDirection` enum — never raw strings
- `contracts.py` calls `pricing/dispatch.py` for ALL Greeks — never computes locally, never imports `bsm.py` or `american.py` directly
- All thresholds come from `ScanConfig` / `PricingConfig` — no hardcoded magic numbers in function bodies (module-level constants serve as defaults only)
- No API calls — receives pre-fetched data from services layer
- No `print()` — use `logging` module only
- No raw dicts for structured data — always typed models

## Key Constants

### Indicator Weights (composite.py)
18 indicators across 6 categories, individual weights sum to 1.0:

| Category | Indicators | Weights |
|----------|-----------|---------|
| Oscillators | rsi, stochastic_rsi, williams_r | 0.08, 0.05, 0.05 |
| Trend | adx, roc, supertrend | 0.08, 0.05, 0.05 |
| Volatility | atr_pct, bb_width, keltner_width | 0.05, 0.05, 0.04 |
| Volume | obv, ad, relative_volume | 0.05, 0.05, 0.05 |
| Moving Averages | sma_alignment, vwap_deviation | 0.08, 0.05 |
| Options | iv_rank, iv_percentile, put_call_ratio, max_pain_distance | 0.06, 0.06, 0.05, 0.05 |

### Inverted Indicators (normalization.py)
Higher raw value = worse signal, flipped after normalization:
`bb_width`, `atr_pct`, `relative_volume`, `keltner_width`

### Direction Thresholds (direction.py)
- `ADX_TREND_THRESHOLD = 15.0` (below → NEUTRAL)
- `RSI_OVERBOUGHT = 70.0`, `RSI_OVERSOLD = 30.0`
- `SMA_BULLISH_THRESHOLD = 0.5`, `SMA_BEARISH_THRESHOLD = -0.5`

### Contract Thresholds (contracts.py)
- Delta: primary [0.20, 0.50], fallback [0.10, 0.80], target 0.35
- DTE: [30, 60] days
- Liquidity: OI >= 100, volume >= 1, spread/mid <= 10%
- Zero-bid exemption: bid=0/ask>0 skips spread check

## v3 → Arena Field Name Mapping

| v3 name | Arena name | Notes |
|---------|-----------|-------|
| `atr_percent` | `atr_pct` | Field renamed |
| `obv_trend` | `obv` | Simplified |
| `ad_trend` | `ad` | Simplified |
| `stoch_rsi` | `stochastic_rsi` | Full name |
| `max_pain` | `max_pain_distance` | More descriptive |
| `implied_volatility` | `market_iv` | Clarifies source |
| `score` | `composite_score` | On TickerScore |
| `signals: dict[str, float]` | `signals: IndicatorSignals` | Typed model |

## Integration Rules

| Can Import From | Cannot Import From |
|----------------|-------------------|
| `models/` (enums, config, scan, options) | `services/` (no API calls) |
| `pricing/dispatch` (Greeks, IV) | `pricing/bsm`, `pricing/american` (use dispatch) |
| `math`, `logging`, `decimal` | `indicators/` (wrong direction) |
| | `agents/`, `reporting/`, `cli` |

## What Claude Gets Wrong — Scoring-Specific

- Don't return `dict[str, float]` from normalization/composite — use `IndicatorSignals`
- Don't import `bsm_greeks` directly — always go through `pricing/dispatch.py`
- Don't hardcode thresholds in function bodies — accept config parameters with module-level defaults
- Don't use v3 field names (`atr_percent`, `stoch_rsi`, etc.) — use Arena names from `IndicatorSignals`
- Don't forget the zero-bid exemption in contract filtering
- Don't compute Greeks locally in contracts.py — dispatch handles BAW vs BSM routing
- Don't use `Optional[X]` — use `X | None`
- Don't skip the floor value (1.0) in composite scoring — `log(0)` is undefined
- Don't mix up `ScanConfig` (direction thresholds) and `PricingConfig` (contract thresholds)
