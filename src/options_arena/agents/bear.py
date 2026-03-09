"""Bear agent for Options Arena AI debate.

Makes the strongest possible case AGAINST entering a long options position.
Receives the bull agent's argument via ``DebateDeps.opponent_argument`` and
counters its specific claims. Output is a structured ``AgentResponse`` with
direction "bearish".

Architecture rules:
- No inter-agent imports (never imports bull.py or risk.py).
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
from options_arena.agents.prompts.bear import BEAR_SYSTEM_PROMPT
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

bear_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=AgentResponse,
    retries=2,
)


@bear_agent.system_prompt(dynamic=True)
async def bear_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the bear system prompt, injecting the bull's argument if available.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest ``opponent_argument`` from deps. Bull argument is wrapped in
    ``<<<BULL_ARGUMENT>>>`` delimiters to prevent instruction bleed.
    """
    base = BEAR_SYSTEM_PROMPT
    if ctx.deps.opponent_argument is not None:
        base += f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.opponent_argument}\n<<<END_BULL_ARGUMENT>>>"
    return base


@bear_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: AgentResponse,
) -> AgentResponse:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_agent_response(output)
