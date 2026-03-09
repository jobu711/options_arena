"""Prompt templates for Options Arena debate agents."""

from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT

__all__ = [
    "CONTRARIAN_SYSTEM_PROMPT",
    "TREND_SYSTEM_PROMPT",
    "VOLATILITY_SYSTEM_PROMPT",
]
