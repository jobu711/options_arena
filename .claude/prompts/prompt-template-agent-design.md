# New PydanticAI Debate Agent — Prompt Template for Options Arena

> Use this template when adding a new AI debate agent (e.g., volatility, contrarian, flow) to the `agents/` module.

## The Template

```xml
<role>
You are a PydanticAI agent architect specializing in structured LLM debate systems
for options analysis. You design agents that produce type-safe, validator-constrained
JSON outputs from Groq-hosted Llama 3.3 70B, coordinated by a never-raises
orchestrator. Your work matters because a poorly designed agent silently corrupts
downstream verdict confidence and risk assessment.
</role>

<context>
### Architecture Boundaries (agents/)

| Rule | Detail |
|------|--------|
| No inter-agent imports | Each agent file is self-contained. Only orchestrator imports from all agents. |
| No data fetching | Agents receive pre-fetched data via DebateDeps. No httpx, yfinance, or service imports. |
| No pricing imports | Greeks arrive pre-computed on OptionContract.greeks. Never import from pricing/. |
| Typed boundaries | Agent outputs are AgentResponse or custom Pydantic models. Never raw dicts. |
| Logging only | logging.getLogger(__name__) — never print(). |
| Never-raises orchestrator | run_debate() catches all errors and returns data-driven fallback. |

### DebateDeps Dataclass (current shape)

```python
@dataclass
class DebateDeps:
    """Injected into every agent via RunContext[DebateDeps]."""
    context: MarketContext
    ticker_score: TickerScore
    contracts: list[OptionContract]
    opponent_argument: str | None = None       # For bear (receives bull's text)
    bear_counter_argument: str | None = None   # For bull rebuttal
    bull_response: AgentResponse | None = None # For risk agent
    bear_response: AgentResponse | None = None # For risk agent
    {{NEW_DEPS_FIELDS}}                        # Add fields for your agent here
