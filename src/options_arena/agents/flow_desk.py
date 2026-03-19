"""Flow desk agent for interactive mode.

Distinct from the debate-mode flow agent (``flow_agent.py``). Returns plain
``str`` output (no structured Pydantic model), uses tool wrappers via the toolset
builder, and enforces a tool-call budget via ``UsageLimits``.

Architecture:
- ``flow_desk``: Module-level ``Agent[DeskDeps, str]`` instance (``model=None``).
- ``run_flow_desk_query()``: Wraps ``flow_desk.run()`` with timeout, think-tag
  stripping, and never-raises error handling.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import strip_think_tags
from options_arena.agents._toolsets import DESK_SUCCESS_CONFIDENCE, build_flow_toolset
from options_arena.agents.prompts.desk_flow import DESK_FLOW_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType

logger = logging.getLogger(__name__)

flow_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_flow_toolset(),  # type: ignore[arg-type]
)


@flow_desk.system_prompt(dynamic=True)
async def _flow_desk_prompt(ctx: RunContext[DeskDeps]) -> str:  # noqa: ARG001
    """Return the flow desk system prompt."""
    return DESK_FLOW_PROMPT


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
