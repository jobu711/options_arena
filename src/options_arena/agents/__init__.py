"""Options Arena — AI Debate Agents.

Re-exports the public API for the agents package: orchestrator entry points,
debate data structures, model configuration, and context rendering.
"""

from options_arena.agents._desk_deps import (
    DeskDeps as DeskDeps,  # noqa: PLC0414 -- explicit re-export
)
from options_arena.agents._parsing import (
    DebateDeps,
    DebateResult,
    render_context_block,
    render_flow_context,
    render_fundamental_context,
    render_macro_context,
    render_trend_context,
    render_volatility_context,
)
from options_arena.agents._routing import classify_intent, run_agency_query
from options_arena.agents._toolsets import (
    build_contrarian_toolset,
    build_flow_toolset,
    build_fundamental_toolset,
    build_risk_toolset,
    build_trend_toolset,
    build_volatility_toolset,
)
from options_arena.agents.contrarian_agent import contrarian_agent
from options_arena.agents.contrarian_desk import contrarian_desk, run_contrarian_desk_query
from options_arena.agents.flow_agent import flow_agent
from options_arena.agents.flow_desk import flow_desk, run_flow_desk_query
from options_arena.agents.fundamental_agent import fundamental_agent
from options_arena.agents.fundamental_desk import fundamental_desk, run_fundamental_desk_query
from options_arena.agents.model_config import build_debate_model
from options_arena.agents.orchestrator import (
    AGENT_VOTE_WEIGHTS,
    DebatePhase,
    DebateProgressCallback,
    VoteWeights,
    auto_tune_weights,
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
from options_arena.agents.risk_desk import risk_desk, run_risk_desk_query
from options_arena.agents.trend_agent import trend_agent
from options_arena.agents.trend_desk import run_trend_desk_query, trend_desk
from options_arena.agents.volatility import volatility_agent
from options_arena.agents.volatility_desk import run_vol_desk_query, vol_desk

__all__ = [
    "AGENT_VOTE_WEIGHTS",
    "DeskDeps",
    "VoteWeights",
    "classify_intent",
    "run_agency_query",
    "DebateDeps",
    "DebatePhase",
    "DebateProgressCallback",
    "DebateResult",
    "auto_tune_weights",
    "build_contrarian_toolset",
    "build_debate_model",
    "build_flow_toolset",
    "build_fundamental_toolset",
    "build_market_context",
    "build_risk_toolset",
    "build_trend_toolset",
    "build_volatility_toolset",
    "classify_macd_signal",
    "compute_agreement_score",
    "compute_auto_tune_weights",
    "contrarian_agent",
    "contrarian_desk",
    "effective_batch_ticker_delay",
    "extract_agent_predictions",
    "flow_agent",
    "flow_desk",
    "fundamental_agent",
    "fundamental_desk",
    "render_context_block",
    "render_flow_context",
    "render_fundamental_context",
    "render_macro_context",
    "render_trend_context",
    "render_volatility_context",
    "risk_desk",
    "run_contrarian_desk_query",
    "run_debate",
    "run_flow_desk_query",
    "run_fundamental_desk_query",
    "run_risk_desk_query",
    "run_trend_desk_query",
    "run_vol_desk_query",
    "should_debate",
    "synthesize_verdict",
    "trend_agent",
    "trend_desk",
    "vol_desk",
    "volatility_agent",
]
