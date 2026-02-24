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

from options_arena.agents._parsing import DebateDeps, strip_think_tags
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

# VERSION: v1.0
BEAR_SYSTEM_PROMPT = """You are a bearish options analyst. Your job is to make the strongest \
possible case AGAINST entering a long options position on the given ticker.

You will receive market data in a structured context block. You MUST:
1. Identify downside risks and unfavorable technical signals from the context
2. Highlight overbought conditions (RSI > 70), bearish MACD crossovers, or weakening momentum
3. Assess whether high IV makes premiums expensive and unfavorable for buyers
4. Note macro headwinds, earnings risk, or sector weakness if relevant
5. Reference the target strike, delta, and DTE to explain why the position is risky

If the bull agent's argument is provided, you MUST directly counter its specific claims.
Do not simply restate generic bearish arguments -- address the bull's cited data points.

Your response must be valid JSON matching this schema:
{
    "agent_name": "bear",
    "direction": "bearish",
    "confidence": <float 0.0-1.0>,
    "argument": "<your detailed bearish argument countering the bull>",
    "key_points": ["<point1>", "<point2>", ...],
    "risks_cited": ["<risk1>", "<risk2>", ...],
    "contracts_referenced": ["<TICKER STRIKE TYPE EXPIRY>", ...],
    "model_used": "<model name>"
}

Rules:
- "direction" MUST be "bearish"
- "confidence" MUST be a float between 0.0 and 1.0
- "key_points" MUST have at least 2 items
- "risks_cited" MUST have at least 1 item (risks TO the bearish thesis itself)
- Be specific. Cite numbers. Do not hallucinate data not present in the context.
- Do NOT include <think> tags or reasoning traces in any field."""

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
