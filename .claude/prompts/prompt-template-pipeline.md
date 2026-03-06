# Scan Pipeline Extension — Prompt Template for Options Arena

> Use this template when adding a new signal, filter, or data dimension to the 4-phase async scan pipeline in `scan/`.

## The Template

```xml
<role>
You are a pipeline architect specializing in Options Arena's 4-phase async scan
pipeline. You coordinate changes across 6+ files to add new signals atomically —
from indicator function through registry, model, weight, normalization, and
direction thresholds. Your work matters because a single mismatched field name
or raw-vs-normalized signal confusion silently produces wrong direction calls
for every ticker in the universe.
</role>

<context>
### 4-Phase Data Flow

```
Phase 1: Universe + OHLCV
  UniverseService → list[str] tickers
  MarketDataService → BatchOHLCVResult → dict[str, list[OHLCV]]
  Filter: len(data) >= config.ohlcv_min_bars (200)

Phase 2: Indicators + Scoring + Direction
  ohlcv_to_dataframe(list[OHLCV]) → pd.DataFrame
  compute_indicators(df, INDICATOR_REGISTRY) → IndicatorSignals (RAW values)
  score_universe(raw_signals) → list[TickerScore] (NORMALIZED 0-100 values)
  determine_direction(adx=RAW, rsi=RAW, sma=RAW) → SignalDirection

Phase 3: Liquidity Pre-filter + Options + Contracts
  Liquidity filter: avg_dollar_volume >= min, latest_close >= min
  Top-N by composite_score
  FredService.fetch_risk_free_rate() → float (ONCE for entire scan)
  For each top-N: fetch chains → recommend_contracts() → list[OptionContract]

Phase 4: Persist
  Repository.save_scan_run() + save_ticker_scores()
```

### Raw vs Normalized — THE CRITICAL DISTINCTION

```python
# RAW signals — direct indicator output (e.g., RSI = 62.5, ADX = 23.4)
raw_signals: dict[str, IndicatorSignals] = {}
for ticker, ohlcv_list in ohlcv_map.items():
    df = ohlcv_to_dataframe(ohlcv_list)
    raw_signals[ticker] = compute_indicators(df, INDICATOR_REGISTRY)

# NORMALIZED signals — percentile-ranked 0-100 across universe
scored = score_universe(raw_signals)  # TickerScore.signals = NORMALIZED

# Direction uses RAW values against ABSOLUTE thresholds
for ts in scored:
    raw = raw_signals[ts.ticker]
    ts.direction = determine_direction(
        adx=raw.adx or 0.0,        # RAW ADX vs threshold 15.0
        rsi=raw.rsi or 50.0,        # RAW RSI vs thresholds 30/70
        sma_alignment=raw.sma_alignment or 0.0,
        config=scan_config,
    )
```

### Phase Classification Decision Tree

- **OHLCV-based indicator** (uses price/volume history) → Phase 2
  - Computed from DataFrame columns: close, high, low, volume
  - Goes into INDICATOR_REGISTRY (14 entries currently)
  - Examples: RSI, ADX, BB Width, OBV

- **Chain-based indicator** (uses option chain data) → Phase 3
  - Requires ExpirationChain / OptionContract data
  - NOT in INDICATOR_REGISTRY — computed separately
  - Examples: put_call_ratio, max_pain_distance, iv_rank, iv_percentile

### IndicatorSpec Registry (14 OHLCV entries)

```python
INDICATOR_REGISTRY: list[IndicatorSpec] = [
    IndicatorSpec(field_name="rsi", func=rsi, input_shape=InputShape.CLOSE, ...),
    IndicatorSpec(field_name="stochastic_rsi", func=stoch_rsi, input_shape=InputShape.CLOSE, ...),
    # ... 12 more OHLCV-based entries
]
```

### Function Name ≠ Field Name (4 mismatches)

| Function Name | IndicatorSignals Field |
|---------------|----------------------|
| stoch_rsi | stochastic_rsi |
| atr_percent | atr_pct |
| obv_trend | obv |
| ad_trend | ad |

### INDICATOR_WEIGHTS (must sum to 1.0)

```python
INDICATOR_WEIGHTS: dict[str, float] = {
    "rsi": 0.08, "stochastic_rsi": 0.06, ...,  # Sum = 1.0
}
```

### Scoring Normalization

- `score_universe(raw_signals)` percentile-ranks each indicator 0-100 across the universe
- Some indicators are "inverted" (lower raw = better): bb_width, atr_pct, keltner_width
- `get_active_indicators()` detects universally-missing indicators and renormalizes weights
- Composite score = weighted sum of normalized (and possibly inverted) values

### Concurrency Control

```python
# Phase 3: Semaphore limits concurrent chain fetches
semaphore = asyncio.Semaphore(config.max_concurrent_requests)

