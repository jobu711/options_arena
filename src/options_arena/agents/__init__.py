"""Options Arena — AI Debate Agents.

Re-exports the public API for the agents package: orchestrator entry points,
debate data structures, model configuration, and context rendering.
"""

from options_arena.agents._parsing import DebateDeps, DebateResult, render_context_block
from options_arena.agents.model_config import build_debate_model, build_ollama_model
from options_arena.agents.orchestrator import build_market_context, run_debate, should_debate

__all__ = [
    "DebateDeps",
    "DebateResult",
    "build_debate_model",
    "build_market_context",
    "build_ollama_model",
    "render_context_block",
    "run_debate",
    "should_debate",
]
