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
    DebateDeps,
    build_cleaned_risk_assessment,
)
from options_arena.agents.prompts.risk import RISK_SYSTEM_PROMPT
from options_arena.models import RiskAssessment

logger = logging.getLogger(__name__)

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
