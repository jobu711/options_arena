"""Options Arena — AI Agents.

Re-exports the public API for the agents package: recommendation orchestrator,
desk agents, synthesis agent, shared utilities, and routing.
"""

# ---------------------------------------------------------------------------
# Shared context utilities
# ---------------------------------------------------------------------------
from options_arena.agents._context import (
    DebatePhase as DebatePhase,
)
from options_arena.agents._context import (
    build_market_context as build_market_context,
)
from options_arena.agents._context import (
    classify_macd_signal as classify_macd_signal,
)
from options_arena.agents._context import (
    should_recommend as should_recommend,
)
from options_arena.agents._desk_deps import (
    DeskDeps as DeskDeps,  # noqa: PLC0414 -- explicit re-export
)

# ---------------------------------------------------------------------------
# Backward-compat rendering helpers (still used by desk/synthesis agents)
# ---------------------------------------------------------------------------
from options_arena.agents._parsing import (
    render_context_block as render_context_block,
)
from options_arena.agents._parsing import (
    render_flow_context as render_flow_context,
)
from options_arena.agents._parsing import (
    render_fundamental_context as render_fundamental_context,
)
from options_arena.agents._parsing import (
    render_macro_context as render_macro_context,
)
from options_arena.agents._parsing import (
    render_trend_context as render_trend_context,
)
from options_arena.agents._parsing import (
    render_volatility_context as render_volatility_context,
)

# ---------------------------------------------------------------------------
# Routing (agency interactive desk queries)
# ---------------------------------------------------------------------------
from options_arena.agents._routing import (
    classify_intent as classify_intent,
)
from options_arena.agents._routing import (
    run_agency_query as run_agency_query,
)

# ---------------------------------------------------------------------------
# Toolsets (per-desk + synthesis)
# ---------------------------------------------------------------------------
from options_arena.agents._toolsets import (
    build_contrarian_toolset as build_contrarian_toolset,
)
from options_arena.agents._toolsets import (
    build_flow_toolset as build_flow_toolset,
)
from options_arena.agents._toolsets import (
    build_fundamental_toolset as build_fundamental_toolset,
)
from options_arena.agents._toolsets import (
    build_research_toolset as build_research_toolset,
)
from options_arena.agents._toolsets import (
    build_risk_toolset as build_risk_toolset,
)
from options_arena.agents._toolsets import (
    build_synthesis_toolset as build_synthesis_toolset,
)
from options_arena.agents._toolsets import (
    build_trend_toolset as build_trend_toolset,
)
from options_arena.agents._toolsets import (
    build_volatility_toolset as build_volatility_toolset,
)

# ---------------------------------------------------------------------------
# Desk agents (7 desks — interactive + recommendation modes)
# ---------------------------------------------------------------------------
from options_arena.agents.contrarian_desk import (
    contrarian_desk as contrarian_desk,
)
from options_arena.agents.contrarian_desk import (
    run_contrarian_desk_query as run_contrarian_desk_query,
)
from options_arena.agents.contrarian_desk import (
    run_contrarian_desk_recommendation as run_contrarian_desk_recommendation,
)
from options_arena.agents.flow_desk import (
    flow_desk as flow_desk,
)
from options_arena.agents.flow_desk import (
    run_flow_desk_query as run_flow_desk_query,
)
from options_arena.agents.flow_desk import (
    run_flow_desk_recommendation as run_flow_desk_recommendation,
)
from options_arena.agents.fundamental_desk import (
    fundamental_desk as fundamental_desk,
)
from options_arena.agents.fundamental_desk import (
    run_fundamental_desk_query as run_fundamental_desk_query,
)
from options_arena.agents.fundamental_desk import (
    run_fundamental_desk_recommendation as run_fundamental_desk_recommendation,
)

# ---------------------------------------------------------------------------
# Model configuration + routing
# ---------------------------------------------------------------------------
from options_arena.agents.model_config import (
    build_debate_model as build_debate_model,
)
from options_arena.agents.model_routing import (
    build_model_for_tier as build_model_for_tier,
)
from options_arena.agents.model_routing import (
    route_model_tier as route_model_tier,
)

