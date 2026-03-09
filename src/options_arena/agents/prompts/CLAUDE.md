# CLAUDE.md — Agent Prompts (`agents/prompts/`)

## Purpose

Centralized prompt library for all 8 debate agent system prompts. Each file exports
a single `{AGENT}_SYSTEM_PROMPT` string constant used by the corresponding agent module.

## Files

| File | Exports | Agent Phase |
|------|---------|-------------|
| `bull.py` | `BULL_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `bear.py` | `BEAR_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `trend_agent.py` | `TREND_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `volatility.py` | `VOLATILITY_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `flow_agent.py` | `FLOW_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `fundamental_agent.py` | `FUNDAMENTAL_SYSTEM_PROMPT` | Phase 1 (parallel) |
| `risk.py` | `RISK_SYSTEM_PROMPT` | Phase 2 (sequential) |
| `contrarian_agent.py` | `CONTRARIAN_SYSTEM_PROMPT` | Phase 3 (sequential) |
| `__init__.py` | Re-exports all 8 constants | — |

## Conventions

### File Structure

Each prompt file follows this pattern:

```python
"""Module docstring describing the agent's role and signals."""

from options_arena.agents._parsing import PROMPT_RULES_APPENDIX

AGENT_SYSTEM_PROMPT = (
    """Prompt text here...\n\n"""
    + PROMPT_RULES_APPENDIX
)
```

### Rules

1. **One constant per file** — each file exports exactly one `*_SYSTEM_PROMPT` constant
2. **`PROMPT_RULES_APPENDIX` concatenation** — every prompt ends with the shared appendix
3. **Token budget** — each prompt must be < 8000 chars (approx 2000 tokens)
4. **No business logic** — prompt files contain only string constants and the appendix import
5. **No service/pricing imports** — only import from `_parsing.py`
6. **Version header** — include `# VERSION: vX.Y` comment in the prompt text
7. **Static only** — dynamic injection (opponent arguments, Phase 1 outputs) stays in agent modules

### Import Pattern

Consumers should import from the package:
```python
from options_arena.agents.prompts import BULL_SYSTEM_PROMPT
```

Or from submodules:
```python
from options_arena.agents.prompts.bull import BULL_SYSTEM_PROMPT
```

### What Stays in Agent Modules

- `_REBUTTAL_PREFIX` / `_REBUTTAL_SUFFIX` (bull.py — dynamic injection)
- `@system_prompt(dynamic=True)` decorators (bear, risk — runtime deps)
- `@output_validator` decorators (all agents — think-tag stripping)
- `Agent` instances and their configuration
