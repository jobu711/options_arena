"""Options Arena — AI Debate Agents.

Re-exports the public API for the agents package. Agents and orchestrator
are added by subsequent tasks (#67, #63).
"""

from options_arena.agents._parsing import DebateDeps, DebateResult, render_context_block
from options_arena.agents.model_config import build_ollama_model

__all__ = [
    "DebateDeps",
    "DebateResult",
    "build_ollama_model",
    "render_context_block",
]
