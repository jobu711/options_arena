"""Fundamental agent for Options Arena AI debate.

Assesses fundamental catalysts (earnings, IV crush, short interest, dividends)
and their impact on options positioning. Output is a structured
``FundamentalThesis`` with direction and catalyst impact assessment.

Architecture rules:
- No inter-agent imports (never imports bull.py, bear.py, risk.py, etc.).
- model=None at init; actual model passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_fundamental_thesis,
)
from options_arena.agents.prompts.fundamental_agent import FUNDAMENTAL_SYSTEM_PROMPT
from options_arena.models import FundamentalThesis

logger = logging.getLogger(__name__)

fundamental_agent: Agent[DebateDeps, FundamentalThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=FundamentalThesis,
    retries=2,
)


@fundamental_agent.system_prompt(dynamic=True)
async def fundamental_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the fundamental system prompt, injecting bull/bear arguments if available.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up bull and bear arguments from deps. Arguments are wrapped in delimiters
    to prevent instruction bleed.
    """
    base = FUNDAMENTAL_SYSTEM_PROMPT
    if ctx.deps.bull_response is not None:
        base += (
            f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.bull_response.argument}\n<<<END_BULL_ARGUMENT>>>"
        )
    if ctx.deps.bear_response is not None:
        base += (
            f"\n\n<<<BEAR_ARGUMENT>>>\n{ctx.deps.bear_response.argument}\n<<<END_BEAR_ARGUMENT>>>"
        )
    return base


@fundamental_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: FundamentalThesis,
) -> FundamentalThesis:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_fundamental_thesis(output)
