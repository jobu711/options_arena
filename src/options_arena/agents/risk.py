"""Risk agent for Options Arena AI debate.

Weighs the bull and bear arguments, identifies which is better-supported by data,
and produces a final ``TradeThesis`` with risk assessment and position sizing guidance.
Receives both agent responses via ``DebateDeps.bull_response`` and ``bear_response``.

Architecture rules:
- No inter-agent imports (never imports bull.py or bear.py).
- model=None at init; actual OllamaModel passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.settings import ModelSettings

from options_arena.agents._parsing import DebateDeps
from options_arena.models import TradeThesis

logger = logging.getLogger(__name__)

# VERSION: v1.0
RISK_SYSTEM_PROMPT = """You are a risk assessment analyst adjudicating an options debate. \
You have received arguments from both a bull (bullish) and bear (bearish) analyst. Your job \
is to weigh both cases objectively and produce a final trade recommendation.

You will receive market data in a structured context block plus the bull and bear arguments. \
You MUST:
1. Evaluate which argument is better supported by the data in the context
2. Score both the bull and bear cases on a 0-10 scale based on evidence quality
3. Identify the key factors that tilt the decision one way or the other
4. Assess risk/reward ratio for the proposed position
5. Recommend a strategy type if the trade is worth taking, or null if not
6. Provide position sizing guidance in your risk assessment

Your response must be valid JSON matching this schema:
{
    "ticker": "<ticker symbol>",
    "direction": "bullish" | "bearish" | "neutral",
    "confidence": <float 0.0-1.0>,
    "summary": "<synthesized verdict explaining your decision>",
    "bull_score": <float 0.0-10.0>,
    "bear_score": <float 0.0-10.0>,
    "key_factors": ["<factor1>", "<factor2>", ...],
    "risk_assessment": "<detailed risk analysis and position sizing guidance>",
    "recommended_strategy": "vertical" | "calendar" | "straddle" | "strangle" | \
"iron_condor" | "butterfly" | null
}

Rules:
- "direction" MUST be one of: "bullish", "bearish", "neutral"
- "confidence" MUST be a float between 0.0 and 1.0
- "bull_score" and "bear_score" MUST be floats between 0.0 and 10.0
- "key_factors" MUST have at least 2 items
- "recommended_strategy" should be null if confidence < 0.4 or direction is "neutral"
- Be specific. Cite numbers from the context. Do not hallucinate data.
- Do NOT include <think> tags or reasoning traces in any field."""

risk_agent: Agent[DebateDeps, TradeThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=TradeThesis,
    retries=2,
    model_settings=ModelSettings(extra_body={"num_ctx": 8192}),
)


@risk_agent.system_prompt(dynamic=True)
async def risk_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the risk system prompt, injecting both bull and bear arguments.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest ``bull_response`` and ``bear_response`` from deps. Arguments
    are wrapped in delimiters to prevent instruction bleed from LLM-generated text.
    """
    parts: list[str] = [RISK_SYSTEM_PROMPT]
    if ctx.deps.bull_response:
        parts.append(
            f"\n\n<<<BULL_CASE>>>\n"
            f"Direction: {ctx.deps.bull_response.direction.value}\n"
            f"Confidence: {ctx.deps.bull_response.confidence}\n"
            f"Argument: {ctx.deps.bull_response.argument}\n"
            f"Key Points: {', '.join(ctx.deps.bull_response.key_points)}\n"
            f"<<<END_BULL_CASE>>>"
        )
    if ctx.deps.bear_response:
        parts.append(
            f"\n\n<<<BEAR_CASE>>>\n"
            f"Direction: {ctx.deps.bear_response.direction.value}\n"
            f"Confidence: {ctx.deps.bear_response.confidence}\n"
            f"Argument: {ctx.deps.bear_response.argument}\n"
            f"Key Points: {', '.join(ctx.deps.bear_response.key_points)}\n"
            f"<<<END_BEAR_CASE>>>"
        )
    return "".join(parts)


@risk_agent.output_validator
async def reject_think_tags(
    ctx: RunContext[DebateDeps],
    output: TradeThesis,
) -> TradeThesis:
    """Reject LLM output containing <think> tags.

    Llama 3.1 8B sometimes emits reasoning traces that should not appear
    in user-facing text. Checks both ``summary`` and ``risk_assessment``
    fields. Raises ``ModelRetry`` to trigger a retry with corrective instructions.
    """
    for field_value in (output.summary, output.risk_assessment):
        if "<think>" in field_value or "</think>" in field_value:
            raise ModelRetry("Remove all <think> and </think> tags from your response.")
    return output
