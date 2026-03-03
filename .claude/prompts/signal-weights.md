<role>
You are a quantitative finance researcher specializing in scoring system
calibration. You balance empirical evidence against overfitting risk — small
samples demand regularization.
</role>

<context>
## Chain Position

**Prompt 3 of 3.** Prompt 1 ranked 58 indicators by IC, identified redundancy clusters.
Prompt 2 analyzed regime-conditional IC and direction asymmetry.
This prompt proposes updated `INDICATOR_WEIGHTS` based on that evidence.

## Current INDICATOR_WEIGHTS (scoring/composite.py)

```python
INDICATOR_WEIGHTS: dict[str, tuple[float, str]] = {
    "rsi": (0.08, "oscillators"), "stochastic_rsi": (0.05, "oscillators"),
    "williams_r": (0.05, "oscillators"),
    "adx": (0.08, "trend"), "roc": (0.05, "trend"), "supertrend": (0.05, "trend"),
    "atr_pct": (0.05, "volatility"), "bb_width": (0.05, "volatility"),
    "keltner_width": (0.04, "volatility"),
    "obv": (0.05, "volume"), "ad": (0.05, "volume"), "relative_volume": (0.05, "volume"),
    "sma_alignment": (0.08, "moving_averages"), "vwap_deviation": (0.05, "moving_averages"),
    "iv_rank": (0.06, "options"), "iv_percentile": (0.06, "options"),
    "put_call_ratio": (0.05, "options"), "max_pain_distance": (0.05, "options"),
}  # Sum = 1.0, validated at import time
```

Category totals: oscillators 0.18, trend 0.18, volatility 0.14, volume 0.15,
moving_averages 0.13, options 0.22. Composite = weighted geometric mean of
percentile-ranked indicators. Inverted: bb_width, atr_pct, relative_volume, keltner_width.

Output must be valid Python replacing the dict in `scoring/composite.py`.
Field names must exactly match `IndicatorSignals` fields.

Use `<scratchpad>` tags for chain-of-thought reasoning before presenting final results.
</context>

<data>
<!-- Paste Prompt 1 + 2 outputs, then backtest data:
GET /api/analytics/score-calibration?holding_days=5 → ScoreCalibrationBucket[]
GET /api/analytics/win-rate → WinRateResult[] -->

{{PASTE PROMPT 1+2 OUTPUTS + API RESPONSES HERE}}
</data>

<task>
### Step 1 — Weight Derivation
For each weighted indicator: use IC*Stability from Prompt 1 as primary input.
Adjust for redundancy (shift weight to cluster keeper). Note regime findings
from Prompt 2 but keep static weights (regime-adaptive is future work).

### Step 2 — DSE Promotion
Promote DSE indicators with IC*Stability > median of current 18, AND in a
different cluster than existing weighted indicators.

### Step 3 — Regularization
- Shrinkage: 70% IC-derived + 30% equal weights (James-Stein).
- Floor 0.02, ceiling 0.12. No category > 0.30 total. Renormalize to sum 1.0.

### Step 4 — Backtest Comparison
Estimate current vs proposed: win rate and avg return by score bucket.

### Step 5 — Update Threshold
Minimum sample size before updating weights in production.
</task>

<output_format>
Use `<scratchpad>` first, then present:

**Proposed INDICATOR_WEIGHTS** (valid Python dict):
```python
INDICATOR_WEIGHTS: dict[str, tuple[float, str]] = {
    "rsi": (0.09, "oscillators"),  # was 0.08, IC rank #3
    # ... all entries with # was X.XX comments for changes ...
}  # Sum = 1.0
```

**Change Summary:**

| Indicator | Current | Proposed | Delta | Rationale |
|---|---|---|---|---|
| rsi | 0.08 | 0.09 | +0.01 | Top IC in oscillators |
| iv_hv_spread | -- | 0.04 | +0.04 | Promoted, IC rank #5 |

**Backtest Comparison:**

| Metric | Current | Proposed | Delta |
|---|---|---|---|
| Overall Win Rate | 52% | 55% | +3% |
| Avg Return (T+5) | 2.1% | 3.0% | +0.9% |

**Category Distribution** (current vs proposed, no category > 0.30).
**Update Threshold** (min N before production update).
</output_format>

<constraints>
- Weights MUST sum to 1.0. No weight below 0.02 or above 0.12. No category > 0.30.
- Field names must exactly match IndicatorSignals (case-sensitive).
- Do not remove a weighted indicator unless |IC| < 0.01 AND redundant.
- Promoted DSE indicators must have IC evidence — never domain intuition alone.
- If sample < 500: conservative only (max 0.02 shift per indicator).
- Acknowledge overfitting risk; propose holdout validation strategy.
</constraints>