```

### Shared Constants (from _parsing.py)

- `PROMPT_RULES_APPENDIX` — confidence calibration scale + data anchors + citation rules.
  Appended to all agent prompts.
- `strip_think_tags(text)` — removes <think>...</think> blocks, returns original if empty.
- `build_cleaned_agent_response(output)` — strips think tags from AgentResponse fields.
- `build_cleaned_trade_thesis(output)` — strips think tags from TradeThesis fields.

### Token Budget

- System prompt: < 1500 tokens (including PROMPT_RULES_APPENDIX at ~200 tokens)
- Context block (MarketContext rendered as key-value text): ~300-500 tokens
- Total agent input: < 2500 tokens per run

### Existing Agent Reference: bull.py (v2.1)

{{BULL_PY_SOURCE}}
<!-- Read src/options_arena/agents/bull.py for the gold-standard pattern -->

### Existing Output Types

- `AgentResponse` — general-purpose: agent_name, direction, confidence, argument, key_points, risks_cited, contracts_referenced, model_used
- `TradeThesis` — risk-specific: ticker, direction, confidence, summary, bull_score, bear_score, key_factors, risk_assessment, recommended_strategy

### Orchestrator Flow

Bull → Bear → [Rebuttal + Volatility parallel] → Risk → DebateResult
Your agent slots in at: {{ORCHESTRATOR_POSITION}}
</context>

<task>
Design and implement a new "{{AGENT_NAME}}" debate agent for Options Arena with:

1. A system prompt constant with version header (# VERSION: v1.0)
2. A module-level Agent[DebateDeps, {{OUTPUT_TYPE}}] instance
3. A system_prompt decorator (static or dynamic based on whether runtime deps are needed)
4. An output_validator that strips <think> tags via shared helpers
5. Any new fields needed on DebateDeps
6. Integration point in orchestrator.py (where it runs in the sequence)
7. A 6-test scaffold covering: valid output, confidence bounds, think-tag stripping,
   TestModel override, fallback behavior, and timeout handling

The agent must: {{AGENT_GOAL_DESCRIPTION}}
</task>

<instructions>
### Decision Tree

1. **Output type selection**:
   - Does the agent produce a directional argument (bullish/bearish)? → Use `AgentResponse`
   - Does the agent produce a risk/strategy assessment? → Use `TradeThesis`
   - Does the agent need fields not on either? → Define a new frozen Pydantic model in
     `models/analysis.py` with `confidence` field_validator and add to `__init__.py` re-exports

2. **Prompt type selection**:
   - Does the prompt depend on runtime data (other agents' outputs)? → `@agent.system_prompt(dynamic=True)` with `async def(ctx: RunContext[DebateDeps])`
   - Is the prompt fully static? → `@agent.system_prompt` bare decorator with `def() -> str`

3. **Confidence anchor design**:
   - Map composite score ranges to confidence bounds in the prompt
   - If your agent sees conflicting signals, force confidence <= 0.5
   - Use PROMPT_RULES_APPENDIX for the standard calibration scale

4. **Think-tag stripping strategy**:
   - For AgentResponse output: use `build_cleaned_agent_response(output)`
   - For TradeThesis output: use `build_cleaned_trade_thesis(output)`
   - For custom output type: create a new `build_cleaned_{{agent}}_output()` helper in
     `_parsing.py` using `strip_think_tags()` on each string field, then return a
     new frozen instance via model constructor (NOT mutation — models are frozen)

5. **Orchestrator integration**:
   - Add your agent's run call in orchestrator.py at the correct position
   - Wrap in `asyncio.wait_for(timeout=config.agent_timeout)`
   - Accumulate RunUsage: `total_usage = ... + new_result.usage()`
   - On failure: log warning, continue with degraded result (never crash)
</instructions>

<constraints>
1. Use model=None at Agent init; pass GroqModel at agent.run(model=...) time — this enables TestModel override in tests.
2. Never import from other agent files (bull.py, bear.py, risk.py). Import only from _parsing.py and models/.
3. Never fetch data — no httpx, yfinance, or service imports. All data arrives via DebateDeps.
4. Never import from pricing/ — Greeks arrive pre-computed on OptionContract.greeks.
5. Wrap every agent.run() call in asyncio.wait_for(timeout=config.agent_timeout).
6. Always add @agent.output_validator that delegates to a shared helper from _parsing.py — never inline stripping logic, never use ModelRetry.
7. Use logging.getLogger(__name__) — never print().
8. Use X | None syntax — never Optional[X] or typing imports.
9. Use dynamic=True on system_prompt decorator when the prompt depends on runtime deps (opponent arguments, other agent outputs).
10. Set models.ALLOW_MODEL_REQUESTS = False at module level in every test file.
11. Use string concatenation (not str.format()) when injecting LLM-generated text into prompts — LLM text contains curly braces that crash format().
12. Add RichHandler(markup=False) in any CLI rendering — agent text contains [TICKER] brackets that crash Rich markup.
13. Bull → Bear must be sequential. Parallel execution only for independent agents (rebuttal + volatility). Risk always runs last.
14. Return structured Pydantic model from agent — never dict, dict[str, Any], or dict[str, float].
15. Include # VERSION: v1.0 comment above every prompt constant.
</constraints>

<examples>
### Example 1: Bull Agent (gold-standard static→dynamic pattern)

```python
# File: src/options_arena/agents/bull.py
"""Bull agent for Options Arena AI debate."""

import logging
from pydantic_ai import Agent, RunContext
from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX, DebateDeps, build_cleaned_agent_response,
)
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

# VERSION: v2.1
BULL_SYSTEM_PROMPT = (
    """You are a bullish options analyst. Your job is to make the strongest \
possible case FOR entering a long options position on the given ticker.

You will receive market data in a structured context block. You MUST:
1. Cite specific indicator values (RSI, IV rank, MACD signal) from the context
2. Reference the target strike price, delta, and DTE from the context
...
"""
    + PROMPT_RULES_APPENDIX  # Appends confidence calibration + citation rules
)

bull_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,              # Overridden per-run with GroqModel or TestModel
    deps_type=DebateDeps,
    output_type=AgentResponse,
    retries=2,
)

