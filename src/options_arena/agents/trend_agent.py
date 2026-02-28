"""Trend agent for Options Arena AI debate.

Direction-agnostic momentum and trend analysis. Replaces the Bull agent in the
6-agent protocol (``run_debate_v2``). Analyzes ADX, SuperTrend, SMA alignment,
RSI, and other trend/momentum signals without bullish or bearish bias.

Architecture rules:
- No inter-agent imports (never imports bull.py, bear.py, risk.py, etc.).
- model=None at init; actual GroqModel passed at agent.run(model=...) time.
- No data fetching (no httpx, yfinance, or service imports).
- No pricing imports (Greeks arrive pre-computed on contracts).
"""

import logging

from pydantic_ai import Agent, RunContext

from options_arena.agents._parsing import (
    DebateDeps,
    build_cleaned_agent_response,
)
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.models import AgentResponse

logger = logging.getLogger(__name__)

trend_agent: Agent[DebateDeps, AgentResponse] = Agent(
    model=None,
    deps_type=DebateDeps,
    output_type=AgentResponse,
    retries=2,
)


@trend_agent.system_prompt
def trend_system_prompt() -> str:
    """Return the trend agent system prompt.

    Static prompt -- trend agent does not depend on prior agent outputs.
    """
    return TREND_SYSTEM_PROMPT


@trend_agent.output_validator
async def clean_think_tags(
    ctx: RunContext[DebateDeps],
    output: AgentResponse,
) -> AgentResponse:
    """Strip ``<think>`` tags from LLM output via shared helper."""
    return build_cleaned_agent_response(output)
