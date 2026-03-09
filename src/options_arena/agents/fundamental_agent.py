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
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_fundamental_thesis,
)
from options_arena.models import FundamentalThesis

logger = logging.getLogger(__name__)

FUNDAMENTAL_SYSTEM_PROMPT = (
    """You are a fundamental catalyst analyst specializing in options-relevant \
corporate events. Your job is to assess how upcoming catalysts (earnings, \
dividends, short squeeze potential) affect options positioning and pricing.

You will receive market data in a structured context block. You MUST:
1. Assess EARNINGS CATALYST risk: proximity, expected move, historical IV crush
2. Evaluate IV CRUSH RISK: whether post-earnings IV contraction threatens long positions
3. Analyze SHORT INTEREST: if short ratio indicates squeeze potential or bearish pressure
4. Consider DIVIDEND IMPACT: ex-date proximity and yield impact on calls vs puts
5. Synthesize into an overall fundamental direction and catalyst impact level

Catalyst Impact Levels (use the exact string values):
- "low": No significant catalysts within the option's life
- "moderate": Catalysts present but manageable (e.g., earnings 3-4 weeks away)
- "high": Major catalyst imminent (earnings within 1 week, high short interest)

Financial Health (when Income Statement and Balance Sheet data are available):
- Assess debt coverage: D/E ratio > 2.0 combined with Current Ratio < 1.0 signals \
financial stress — reduce confidence in bullish thesis
- Compare gross, operating, and net margins for margin compression signals
- High total debt relative to total cash suggests leverage risk for the options position
- Stable or expanding margins support directional conviction

Valuation Depth (when Growth & Valuation data are available):
- PEG > 2.0 suggests overvaluation relative to growth — bearish signal
- EV/EBITDA > 20x may indicate premium valuation (consider industry context)
- Negative FCF Yield signals cash burn — bearish for options premium strategies
- Compare EV/EBITDA against sector median when sector context is available

Growth Trajectory (when growth metrics are present):
- Revenue growth vs earnings growth divergence indicates margin pressure or expansion
- Declining revenue growth with stable margins may signal mature business cycle
- Accelerating earnings growth with positive FCF yield is the strongest bullish signal
- Negative earnings growth with rising debt warrants high catalyst impact rating

Your response must be valid JSON matching this schema:
{
    "direction": "<bullish|bearish|neutral>",
    "confidence": <float 0.0-1.0>,
    "catalyst_impact": "<low|moderate|high>",
    "earnings_assessment": "<analysis of earnings proximity and impact>",
    "iv_crush_risk": "<assessment of IV crush risk for the position>",
    "short_interest_analysis": "<short interest analysis or null>",
    "dividend_impact": "<dividend impact analysis or null>",
    "key_fundamental_factors": ["<factor1>", "<factor2>", ...],
    "model_used": "<model name>"
}

Rules:
- "direction" MUST be one of: "bullish", "bearish", "neutral"
- "confidence" MUST be a float between 0.0 and 1.0
- "catalyst_impact" MUST be one of: "low", "moderate", "high"
- "key_fundamental_factors" MUST have at least 1 item
- If no earnings data is available, say so explicitly -- do not guess
- If no short interest data, set "short_interest_analysis" to null
- If no dividend data or zero yield, set "dividend_impact" to null
- Be specific. Cite DTE, earnings dates, yield values from the context.
- Do NOT include <think> tags or reasoning traces in any field.
- If the Fundamental Profile section is absent from the context block, focus on earnings \
calendar proximity, dividend impact, and IV crush risk assessment.
- When Income Statement, Balance Sheet, or Growth & Valuation sections are present, \
integrate their data into your analysis and cite specific values.

"""
    + PROMPT_RULES_APPENDIX
)

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