@bull_agent.system_prompt(dynamic=True)  # dynamic=True for rebuttal injection
async def bull_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    base = BULL_SYSTEM_PROMPT
    if ctx.deps.bear_counter_argument is not None:
        # String concatenation, NOT str.format() — LLM text has curly braces
        base += _REBUTTAL_PREFIX + ctx.deps.bear_counter_argument + _REBUTTAL_SUFFIX
    return base

@bull_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps], output: AgentResponse,
) -> AgentResponse:
    """Strip <think> tags via shared helper — never inline, never ModelRetry."""
    return build_cleaned_agent_response(output)
```

### Example 2: TestModel test pattern

```python
# File: tests/unit/agents/test_bull.py
import pytest
from pydantic_ai import models
from pydantic_ai.models.test import TestModel
from options_arena.agents.bull import bull_agent
from options_arena.agents._parsing import DebateDeps

# Prevents accidental real API calls
models.ALLOW_MODEL_REQUESTS = False

@pytest.mark.asyncio
async def test_bull_agent_produces_valid_output(mock_deps: DebateDeps) -> None:
    with bull_agent.override(model=TestModel()):
        result = await bull_agent.run("Analyze AAPL", deps=mock_deps)
    assert isinstance(result.output, AgentResponse)
    assert 0.0 <= result.output.confidence <= 1.0
    assert result.output.direction.value == "bullish"

@pytest.mark.asyncio
async def test_bull_agent_with_custom_output(mock_deps: DebateDeps) -> None:
    test_model = TestModel(custom_output_args={
        "agent_name": "bull", "direction": "bullish", "confidence": 0.75,
        "argument": "Strong momentum.", "key_points": ["RSI trending up"],
        "risks_cited": ["Earnings next week"],
        "contracts_referenced": ["AAPL 190C 2026-04-18"], "model_used": "test",
    })
    with bull_agent.override(model=test_model):
        result = await bull_agent.run("test", deps=mock_deps)
    assert result.output.confidence == 0.75
```
</examples>

<output_format>
Deliver these files in order:

1. **System prompt constant** — `{{AGENT_NAME}}_SYSTEM_PROMPT` string with:
   - # VERSION: v1.0 comment above
   - Role definition (2-3 sentences)
   - Required behaviors (numbered list)
   - JSON schema for output type
   - Rules (citation, confidence bounds, no hallucination)
   - + PROMPT_RULES_APPENDIX concatenation

2. **Agent definition** — Module-level `Agent[DebateDeps, OutputType]` with:
   - model=None, deps_type=DebateDeps, output_type=..., retries=2

3. **system_prompt decorator** — Static or dynamic based on decision tree

4. **output_validator** — Delegates to shared _parsing.py helper

5. **DebateDeps additions** — New fields (if any) with type annotations and defaults

6. **Orchestrator integration** — Where in the flow, timeout wrapping, usage accumulation

7. **Test scaffold** (6 tests):
   - test_{{agent}}_produces_valid_output
   - test_{{agent}}_confidence_bounds
   - test_{{agent}}_strips_think_tags
   - test_{{agent}}_with_test_model_override
   - test_{{agent}}_fallback_on_timeout
   - test_orchestrator_with_{{agent}}_failure
</output_format>
```

## Quick-Reference Checklist

- [ ] `model=None` at Agent init (not `model="groq:..."`)
- [ ] `@agent.output_validator` delegates to `_parsing.py` shared helper
- [ ] `asyncio.wait_for(timeout=config.agent_timeout)` on every `agent.run()`
- [ ] `dynamic=True` on system_prompt if prompt depends on runtime deps
- [ ] `# VERSION: v1.0` comment above prompt constant
- [ ] `models.ALLOW_MODEL_REQUESTS = False` in every test file
- [ ] No imports from other agent files, services, or pricing
- [ ] String concatenation (not `.format()`) for injecting LLM text into prompts

## When to Use This Template

**Use when:**
- Adding a new debate agent role (volatility analyst, sector specialist, etc.)
- Extending an existing agent with a fundamentally different output type
- Building a specialized agent for a new analysis dimension (flow, fundamentals)

**Do not use when:**
- Modifying an existing agent's prompt text (just edit the constant directly)
- Adding a new field to an existing output type (use Template 5: Model Design)
- Working on the orchestrator's fallback logic (that's orchestrator-internal)
