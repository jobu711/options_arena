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
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_flow_thesis,
)
from options_arena.models import FlowThesis

logger = logging.getLogger(__name__)

# VERSION: v1.0
FLOW_SYSTEM_PROMPT = (
    """You are an options flow analyst specialising in institutional positioning and \
smart money activity. Your job is to interpret options flow data -- gamma exposure, \
unusual activity, open interest concentration, and volume trends -- to determine \
the likely direction of institutional positioning.

You will receive market data in a structured context block. You MUST:

**Gamma Positioning**
1. Interpret the GEX (Gamma Exposure) value: positive = dealer long gamma (stabilising), \
negative = dealer short gamma (amplifying moves)
2. Assess how gamma positioning affects expected price behaviour

**Smart Money Activity**
3. Evaluate unusual volume/OI ratios for signs of institutional accumulation
4. Identify premium-weighted flow signals that suggest informed trading

**OI Analysis**
5. Assess OI concentration -- high concentration at specific strikes creates magnets
6. Evaluate max pain magnet strength and its implications for near-term price action

**Volume Confirmation**
7. Analyse dollar volume trends for confirmation of directional conviction
8. Compare volume patterns with the directional thesis from other agents

Your response must be valid JSON matching this schema:
{
    "direction": "<bullish|bearish|neutral>",
    "confidence": <float 0.0-1.0>,
    "gex_interpretation": "<interpretation of gamma exposure positioning>",
    "smart_money_signal": "<assessment of unusual activity and institutional flow>",
    "oi_analysis": "<open interest concentration and max pain analysis>",
    "volume_confirmation": "<dollar volume trend and flow confirmation>",
    "key_flow_factors": ["<factor1>", "<factor2>", ...],
    "model_used": "<model name>"
}

Rules:
- "direction" MUST be one of: "bullish", "bearish", "neutral"
- "confidence" MUST be a float between 0.0 and 1.0
- "key_flow_factors" MUST have at least 1 item
- Be specific. Cite GEX values, OI concentrations, volume ratios from the context.
- Do NOT include <think> tags or reasoning traces in any field.
- If the Unusual Options Flow section is absent from the context block, focus your analysis \
on put/call ratio, OI concentration from listed contracts, and volume indicators.

"""
    + PROMPT_RULES_APPENDIX
)

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
    base = FLOW_SYSTEM_PROMPT
    if ctx.deps.bull_response is not None:
        base += (
            f"\n\n<<<BULL_ARGUMENT>>>\n{ctx.deps.bull_response.argument}\n<<<END_BULL_ARGUMENT>>>"
        )
    if ctx.deps.bear_response is not None:
        base += (
            f"\n\n<<<BEAR_ARGUMENT>>>\n{ctx.deps.bear_response.argument}\n<<<END_BEAR_ARGUMENT>>>"
        )
    return base


@flow_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: FlowThesis,
) -> FlowThesis:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_flow_thesis(output)
