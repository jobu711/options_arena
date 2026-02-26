"""Options Arena — AI Debate Agents.

Re-exports the public API for the agents package: orchestrator entry points,
debate data structures, model configuration, and context rendering.
"""

from options_arena.agents._parsing import DebateDeps, DebateResult, render_context_block
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.orchestrator import (
    DebatePhase,
    DebateProgressCallback,
    build_market_context,
    run_debate,
    should_debate,
)
from options_arena.agents.volatility import volatility_agent

__all__ = [
    "DebateDeps",
    "DebatePhase",
    "DebateProgressCallback",
    "DebateResult",
    "build_debate_model",
    "build_market_context",
    "render_context_block",
    "run_debate",
    "should_debate",
    "volatility_agent",
]
