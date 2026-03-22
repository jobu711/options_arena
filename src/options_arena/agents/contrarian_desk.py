"""Contrarian desk agent for interactive and recommendation modes.

Distinct from the debate-mode contrarian agent (``contrarian_agent.py``). Two agent
instances:

- ``contrarian_desk``: Interactive ``Agent[DeskDeps, str]`` — plain text output.
- ``contrarian_desk_recommend``: Recommendation ``Agent[DeskDeps, ContrarianAssessment]``
  — structured output for the unified recommendation pipeline.

Both share the same toolset (``build_contrarian_toolset()``) and learned-patterns
injection.  ``run_contrarian_desk_query()`` serves interactive mode;
``run_contrarian_desk_recommendation()`` serves the recommendation pipeline.
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
from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE, build_contrarian_toolset
from options_arena.agents.prompts import RECOMMEND_CONTRARIAN_PROMPT
from options_arena.agents.prompts.desk_contrarian import DESK_CONTRARIAN_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType, SignalDirection
from options_arena.models.recommendation import ContrarianAssessment

logger = logging.getLogger(__name__)

contrarian_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_contrarian_toolset(),  # type: ignore[arg-type]
)


@contrarian_desk.system_prompt(dynamic=True)
async def _contrarian_desk_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the contrarian desk system prompt with learned patterns."""
    base = DESK_CONTRARIAN_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@contrarian_desk.output_validator
async def _strip_think(ctx: RunContext[DeskDeps], output: str) -> str:  # noqa: ARG001
    """Strip ``<think>`` tags from LLM output."""
    return strip_think_tags(output)


async def run_contrarian_desk_query(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None = None,
    config: AgencyConfig | None = None,
) -> DeskResponse:
    """Run a contrarian desk query with timeout and error handling.

    Returns a ``DeskResponse`` -- never raises.
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Contrarian desk query called without a model")
        return DeskResponse(
            desk=DeskType.CONTRARIAN,
            response="Error: no LLM model configured. Set GROQ_API_KEY or pass --provider.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    try:
        limits = UsageLimits(
            request_limit=cfg.contrarian_tool_budget + 2,
            tool_calls_limit=cfg.contrarian_tool_budget,
        )
        result = await asyncio.wait_for(
            contrarian_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            ),
            timeout=cfg.agent_timeout,
        )
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.CONTRARIAN,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=DESK_SUCCESS_CONFIDENCE,
        )
    except TimeoutError:
        logger.warning("Contrarian desk query timed out after %.1fs", cfg.agent_timeout)
        return DeskResponse(
            desk=DeskType.CONTRARIAN,
            response="Query timed out. Please try a simpler question.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    except Exception as exc:
        logger.warning("Contrarian desk query failed: %s", exc)
        return DeskResponse(
            desk=DeskType.CONTRARIAN,
            response="An internal error occurred processing your query.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )


# ---------------------------------------------------------------------------
# Recommendation agent — structured ``ContrarianAssessment`` output
# ---------------------------------------------------------------------------

contrarian_desk_recommend: Agent[DeskDeps, ContrarianAssessment] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=ContrarianAssessment,
    retries=2,
    tools=build_contrarian_toolset(),  # type: ignore[arg-type]
)


@contrarian_desk_recommend.system_prompt(dynamic=True)
async def _contrarian_recommend_prompt(ctx: RunContext[DeskDeps]) -> str:
    """Return the contrarian recommendation prompt with learned patterns."""
    base = RECOMMEND_CONTRARIAN_PROMPT
    if ctx.deps.learned_patterns:
        base += f"\n\n{ctx.deps.learned_patterns}"
    return base


@contrarian_desk_recommend.output_validator
async def _clean_contrarian_assessment(
    ctx: RunContext[DeskDeps],  # noqa: ARG001
    output: ContrarianAssessment,
) -> ContrarianAssessment:
    """Strip ``<think>`` tags from structured assessment fields."""
    return build_cleaned_domain_assessment(output)


def _build_contrarian_recommend_fallback(deps: DeskDeps) -> ContrarianAssessment:
    """Build a low-confidence fallback ``ContrarianAssessment``."""
    return ContrarianAssessment(
        desk=DeskType.CONTRARIAN,
        direction=SignalDirection.NEUTRAL,
        confidence=0.2,
        summary=f"Contrarian assessment unavailable for {deps.ticker}",
        key_factors=["Assessment unavailable"],
        risks=["Unable to analyze contrarian view"],
        contracts_referenced=[],
        tools_used=list(deps.tools_used),
        model_used="data-driven-fallback",
        consensus_challenged=None,
        contrarian_thesis=None,
    )


async def run_contrarian_desk_recommendation(
    deps: DeskDeps,
    *,
    model: Model | None = None,
    model_settings: ModelSettings | None = None,
    config: AgencyConfig | None = None,
) -> ContrarianAssessment:
    """Run the contrarian recommendation agent — never raises.

    Returns a ``ContrarianAssessment`` on success or a low-confidence fallback
    on any failure (no model, timeout, exception).
    """
    cfg = config or AgencyConfig()
    if model is None:
        logger.warning("Contrarian desk recommendation called without a model")
        return _build_contrarian_recommend_fallback(deps)
    try:
        limits = UsageLimits(
            request_limit=cfg.contrarian_tool_budget + 2,
            tool_calls_limit=cfg.contrarian_tool_budget,
        )
        result = await asyncio.wait_for(
            contrarian_desk_recommend.run(
                deps.query,
                model=model,
                deps=deps,
                usage_limits=limits,
                model_settings=model_settings,
            ),
            timeout=cfg.agent_timeout,
        )
        return result.output
    except TimeoutError:
        logger.warning("Contrarian desk recommendation timed out after %.1fs", cfg.agent_timeout)
        return _build_contrarian_recommend_fallback(deps)
    except Exception as exc:
        logger.warning("Contrarian desk recommendation failed: %s", exc)
        return _build_contrarian_recommend_fallback(deps)
