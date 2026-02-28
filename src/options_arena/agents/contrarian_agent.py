"""Contrarian agent for Options Arena AI debate.

Adversarial stress-tester that challenges the consensus from all prior agents.
Runs in Phase 3 of the 6-agent protocol, after trend, volatility, flow,
fundamental, and risk agents have completed. Sees ALL prior outputs and
identifies weaknesses in the consensus direction.

Architecture rules:
- No inter-agent imports (never imports bull.py, bear.py, risk.py, etc.).
- model=None at init; actual GroqModel passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_contrarian_thesis,
)
from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.models import ContrarianThesis

logger = logging.getLogger(__name__)

contrarian_agent: Agent[DebateDeps, ContrarianThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=ContrarianThesis,
    retries=2,
)


@contrarian_agent.system_prompt(dynamic=True)
async def contrarian_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the contrarian system prompt, injecting all prior agent outputs.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest agent outputs from deps. Prior outputs are wrapped in
    delimiters to prevent instruction bleed from LLM-generated text.
    """
    base = CONTRARIAN_SYSTEM_PROMPT

    if ctx.deps.all_prior_outputs is not None:
        base += (
            "\n\n<<<PRIOR_AGENT_OUTPUTS>>>\n"
            + ctx.deps.all_prior_outputs
            + "\n<<<END_PRIOR_AGENT_OUTPUTS>>>"
        )
    return base


@contrarian_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: ContrarianThesis,
) -> ContrarianThesis:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_contrarian_thesis(output)
