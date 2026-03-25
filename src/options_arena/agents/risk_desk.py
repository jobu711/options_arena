"""Risk desk agent for interactive and recommendation modes.

Distinct from the debate-mode risk agent (``risk.py``). Two agent instances:

- ``risk_desk``: Interactive ``Agent[DeskDeps, str]`` — plain text output.
- ``risk_desk_recommend``: Recommendation ``Agent[DeskDeps, RiskDeskAssessment]``
  — structured output for the unified recommendation pipeline.

Both share the same toolset (``build_risk_toolset()``) and learned-patterns
injection.  ``run_risk_desk_query()`` serves interactive mode;
``run_risk_desk_recommendation()`` serves the recommendation pipeline.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import RunUsage, UsageLimits

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import build_cleaned_domain_assessment, strip_think_tags
from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE, build_risk_toolset
from options_arena.agents.prompts import RECOMMEND_RISK_PROMPT
from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT
from options_arena.agents.prompts.recommend_risk import RISK_SPREAD_CONTEXT_BLOCK
from options_arena.models import AgencyConfig, DeskResponse, DeskType, SignalDirection
from options_arena.models.options import SpreadAnalysis
from options_arena.models.recommendation import RiskDeskAssessment

logger = logging.getLogger(__name__)

risk_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_risk_toolset(),  # type: ignore[arg-type]
)


@risk_desk.system_prompt(dynamic=True)
async def _risk_desk_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the risk desk system prompt with learned patterns."""
    base = DESK_RISK_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@risk_desk.output_validator
async def _strip_think(ctx: RunContext[DeskDeps], output: str) -> str:  # noqa: ARG001
    """Strip ``<think>`` tags from LLM output."""
    return strip_think_tags(output)


async def run_risk_desk_query(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None = None,
    config: AgencyConfig | None = None,
) -> DeskResponse:
    """Run a risk desk query with timeout and error handling.

    Returns a ``DeskResponse`` -- never raises.
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Risk desk query called without a model")
        return DeskResponse(
            desk=DeskType.RISK,
            response="Error: no LLM model configured. Set GROQ_API_KEY or pass --provider.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    try:
        limits = UsageLimits(
            request_limit=cfg.risk_tool_budget + 2,
            tool_calls_limit=cfg.risk_tool_budget,
        )
        result = await asyncio.wait_for(
            risk_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            ),
            timeout=cfg.agent_timeout,
        )
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.RISK,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=DESK_SUCCESS_CONFIDENCE,
        )
    except TimeoutError:
        logger.warning("Risk desk query timed out after %.1fs", cfg.agent_timeout)
        return DeskResponse(
            desk=DeskType.RISK,
            response="Query timed out. Please try a simpler question.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    except Exception as exc:
        logger.warning("Risk desk query failed: %s", exc)
        return DeskResponse(
            desk=DeskType.RISK,
            response="An internal error occurred processing your query.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Recommendation agent — structured ``RiskDeskAssessment`` output
# ---------------------------------------------------------------------------

risk_desk_recommend: Agent[DeskDeps, RiskDeskAssessment] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=RiskDeskAssessment,
    retries=2,
    tools=build_risk_toolset(),  # type: ignore[arg-type]
)


def _render_risk_spread_block(spread: SpreadAnalysis) -> str:
    """Render the ``<<<SPREAD_CONTEXT>>>`` block for the risk desk prompt."""
    rr = f"{spread.risk_reward_ratio:.2f}" if spread.risk_reward_ratio is not None else "--"
    return RISK_SPREAD_CONTEXT_BLOCK.format(
        spread_type=spread.spread.spread_type.value,
        max_loss=str(spread.max_loss),
        pop_estimate=f"{spread.pop_estimate:.0%}",
        risk_reward=rr,
    )


@risk_desk_recommend.system_prompt(dynamic=True)
async def _risk_recommend_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the risk recommendation prompt with learned patterns and spread context."""
    base = RECOMMEND_RISK_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    if ctx.deps.spread_analysis is not None:
        base += f"\n\n{_render_risk_spread_block(ctx.deps.spread_analysis)}"
    return base


@risk_desk_recommend.output_validator
async def _clean_risk_assessment(
    ctx: RunContext[DeskDeps],  # noqa: ARG001
    output: RiskDeskAssessment,
) -> RiskDeskAssessment:
    """Strip ``<think>`` tags from structured assessment fields."""
    return build_cleaned_domain_assessment(output)


def _build_risk_recommend_fallback(deps: DeskDeps) -> RiskDeskAssessment:
    """Build a low-confidence fallback ``RiskDeskAssessment``."""
    return RiskDeskAssessment(
        desk=DeskType.RISK,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        summary=f"Risk assessment unavailable for {deps.ticker}",
        key_factors=["Assessment unavailable"],
        risks=["Unable to analyze risk"],
        contracts_referenced=[],
        tools_used=list(deps.tools_used),
        model_used="data-driven-fallback",
        max_position_pct=0.02,
        hedging_suggestion="Review required",
        portfolio_correlation_note=None,
    )


async def run_risk_desk_recommendation(
    deps: DeskDeps,
    *,
    model: Model | None = None,
    model_settings: ModelSettings | None = None,
    config: AgencyConfig | None = None,
) -> tuple[RiskDeskAssessment, RunUsage]:
    """Run the risk recommendation agent — never raises.

    Returns a ``(RiskDeskAssessment, RunUsage)`` tuple on success or a
    low-confidence fallback with empty usage on any failure (no model,
    timeout, exception).
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Risk desk recommendation called without a model")
        return _build_risk_recommend_fallback(deps), RunUsage()
    try:
        limits = UsageLimits(
            request_limit=cfg.risk_tool_budget + 2,
            tool_calls_limit=cfg.risk_tool_budget,
        )
        result = await asyncio.wait_for(
            risk_desk_recommend.run(
                deps.query,
                model=model,
                deps=deps,
                usage_limits=limits,
                model_settings=model_settings,
            ),
            timeout=cfg.agent_timeout,
        )
        return result.output, result.usage()
    except TimeoutError:
        logger.warning("Risk desk recommendation timed out after %.1fs", cfg.agent_timeout)
        return _build_risk_recommend_fallback(deps), RunUsage()
    except Exception as exc:
        logger.warning("Risk desk recommendation failed: %s", exc)
        return _build_risk_recommend_fallback(deps), RunUsage()
