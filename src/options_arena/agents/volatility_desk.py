"""Volatility desk agent for interactive mode.

Distinct from the debate-mode volatility agent (``volatility.py``). Returns plain
``str`` output (no structured Pydantic model), uses tool wrappers via the toolset
builder, and enforces a tool-call budget via ``UsageLimits``.

Architecture:
- ``vol_desk``: Module-level ``Agent[DeskDeps, str]`` instance (``model=None``).
- ``run_vol_desk_query()``: Wraps ``vol_desk.run()`` with timeout, think-tag
  stripping, and never-raises error handling.
"""

from __future__ import annotations

import asyncio
import logging

from pydantic_ai import Agent, RunContext
from pydantic_ai.usage import UsageLimits

from options_arena.agents._desk_deps import DeskDeps
from options_arena.agents._parsing import strip_think_tags
from options_arena.agents._toolsets import build_volatility_toolset
from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT
from options_arena.models import AgencyConfig, DeskResponse, DeskType

logger = logging.getLogger(__name__)

vol_desk: Agent[DeskDeps, str] = Agent(
    model=None,
    deps_type=DeskDeps,
    output_type=str,
    retries=2,
    tools=build_volatility_toolset(),  # type: ignore[arg-type]
)


@vol_desk.system_prompt(dynamic=True)
async def _vol_desk_prompt(ctx: RunContext[DeskDeps]) -> str:  # noqa: ARG001
    """Return the volatility desk system prompt."""
    return DESK_VOLATILITY_PROMPT


async def run_vol_desk_query(
    query: str,
    deps: DeskDeps,
    *,
    model: object | None = None,
    config: AgencyConfig | None = None,
) -> DeskResponse:
    """Run a volatility desk query with timeout and error handling.

    Returns a ``DeskResponse`` -- never raises.
    """
    cfg = config or AgencyConfig()
    try:
        limits = UsageLimits(request_limit=cfg.default_tool_budget + 2)
        if model is not None:
            coro = vol_desk.run(  # type: ignore[call-overload]
                query,
                model=model,
                deps=deps,
                usage_limits=limits,
            )
        else:
            coro = vol_desk.run(
                query,
                deps=deps,
                usage_limits=limits,
            )
        result = await asyncio.wait_for(coro, timeout=cfg.agent_timeout)
        output = strip_think_tags(result.output)
        return DeskResponse(
            desk=DeskType.VOLATILITY,
            response=output,
            tools_used=list(deps.tools_used),
            confidence=0.7,
        )
    except TimeoutError:
        logger.warning("Volatility desk query timed out after %.1fs", cfg.agent_timeout)
        return DeskResponse(
            desk=DeskType.VOLATILITY,
            response="Query timed out. Please try a simpler question.",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
    except Exception as exc:
        logger.warning("Volatility desk query failed: %s", exc)
        return DeskResponse(
            desk=DeskType.VOLATILITY,
            response=f"Error processing query: {exc}",
            tools_used=list(deps.tools_used),
            confidence=0.0,
        )
