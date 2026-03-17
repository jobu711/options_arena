"""Flow agent for Options Arena AI debate.

Analyses options flow data -- gamma exposure (GEX), unusual activity, OI
concentration, and volume trends -- to produce a structured ``FlowThesis``.
Provides smart-money signal interpretation to complement the directional
bull/bear debate.

Architecture rules:
- No inter-agent imports (never imports bull.py, bear.py, risk.py, or volatility.py).
- model=None at init; actual model passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_flow_thesis,
)
from options_arena.agents.prompts.flow_agent import FLOW_SYSTEM_PROMPT
from options_arena.models import FlowThesis

logger = logging.getLogger(__name__)

flow_agent: Agent[DebateDeps, FlowThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=FlowThesis,
    retries=2,
)


@flow_agent.system_prompt(dynamic=True)
async def flow_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the flow system prompt, injecting bull/bear arguments if available.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up bull and bear arguments from deps. Arguments are wrapped in delimiters
    to prevent instruction bleed.
    """
    return FLOW_SYSTEM_PROMPT


@flow_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: FlowThesis,
) -> FlowThesis:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_flow_thesis(output)
