"""Agent prompt library — all system prompts for Options Arena debate agents."""

from options_arena.agents.prompts.bear import BEAR_SYSTEM_PROMPT
from options_arena.agents.prompts.bull import BULL_SYSTEM_PROMPT
from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.agents.prompts.flow_agent import FLOW_SYSTEM_PROMPT
from options_arena.agents.prompts.fundamental_agent import FUNDAMENTAL_SYSTEM_PROMPT
from options_arena.agents.prompts.risk import RISK_SYSTEM_PROMPT
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT

__all__ = [
    "BEAR_SYSTEM_PROMPT",
    "BULL_SYSTEM_PROMPT",
    "CONTRARIAN_SYSTEM_PROMPT",
    "FLOW_SYSTEM_PROMPT",
    "FUNDAMENTAL_SYSTEM_PROMPT",
    "RISK_SYSTEM_PROMPT",
    "TREND_SYSTEM_PROMPT",
    "VOLATILITY_SYSTEM_PROMPT",
]
