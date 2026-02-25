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
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_agent_response,
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
3. Identify momentum and trend signals that support the bullish case
4. Assess whether current IV levels favor the position
5. Note sector-specific catalysts if relevant

Your response must be valid JSON matching this schema:
{
    "agent_name": "bull",
    "direction": "bullish",
    "confidence": <float 0.0-1.0>,
    "argument": "<your detailed bullish argument>",
    "key_points": ["<point1>", "<point2>", ...],
    "risks_cited": ["<risk1>", "<risk2>", ...],
    "contracts_referenced": ["<TICKER STRIKE TYPE EXPIRY>", ...],
    "model_used": "<model name>"
}

Rules:
- "direction" MUST be "bullish"
- "confidence" MUST be a float between 0.0 and 1.0
- "key_points" MUST have at least 2 items
- "risks_cited" MUST have at least 1 item (acknowledge risks even in a bullish case)
- Be specific. Cite numbers. Do not hallucinate data not present in the context.
- Do NOT include <think> tags or reasoning traces in any field.

"""
    + PROMPT_RULES_APPENDIX
)

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
