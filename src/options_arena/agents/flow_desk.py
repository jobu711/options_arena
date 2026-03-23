"""Flow desk agent for interactive mode + recommendation mode.

Distinct from the debate-mode flow agent (``flow_agent.py``). The interactive agent
returns plain ``str`` output, while the recommendation agent returns a structured
``FlowAssessment``.

Architecture:
- ``flow_desk``: Module-level ``Agent[DeskDeps, str]`` instance (``model=None``).
- ``run_flow_desk_query()``: Wraps ``flow_desk.run()`` with timeout, think-tag
  stripping, and never-raises error handling.
- ``flow_desk_recommend``: Module-level ``Agent[DeskDeps, FlowAssessment]`` instance.
- ``run_flow_desk_recommendation()``: Wraps ``flow_desk_recommend.run()`` with
  timeout and never-raises error handling.
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
from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE, build_flow_toolset
from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT
from options_arena.agents.prompts.recommend_flow import RECOMMEND_FLOW_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType, SignalDirection
from options_arena.models.recommendation import FlowAssessment

logger = logging.getLogger(__name__)

flow_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_flow_toolset(),  # type: ignore[arg-type]
)


@flow_desk.system_prompt(dynamic=True)
async def _flow_desk_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the flow desk system prompt with learned patterns."""
    base = DESK_FLOW_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@flow_desk.output_validator
async def _strip_think(ctx: RunContext[DeskDeps], output: str) -> str:  # noqa: ARG001
    """Strip ``<think>`` tags from LLM output."""
    return strip_think_tags(output)


async def run_flow_desk_query(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None = None,
    config: AgencyConfig | None = None,
) -> DeskResponse:
    """Run a flow desk query with timeout and error handling.

    Returns a ``DeskResponse`` -- never raises.
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Flow desk query called without a model")
        return DeskResponse(
            desk=DeskType.FLOW,
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
            flow_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            ),
            timeout=cfg.agent_timeout,
        )
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.FLOW,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=DESK_SUCCESS_CONFIDENCE,
        )
    except TimeoutError:
        logger.warning("Flow desk query timed out after %.1fs", cfg.agent_timeout)
        return DeskResponse(
            desk=DeskType.FLOW,
            response="Query timed out. Please try a simpler question.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    except Exception as exc:
        logger.warning("Flow desk query failed: %s", exc)
        return DeskResponse(
            desk=DeskType.FLOW,
            response="An internal error occurred processing your query.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Recommendation agent — structured FlowAssessment output
# ---------------------------------------------------------------------------

flow_desk_recommend: Agent[DeskDeps, FlowAssessment] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=FlowAssessment,
    retries=2,
    tools=build_flow_toolset(),  # type: ignore[arg-type]
)


@flow_desk_recommend.system_prompt(dynamic=True)
async def _flow_recommend_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the flow recommendation system prompt with learned patterns."""
    base = RECOMMEND_FLOW_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@flow_desk_recommend.output_validator
async def _clean_flow_recommend(
    ctx: RunContext[DeskDeps],  # noqa: ARG001
    output: FlowAssessment,
) -> FlowAssessment:
    """Strip ``<think>`` tags from structured output via shared helper."""
    return build_cleaned_domain_assessment(output)


async def run_flow_desk_recommendation(
    deps: DeskDeps,
    *,
    model: Model | None = None,
    model_settings: ModelSettings | None = None,
    config: AgencyConfig | None = None,
) -> tuple[FlowAssessment, RunUsage]:
    """Run flow desk recommendation -- never raises."""
    if model is None:
        logger.warning("Flow desk recommendation called without model")
        return _build_flow_fallback(deps), RunUsage()
    cfg = config or AgencyConfig()
    try:
        limits = UsageLimits(
            request_limit=cfg.default_tool_budget + 2,
            tool_calls_limit=cfg.default_tool_budget,
        )
        result = await asyncio.wait_for(
            flow_desk_recommend.run(
                f"Produce a structured flow assessment for {deps.ticker}.",
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
        return cleaned, result.usage()
    except TimeoutError:
        logger.warning("Flow desk recommendation timed out")
        return _build_flow_fallback(deps), RunUsage()
    except Exception as exc:
        logger.warning("Flow desk recommendation failed: %s", exc)
        return _build_flow_fallback(deps), RunUsage()


def _build_flow_fallback(deps: DeskDeps) -> FlowAssessment:
    """Build a conservative fallback FlowAssessment."""
    return FlowAssessment(
        desk=DeskType.FLOW,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        summary=f"Flow assessment unavailable for {deps.ticker}",
        key_factors=["Assessment unavailable"],
        risks=["Unable to analyze flow"],
        contracts_referenced=[],
        tools_used=list(deps.tools_used),
        model_used="data-driven-fallback",
        flow_bias=None,
        unusual_activity_noted=False,
    )
