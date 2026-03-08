# CLAUDE.md — Scoring Module

## Purpose
Percentile-rank normalization, composite scoring, direction classification, and
contract filtering with Greeks dispatch. Receives pre-fetched data — **no API calls**.

## Files
| File | Purpose |
|------|---------|
| `normalization.py` | Percentile-rank normalize raw indicators across universe |
| `composite.py` | Weighted geometric mean composite score per ticker |
| `direction.py` | BULLISH / BEARISH / NEUTRAL classification |
| `contracts.py` | Greeks dispatch, delta targeting, contract selection |
| `__init__.py` | Re-exports public API |

## Architecture Rules
- Operates on `IndicatorSignals` typed model — NOT `dict[str, float]`
- `direction.py` returns `SignalDirection` enum — never raw strings
- `contracts.py` calls `pricing/dispatch.py` for ALL Greeks — never imports `bsm.py`/`american.py`
- All thresholds from `ScanConfig`/`PricingConfig` — no hardcoded magic numbers in function bodies

## Key Constants

### Indicator Weights (19 indicators, sum to 1.0)
Oscillators: rsi(0.07), stochastic_rsi(0.05), williams_r(0.05).
Trend: adx(0.07), roc(0.03), supertrend(0.05), macd(0.05).
Volatility: atr_pct(0.05), bb_width(0.05), keltner_width(0.04).
Volume: obv(0.05), ad(0.05), relative_volume(0.05).
Moving Avg: sma_alignment(0.07), vwap_deviation(0.05).
Options: iv_rank(0.06), iv_percentile(0.06), put_call_ratio(0.05), max_pain_distance(0.05).

### Inverted Indicators
Higher raw = worse signal, flipped after normalization: `bb_width`, `atr_pct`, `keltner_width`.
`relative_volume` is NOT inverted — high rel vol = institutional attention.

### Composite Score
- Direction-agnostic "options interest level". Range [1.0, 100.0]; 0.0 = no data
- Floor value 0.5 in geometric mean — `log(0)` is undefined
- Phase 3 recomputes after options indicators populated

### Direction Thresholds
`ADX_TREND_THRESHOLD=15.0` (below→NEUTRAL), `RSI_OVERBOUGHT=70.0`, `RSI_OVERSOLD=30.0`,
`SMA_BULLISH_THRESHOLD=0.5`, `SMA_BEARISH_THRESHOLD=-0.5`, `ROC_THRESHOLD=5.0`.

### Contract Thresholds
Delta: primary [0.20, 0.50], fallback [0.10, 0.80], target 0.35.
DTE: [30, 365]. Liquidity: OI>=100, volume>=1, spread/mid<=30%. Zero-bid exemption: bid=0/ask>0 skips spread check.

## What Claude Gets Wrong — Scoring-Specific
1. Don't return `dict[str, float]` — use `IndicatorSignals`
2. Don't import `bsm_greeks` directly — use `pricing/dispatch`
3. Don't hardcode thresholds in function bodies — use config parameters
4. Don't use v3 field names (`atr_percent`, `stoch_rsi`) — use Arena names
5. Don't forget the zero-bid exemption in contract filtering
6. Don't compute Greeks locally in `contracts.py` — dispatch handles routing
7. Don't skip the floor value (0.5) in composite scoring
8. Don't mix up `ScanConfig` (direction) and `PricingConfig` (contracts)
