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

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_risk_assessment,
    build_cleaned_trade_thesis,
)
from options_arena.models import RiskAssessment, SignalDirection, SpreadType, TradeThesis

logger = logging.getLogger(__name__)

RISK_STRATEGY_TREE = """
Strategy selection decision tree:
- IF direction is "neutral" AND IV RANK > 70: recommend "iron_condor"
- IF direction is "neutral" AND IV RANK 30-70: recommend "butterfly"
- IF direction is "neutral" AND IV RANK < 30: recommend "straddle"
- IF confidence > 0.7 AND IV RANK < 50: recommend "vertical"
- IF confidence 0.4-0.7 AND IV RANK > 50: recommend "calendar"
- IF confidence < 0.4 OR data is highly conflicting: recommend null
- IF both bull_score and bear_score > 6.0: recommend "strangle"
"""

# VERSION: v2.1
RISK_SYSTEM_PROMPT = (
    """You are a risk assessment analyst adjudicating an options debate. \
You have received arguments from both a bull (bullish) and bear (bearish) analyst. Your job \
is to weigh both cases objectively and produce a final trade recommendation.

You will receive market data in a structured context block plus the bull and bear arguments. \
You MUST:
1. Evaluate which argument is better supported by the data in the context
2. Score both the bull and bear cases on a 0-10 scale based on evidence quality
3. Identify the key factors that tilt the decision one way or the other
4. Assess risk/reward ratio for the proposed position
5. If a bull rebuttal is provided (<<<BULL_REBUTTAL>>> block), factor it into the bull_score \
and summary — a well-supported rebuttal should raise the bull_score
6. Recommend a strategy type if the trade is worth taking, or null if not
7. Provide position sizing guidance in your risk assessment
8. Estimate probability of profit (PoP) based on delta and IV data when available
9. Warn about charm (delta decay) risk when DTE < 14 or GAMMA is high
10. Assess bid-ask spread quality — wide spreads indicate liquidity risk
11. Quantify maximum loss as contract premium times 100 (1 contract = 100 shares)

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
- Do NOT include <think> tags or reasoning traces in any field.

"""
    + PROMPT_RULES_APPENDIX
    + "\n\n"
    + RISK_STRATEGY_TREE
)

risk_agent: Agent[DebateDeps, TradeThesis] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=TradeThesis,
    retries=2,
)


@risk_agent.system_prompt(dynamic=True)
async def risk_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the risk system prompt, injecting both bull and bear arguments.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest ``bull_response`` and ``bear_response`` from deps. Arguments
    are wrapped in delimiters to prevent instruction bleed from LLM-generated text.
    """
    parts: list[str] = [RISK_SYSTEM_PROMPT]
    if ctx.deps.bull_response is not None:
        parts.append(
            f"\n\n<<<BULL_CASE>>>\n"
            f"Direction: {ctx.deps.bull_response.direction.value}\n"
            f"Confidence: {ctx.deps.bull_response.confidence}\n"
            f"Argument: {ctx.deps.bull_response.argument}\n"
            f"Key Points: {', '.join(ctx.deps.bull_response.key_points)}\n"
            f"<<<END_BULL_CASE>>>"
        )
    if ctx.deps.bear_response is not None:
        parts.append(
            f"\n\n<<<BEAR_CASE>>>\n"
            f"Direction: {ctx.deps.bear_response.direction.value}\n"
            f"Confidence: {ctx.deps.bear_response.confidence}\n"
            f"Argument: {ctx.deps.bear_response.argument}\n"
            f"Key Points: {', '.join(ctx.deps.bear_response.key_points)}\n"
            f"<<<END_BEAR_CASE>>>"
        )
    if ctx.deps.bull_rebuttal is not None:
        parts.append(
            f"\n\n<<<BULL_REBUTTAL>>>\n"
            f"Direction: {ctx.deps.bull_rebuttal.direction.value}\n"
            f"Confidence: {ctx.deps.bull_rebuttal.confidence}\n"
            f"Argument: {ctx.deps.bull_rebuttal.argument}\n"
            f"Key Points: {', '.join(ctx.deps.bull_rebuttal.key_points)}\n"
            f"<<<END_BULL_REBUTTAL>>>"
        )
    if ctx.deps.vol_response is not None:
        vol = ctx.deps.vol_response
        parts.append(
            f"\n\n<<<VOL_CASE>>>\n"
            f"IV Assessment: {vol.iv_assessment}\n"
            f"Confidence: {vol.confidence}\n"
            f"Strategy Rationale: {vol.strategy_rationale}\n"
            f"Recommended Strategy: "
            f"{vol.recommended_strategy.value if vol.recommended_strategy else 'none'}\n"
            f"Key Volatility Factors: {', '.join(vol.key_vol_factors)}\n"
            f"<<<END_VOL_CASE>>>"
        )
    return "".join(parts)


@risk_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: TradeThesis,
) -> TradeThesis:
    """Strip ``<think>`` tags and log strategy-direction consistency warnings."""
    cleaned = build_cleaned_trade_thesis(output)

    # Post-validation consistency logging (warn only, no modification)
    if (
        cleaned.direction == SignalDirection.NEUTRAL
        and cleaned.recommended_strategy == SpreadType.VERTICAL
    ):
        logger.warning(
            "Strategy inconsistency for %s: neutral direction with directional strategy %s",
            cleaned.ticker,
            cleaned.recommended_strategy.value,
        )
    if cleaned.confidence < 0.4 and cleaned.recommended_strategy is not None:
        logger.warning(
            "Low confidence strategy for %s: confidence=%.2f with strategy=%s",
            cleaned.ticker,
            cleaned.confidence,
            cleaned.recommended_strategy.value,
        )

    return cleaned


# ---------------------------------------------------------------------------
# Risk Agent v2 — expanded RiskAssessment output for 6-agent protocol
# ---------------------------------------------------------------------------

# VERSION: v1.0
RISK_V2_SYSTEM_PROMPT = (
    """You are an expanded risk assessment analyst for the 6-agent options debate protocol. \
