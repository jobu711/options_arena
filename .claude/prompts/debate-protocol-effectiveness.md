<role>
You evaluate multi-agent systems by marginal contribution,
not headcount. More agents != better: redundant agents dilute
signal, and computational cost must justify informational value.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/agents/orchestrator.py — run_debate_v2(), synthesize_verdict()}}
{{All v2 agent prompt templates}}
{{src/options_arena/models/analysis.py — ExtendedTradeThesis, agreement scores}}
{{data from: ai_theses — v2 debates with per-agent JSON outputs}}
{{data from: contract_outcomes — actual P&L results}}

### v2 Protocol
Phase 1 (parallel): Trend + Volatility + [Flow + Fundamental if enriched]
Phase 2 (sequential): Risk_v2 (receives Phase 1 outputs)
Phase 3 (sequential): Contrarian (skipped if >=2 Phase 1 failures)
Phase 4 (algorithmic): synthesize_verdict() — weighted vote, agreement score,
  confidence capping when agreement < 0.4
</context>

<task>
Measure each agent's marginal contribution to outcome prediction.
If agents are noise, simplify. If all add value, reweight to
reflect their individual predictive power.
</task>

<instructions>
### Phase 1 — Agent Value
For each agent independently:
- Does its direction predict actual price movement? (vs T+5, T+10)
- Does its confidence correlate with outcome magnitude?
- Compute per-agent Brier score

Then ablate: recompute synthesize_verdict() excluding one agent
at a time. Which removal hurts most (most valuable)? Which has
no effect (noise)? Which removal improves outcomes (active harm)?

### Phase 2 — System Dynamics
- Win rate by agreement score bands (unanimous vs split)
- Contrarian dissent accuracy when dissent_confidence > 0.6
- Does confidence capping (agreement < 0.4) help or hurt?
- Token cost and latency per agent vs alpha contributed

### Phase 3 — Optimize
Given Phase 1-2 findings:
- Propose data-driven weights for synthesize_verdict()
- Should contrarian weight increase when consensus is very high?
- Backtest: current equal weights vs optimized weights
- If agents should be dropped, show the evidence
</instructions>

<constraints>
- Flow/Fundamental only run with OpenBB enrichment — analyze separately
- Contrarian skipped on >=2 Phase 1 failures — account for selection bias
- Minimum 30 outcomes per agent before concluding
- Don't recommend removing an agent without strong evidence
</constraints>

<output_format>
1. **Agent Ranking** — Predictive power per agent (IC, Brier, ablation impact)
2. **System Analysis** — Agreement dynamics, cost-benefit per agent
3. **Optimized Weights** — Proposed weight vector with backtest comparison
4. **Simplification** — Agents to drop (if any) with supporting evidence
</output_format>
