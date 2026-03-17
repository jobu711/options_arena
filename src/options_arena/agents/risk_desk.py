"""Risk desk agent for interactive mode.

Distinct from the debate-mode risk agent (``risk.py``). Returns plain ``str``
output (no structured Pydantic model), uses tool wrappers via the toolset builder,
and enforces a higher tool-call budget (5) via ``UsageLimits``.

Architecture:
- ``risk_desk``: Module-level ``Agent[DeskDeps, str]`` instance (``model=None``).
- ``run_risk_desk_query()``: Wraps ``risk_desk.run()`` with timeout, think-tag
  stripping, and never-raises error handling.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import strip_think_tags
from options_arena.agents._toolsets import build_risk_toolset
from options_arena.agents.prompts.desk_risk import DESK_RISK_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType

logger = logging.getLogger(__name__)

risk_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_risk_toolset(),  # type: ignore[arg-type]
)


@risk_desk.system_prompt(dynamic=True)
async def _risk_desk_prompt(ctx: RunContext[DeskDeps]) -> str:  # noqa: ARG001
    """Return the risk desk system prompt."""
    return DESK_RISK_PROMPT


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
    try:
        limits = UsageLimits(request_limit=cfg.risk_tool_budget + 2)
        if model is not None:
            coro = risk_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            )
        else:
            coro = risk_desk.run(
                query,
                deps=deps,
                usage_limits=limits,
            )
        result = await asyncio.wait_for(coro, timeout=cfg.agent_timeout)
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.RISK,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=0.7,
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
            response=f"Error processing query: {exc}",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