async def _fetch_with_semaphore(ticker: str) -> OptionsResult:
    async with semaphore:
        chains = await options_data.fetch_chain_all_expirations(ticker)
        ...

results = await asyncio.gather(
    *[_fetch_with_semaphore(t) for t in top_n_tickers],
    return_exceptions=True,  # One failure never crashes batch
)
```

### Service Lifecycle

Pipeline does NOT create services. They are injected via constructor:
```python
class ScanPipeline:
    def __init__(self, settings, market_data, options_data, fred, universe, repository):
```
</context>

<task>
Add "{{NEW_SIGNAL_NAME}}" to the scan pipeline. This requires atomic changes across
6+ files to ensure the signal flows correctly from computation through scoring to
direction determination.

The signal: {{SIGNAL_DESCRIPTION}}
Phase classification: {{PHASE_2_OR_3}}
</task>

<instructions>
### 6-File Change Checklist

For a **Phase 2 (OHLCV-based)** signal:

1. **Indicator function** — `src/options_arena/indicators/{{category}}.py`
   - Implement the function following Template 3 (Indicator)
   - Return pd.Series with NaN warmup

2. **Registry entry** — `src/options_arena/scan/indicators.py`
   - Add IndicatorSpec to INDICATOR_REGISTRY
   - field_name must match IndicatorSignals field EXACTLY
   - Choose correct InputShape enum variant

3. **Model field** — `src/options_arena/models/scan.py`
   - Add `{{field_name}}: float | None = None` to IndicatorSignals

4. **Weight entry** — `src/options_arena/scoring/normalization.py`
   - Add to INDICATOR_WEIGHTS dict
   - Rebalance all weights so sum = 1.0
   - If inverted indicator (lower = better), add to INVERTED_INDICATORS set

5. **Direction thresholds** (if applicable) — `src/options_arena/scoring/direction.py`
   - If this signal affects direction determination, add threshold to
     determine_direction() and ScanConfig
   - Use RAW values, not normalized

6. **Tests** — `tests/unit/indicators/`, `tests/unit/scan/`, `tests/unit/scoring/`
   - Indicator unit tests (5-test scaffold from Template 3)
   - Registry dispatch test (compute_indicators produces non-None field)
   - Weight sum test (verify total = 1.0)
   - Integration test (full Phase 2 flow with mock OHLCV)

For a **Phase 3 (chain-based)** signal:

1. **Indicator function** — `src/options_arena/indicators/options_specific.py`
2. **Phase 3 computation** — `src/options_arena/scan/indicators.py` (compute_options_indicators)
3. **Model field** — `src/options_arena/models/scan.py` (IndicatorSignals)
4. **Weight entry** — `src/options_arena/scoring/normalization.py`
5. **Re-normalization** — Ensure Phase 3 re-normalizes after adding chain-based indicators
6. **Tests** — Include mock chain data

### Data Flow Verification

After implementing, trace the signal through the full pipeline:

```
RAW indicator value (e.g., 62.5)
  ↓ compute_indicators() — stored in raw_signals dict
  ↓ score_universe() — percentile-ranked to 0-100 NORMALIZED
  ↓ (if inverted: 100 - normalized)
  ↓ weighted sum → composite_score
  ↓ determine_direction() uses RAW value (NOT normalized)
```

Verify at each step that:
- Raw signals dict retains the original value
- Normalized signals on TickerScore are 0-100
- Direction logic uses raw values from the retained dict
- Weight sum equals 1.0 after rebalancing
</instructions>

<constraints>
1. Use InputShape enum variants (CLOSE, HLC, CLOSE_VOLUME, HLCV, VOLUME) — never raw strings like "series" or "dataframe".
2. Only 14 OHLCV-based indicators go in INDICATOR_REGISTRY. The 4 options-specific indicators need chain data, computed separately in Phase 3.
3. Never pass normalized signals (0-100 percentile) to determine_direction(). Direction uses RAW ADX/RSI/SMA values against absolute thresholds. Retain raw_signals dict separately.
4. Field names in registry must match IndicatorSignals fields exactly. Watch the 4 mismatches: stoch_rsi→stochastic_rsi, atr_percent→atr_pct, obv_trend→obv, ad_trend→ad.
5. Convert Decimal→float in ohlcv_to_dataframe(). OHLCV prices are Decimal; indicators expect float.
6. Never create services inside the pipeline — they are injected via constructor.
7. Call FredService.fetch_risk_free_rate() ONCE for the entire scan, not per ticker.
8. Fetch options chains only for top-N tickers that pass liquidity pre-filter — not for all scored tickers.
9. OptionContract.greeks is always None from services — Greeks are computed by recommend_contracts() via pricing/dispatch.py.
10. Use X | None syntax — never Optional[X].
11. Use ScanPhase StrEnum — never raw strings for phase identifiers.
12. CancellationToken is instance-scoped — never global.
13. Apply liquidity pre-filter before top-N cutoff — prevents expensive chain fetches for penny stocks.
14. TickerScore is NOT frozen (mutable) — direction can be updated after scoring. IndicatorSignals is also mutable.
</constraints>

<examples>
### Example 1: Phase 2 indicator flow (RSI)

```
1. indicators/oscillators.py: rsi(close, period=14) → pd.Series
2. scan/indicators.py: IndicatorSpec(field_name="rsi", func=rsi, input_shape=InputShape.CLOSE)
3. models/scan.py: IndicatorSignals.rsi: float | None = None
4. scoring/normalization.py: INDICATOR_WEIGHTS["rsi"] = 0.08
5. scoring/direction.py: determine_direction(rsi=raw.rsi or 50.0, ...)
   - RAW rsi > 70 → contributes to BULLISH signal
   - RAW rsi < 30 → contributes to BEARISH signal
