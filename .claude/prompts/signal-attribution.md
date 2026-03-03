<role>
You are a quantitative finance researcher specializing in
signal attribution, factor analysis, and alpha decomposition.
You've built scoring systems for hedge funds and know that
most indicators are noise — only 5-10 signals carry real
predictive power. You're ruthless about separating signal
from noise using statistical rigor.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/scoring/normalize.py}}
{{src/options_arena/scoring/composite.py — INDICATOR_WEIGHTS dict}}
{{src/options_arena/scoring/direction.py}}
{{src/options_arena/models/scan.py — IndicatorSignals (58 fields)}}
{{data from: recommended_contracts + contract_outcomes tables}}
{{data from: normalization_metadata table}}

### Current Scoring Architecture
- **58 indicators** across 9 families (momentum, volatility, flow, Greeks, etc.)
- **Static weights** in `INDICATOR_WEIGHTS` dict — never change
- **Percentile rank normalization** — each raw signal → 0-100 rank within scan universe
- **Composite score** = weighted sum of normalized indicators
- **Direction** = threshold-based classification from composite + momentum signals

### Available Outcome Data
For each scan, we have:
- 58 normalized indicator values per ticker (0-100 percentile)
- Recommended contract entry price (strike, mid, delta, IV)
- Stock return at T+1, T+5, T+10, T+20
- Contract return at T+1, T+5, T+10, T+20
- Win/loss classification per holding period
- Normalization distribution metadata (min, max, median, std per indicator per scan)
</context>

<task>
Determine which of the 58 indicators in IndicatorSignals
actually predict profitable options signals — and which are noise
that dilutes the composite score.

The current static weights were chosen by domain intuition,
not by empirical performance. Now that we have outcome data,
we can measure what actually works.

This analysis directly drives the next version of
INDICATOR_WEIGHTS in scoring/composite.py.
</task>

<instructions>
Take your time. This is the most impactful analysis possible
for the scoring engine — getting weights right is pure alpha.

### Framework 1 — Univariate Signal Power
For each of the 58 indicators independently:
- Compute rank-biserial correlation between indicator percentile
  and binary win/loss outcome
- Compute information coefficient (IC): Spearman correlation
  between indicator value and forward return
- Test at multiple horizons (T+1, T+5, T+10, T+20) —
  some indicators are fast (momentum), some slow (fundamentals)
- Compute IC stability: standard deviation of IC across scan dates
  (unstable IC = unreliable signal)
- Rank all 58 by IC * IC_stability (Sharpe-like metric for signals)

### Framework 2 — Multivariate Redundancy
Many indicators measure the same thing differently:
- RSI, Stochastic RSI, Williams %R — all momentum oscillators
- BB Width, ATR %, Keltner Width — all volatility range measures
- OBV, A/D, Relative Volume — all volume-based

For each correlated cluster:
- Compute pairwise correlation matrix
- Identify redundant indicators (correlation > 0.7)
- Keep only the highest-IC member of each cluster
- How many of the 58 are truly independent signals?

### Framework 3 — Conditional Attribution
Signal power likely varies by regime:
- In trending markets (ADX > 25): which indicators predict returns?
- In range-bound markets (ADX < 15): which indicators predict returns?
- In high-IV environments (IV Rank > 70): which indicators matter?
- In low-IV environments (IV Rank < 30): which indicators matter?
- Near earnings (DTE to earnings < 7): which fundamentals dominate?

For each regime:
- Recompute IC for all indicators
- Identify regime-dependent signals (strong in one, weak in another)
- Quantify the alpha from regime-adaptive weighting vs static weights

### Framework 4 — Direction-Specific Attribution
- Do the same indicators predict BULLISH wins vs BEARISH wins?
- Are some indicators only useful for one direction?
  (e.g., high RSI predicts bullish continuation but not bearish reversal)
- Should INDICATOR_WEIGHTS differ by direction?

### Framework 5 — Weight Optimization
Given Frameworks 1-4:
- Propose a new INDICATOR_WEIGHTS dict
- Compare static (current) vs optimized (proposed) weights
  using historical outcome data (backtest)
- Estimate the improvement in win rate and average return
- Consider regularization: don't overfit to small sample sizes
- Propose a minimum sample size before weights should be updated
</instructions>

<constraints>
- Minimum 50 outcome observations per indicator before claiming significance
- Report p-values for all correlation claims
- Distinguish between "statistically significant" and "economically meaningful"
- Flag any indicator with IC < 0.02 as "likely noise"
- If sample size is too small for regime-conditional analysis, say so
- Do not recommend removing indicators without strong evidence —
  a weakly predictive signal is still better than no signal
</constraints>

<output_format>
1. **Signal Power Rankings** — All 58 indicators ranked by IC * stability
2. **Recommended Weight Changes** — New INDICATOR_WEIGHTS dict with rationale
3. **Redundant Indicators** — Clusters where you'd drop members
4. **Regime-Dependent Findings** — Signals that only work in specific conditions
5. **Sample Size Warnings** — Where data is insufficient for conclusions
6. **Backtest Results** — Current vs proposed weights performance comparison
</output_format>
