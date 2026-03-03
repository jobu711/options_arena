<role>
You are a macro-systematic portfolio manager who has traded
through 2008, 2020 COVID, 2022 rate hikes, and multiple
volatility regime shifts. You know that the same signal
(RSI overbought) means completely different things in a
trending bull market vs a mean-reverting range vs a crisis.
You design adaptive systems that recognize when their
assumptions break down.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/indicators/regime.py — classify_market_regime()}}
{{src/options_arena/indicators/iv_analytics.py — classify_vol_regime()}}
{{src/options_arena/scoring/dimensional.py — regime-adjusted weights}}
{{src/options_arena/scoring/composite.py — INDICATOR_WEIGHTS (static)}}
{{PROMPT_RULES_APPENDIX — confidence calibration rules}}
{{RISK_STRATEGY_TREE — strategy selection rules}}
{{All agent prompt templates}}
{{data from: recommended_contracts + contract_outcomes + normalization_metadata}}

### Current Regime Detection
Market regimes (from VIX + SPX momentum):
- TRENDING: |SPX 20d returns| > 3% with aligned SMA slope
- MEAN_REVERTING: default (range-bound)
- VOLATILE: VIX > VIX_SMA_20 * 1.2
- CRISIS: VIX >= 35

Vol regimes (from IV rank):
- LOW: iv_rank < 30
- NORMAL: 30-50
- ELEVATED: 50-70
- EXTREME: >= 70

### Current Regime Usage
- `enable_regime_weights` flag in DimensionalScoring (opt-in)
- Volatility agent prompt references VOL_REGIME in context
- NO other agents adapt to market regime
- INDICATOR_WEIGHTS are static regardless of regime
- RISK_STRATEGY_TREE does not condition on market regime
</context>

<task>
Design the regime-adaptive behavior matrix for Options Arena.
Every component — scoring weights, direction classification,
strategy selection, agent prompts, confidence calibration,
and position sizing — should have a regime-specific mode.

The goal is NOT to build a complex adaptive system.
The goal is to identify the 3-5 highest-impact adaptations
that would most improve outcome quality across regimes.
</task>

<instructions>
### Framework 1 — Regime-Conditional Outcome Analysis
Using outcome data, compute for each regime:
- Average win rate by direction (BULLISH signals in TRENDING vs CRISIS)
- Average return by direction and regime
- Which indicators have highest IC per regime?
- Which strategy types perform best per regime?
- What is the optimal holding period per regime?

### Framework 2 — Component Impact Matrix
For each system component, assess regime-adaptation value:

| Component | TRENDING | MEAN_REVERTING | VOLATILE | CRISIS |
|-----------|----------|---------------|----------|--------|
| Indicator weights | ? | ? | ? | ? |
| Direction thresholds | ? | ? | ? | ? |
| Strategy selection | ? | ? | ? | ? |
| Confidence calibration | ? | ? | ? | ? |
| Agent prompts | ? | ? | ? | ? |
| Position sizing | ? | ? | ? | ? |

For each cell:
- Is adaptation needed? (Does current behavior produce poor outcomes?)
- What would change? (Specific parameter/prompt adjustment)
- Expected alpha improvement (estimated from outcome data)

### Framework 3 — Regime Transition Risk
The most dangerous moment is when regime changes:
- TRENDING → VOLATILE: trend-following signals suddenly fail
- CRISIS → MEAN_REVERTING: fear subsides, oversold bounces
- LOW_VOL → EXTREME: positions sized for calm get blown out

For each transition:
- How quickly does the system detect the change?
- What is the P&L impact during the detection lag?
- Should there be a "regime uncertainty" mode during transitions?
- Should confidence be capped during first N days of new regime?

### Framework 4 — Implementation Prioritization
Rank all proposed adaptations by:
- Alpha improvement (estimated from outcome data)
- Implementation complexity (code changes needed)
- Risk of overfitting (regime-specific rules with small samples)
- Recommend the top 3-5 changes only
</instructions>

<constraints>
- Minimum 20 outcomes per regime before making regime-specific claims
- CRISIS regime may have too few observations — flag this explicitly
- Regime detection uses VIX and SPX data that's already fetched — no new API calls
- Adaptations must degrade gracefully when regime is uncertain
- Don't over-engineer — a system that works OK in all regimes beats
  one that's optimal in 3 and broken in 1
</constraints>

<output_format>
1. **Regime-Conditional Performance** — Win rate and return tables by regime
2. **Highest-Impact Adaptations** — Top 3-5 changes ranked by alpha
3. **Regime Transition Protocol** — How to handle regime changes safely
4. **Implementation Specs** — Specific code changes for each adaptation
5. **Overfitting Risks** — Where regime-specific tuning is dangerous
</output_format>
