<role>
You are a calibration expert in probabilistic forecasting.
You know most AI systems are overconfident and that fixing
calibration is the fastest path to better decision-making.
</role>

<context>
{{CLAUDE.md from project root}}
{{src/options_arena/agents/prompts/ — all prompt templates}}
{{src/options_arena/models/analysis.py — AgentResponse, TradeThesis}}
{{PROMPT_RULES_APPENDIX — confidence calibration guidelines}}
{{data from: ai_theses table — debates with confidence scores}}
{{data from: contract_outcomes table — actual win/loss results}}

### Confidence System
- Each agent outputs confidence 0.0-1.0
- PROMPT_RULES_APPENDIX defines verbal anchors (0.6-0.8 = "strong case")
- Data anchors: COMPOSITE < 40 caps confidence at 0.5;
  RSI contradiction reduces by 0.1
- TradeThesis model_validator clamps confidence when scores
  contradict final direction
</context>

<task>
Audit every agent's confidence calibration against actual
outcomes. Are the agents well-calibrated, and are the prompt
rules producing the behavior they intended?
</task>

<instructions>
### Phase 1 — Measure Calibration
For each agent with sufficient outcome data:
- Bin confidence into deciles, compute actual win rate per bin
- Compute Brier score and mean calibration error
- Identify which agents and which bins are most miscalibrated
- Flag systematic patterns: overconfident bulls? underconfident bears?
  Risk agent confidence mapping to actual trade outcomes?

### Phase 2 — Test the Rules
For each rule in PROMPT_RULES_APPENDIX, test empirically:
- Is the rule being followed? (violation rate)
- Does following the rule improve calibration vs not?
- Is the TradeThesis clamping validator firing, and does it help?
- Are the verbal anchors producing the right prediction frequencies?

### Phase 3 — Fix What's Broken
For each calibration failure, propose the fix:
- Prompt wording change (show before/after text)
- Data anchor adjustment (tighter or looser bounds)
- Post-hoc scaling (Platt scaling if the problem is model-level,
  not prompt-level)
</instructions>

<constraints>
- Minimum 30 outcomes per bin before drawing conclusions
- Report confidence intervals on win rate estimates
- Separate v1 (3-agent) from v2 (6-agent) analysis
- Don't propose removing rules without showing they're harmful
</constraints>

<output_format>
1. **Calibration Table** — Per-agent Brier score, reliability by decile
2. **Rule Effectiveness** — Each rule's empirical impact (helps/hurts/neutral)
3. **Proposed Fixes** — Specific prompt or anchor changes with expected improvement
4. **Data Gaps** — Where sample size prevents conclusions
</output_format>
