"""Synthesis agent -- weighs domain assessments and produces PositionRecommendation.

The synthesis agent receives assessments from all 6 desk domains and produces
a specific contract recommendation with entry/exit criteria, position sizing,
and risk assessment. This is the final step in the unified recommendation pipeline.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings

from options_arena.agents._parsing import strip_think_tags
from options_arena.agents._toolsets import build_synthesis_toolset
from options_arena.agents.prompts.synthesis import SYNTHESIS_SYSTEM_PROMPT
from options_arena.models import (
    MarketContext,
    OptionContract,
    SignalDirection,
    TickerScore,
)
from options_arena.models.recommendation import (
    DomainAssessment,
    PositionRecommendation,
)

logger = logging.getLogger(__name__)


@dataclass
class SynthesisDeps:
    """Dependencies injected into the synthesis agent via RunContext."""

    context: MarketContext
    assessments: list[DomainAssessment]
    contracts: list[OptionContract]
    ticker_score: TickerScore
    learned_patterns: str = ""
    tuned_weights: str = ""
    tools_used: list[str] = field(default_factory=list)


synthesis_agent: Agent[SynthesisDeps, PositionRecommendation] = Agent(
    model=None,
    deps_type=SynthesisDeps,
    output_type=PositionRecommendation,
    retries=2,
    tools=build_synthesis_toolset(),  # type: ignore[arg-type]
)


@synthesis_agent.system_prompt(dynamic=True)
async def _synthesis_system_prompt(ctx: RunContext[SynthesisDeps]) -> str:
    """Return synthesis system prompt with optional tuned weights and learned patterns."""
    base = SYNTHESIS_SYSTEM_PROMPT
    if ctx.deps.tuned_weights:
        base += f"\n\n<<<TUNED_WEIGHTS>>>\n{ctx.deps.tuned_weights}\n<<<END_TUNED_WEIGHTS>>>"
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@synthesis_agent.output_validator
async def _strip_think_tags(
    ctx: RunContext[SynthesisDeps],  # noqa: ARG001
    output: PositionRecommendation,
) -> PositionRecommendation:
    """Strip ``<think>`` tags from string fields of the recommendation.

    Since ``PositionRecommendation`` is frozen, construct a new instance with
    cleaned string fields.
    """
    cleaned_summary = strip_think_tags(output.summary)
    cleaned_entry_criteria = strip_think_tags(output.entry_criteria)
    cleaned_exit_criteria = strip_think_tags(output.exit_criteria)
    cleaned_position_rationale = strip_think_tags(output.position_rationale)
    cleaned_max_loss = strip_think_tags(output.max_loss_estimate)
    cleaned_risk = strip_think_tags(output.risk_assessment)
    cleaned_contract = strip_think_tags(output.recommended_contract)
    cleaned_strategy_rationale = strip_think_tags(output.strategy_rationale)
    cleaned_key_factors = [strip_think_tags(f) for f in output.key_factors]

    # Only rebuild if something actually changed
    if (
        cleaned_summary == output.summary
        and cleaned_entry_criteria == output.entry_criteria
        and cleaned_exit_criteria == output.exit_criteria
        and cleaned_position_rationale == output.position_rationale
        and cleaned_max_loss == output.max_loss_estimate
        and cleaned_risk == output.risk_assessment
        and cleaned_contract == output.recommended_contract
        and cleaned_strategy_rationale == output.strategy_rationale
        and cleaned_key_factors == output.key_factors
    ):
        return output

    return PositionRecommendation(
        ticker=output.ticker,
        direction=output.direction,
        confidence=output.confidence,
        recommended_contract=cleaned_contract,
        entry_price=output.entry_price,
        entry_criteria=cleaned_entry_criteria,
        exit_criteria=cleaned_exit_criteria,
        stop_loss=output.stop_loss,
        take_profit=output.take_profit,
        position_size_pct=output.position_size_pct,
        position_rationale=cleaned_position_rationale,
        risk_reward_ratio=output.risk_reward_ratio,
        max_loss_estimate=cleaned_max_loss,
        recommended_strategy=output.recommended_strategy,
        strategy_rationale=cleaned_strategy_rationale,
        summary=cleaned_summary,
        key_factors=cleaned_key_factors,
        risk_assessment=cleaned_risk,
        agent_agreement_score=output.agent_agreement_score,
        dissenting_desks=list(output.dissenting_desks),
        model_used=output.model_used,
    )


def _build_user_prompt(deps: SynthesisDeps) -> str:
    """Build the user prompt summarising assessments and available contracts."""
    lines: list[str] = [
        f"Ticker: {deps.context.ticker}",
        f"Current Price: ${deps.context.current_price}",
        f"Composite Score: {deps.ticker_score.composite_score:.1f}/100",
        f"Direction Signal: {deps.ticker_score.direction.value}",
        "",
        "--- Domain Assessments ---",
    ]

    direction_counts: dict[str, int] = {}
    for a in deps.assessments:
        d = a.direction.value
        direction_counts[d] = direction_counts.get(d, 0) + 1
        lines.append(
            f"[{a.desk.value.upper()}] direction={a.direction.value} "
            f"confidence={a.confidence:.2f}: {a.summary}"
        )

    lines.append("")
    lines.append("Direction tally: " + ", ".join(f"{k}={v}" for k, v in direction_counts.items()))
    lines.append("")
    lines.append("--- Available Contracts ---")

    for c in deps.contracts:
        greeks_str = ""
        if c.greeks is not None:
            greeks_str = (
                f" delta={c.greeks.delta:.2f} gamma={c.greeks.gamma:.4f}"
                f" theta={c.greeks.theta:.4f} vega={c.greeks.vega:.4f}"
            )
        lines.append(
            f"  {c.option_type.value.upper()} ${c.strike} "
            f"exp {c.expiration.isoformat()} "
            f"bid=${c.bid} ask=${c.ask} mid=${c.mid}{greeks_str}"
        )

    return "\n".join(lines)


def _build_fallback_recommendation(deps: SynthesisDeps) -> PositionRecommendation:
    """Build a conservative fallback recommendation when the agent fails."""
    ticker = deps.context.ticker
    entry_price = deps.context.current_price

    # Pick the first contract as a placeholder, or synthesize one
    if deps.contracts:
        c = deps.contracts[0]
        contract_str = (
            f"{c.ticker} {float(c.strike):.0f}"
            f"{'C' if c.option_type.value == 'call' else 'P'} "
            f"{c.expiration.isoformat()}"
        )
        entry_price = c.mid
    else:
        contract_str = f"{ticker} ATM (no contracts available)"

    return PositionRecommendation(
        ticker=ticker,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        recommended_contract=contract_str,
        entry_price=entry_price,
        entry_criteria="N/A -- data-driven fallback, manual review required",
        exit_criteria="N/A -- data-driven fallback, manual review required",
        stop_loss=None,
        take_profit=None,
        position_size_pct=0.02,
        position_rationale="Minimum position size due to synthesis agent failure",
        risk_reward_ratio=1.0,
        max_loss_estimate="Unable to estimate -- synthesis agent unavailable",
        recommended_strategy=None,
        strategy_rationale="No strategy recommended -- synthesis agent unavailable",
        summary=(
            f"Data-driven fallback for {ticker}. "
            f"Synthesis agent was unavailable. Exercise additional caution."
        ),
        key_factors=[
            "Synthesis agent unavailable",
            f"Composite score: {deps.ticker_score.composite_score:.1f}",
            f"Direction signal: {deps.ticker_score.direction.value}",
            f"Number of assessments: {len(deps.assessments)}",
            f"Number of contracts: {len(deps.contracts)}",
        ],
        risk_assessment="High risk -- AI synthesis unavailable, manual review required",
        agent_agreement_score=None,
        dissenting_desks=[],
        model_used="data-driven-fallback",
    )


async def run_synthesis(
    deps: SynthesisDeps,
    model: Model | None,
    model_settings: ModelSettings | None = None,
    timeout: float = 120.0,
) -> PositionRecommendation:
    """Run synthesis agent -- never raises, returns fallback on failure.

    Parameters
    ----------
    deps
        Synthesis dependencies with assessments, contracts, and market context.
    model
        PydanticAI model instance (e.g., ``GroqModel``).
    model_settings
        Optional model settings (e.g., temperature, max_tokens).
    timeout
        Per-agent timeout in seconds.

    Returns
    -------
    PositionRecommendation
        The synthesized position recommendation, or a conservative fallback.
    """
    if model is None:
        logger.warning("Synthesis agent called without a model")
        return _build_fallback_recommendation(deps)

    try:
        user_prompt = _build_user_prompt(deps)
        result = await asyncio.wait_for(
            synthesis_agent.run(
                user_prompt,
                model=model,
                deps=deps,
                model_settings=model_settings,
            ),
            timeout=timeout,
        )
        # The @output_validator (_strip_think_tags) already handles ALL string
        # fields before result.output is returned — no additional stripping needed.
        return result.output
    except TimeoutError:
        logger.warning("Synthesis agent timed out after %.1fs", timeout)
        return _build_fallback_recommendation(deps)
    except Exception as exc:
        logger.warning("Synthesis agent failed: %s (%s)", exc, type(exc).__name__)
        return _build_fallback_recommendation(deps)
