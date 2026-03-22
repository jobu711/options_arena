"""Typed tool response wrapper for structured agent tool outputs.

``ToolResponse[T]`` replaces raw strings as tool return values, giving agents
structured status, summary text, optional typed data, and suggested next actions.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from options_arena.models.enums import ToolStatus


class ToolResponse[T](BaseModel):
    """Immutable result envelope returned by every agent tool.

    Parameters
    ----------
    status
        Outcome of the tool call (success / warning / error).
    summary
        Human-readable one-liner the LLM can use directly.
    data
        Typed payload; ``None`` when ``status`` is ``ERROR``.
    next_actions
        Optional list of follow-up tool calls the agent should consider.
    """

    model_config = ConfigDict(frozen=True)

    status: ToolStatus
    summary: str
    data: T | None = None
    next_actions: list[str] = Field(default_factory=list)
