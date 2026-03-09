"""Risk agent for Options Arena AI debate.

Synthesizes Phase 1 agent outputs (trend, volatility, flow, fundamental) into a
comprehensive ``RiskAssessment`` with risk level, PoP estimate, and position sizing.

Architecture rules:
- No inter-agent imports (never imports bull.py or bear.py).
- model=None at init; actual model passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    PROMPT_RULES_APPENDIX,
    DebateDeps,
    build_cleaned_risk_assessment,
)
from options_arena.models import RiskAssessment

logger = logging.getLogger(__name__)

RISK_SYSTEM_PROMPT = (
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

risk_agent: Agent[DebateDeps, RiskAssessment] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=RiskAssessment,
    retries=2,
)


@risk_agent.system_prompt(dynamic=True)
async def risk_dynamic_prompt(ctx: RunContext[DebateDeps]) -> str:
    """Return the expanded risk system prompt, injecting Phase 1 agent outputs.

    Uses ``dynamic=True`` so the prompt is re-evaluated on every run, picking
    up the latest Phase 1 outputs from deps.
    """
    parts: list[str] = [RISK_SYSTEM_PROMPT]
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


@risk_agent.output_validator
async def clean_risk_think_tags(
    ctx: RunContext[DebateDeps],
    output: RiskAssessment,
) -> RiskAssessment:
    """Strip ``<think>`` tags from RiskAssessment output via shared helper."""
    return build_cleaned_risk_assessment(output)
