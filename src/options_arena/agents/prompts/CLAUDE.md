# CLAUDE.md — Agent Prompts (`agents/prompts/`)

## Purpose

Centralized prompt library for desk, recommendation, and synthesis agent system prompts.
Each file exports a single prompt string constant used by the corresponding agent module.

## Files

| File | Exports | Agent Mode |
|------|---------|------------|
| `desk_trend.py` | `DESK_TREND_PROMPT` | Interactive desk query |
| `desk_volatility.py` | `DESK_VOLATILITY_PROMPT` | Interactive desk query |
| `desk_flow.py` | `DESK_FLOW_PROMPT` | Interactive desk query |
| `desk_fundamental.py` | `DESK_FUNDAMENTAL_PROMPT` | Interactive desk query |
| `desk_risk.py` | `DESK_RISK_PROMPT` | Interactive desk query |
| `desk_contrarian.py` | `DESK_CONTRARIAN_PROMPT` | Interactive desk query |
| `desk_research.py` | `DESK_RESEARCH_PROMPT` | Interactive desk query |
| `recommend_trend.py` | `RECOMMEND_TREND_PROMPT` | Recommendation assessment |
| `recommend_volatility.py` | `RECOMMEND_VOLATILITY_PROMPT` | Recommendation assessment |
| `recommend_flow.py` | `RECOMMEND_FLOW_PROMPT` | Recommendation assessment |
| `recommend_fundamental.py` | `RECOMMEND_FUNDAMENTAL_PROMPT` | Recommendation assessment |
| `recommend_risk.py` | `RECOMMEND_RISK_PROMPT` | Recommendation assessment |
| `recommend_contrarian.py` | `RECOMMEND_CONTRARIAN_PROMPT` | Recommendation assessment |
| `synthesis.py` | `SYNTHESIS_SYSTEM_PROMPT` | Synthesis agent |
| `__init__.py` | Re-exports all constants | -- |

## Conventions

### File Structure

```python
"""Module docstring describing the agent's role and signals."""

# Desk prompts: conversational, NO PROMPT_RULES_APPENDIX
DESK_TREND_PROMPT = """You are a trend and momentum desk analyst. ..."""

# Recommendation prompts: structured output, with PROMPT_RULES_APPENDIX
from options_arena.agents._parsing import PROMPT_RULES_APPENDIX
RECOMMEND_TREND_PROMPT = """...\n\n""" + PROMPT_RULES_APPENDIX

# Synthesis prompt: with PROMPT_RULES_APPENDIX
SYNTHESIS_SYSTEM_PROMPT = """...\n\n""" + PROMPT_RULES_APPENDIX
```

### Rules

1. **One constant per file** — each file exports exactly one prompt constant
2. **Desk prompts**: conversational, NO `PROMPT_RULES_APPENDIX`
3. **Recommendation + Synthesis prompts**: end with `PROMPT_RULES_APPENDIX` concatenation
4. **Token budget** — each prompt must be < 8000 chars (approx 2000 tokens)
5. **No business logic** — prompt files contain only string constants and the appendix import
6. **No service/pricing imports** — only import from `_parsing.py`
7. **Static only** — dynamic injection (learned patterns, tuned weights) stays in agent modules

### Import Pattern

Consumers should import from the package:
```python
from options_arena.agents.prompts import DESK_TREND_PROMPT
```

Or from submodules:
```python
from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT
```

### What Stays in Agent Modules

- `@system_prompt(dynamic=True)` decorators (runtime deps injection)
- `@output_validator` decorators (think-tag stripping)
- `Agent` instances and their configuration
