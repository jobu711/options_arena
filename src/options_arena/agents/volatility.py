"""Volatility agent for Options Arena AI debate.

Assesses whether implied volatility is mispriced and recommends vol-specific
strategies. Receives bull and bear arguments via ``DebateDeps`` to incorporate
directional context. Output is a structured ``VolatilityThesis``.

Architecture rules:
- No inter-agent imports (never imports bull.py, bear.py, or risk.py).
- model=None at init; actual model passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_volatility_thesis,
)
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT
from options_arena.models import VolatilityThesis

logger = logging.getLogger(__name__)

volatility_agent: Agent[DebateDeps, VolatilityThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=VolatilityThesis,
    retries=2,
)


@volatility_agent.system_prompt(dynamic=True)
async def volatility_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the volatility system prompt, injecting bull/bear arguments if available.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up bull and bear arguments from deps. Arguments are wrapped in delimiters
    to prevent instruction bleed.
    """
    base = VOLATILITY_SYSTEM_PROMPT
    if ctx.deps.bull_response is not None:
        base += (
            f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.bull_response.argument}\n<<<END_BULL_ARGUMENT>>>"
        )
    if ctx.deps.bear_response is not None:
        base += (
            f"\n\n<<<BEAR_ARGUMENT>>>\n{ctx.deps.bear_response.argument}\n<<<END_BEAR_ARGUMENT>>>"
        )
    return base


@volatility_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: VolatilityThesis,
) -> VolatilityThesis:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_volatility_thesis(output)
