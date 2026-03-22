"""Trend desk agent for interactive mode + recommendation mode.

Distinct from the debate-mode trend agent (``trend_agent.py``). The interactive agent
returns plain ``str`` output, while the recommendation agent returns a structured
``TrendAssessment``.

Architecture:
- ``trend_desk``: Module-level ``Agent[DeskDeps, str]`` instance (``model=None``).
- ``run_trend_desk_query()``: Wraps ``trend_desk.run()`` with timeout, think-tag
  stripping, and never-raises error handling.
- ``trend_desk_recommend``: Module-level ``Agent[DeskDeps, TrendAssessment]`` instance.
- ``run_trend_desk_recommendation()``: Wraps ``trend_desk_recommend.run()`` with
  timeout and never-raises error handling.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.models import Model
from pydantic_ai.settings import ModelSettings
from pydantic_ai.usage import UsageLimits

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import build_cleaned_domain_assessment, strip_think_tags
from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE, build_trend_toolset
from options_arena.agents.prompts.desk_trend import DESK_TREND_PROMPT
from options_arena.agents.prompts.recommend_trend import RECOMMEND_TREND_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType, SignalDirection
from options_arena.models.recommendation import TrendAssessment

logger = logging.getLogger(__name__)

trend_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_trend_toolset(),  # type: ignore[arg-type]
)


@trend_desk.system_prompt(dynamic=True)
async def _trend_desk_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the trend desk system prompt with learned patterns."""
    base = DESK_TREND_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@trend_desk.output_validator
async def _strip_think(ctx: RunContext[DeskDeps], output: str) -> str:  # noqa: ARG001
    """Strip ``<think>`` tags from LLM output."""
    return strip_think_tags(output)


async def run_trend_desk_query(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None = None,
    config: AgencyConfig | None = None,
) -> DeskResponse:
    """Run a trend desk query with timeout and error handling.

    Returns a ``DeskResponse`` -- never raises.
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Trend desk query called without a model")
        return DeskResponse(
            desk=DeskType.TREND,
            response="Error: no LLM model configured. Set GROQ_API_KEY or pass --provider.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    try:
        limits = UsageLimits(
            request_limit=cfg.default_tool_budget + 2,
            tool_calls_limit=cfg.default_tool_budget,
        )
        result = await asyncio.wait_for(
            trend_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            ),
            timeout=cfg.agent_timeout,
        )
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.TREND,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=DESK_SUCCESS_CONFIDENCE,
        )
    except TimeoutError:
        logger.warning("Trend desk query timed out after %.1fs", cfg.agent_timeout)
        return DeskResponse(
            desk=DeskType.TREND,
            response="Query timed out. Please try a simpler question.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    except Exception as exc:
        logger.warning("Trend desk query failed: %s", exc)
        return DeskResponse(
            desk=DeskType.TREND,
            response="An internal error occurred processing your query.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Recommendation agent — structured TrendAssessment output
# ---------------------------------------------------------------------------

trend_desk_recommend: Agent[DeskDeps, TrendAssessment] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=TrendAssessment,
    retries=2,
    tools=build_trend_toolset(),  # type: ignore[arg-type]
)


@trend_desk_recommend.system_prompt(dynamic=True)
async def _trend_recommend_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the trend recommendation system prompt with learned patterns."""
    base = RECOMMEND_TREND_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@trend_desk_recommend.output_validator
async def _clean_trend_recommend(
    ctx: RunContext[DeskDeps],  # noqa: ARG001
    output: TrendAssessment,
) -> TrendAssessment:
    """Strip ``<think>`` tags from structured output via shared helper."""
    return build_cleaned_domain_assessment(output)


async def run_trend_desk_recommendation(
    deps: DeskDeps,
    *,
    model: Model | None = None,
    model_settings: ModelSettings | None = None,
    config: AgencyConfig | None = None,
) -> TrendAssessment:
    """Run trend desk recommendation -- never raises."""
    if model is None:
        logger.warning("Trend desk recommendation called without model")
        return _build_trend_fallback(deps)
    cfg = config or AgencyConfig()
    try:
        limits = UsageLimits(
            request_limit=cfg.default_tool_budget + 2,
            tool_calls_limit=cfg.default_tool_budget,
        )
        result = await asyncio.wait_for(
            trend_desk_recommend.run(
                f"Produce a structured trend assessment for {deps.ticker}.",
                model=model,
                deps=deps,
                model_settings=model_settings,
                usage_limits=limits,
            ),
            timeout=cfg.agent_timeout,
        )
        output = result.output
        # Defense-in-depth: strip think tags again
        cleaned = build_cleaned_domain_assessment(output)
        return cleaned
    except TimeoutError:
        logger.warning("Trend desk recommendation timed out")
        return _build_trend_fallback(deps)
    except Exception as exc:
        logger.warning("Trend desk recommendation failed: %s", exc)
        return _build_trend_fallback(deps)


def _build_trend_fallback(deps: DeskDeps) -> TrendAssessment:
    """Build a conservative fallback TrendAssessment."""
    return TrendAssessment(
        desk=DeskType.TREND,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        summary=f"Trend assessment unavailable for {deps.ticker}",
        key_factors=["Assessment unavailable"],
        risks=["Unable to analyze trend"],
        contracts_referenced=[],
        tools_used=list(deps.tools_used),
        model_used="data-driven-fallback",
        trend_strength=None,
        momentum_signal=None,
    )