6. Pipeline: raw_signals["AAPL"].rsi = 62.5 (RAW)
            scored[0].signals.rsi = 78.0 (NORMALIZED, percentile rank)
            determine_direction(rsi=62.5) — uses RAW
```

### Example 2: Phase 3 indicator flow (put_call_ratio)

```
1. indicators/options_specific.py: put_call_ratio_volume(calls_vol, puts_vol) → float
2. scan/indicators.py: compute_options_indicators() adds to IndicatorSignals
3. models/scan.py: IndicatorSignals.put_call_ratio: float | None = None
4. scoring/normalization.py: INDICATOR_WEIGHTS["put_call_ratio"] = 0.00
   (Currently zero weight — chain data not always available)
5. Pipeline Phase 3: computed from chain data, added to signals,
   Phase 3 re-normalization runs after chain-based indicators are added
```

### Example 3: Weight rebalancing calculation

```python
# Before: 14 indicators, sum = 1.0
# Adding "new_indicator" with target weight 0.06

# Scale factor: (1.0 - 0.06) / 1.0 = 0.94
# Multiply all existing weights by 0.94
# Add new entry: "new_indicator": 0.06

INDICATOR_WEIGHTS = {
    "rsi": 0.08 * 0.94,  # 0.0752 → round to 0.075
    # ... scale all others ...
    "new_indicator": 0.06,
}
# Verify: sum(weights.values()) ≈ 1.0
```
</examples>

<output_format>
Deliver in this order:

1. **6-file change checklist** with exact file paths and the specific change in each:
   ```
   [ ] src/options_arena/indicators/{{category}}.py — New function
   [ ] src/options_arena/scan/indicators.py — Registry entry
   [ ] src/options_arena/models/scan.py — IndicatorSignals field
   [ ] src/options_arena/scoring/normalization.py — Weight + inversion flag
   [ ] src/options_arena/scoring/direction.py — Threshold (if applicable)
   [ ] tests/ — Test files
   ```

2. **Data flow diagram** showing the signal at each pipeline stage:
   ```
   RAW value → normalized value → (inverted?) → weighted → composite → direction
   ```

3. **Weight rebalancing calculation** — show old weights, scale factor, new weights, sum verification

4. **Integration test assertions**:
   ```python
   # After full pipeline run:
   assert result.scores[0].signals.{{field_name}} is not None  # Field populated
   assert 0.0 <= result.scores[0].signals.{{field_name}} <= 100.0  # Normalized
   assert raw_signals["AAPL"].{{field_name}} != result.scores[0].signals.{{field_name}}  # Raw ≠ Normalized
   ```
</output_format>
```

## Quick-Reference Checklist

- [ ] Phase classification correct: OHLCV-based → Phase 2 registry, chain-based → Phase 3 separate
- [ ] Registry field_name matches IndicatorSignals field exactly (watch the 4 mismatches)
- [ ] Raw signals retained separately from normalized TickerScore.signals
- [ ] determine_direction() uses RAW values, not normalized
- [ ] INDICATOR_WEIGHTS sum = 1.0 after rebalancing
- [ ] Inverted indicators added to INVERTED_INDICATORS set
- [ ] Decimal→float conversion in ohlcv_to_dataframe()
- [ ] asyncio.Semaphore for Phase 3 concurrency control

## When to Use This Template

**Use when:**
- Adding a new signal/indicator to the scan pipeline
- Adding a new filter dimension (sector, market cap, liquidity threshold)
- Extending Phase 3 with new chain-based computations
- Modifying the scoring weights or normalization logic

**Do not use when:**
- Implementing the indicator function itself (use Template 3: Indicator)
- Adding a new pricing Greek (use Template 2: Pricing)
- Adding a new debate agent (use Template 1: Agent Design)
- Adding a new Pydantic model field (use Template 5: Model Design)
