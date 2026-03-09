"""Bull agent for Options Arena AI debate.

Makes the strongest possible case FOR entering a long options position.
Cites specific indicator values, strikes, expirations, and Greeks from the
context block. Output is a structured ``AgentResponse`` with direction "bullish".

Architecture rules:
- No inter-agent imports (never imports bear.py or risk.py).
- model=None at init; actual OllamaModel passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_agent_response,
)
from options_arena.agents.prompts.bull import BULL_SYSTEM_PROMPT
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

_REBUTTAL_PREFIX = """

The bear has countered your argument with these key points:
<<<BEAR_COUNTER>>>
"""

_REBUTTAL_SUFFIX = """<<<END_BEAR_COUNTER>>>

Provide a BRIEF rebuttal addressing the bear's strongest 2-3 points.
Do not repeat your original argument -- focus only on defending against the counter.
Keep this concise (3-5 sentences)."""

bull_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=AgentResponse,
    retries=2,
)


@bull_agent.system_prompt(dynamic=True)
async def bull_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the bull system prompt, appending rebuttal instructions when active.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run. When
    ``ctx.deps.bear_counter_argument`` is set (rebuttal mode), appends
    rebuttal instructions with the bear's key points. Otherwise returns
    the base prompt unchanged.
    """
    base = BULL_SYSTEM_PROMPT
    if ctx.deps.bear_counter_argument is not None:
        base += _REBUTTAL_PREFIX + ctx.deps.bear_counter_argument + _REBUTTAL_SUFFIX
    return base


@bull_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: AgentResponse,
) -> AgentResponse:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_agent_response(output)