# ---------------------------------------------------------------------------
# Recommendation orchestrator (PRIMARY entry point)
# ---------------------------------------------------------------------------
from options_arena.agents.recommendation_orchestrator import (
    RecommendationProgressCallback as RecommendationProgressCallback,
)
from options_arena.agents.recommendation_orchestrator import (
    run_recommendation as run_recommendation,
)
from options_arena.agents.research_desk import (
    research_desk as research_desk,
)
from options_arena.agents.research_desk import (
    run_research_desk_query as run_research_desk_query,
)
from options_arena.agents.risk_desk import (
    risk_desk as risk_desk,
)
from options_arena.agents.risk_desk import (
    run_risk_desk_query as run_risk_desk_query,
)
from options_arena.agents.risk_desk import (
    run_risk_desk_recommendation as run_risk_desk_recommendation,
)

# ---------------------------------------------------------------------------
# Synthesis agent
# ---------------------------------------------------------------------------
from options_arena.agents.synthesis_agent import (
    SynthesisDeps as SynthesisDeps,
)
from options_arena.agents.synthesis_agent import (
    run_synthesis as run_synthesis,
)
from options_arena.agents.synthesis_agent import (
    synthesis_agent as synthesis_agent,
)
from options_arena.agents.trend_desk import (
    run_trend_desk_query as run_trend_desk_query,
)
from options_arena.agents.trend_desk import (
    run_trend_desk_recommendation as run_trend_desk_recommendation,
)
from options_arena.agents.trend_desk import (
    trend_desk as trend_desk,
)
from options_arena.agents.trend_desk import (
    trend_desk_recommend as trend_desk_recommend,
)
from options_arena.agents.volatility_desk import (
    run_vol_desk_query as run_vol_desk_query,
)
from options_arena.agents.volatility_desk import (
    run_vol_desk_recommendation as run_vol_desk_recommendation,
)
from options_arena.agents.volatility_desk import (
    vol_desk as vol_desk,
)
from options_arena.agents.volatility_desk import (
    vol_desk_recommend as vol_desk_recommend,
)

# ---------------------------------------------------------------------------
# Public API — recommendation-oriented
# ---------------------------------------------------------------------------
__all__ = [
    # --- Recommendation orchestrator (primary entry point) ---
    "RecommendationProgressCallback",
    "run_recommendation",
    # --- Context utilities ---
    "DebatePhase",
    "build_market_context",
    "classify_macd_signal",
    "should_recommend",
    # --- Desk agents (7 desks) ---
    "DeskDeps",
    "contrarian_desk",
    "flow_desk",
    "fundamental_desk",
    "research_desk",
    "risk_desk",
    "trend_desk",
    "trend_desk_recommend",
    "vol_desk",
    "vol_desk_recommend",
    # --- Desk query runners ---
    "run_contrarian_desk_query",
    "run_contrarian_desk_recommendation",
    "run_flow_desk_query",
    "run_flow_desk_recommendation",
    "run_fundamental_desk_query",
    "run_fundamental_desk_recommendation",
    "run_research_desk_query",
    "run_risk_desk_query",
    "run_risk_desk_recommendation",
    "run_trend_desk_query",
    "run_trend_desk_recommendation",
    "run_vol_desk_query",
    "run_vol_desk_recommendation",
    # --- Toolsets ---
    "build_contrarian_toolset",
    "build_debate_model",
    "build_model_for_tier",
    "route_model_tier",
    "build_flow_toolset",
    "build_fundamental_toolset",
    "build_research_toolset",
    "build_risk_toolset",
    "build_synthesis_toolset",
    "build_trend_toolset",
    "build_volatility_toolset",
    # --- Synthesis agent ---
    "SynthesisDeps",
    "run_synthesis",
    "synthesis_agent",
    # --- Routing (agency) ---
    "classify_intent",
    "run_agency_query",
    # --- Rendering helpers ---
    "render_context_block",
    "render_flow_context",
    "render_fundamental_context",
    "render_macro_context",
    "render_trend_context",
    "render_volatility_context",
]