You have received outputs from Phase 1 agents (trend, volatility, flow, fundamental). Your job \
is to synthesize their findings into a comprehensive risk assessment.

You will receive market data in a structured context block plus Phase 1 agent outputs. \
You MUST:
1. Assess overall risk level (low, moderate, high, extreme) based on all agent outputs
2. Estimate probability of profit (PoP) if the recommended position is taken
3. Quantify maximum loss for the proposed position
4. Evaluate charm (delta decay) risk for the given DTE
5. Assess bid-ask spread quality and liquidity risk
6. Identify key risks and any risk mitigants from the data
7. Provide position sizing guidance based on the risk level

Your response must be valid JSON matching this schema:
{
    "risk_level": "low" | "moderate" | "high" | "extreme",
    "confidence": <float 0.0-1.0>,
    "pop_estimate": <float 0.0-1.0 or null>,
    "max_loss_estimate": "<quantified max loss description>",
    "charm_decay_warning": "<charm/delta decay assessment or null>",
    "spread_quality_assessment": "<bid-ask spread quality assessment or null>",
    "key_risks": ["<risk1>", "<risk2>", ...],
    "risk_mitigants": ["<mitigant1>", ...],
    "recommended_position_size": "<sizing guidance or null>",
    "model_used": "<model name>"
}

Rules:
- "risk_level" MUST be one of: "low", "moderate", "high", "extreme"
- "confidence" MUST be a float between 0.0 and 1.0
- "pop_estimate" is optional — set to null if insufficient data to estimate
- "key_risks" MUST have at least 1 item
- "risk_mitigants" may be empty if no mitigants apply
- Cite specific numbers from the context block and agent outputs.
- Do NOT include <think> tags or reasoning traces in any field.

"""
    + PROMPT_RULES_APPENDIX
)

risk_agent_v2: Agent[DebateDeps, RiskAssessment] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=RiskAssessment,
    retries=2,
)


@risk_agent_v2.system_prompt(dynamic=True)
async def risk_v2_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the expanded risk system prompt, injecting Phase 1 agent outputs.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest Phase 1 outputs from deps.
    """
    parts: list[str] = [RISK_V2_SYSTEM_PROMPT]
    if ctx.deps.trend_response is not None:
        trend = ctx.deps.trend_response
        parts.append(
            f"\n\n<<<TREND_AGENT>>>\n"
            f"Direction: {trend.direction.value}\n"
            f"Confidence: {trend.confidence}\n"
            f"Argument: {trend.argument}\n"
            f"Key Points: {', '.join(trend.key_points)}\n"
            f"<<<END_TREND_AGENT>>>"
        )
    if ctx.deps.volatility_thesis is not None:
        vol = ctx.deps.volatility_thesis
        parts.append(
            f"\n\n<<<VOLATILITY_AGENT>>>\n"
            f"IV Assessment: {vol.iv_assessment}\n"
            f"Confidence: {vol.confidence}\n"
            f"Strategy Rationale: {vol.strategy_rationale}\n"
            f"Recommended Strategy: "
            f"{vol.recommended_strategy.value if vol.recommended_strategy else 'none'}\n"
            f"Key Volatility Factors: {', '.join(vol.key_vol_factors)}\n"
            f"<<<END_VOLATILITY_AGENT>>>"
        )
    if ctx.deps.flow_thesis is not None:
        flow = ctx.deps.flow_thesis
        parts.append(
            f"\n\n<<<FLOW_AGENT>>>\n"
            f"Direction: {flow.direction.value}\n"
            f"Confidence: {flow.confidence}\n"
            f"GEX: {flow.gex_interpretation}\n"
            f"Smart Money: {flow.smart_money_signal}\n"
            f"Key Factors: {', '.join(flow.key_flow_factors)}\n"
            f"<<<END_FLOW_AGENT>>>"
        )
    if ctx.deps.fundamental_thesis is not None:
        fund = ctx.deps.fundamental_thesis
        parts.append(
            f"\n\n<<<FUNDAMENTAL_AGENT>>>\n"
            f"Direction: {fund.direction.value}\n"
            f"Confidence: {fund.confidence}\n"
            f"Catalyst Impact: {fund.catalyst_impact.value}\n"
            f"Earnings Assessment: {fund.earnings_assessment}\n"
            f"Key Factors: {', '.join(fund.key_fundamental_factors)}\n"
            f"<<<END_FUNDAMENTAL_AGENT>>>"
        )
    return "".join(parts)


@risk_agent_v2.output_validator
async def clean_risk_v2_think_tags(
    ctx: RunContext[DebateDeps],
    output: RiskAssessment,
) -> RiskAssessment:
    """Strip ``<think>`` tags from RiskAssessment output via shared helper."""
    return build_cleaned_risk_assessment(output)
