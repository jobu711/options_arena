"""Options Arena — AI Debate Agents.

Re-exports the public API for the agents package: orchestrator entry points,
debate data structures, model configuration, and context rendering.
"""

from options_arena.agents._parsing import (
    DebateDeps,
    DebateResult,
    render_context_block,
    render_flow_context,
    render_fundamental_context,
    render_trend_context,
    render_volatility_context,
)
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    DebatePhase,
    DebateProgressCallback,
    build_market_context,
    classify_macd_signal,
    compute_agreement_score,
    compute_auto_tune_weights,
    effective_batch_ticker_delay,
    extract_agent_predictions,
    run_debate,
    should_debate,
    synthesize_verdict,
)
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.volatility import volatility_agent

__all__ = [
    "AGENT_VOTE_WEIGHTS",
    "DebateDeps",
    "DebatePhase",
    "DebateProgressCallback",
    "DebateResult",
    "build_debate_model",
    "build_market_context",
    "classify_macd_signal",
    "compute_agreement_score",
    "compute_auto_tune_weights",
    "effective_batch_ticker_delay",
    "extract_agent_predictions",
    "contrarian_agent",
    "flow_agent",
    "fundamental_agent",
    "render_context_block",
    "render_flow_context",
    "render_fundamental_context",
    "render_trend_context",
    "render_volatility_context",
    "run_debate",
    "should_debate",
    "synthesize_verdict",
    "trend_agent",
    "volatility_agent",
]
