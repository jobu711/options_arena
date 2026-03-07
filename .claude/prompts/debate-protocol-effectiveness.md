<role>
You evaluate multi-agent systems by marginal contribution,
not headcount. More agents != better: redundant agents dilute
signal, and computational cost must justify informational value.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/agents/orchestrator.py — run_debate(), synthesize_verdict()}}
{{src/options_arena/agents/prompts/ — trend_agent.py, contrarian_agent.py}}
{{Inline prompts in: volatility.py, flow_agent.py, fundamental_agent.py, risk.py}}
{{src/options_arena/agents/_parsing.py — PROMPT_RULES_APPENDIX, build_cleaned_*()}}
{{src/options_arena/models/analysis.py — ExtendedTradeThesis, agreement scores}}
{{data from: ai_theses — per-agent JSON outputs (debate_protocol='v2' for all current)}}
{{data from: contract_outcomes — actual P&L at T+1, T+5, T+10, T+20}}
{{data from: recommended_contracts — entry price, composite score, direction}}

### Protocol (6 agents, 4 phases)
Phase 1 (parallel): Trend + Volatility + Flow + Fundamental
  - Flow/Fundamental always run; OpenBB enrichment is optional input, not gate
Phase 2 (sequential): Risk (risk_agent_v2 instance, receives all Phase 1 outputs)
Phase 3 (sequential): Contrarian (skipped if >=2 Phase 1 failures — selection bias)
Phase 4 (algorithmic): synthesize_verdict() — weighted vote, agreement score,
  confidence capping when agreement < 0.4

### Current Weights (AGENT_VOTE_WEIGHTS)
trend: 0.25, volatility: 0.20, flow: 0.20, fundamental: 0.15,
risk: 0.15, contrarian: 0.05
Note: Volatility excluded from direction voting (no direction field).
Contrarian has lowest weight. These are NOT equal weights.
</context>

<task>
Measure each agent's marginal contribution to outcome prediction.
If agents are noise, simplify. If all add value, reweight to
reflect their individual predictive power.
</task>

<instructions>
### Phase 1 — Agent Value
For each of the 6 agents independently:
- Does its direction predict actual price movement? (vs T+1, T+5, T+10, T+20)
- Does its confidence correlate with outcome magnitude?
- Compute per-agent Brier score across all holding periods
- Volatility has no direction — evaluate via strategy accuracy and IV forecast

Then ablate: recompute synthesize_verdict() excluding one agent
at a time. Which removal hurts most (most valuable)? Which has
no effect (noise)? Which removal improves outcomes (active harm)?

### Phase 2 — System Dynamics
- Win rate by agreement score bands (unanimous vs split vs contested)
- Contrarian dissent accuracy when dissent_confidence > 0.6
- Does confidence capping (agreement < 0.4) help or hurt?
- Token cost and latency per agent vs alpha contributed
- Correlation between enrichment_ratio and debate quality

### Phase 3 — Optimize
Given Phase 1-2 findings:
- Propose data-driven weights replacing current AGENT_VOTE_WEIGHTS
- Should contrarian weight (currently 0.05) increase when consensus is very high?
- Backtest: current weights vs optimized weights across all holding periods
- If agents should be dropped, show the evidence
- Consider whether Volatility should gain direction voting capability
</instructions>

<constraints>
- Flow/Fundamental run with or without OpenBB — stratify analysis by enrichment level
- Contrarian skipped on >=2 Phase 1 failures — account for selection bias
- Minimum 30 outcomes per agent before concluding
- Don't recommend removing an agent without strong evidence
- ai_theses stores legacy bull_json/bear_json/rebuttal_json columns but these are
  NULL for current protocol — ignore them, use flow_json/fundamental_json/risk_v2_json/contrarian_json
</constraints>

<output_format>
1. **Agent Ranking** — Predictive power per agent (IC, Brier, ablation impact)
2. **System Analysis** — Agreement dynamics, enrichment impact, cost-benefit
3. **Optimized Weights** — Proposed weight vector with backtest comparison vs current
4. **Simplification** — Agents to drop or restructure (if any) with evidence
</output_format>
