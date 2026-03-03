<role>
You are a quantitative finance researcher specializing in regime-conditional
signal analysis. Indicator predictive power shifts across market regimes — a
signal that works in trends fails in ranges.
</role>

<context>
## Chain Position

**Prompt 2 of 3.** Prompt 1 (signal-attribution.md) produced signal power rankings,
redundancy clusters, and the list of top signals marked "Keep? Yes."
This prompt analyzes how those signals behave across regimes and directions.
Prompt 3 (signal-weights.md) will use these findings to propose new weights.

## Direction Algorithm (scoring/direction.py)

1. **ADX gate**: ADX < 15.0 -> NEUTRAL. 2. **RSI**: >70 strong bullish (+2),
>50 mild (+1), <30 strong bearish (+2), <50 mild bearish (+1).
3. **SMA alignment**: >0.5 bullish (+1), <-0.5 bearish (+1). 4. Tie: SMA sign decides.

## Regime Definitions

| Regime | Condition | Field |
|---|---|---|
| Trending | adx >= 25 | adx |
| Ranging | adx < 15 | adx |
| Transition | 15 <= adx < 25 | adx |
| High-IV | iv_rank >= 70 | iv_rank |
| Low-IV | iv_rank < 30 | iv_rank |
| Near-Earnings | days_to_earnings_impact <= 7 | days_to_earnings_impact |
| High-Vol Regime | vol_regime >= 70 | vol_regime |

Use `<scratchpad>` tags for chain-of-thought reasoning before presenting final results.
</context>

<data>
<!-- Paste Prompt 1 output (signal rankings + cluster assignments), then paste
the same outcome dataset including adx, iv_rank, days_to_earnings_impact,
vol_regime columns for regime segmentation, plus rc.direction for direction splits. -->

{{PASTE PROMPT 1 OUTPUT + QUERY RESULTS HERE}}
</data>

<task>
Analyze how top signals from Prompt 1 perform across regimes and directions.
Focus only on indicators marked "Keep? Yes" in Prompt 1.

### Step 1 — Regime-Conditional IC
Recompute IC (Spearman vs T+5 contract return) within each regime segment.
Identify **regime-dependent signals**: |IC_regime1 - IC_regime2| > 0.05.

### Step 2 — Direction-Specific Attribution
Split by `direction` (bullish vs bearish). Recompute IC per direction.
Identify **asymmetric signals**: useful for one direction but not the other.

### Step 3 — Regime Alpha Estimate
Compare IC using static weights vs regime-best weights. Is the improvement
large enough to justify complexity?
</task>

<output_format>
Use `<scratchpad>` first, then present:

**Regime-Conditional IC Matrix** (bold cells where |regime IC - All IC| > 0.05):

| Indicator | All | Trending | Ranging | Trans | High-IV | Low-IV | Near-Earn |
|---|---|---|---|---|---|---|---|
| rsi | 0.08 | 0.12 | 0.02 | 0.07 | 0.06 | 0.09 | 0.03 |
| sma_alignment | 0.09 | 0.15 | 0.01 | 0.06 | 0.07 | 0.10 | 0.04 |

**Direction-Specific IC** (flag asymmetry > 0.05):

| Indicator | All | Bullish | Bearish | Asymmetry |
|---|---|---|---|---|
| rsi | 0.08 | 0.11 | 0.03 | 0.08 |

Then: **Regime-Dependent Signals** (recommended action per regime),
**Regime Alpha Estimate** (static vs adaptive IC improvement),
**Sample Sizes** (N per regime cell, flag < 30 as "N/A (N=X)").
</output_format>

<constraints>
- Min 30 observations per regime cell before reporting IC. Below: "N/A (N=X)."
- Require |delta IC| > 0.05 for "regime-dependent" label.
- Acknowledge if total sample makes regime splits unreliable.
- Note coverage % for days_to_earnings_impact and vol_regime (may be sparse).
</constraints>
