"""Agent prompt library — all system prompts for Options Arena debate agents."""

from options_arena.agents.prompts.contrarian_agent import CONTRARIAN_SYSTEM_PROMPT
from options_arena.agents.prompts.desk_volatility import DESK_VOLATILITY_PROMPT
from options_arena.agents.prompts.flow_agent import FLOW_SYSTEM_PROMPT
from options_arena.agents.prompts.fundamental_agent import FUNDAMENTAL_SYSTEM_PROMPT
from options_arena.agents.prompts.risk import RISK_SYSTEM_PROMPT
from options_arena.agents.prompts.trend_agent import TREND_SYSTEM_PROMPT
from options_arena.agents.prompts.volatility import VOLATILITY_SYSTEM_PROMPT

__all__ = [
    "CONTRARIAN_SYSTEM_PROMPT",
    "DESK_VOLATILITY_PROMPT",
    "FLOW_SYSTEM_PROMPT",
    "FUNDAMENTAL_SYSTEM_PROMPT",
    "RISK_SYSTEM_PROMPT",
    "TREND_SYSTEM_PROMPT",
    "VOLATILITY_SYSTEM_PROMPT",
]
