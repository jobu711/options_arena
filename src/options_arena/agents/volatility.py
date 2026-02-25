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
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_volatility_thesis,
)
from options_arena.models import VolatilityThesis

logger = logging.getLogger(__name__)

# VERSION: v1.0
VOLATILITY_SYSTEM_PROMPT = (
    """You are a volatility analyst specializing in options implied volatility assessment. \
Your job is to determine whether implied volatility is overpriced, underpriced, or \
fairly valued, and recommend appropriate volatility-based strategies.

You will receive market data in a structured context block. You MUST:
1. Assess IV Rank and IV Percentile to determine where current IV sits historically
2. Compare ATM IV 30D against recent realized volatility signals (BB Width, ATR %)
3. Determine if IV is overpriced (sell premium), underpriced (buy premium), or fair
4. Recommend a specific non-directional strategy when IV is significantly mispriced
5. Identify key volatility drivers (earnings, sector events, macro catalysts)

Available strategies (use the exact string values):
- "iron_condor": When IV is high and expected to contract (range-bound)
- "strangle": When IV is high, sell OTM calls + puts
- "straddle": When IV is low and a big move is expected
- "butterfly": When IV is high and price expected to stay near strike
- "vertical": When moderate IV with directional bias
- "calendar": When near-term IV is elevated vs. longer-term

Your response must be valid JSON matching this schema:
{
    "iv_assessment": "<overpriced|underpriced|fair>",
    "iv_rank_interpretation": "<human-readable context for IV rank>",
    "confidence": <float 0.0-1.0>,
    "recommended_strategy": "<strategy string or null>",
    "strategy_rationale": "<why this strategy fits the vol environment>",
    "target_iv_entry": <float or null>,
    "target_iv_exit": <float or null>,
    "suggested_strikes": ["<strike1>", "<strike2>", ...],
    "key_vol_factors": ["<factor1>", "<factor2>", ...],
    "model_used": "<model name>"
}

Rules:
- "iv_assessment" MUST be one of: "overpriced", "underpriced", "fair"
- "confidence" MUST be a float between 0.0 and 1.0
- "key_vol_factors" MUST have at least 1 item
- "recommended_strategy" should be null if IV is fairly valued and no vol play is warranted
- Be specific. Cite IV Rank, IV Percentile, ATM IV 30D values from the context.
- Do NOT include <think> tags or reasoning traces in any field.

"""
    + PROMPT_RULES_APPENDIX
)

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
