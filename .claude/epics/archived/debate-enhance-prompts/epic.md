---
name: debate-enhance-prompts
status: completed
created: 2026-02-24T21:49:24Z
updated: 2026-02-25T09:53:05Z
completed: 2026-02-25T09:53:05Z
progress: 100%
prd: .claude/prds/ai-debate-enhance.md
parent: .claude/epics/ai-debate-enhance/epic.md
github: https://github.com/jobu711/options_arena/issues/76
---

# Epic 2: Enhance Agent Prompts — Calibration, Strategy, Citations

## Overview

Agent prompts lack confidence calibration, data citation rules, and strategy guidance.
Agents produce arbitrary confidence values and vague references to data. This epic adds
a shared prompt appendix for calibration and citation, a strategy decision tree for the
Risk agent, and extracts the duplicated output validator into a shared helper.

## Scope

### PRD Requirements Covered
FR-A3 (Confidence Calibration), FR-A4 (Strategy Decision Tree), FR-A5 (Data Citations)

### The Elegant Approach

**Shared constant, not copy-paste.** Create `PROMPT_RULES_APPENDIX` in `_parsing.py`
containing calibration scale + data anchors + citation rules. Each agent appends it to
their system prompt. One source of truth, one place to update.

**Deduplicate output validators.** Extract `build_cleaned_agent_response()` and
`build_cleaned_trade_thesis()` into `_parsing.py`. Each agent's `@output_validator`
becomes a 2-line delegation. Saves ~77 lines of identical code across 3 agents.

### Deliverables

**`src/options_arena/agents/_parsing.py`** — Add:

```python
# VERSION: v2.0
PROMPT_RULES_APPENDIX = """
Confidence calibration (MUST follow these guidelines):
- 0.0-0.2: Extremely weak case, minimal data support
- 0.2-0.4: Weak case, some data but significant contradictions
- 0.4-0.6: Moderate case, mixed signals in the data
- 0.6-0.8: Strong case, most indicators confirm thesis
- 0.8-1.0: Very strong case, overwhelming data support

Data anchors:
- If COMPOSITE SCORE < 40: your confidence MUST NOT exceed 0.5
- If COMPOSITE SCORE > 70 and direction matches: confidence MUST be at least 0.4
- If RSI contradicts your thesis direction: reduce confidence by at least 0.1

Data citation rules (MANDATORY):
- When referencing data, use the EXACT label and value from the context block.
- WRONG: "The RSI is showing strength" or "momentum is bullish"
- RIGHT: "RSI(14): 65.3 is above the 50 midpoint, confirming bullish momentum"
- WRONG: "Volatility is elevated"
- RIGHT: "IV RANK: 85.0 places current IV in the top 15% of its 52-week range"
- Every claim MUST cite at least one specific number from the context."""


def build_cleaned_agent_response(output: AgentResponse) -> AgentResponse:
    """Strip <think> tags from all text fields. Returns original if no tags found."""
    fields = [output.argument, *output.key_points, *output.risks_cited, *output.contracts_referenced]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return AgentResponse(
        agent_name=output.agent_name,
        direction=output.direction,
        confidence=output.confidence,
        argument=strip_think_tags(output.argument),
        key_points=[strip_think_tags(p) for p in output.key_points],
        risks_cited=[strip_think_tags(r) for r in output.risks_cited],
        contracts_referenced=[strip_think_tags(c) for c in output.contracts_referenced],
        model_used=output.model_used,
    )


def build_cleaned_trade_thesis(output: TradeThesis) -> TradeThesis:
    """Strip <think> tags from all text fields. Returns original if no tags found."""
    fields = [output.summary, output.risk_assessment, *output.key_factors]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return TradeThesis(
        ticker=output.ticker, direction=output.direction, confidence=output.confidence,
        summary=strip_think_tags(output.summary), bull_score=output.bull_score,
        bear_score=output.bear_score,
        key_factors=[strip_think_tags(f) for f in output.key_factors],
        risk_assessment=strip_think_tags(output.risk_assessment),
        recommended_strategy=output.recommended_strategy,
    )
```

**`src/options_arena/agents/bull.py`** — Append `PROMPT_RULES_APPENDIX` to prompt,
replace 29-line validator with:

```python
@bull_agent.output_validator
async def clean_think_tags(ctx: RunContext[DebateDeps], output: AgentResponse) -> AgentResponse:
    return build_cleaned_agent_response(output)
```

**`src/options_arena/agents/bear.py`** — Same pattern.

**`src/options_arena/agents/risk.py`** — Append `PROMPT_RULES_APPENDIX` + strategy tree:

```python
RISK_STRATEGY_TREE = """
Strategy selection decision tree:
- IF direction is "neutral" AND IV RANK > 70: recommend "iron_condor"
- IF direction is "neutral" AND IV RANK < 30: recommend "straddle"
- IF confidence > 0.7 AND IV RANK < 50: recommend "vertical"
- IF confidence 0.4-0.7 AND IV RANK > 50: recommend "calendar"
- IF confidence < 0.4 OR data is highly conflicting: recommend null
- IF both bull_score and bear_score > 6.0: recommend "strangle"
"""
```

Replace 25-line validator with 2-line delegation to `build_cleaned_trade_thesis()`.

### Tests (~6)
- `PROMPT_RULES_APPENDIX` is present in each agent's effective system prompt
- `RISK_STRATEGY_TREE` is in risk prompt only
- `build_cleaned_agent_response()` strips tags correctly
- `build_cleaned_trade_thesis()` strips tags correctly
- `build_cleaned_agent_response()` returns original when no tags
- Version headers intact on all prompts

### Verification Gate
```bash
uv run ruff check . --fix && uv run ruff format .
uv run pytest tests/ -v
uv run mypy src/ --strict
```

## Dependencies
- **Blocked by**: Epic 1 (prompts reference `COMPOSITE SCORE` from expanded context)
- **Blocks**: Epics 4, 5 (new agents will use shared appendix + validator helper)

## Key Decision
Strategy tree uses `SpreadType` enum values as string literals in the prompt. The LLM
outputs one of these exact strings, which maps to `TradeThesis.recommended_strategy`.
No new enum values needed — `SpreadType` already has all 6 strategies.

## Tasks Created
- [ ] #77 - Add shared prompt rules appendix and output validator helpers to _parsing.py (parallel: false)
- [ ] #78 - Update Bull agent — integrate shared appendix and deduplicate validator (parallel: true)
- [ ] #79 - Update Bear agent — integrate shared appendix and deduplicate validator (parallel: true)
- [ ] #80 - Update Risk agent — integrate appendix, strategy tree, and deduplicate validator (parallel: true)
- [ ] #81 - Write tests for shared helpers and prompt integration (parallel: false)

Total tasks: 5
Parallel tasks: 3 (#78, #79, #80 — after #77 completes)
Sequential tasks: 2 (#77 first, #81 last)
Estimated total effort: 9 hours
