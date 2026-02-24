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

from options_arena.agents._parsing import DebateDeps, strip_think_tags
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

# VERSION: v1.0
BULL_SYSTEM_PROMPT = """You are a bullish options analyst. Your job is to make the strongest \
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
- Do NOT include <think> tags or reasoning traces in any field."""

bull_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=AgentResponse,
    retries=2,
)


@bull_agent.system_prompt
def bull_system_prompt() -> str:
    """Return the static bull system prompt."""
    return BULL_SYSTEM_PROMPT


@bull_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: AgentResponse,
) -> AgentResponse:
    """Strip ``<think>`` tags from LLM output instead of rejecting.

    Llama models sometimes emit reasoning traces wrapped in ``<think>`` tags.
    Stripping is far cheaper than retrying (5-10 min per retry on CPU).
    Constructs a new frozen instance with cleaned text fields.
    """
    fields = [
        output.argument,
        *output.key_points,
        *output.risks_cited,
        *output.contracts_referenced,
    ]
    if not any("<think>" in v or "</think>" in v for v in fields):
        return output
    return AgentResponse(
        agent_name=output.agent_name,
        direction=output.direction,
        confidence=output.confidence,
        argument=strip_think_tags(output.argument),
        key_points=[strip_think_tags(p) for p in output.key_points],
        risks_cited=[strip_think_tags(r) for r in output.risks_cited],
        contracts_referenced=[strip_think_tags(c) for c in output.contracts_referenced],
        model_used=output.model_used,
    )
