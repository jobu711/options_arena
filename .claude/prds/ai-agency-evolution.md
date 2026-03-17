---
name: ai-agency-evolution
description: Evolve Options Arena into an AI advisory agency with specialized desks, interactive routing, and self-improving behavior
status: planned
created: 2026-03-14T03:03:29Z
revised: 2026-03-17T14:10:53Z
revision_notes: Added analysis/ and indicators/ tool enrichment for desks (Epics 7-8), revised desk descriptions, re-phased to 8 epics, updated Cross-PRD section (scientific-ml now merged)
---

# PRD: ai-agency-evolution

## Executive Summary

Transform Options Arena from a batch analysis tool into an AI advisory agency — a team of specialized "desk" agents (Volatility, Risk, Flow, Fundamental, Trend, Contrarian, Research) coordinated by an Advisor agent that routes queries and synthesizes multi-desk responses. Each desk is a **separate PydanticAI Agent instance** from the existing debate agent, with its own `DeskDeps` dependency type and `str` output for conversational responses. A three-phase self-improvement engine progressively tunes weights, evolves prompts, and mines strategy patterns from historical outcomes.

## Problem Statement

### What problem are we solving?

Options Arena currently operates as a **batch pipeline tool**: users trigger scans, launch debates, and read reports. There is no persistent advisory relationship — the system has no memory between sessions, no ability to answer ad-hoc questions, and no mechanism to learn from its own track record. Users must manually connect the dots between scan results, debate outputs, and outcome data.

### Why is this important now?

The foundation is ready. Options Arena already has:
- 6 agent modules (trend, volatility, flow, fundamental, risk, contrarian) running a 6-agent debate pipeline with structured outputs and independent judgment
- Outcome tracking with P&L at T+1/5/10/20 and agent accuracy heatmaps
- Auto-tuning infrastructure (`compute_auto_tune_weights()`) that derives vote weights from accuracy
- Background task infrastructure (operation mutex, WebSocket progress)
- PydanticAI's `FunctionToolset` capability — agents CAN use tools via injectable toolsets, enabling clean separation between debate and interactive modes
- **Scientific ML pipeline** (v2.10.0): GARCH/EGARCH vol forecasting, Markov-switching regime detection, FRED macro regime classification, Hurst exponent — all with guarded imports and `[ml]` optional extra
- **Competitive analysis modules** (`analysis/`): DCF/DDM/Graham/residual income valuation, correlation matrices, risk-adjusted performance metrics (Sharpe, Sortino, Calmar), Kelly criterion position sizing — all pure math, no optional deps
- **9 functions wrapped as desk tools** (from 21 toolifiable candidates across `analysis/` and `indicators/`) via `FunctionToolset` — 5 in Epic 7 (pure math), 4 in Epic 8 (statistical/ML)

The pieces exist. This PRD assembles them into an agency.

## User Stories

### Advisory Interaction
- **As a trader**, I want to ask "What's the best play on AAPL right now?" and get a synthesized answer from multiple specialist desks, so I don't have to run a full scan + debate just for one question.
  - *Acceptance*: Query returns within 30s, cites specific data points, includes confidence score.

- **As a power user**, I want to directly ask the Volatility Desk "Analyze TSLA's term structure" for deep domain expertise, so I can get focused analysis without routing overhead.
  - *Acceptance*: Direct desk queries bypass Advisor routing, return desk-specific conversational output.

### Self-Improvement
- **As a user who tracks outcomes**, I want the system to automatically tune its indicator and vote weights based on which signals actually predicted profitable trades, so recommendations improve over time.
  - *Acceptance*: Weights update after each outcome collection batch (minimum 50 samples). Weight history is viewable.

- **As a user**, I want the system to discover patterns in its own wins and losses (e.g., "bearish high-IV tech in earnings week has 62% loss rate") and surface them as strategy rules I can approve or reject.
  - *Acceptance*: Rules require human approval before affecting recommendations. Rules show sample size, win rate, avg return.

## Architecture & Design

### Chosen Approach: Evolve-in-Place

Create separate desk Agent instances alongside the existing 6-agent debate pipeline. Add Advisor agent for routing and learning module for self-improvement. The debate system remains untouched — desk agents share domain expertise via prompts but are independent PydanticAI Agent instances with their own deps, output type, and toolsets.

**Why this approach**: Maximizes reuse of existing agent domain expertise and service layer. Zero regression risk to the debate pipeline — existing agents are never modified. Every self-improvement gain benefits both debates (via weight/prompt tuning) and direct queries.

### Module Changes

| Module | Change | Boundary Compliance |
|--------|--------|-------------------|
| `agents/` | New desk agent instances (`*_desk.py`) with `FunctionToolset`. New `advisor.py`, `research_desk.py`, `_routing.py`. Existing debate agents untouched. | Yes — desk agents access services via DeskDeps |
| `agents/prompts/` | New `desk_*.py` prompt files for interactive mode. Prompt versioning system (SQLite-backed) for desk prompts only. | Yes — prompts/ manages prompt text |
| `models/` | New models: `AgencyQuery`, `DeskResponse`, `Citation`, `PromptVersion`, `StrategyRule`, enums. Extend existing `WeightSnapshot`. | Yes — data shapes only |
| `data/` | Migrations 034-037 for agency tables + new repository mixin (`AgencyMixin`) | Yes — persistence only |
| `learning/` | **New module**: weight tuner, prompt lab, strategy book | Accesses: `models/`, `data/`, `scoring/`, `agents/prompts/` (text only) |
| `api/` | New route groups: `/api/agency/*`, `/api/learning/*` | Yes — top of stack |
| `cli/` | New `agency` subcommand group | Yes — top of stack |
| `services/` | Minor convenience methods for desk tool-use | Yes — external API access |

### Boundary Table Addition

| Module | Responsibility | Can Access | Cannot Access |
|--------|---------------|------------|---------------|
| `learning/` | Weight tuning, prompt lab, strategy mining | `models/`, `data/`, `scoring/`, `agents/prompts/` (text only) | `agents/` (instances/orchestrator), `services/`, `pricing/`, `cli/`, `api/` |

Key rules:
- `learning/` accesses `agents/prompts/` for prompt text only — never imports agent instances or orchestrator
- Auto-tune logic (`compute_auto_tune_weights`) relocates from `agents/orchestrator.py` to `learning/weight_tuner.py`
- `learning/` is a middle-stack module, NOT top-of-stack

### Data Models

#### Agency Interaction

```python
class DeskType(StrEnum):
    TREND = "trend"
    VOLATILITY = "volatility"
    FLOW = "flow"
    FUNDAMENTAL = "fundamental"
    RISK = "risk"
    CONTRARIAN = "contrarian"
    RESEARCH = "research"

class QueryType(StrEnum):
    ANALYSIS = "analysis"
    COMPARISON = "comparison"
    STRATEGY = "strategy"
    RISK_CHECK = "risk_check"
    GENERAL = "general"

class QueryIntent(BaseModel):
    model_config = ConfigDict(frozen=True)
    desks: list[DeskType]
    query_type: QueryType
    tickers: list[str]

class AgencyQuery(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str                          # UUID for correlation
    query: str                             # Natural language question
    desk: DeskType | None = None           # Direct desk mode (bypass Advisor)
    tickers: list[str] | None = None       # Override auto-extraction

class Citation(BaseModel):
    model_config = ConfigDict(frozen=True)
    desk: DeskType
    label: str          # e.g., "IV Rank", "RSI", "52-week range"
    value: str          # e.g., "78.5", "BULLISH", "$185.50"
    source: str         # e.g., "yfinance", "computed", "FRED"

class DeskResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    desk: DeskType
    response: str
    tools_used: list[str]
    confidence: float  # 0.0-1.0, field_validator + isfinite

class AgencyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str
    desk_responses: list[DeskResponse]
    synthesis: str
    citations: list[Citation]
    confidence: float  # 0.0-1.0, field_validator + isfinite

@dataclass
class DeskDeps:
    """Injected into desk agents for interactive queries."""
    query: str                              # User's question
    ticker: str                             # Primary ticker
    market_data: MarketDataService          # Live quote/OHLCV access
    options_data: OptionsDataService        # Chain/IV access
    fred: FredService                       # Risk-free rate
    repo: Repository                        # Historical data access
    tool_call_budget: int = 3               # Max tool calls allowed
    tools_used: list[str] = field(default_factory=list)  # Accumulator
```

#### Self-Improvement

```python
class PromptVersion(BaseModel):
    model_config = ConfigDict(frozen=True)
    version_id: str
    agent_name: str               # Desk agent name only (not debate agents)
    prompt_hash: str
    is_active: bool
    sample_count: int = 0
    accuracy: float | None = None

class RuleStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"

class ConditionOperator(StrEnum):
    EQ = "eq"
    GT = "gt"
    LT = "lt"
    GTE = "gte"
    LTE = "lte"
    IN = "in"

class StrategyCondition(BaseModel):
    model_config = ConfigDict(frozen=True)
    field: str                    # e.g. "sector", "iv_rank_bucket", "dte_bucket", "direction"
    operator: ConditionOperator   # StrEnum, not raw str
    value: str                    # string-encoded, parsed per operator

class StrategyRule(BaseModel):
    model_config = ConfigDict(frozen=True)
    rule_id: str
    pattern: str
    conditions: list[StrategyCondition]  # typed model, not raw dict
    win_rate: float
    avg_return: float
    sample_size: int
    status: RuleStatus

class AgentMemory(BaseModel):
    model_config = ConfigDict(frozen=True)
    memory_id: str                     # UUID
    agent_name: str                    # Desk agent name (e.g., "volatility", "risk")
    scope: str                         # Scoping key (e.g., "AAPL", "Technology", "high_vol")
    scope_type: str                    # "ticker", "sector", or "regime"
    content: str                       # Human-readable pattern text
    sample_size: int                   # Number of outcomes supporting this memory
    win_rate: float                    # 0.0-1.0, field_validator + isfinite
    created_at: datetime               # UTC validator required

class WeightType(StrEnum):
    VOTE = "vote"
    INDICATOR = "indicator"

# NOTE: Extends the existing WeightSnapshot model in models/analytics.py.
# Add `weight_type: WeightType` and `accuracy_at_time: float | None` fields
# to the existing model rather than creating a new one.
# The existing `AgentWeightsComparison` already has name/value fields that
# serve the same purpose as WeightEntry — reuse those.
```

#### Migrations

| Number | Table | Purpose |
|--------|-------|---------|
| 034 | `agency_queries` | Query persistence for audit trail |
| 035 | `prompt_versions` | Desk prompt variant tracking + accuracy |
| 036 | `strategy_rules`, `agent_memory` | Strategy mining + short/long-term memory |
| 037 | `weight_snapshots` (alter) | Add `weight_type`, `accuracy_at_time` columns |

All models follow project conventions: `frozen=True`, UTC validators on datetimes, `math.isfinite()` on numerics, confidence clamped `[0.0, 1.0]`, `StrEnum` for categoricals.

### Tool Scoping Map

Each desk receives only domain-relevant tools, preventing cross-domain hallucination
(pattern from TradingAgents). Tools are organized in three tiers:

- **Base tools** (Epics 1-3): Wrap `services/` methods — async, require DeskDeps service fields
- **Analysis tools** (Epic 7): Wrap `analysis/` functions — pure math, no optional deps, always available
- **ML tools** (Epic 8): Wrap `indicators/` ML functions — require `[ml]` extra (`arch`, `statsmodels`), conditionally registered

Tool call budget: 3 per specialist desk, **5 for Risk** (correlation + position sizing), 5 for Research.

```
Desk            Base Tools (Epics 1-3)               Analysis Tools (Epic 7)             ML Tools (Epic 8)
                                                     [always available]                   [requires [ml] extra]
─────────────── ──────────────────────────────────── ─────────────────────────────────── ───────────────────────────────
Trend           fetch_quote,                         —                                   compute_hurst_exponent,
                fetch_related_ohlcv,                                                     compute_markov_regime
                compute_indicator_on_demand

Volatility      fetch_quote,                         compute_hv_yang_zhang               compute_garch_forecast
                fetch_vol_surface_slice,
                compute_iv_for_strike

Flow            fetch_quote,                         —                                   —
                fetch_chain_summary,
                fetch_unusual_activity

Fundamental     fetch_quote,                         compute_composite_valuation         compute_macro_regime
                fetch_earnings_history,
                fetch_sector_comparison

Risk            fetch_quote,                         compute_position_size,              compute_macro_regime,
                fetch_correlation,                   compute_risk_adjusted_metrics,      compute_markov_regime
                fetch_portfolio_exposure             compute_correlation_matrix

Contrarian      fetch_quote,                         —                                   —
                fetch_debate_history

Research        fetch_quote,                         compute_composite_valuation,        compute_garch_forecast,
                fetch_iv_snapshot,                   compute_position_size,              compute_macro_regime,
                fetch_chain_summary,                 compute_hv_yang_zhang               compute_hurst_exponent
                fetch_earnings_date,
                compute_indicator_on_demand,
                fetch_debate_history
```

**Tool counts per desk** (base + analysis + ML): Trend 3+0+2=5, Volatility 3+1+1=5, Flow 3+0+0=3, Fundamental 3+1+1=5, Risk 3+3+2=8, Contrarian 2+0+0=2, Research 6+3+3=12.

Research desk rationale: curated subset of cross-domain tools (12 total), not "all tools from all desks" — prevents a god-agent. Budget: 5 tool calls (agents must prioritize).

### Desk Capability Descriptions

Each desk's analytical scope, reflecting full enrichment across all three tool tiers:

- **Trend**: Price momentum + directional analysis. Base: OHLCV-derived indicators, SMA alignment. ML: Hurst exponent (mean-reversion vs trending), Markov regime detection (regime-aware trend confidence).
- **Volatility**: IV surface + vol forecasting. Base: IV rank/percentile, term structure. Analysis: Yang-Zhang HV (drift-independent realized vol). ML: GARCH forecast (forward-looking vol estimate).
- **Flow**: Options flow + microstructure. Put/call ratios, unusual activity, GEX. No analysis/ML tools — domain is data-observation, not computation.
- **Fundamental**: Equity valuation + macro context. Base: earnings, sector comparison. Analysis: Composite valuation (Owner Earnings DCF, Three-Stage DCF, EV/EBITDA relative, Residual Income — 4-model ensemble with waterfall weighting). ML: Macro regime classification (expansionary/contractionary/transitional from FRED data).
- **Risk**: Portfolio risk quantification — the most tool-rich desk. Base: correlation, exposure. Analysis: Position sizing (Kelly criterion, vol-regime-aware 4-tier allocation), risk-adjusted metrics (Sharpe, Sortino, Calmar, max drawdown), correlation matrix (multi-asset log-return Pearson). ML: Macro regime, Markov regime.
- **Contrarian**: Dissent + historical pattern challenge. Deliberately tool-light (2 tools). Debates prior analysis rather than running its own computations.
- **Research**: Cross-domain synthesis with curated tools from all tiers (12 tools, budget 5). The generalist that can pull from any domain for open-ended queries.

### Graceful Tool Degradation

Tool availability is runtime-detected. Each `FunctionToolset` registers tools conditionally:

- **Base tools** (Epics 1-3): Always available — wrap `services/` methods
- **Analysis tools** (Epic 7): Always available — pure math, no optional deps
- **ML tools** (Epic 8): Registered only when `[ml]` extra is installed. If `arch`/`statsmodels` import fails at tool registration time, the tool is omitted from the toolset (not registered as a no-op)

Desk behavior: agents work with whatever tools are registered. Fewer tools = narrower analysis, not failure. Each desk's system prompt includes a `<<<AVAILABLE_TOOLS>>>` block listing what's actually registered, so the agent doesn't hallucinate tool calls for unavailable tools.

Tool registration pattern:
```python
def build_volatility_toolset() -> FunctionToolset:
    """Build toolset for Volatility desk. ML tools conditionally included."""
    toolset = FunctionToolset()
    # Base tools — always registered
    toolset.tool(fetch_quote)
    toolset.tool(fetch_vol_surface_slice)
    toolset.tool(compute_iv_for_strike)
    # Analysis tools — always registered (no optional deps)
    toolset.tool(compute_hv_yang_zhang_tool)
    # ML tools — conditionally registered
    try:
        from options_arena.indicators.vol_forecast import compute_garch_forecast
        toolset.tool(compute_garch_forecast_tool)
    except ImportError:
        pass  # [ml] extra not installed — desk works without GARCH
    return toolset
```

### Tool Return Convention

Tools return **formatted strings**, not raw Pydantic models (FinRobot pattern):
- Convention: `f"{label}: {value}"` per data point, newline-separated
- Error cases return `f"Error: {message}"` — never raise exceptions
- Each tool appends its name to `ctx.deps.tools_used` before returning

```python
@desk_toolset.tool
async def fetch_iv_snapshot(ctx: RunContext[DeskDeps], ticker: str) -> str:
    """Fetch current IV rank, percentile for a ticker."""
    ctx.deps.tools_used.append("fetch_iv_snapshot")
    data = await ctx.deps.options_data.fetch_iv_data(ticker)
    if data is None:
        return f"Error: IV data unavailable for {ticker}"
    return f"IV Rank: {data.iv_rank:.1f}\nIV Percentile: {data.iv_percentile:.1f}\n..."
```

### Interactive Mode Prompts

Desk agents use **separate system prompts** from debate agents:
- Stored in `agents/prompts/desk_*.py` (e.g., `desk_volatility.py`, `desk_risk.py`)
- Interactive prompts are shorter (~2000 chars), conversational, tool-use-oriented
- No `PROMPT_RULES_APPENDIX` (designed for structured output, not conversation)
- Mode-specific context injected via `instructions=` parameter at `run()` time
- `<think>` tag stripping handled post-`run()` via helper function (not `@output_validator` — desk agents have `output_type=str`, no validator needed)

### Core Logic

#### Separate Agent Instances (Debate vs Desk)

PydanticAI enforces a single `deps_type` and `output_type` per Agent instance. When `@output_validator` is registered (as on all 6 debate agents), `output_type` override at run time raises `UserError`. This means the PRD's original "same Agent instance in two modes" design is **architecturally impossible**.

**Resolution: Create dedicated desk Agent instances alongside existing debate agents.**

```python
# Architecture: Separate Agent Instances per Mode
#
# Debate mode (existing, UNTOUCHED — zero regression risk):
#   trend_agent: Agent[DebateDeps, AgentResponse]        # structured thesis
#   vol_agent: Agent[DebateDeps, VolatilityThesis]       # structured thesis
#   flow_agent: Agent[DebateDeps, AgentResponse]         # structured thesis
#   fund_agent: Agent[DebateDeps, AgentResponse]         # structured thesis
#   risk_agent: Agent[DebateDeps, RiskAssessment]        # structured thesis
#   contrarian_agent: Agent[DebateDeps, AgentResponse]   # structured thesis
#
# Interactive desk mode (NEW):
#   trend_desk: Agent[DeskDeps, str]                     # conversational
#   vol_desk: Agent[DeskDeps, str]                       # conversational
#   flow_desk: Agent[DeskDeps, str]                      # conversational
#   fund_desk: Agent[DeskDeps, str]                      # conversational
#   risk_desk: Agent[DeskDeps, str]                      # conversational
#   contrarian_desk: Agent[DeskDeps, str]                # conversational
#   research_desk: Agent[DeskDeps, str]                  # conversational (new)
#
# Tools injected via FunctionToolset at run() time for testability:
#   result = await vol_desk.run(
#       prompt, deps=desk_deps,
#       toolsets=[vol_toolset],
#       usage_limits=UsageLimits(tool_calls_limit=3),
#       instructions=mode_specific_context,
#       model=build_debate_model(provider),
#   )
```

**Why separate instances (Path A) over alternatives:**
- **Path B** (superset deps + union output): Requires removing `@output_validator` from all debate agents, re-introducing `<think>` tag bleed-through for Llama 3.x. Unacceptable regression risk.
- **Path C** (keep structured output for interactive): Forces unnatural structured-thesis output for conversational queries. Poor UX.
- **Path A** (separate instances): Zero changes to debate agents. Clean type safety. Tools injected via `FunctionToolset` at run time for testability.

PydanticAI features that enable this cleanly:
- `FunctionToolset` — standalone tool collections, passable at `run(toolsets=[...])` time
- `UsageLimits(tool_calls_limit=N)` — enforces tool call budget
- `instructions=` parameter on `run()` — mode-specific context without changing system prompt
- `model=None` at init, actual model at `run(model=...)` — enables `TestModel` for testing

#### Advisor Routing Flow

```
User query
  -> Advisor classifies intent (desks + query_type + tickers)
  -> Parallel dispatch to relevant desk(s) via asyncio.gather
  -> Collect DeskResponses
  -> Advisor synthesizes into unified AgencyResponse
  -> Return to user (with citations + confidence)
```

Intent classification: rule-based for V1 (keyword matching + ticker extraction via regex). Upgradeable to LLM-based later.

#### Self-Improvement (3 Phases)

| Phase | Trigger | Input | Output | Min Samples |
|-------|---------|-------|--------|-------------|
| 1: Weight Tuning | After outcome collection | Historical outcomes | Updated vote + indicator weights | 50 |
| 2: Prompt A/B | Continuous during desk queries | Desk queries tagged with prompt version | Promoted prompt variant | 30 per variant |
| 3: Strategy Mining | Manual CLI/API trigger | All historical outcomes | StrategyRule candidates | 100 total (20 per pattern cell) |

**Phase 1 — Weight Tuning** (FinRL pattern): Extends existing `compute_auto_tune_weights()` to cover indicator weights (not just vote weights). Key insight from FinRL: composite score calibration should be driven by historical returns, not hand-tuned constants. Existing infrastructure that just needs connecting:
- `AgentAccuracyReport` — per-agent direction hit rate + Brier score
- `CalibrationBucket` — confidence calibration curves
- `compute_auto_tune_weights()` — inverse-Brier vote weights
- `WeightSnapshot` — weight history tracking (extended with `weight_type` and `accuracy_at_time`)
- `auto_tune_weights()` — full accuracy -> weights -> persist flow

**Phase 2 — Prompt A/B Testing** (FinGPT evaluation methodology):
- **Scope**: Desk agent prompts ONLY. Debate agent prompts remain static module-level constants (no A/B on debate prompts in V1).
- **Injection mechanism**: All desk agent system prompts use `dynamic=True` with prompt text loaded from DB via `PromptVersion`.
- **Selection**: `learning/prompt_lab.py` queries active variants, assigns via round-robin to ensure balanced sampling.
- **Comparison**: After 30+ samples per variant, Wilcoxon signed-rank test on response quality (citation density + user feedback if available).
- **Rollback**: If new prompt degrades below baseline, auto-revert to previous active version.

**Phase 3 — Strategy Mining** (FinMem three-tier memory + optopsy metrics):
- **Trigger**: Manual — CLI command `options-arena agency learn mine` or `POST /api/learning/mine`. Not a cron job; user controls when mining runs.
- **Minimum data**: 100 total outcomes before mining is available. Per-cell minimum is 20 after grouping by dimensions.
- **Short-term (working)**: Recent debates for same ticker/sector from `ai_theses` table. Rendered as context in agent prompts.
- **Long-term (patterns)**: `agent_memory` SQLite table, scoped by agent + ticker/sector/regime. Example: "When IV Rank >80 in Technology, bearish puts outperform by 12% (n=67)".
- **Reflective (meta-learning)**: Groups outcomes by dimensions (sector x IV bucket x DTE bucket x direction). Chi-squared test for significance, minimum 20 samples per pattern. Generates `StrategyRule` candidates for human approval.
- **Evaluation metrics** (optopsy reference): Sharpe, Sortino, VaR, CVaR, Calmar for evaluating mined strategy performance. Memory injected into prompts as delimited text blocks (`<<<LEARNED_PATTERNS>>>`).

## Open Source Patterns

Patterns cherry-picked from the open source options/trading ecosystem (45 repos evaluated,
research date: 2026-03-13). Full analysis: `docs/architecture/ai-agency-integration-plan.md`.

| Source | Stars | License | Pattern Adopted |
|--------|-------|---------|-----------------|
| **TradingAgents** | 32k | Apache-2.0 | Tool-per-role scoping — each desk gets only domain-relevant tools, preventing cross-domain hallucination. Maps to PydanticAI's `FunctionToolset` + `run(toolsets=[...])`. |
| **FinRobot** | 6.4k | MIT | API-to-tool wrapping — thin wrapper around existing `services/` methods. Tools return `str` for agent consumption, never-raises contract. |
| **FinRL** | 14.2k | MIT | Reward signal design — `log(portfolio_value_t / portfolio_value_{t-1})`. Applied as Brier score + P&L correlation for indicator weight tuning. |
| **FinGPT** | 18.8k | MIT | Evaluation methodology for prompt A/B testing — F1/accuracy comparison after 30+ samples per variant. Applied to desk prompts only (debate prompts are static). |
| **FinMem** | 856 | MIT | Three-tier memory (working -> long-term patterns -> reflective meta-learning), implemented via SQLite not vector DB. |
| **optopsy** | 1.3k | AGPL | 38-strategy taxonomy and performance metrics (Sharpe, Sortino, VaR, CVaR, Calmar) — reference only, not a dependency. |

## Architectural Decisions

1. **PydanticAI stays — no LangGraph.** `FunctionToolset` + typed deps + `TestModel` already sufficient. TradingAgents uses LangGraph but we get the same capabilities with better type safety.

2. **Separate desk Agent instances, not dual-mode.** PydanticAI enforces single `deps_type` and `output_type` per Agent. With `@output_validator` registered on debate agents, `output_type` override at run time raises `UserError`. Separate instances avoid regression risk. See "Separate Agent Instances" section.

3. **SQLite memory, not vector DB.** Options Arena's data is structured (sector, IV rank bucket, DTE bucket). SQL WHERE clauses on discrete fields are more reliable than cosine similarity. Vector DB deferred to Phase 4+ when semantic search is needed.

4. **Prompt injection for learning, not RL.** Feedback loop: outcome data -> statistical analysis -> pattern extraction -> prompt text. The LLM is not trained; its prompts are enriched with historical context. FinRL's DRL approach is architecturally wrong for LLM agents.

5. **Service DI through `DeskDeps`.** Runtime injection, not import-time coupling. `agents/` never imports `services/` at module level. Preserves testability and boundary table.

6. **Tool call budgeting.** Cap at 3 per specialist desk, 5 for Risk desk (needs correlation + position sizing), 5 for Research desk. Failed tools return error strings, not exceptions. Prevents runaway API costs.

7. **Three-tier tool architecture.** Base (services) → Analysis (pure math) → ML (optional deps). Analysis tools are always available. ML tools conditionally registered via guarded imports. Desks degrade gracefully — fewer tools means narrower analysis, not failure.

8. **Existing computation modules as tool sources.** `analysis/` and `indicators/` functions are wrapped as `FunctionToolset` tools, not reimplemented. Tools return formatted strings per the Tool Return Convention. The underlying functions are unchanged — tool wrappers are thin adapters.

## Requirements

### Functional Requirements

1. Users can submit natural language queries to the Advisor or directly to a specific desk
2. Advisor classifies intent and routes to appropriate desk(s)
3. Desk agents use tools to fetch live data and produce cited responses
4. Weight auto-tuning runs after each outcome collection batch (min 50 samples)
5. Prompt versions tracked in SQLite with accuracy metrics
6. A/B testing splits desk queries between active prompt variants
7. Strategy rules mined on manual trigger from outcome patterns (min 100 total outcomes)
8. Strategy rules require human approval before affecting recommendations
9. All agency interactions persisted for audit trail

### Non-Functional Requirements

1. Query response time: <30s for single-desk, <60s for multi-desk
2. Weight tuning: completes in <30s for 1000 outcomes
3. Windows compatible (no Unix-only dependencies)
4. Graceful degradation: if LLM unreachable, desk queries return data-driven responses (like existing debate fallback)
5. Never-raises contract on learning — errors logged, not propagated

## API / CLI Surface

### API Endpoints

```
# Agency interaction
POST   /api/agency/query              # Submit query (advisor or direct desk)
GET    /api/agency/query/{id}         # Get response
WS     /api/agency/ws                 # Streaming interaction

# Learning
GET    /api/learning/weights          # Current tuned weights
GET    /api/learning/weights/history  # Weight evolution
POST   /api/learning/mine             # Trigger strategy mining
GET    /api/learning/prompts          # Prompt versions by agent
POST   /api/learning/prompts/{id}/promote  # Manual promotion
GET    /api/learning/playbook         # Strategy rules
PUT    /api/learning/playbook/{id}    # Approve/reject rule
```

### CLI Commands

```bash
options-arena agency ask "What's the best play on AAPL right now?"
options-arena agency ask --desk volatility "TSLA term structure analysis"
options-arena agency learn status
options-arena agency learn weights
options-arena agency learn mine
options-arena agency learn playbook
```

### Frontend Components

- `AgencyChat.vue` — Chat interface for advisor interaction
- `DeskSelector.vue` — Direct desk access with desk descriptions
- `LearningDashboard.vue` — Weight evolution charts, prompt comparison, playbook viewer

Note: Frontend components are built incrementally within each epic, not as a standalone epic.

## Testing Strategy

- **Unit tests**: Desk tool functions (mock services), advisor routing/classification, weight tuning algorithm, prompt A/B selection, strategy pattern mining
- **Tool wrapper tests** (Epics 7-8): Each analysis/ML tool wrapper tested independently — verify string formatting, error handling (`None` inputs, missing `[ml]` deps), and that underlying function is called with correct args. Mock the underlying function, not the service layer.
- **Toolset registration tests** (Epic 8): Verify ML tools are conditionally registered — mock `ImportError` on `arch`/`statsmodels`, assert toolset still builds with base + analysis tools only
- **Integration tests**: Full query -> route -> desk -> synthesize flow (PydanticAI TestModel). Include tests with enriched desks (analysis + ML tools available) and degraded desks (ML tools absent)
- **API tests**: All new endpoints with test database
- **E2E Playwright**: Agency chat flow, learning dashboard
- **Estimated**: ~180+ new tests across all 8 epics (up from ~150 for 6 epics)

## Success Criteria

1. Users can get a multi-desk synthesized answer to a natural language question within 30 seconds
2. Weight auto-tuning produces measurably different weights from manual defaults after 100+ outcomes
3. Prompt A/B testing identifies a statistically significant winner within 60 desk queries per variant
4. Strategy mining surfaces at least 3 actionable rules from 200+ historical outcomes
5. All existing debate and scan functionality continues to work unchanged (zero regression)

## Constraints & Assumptions

- **LLM cost**: Each desk query costs 1 LLM call (Groq free tier or Anthropic). Multi-desk queries cost N calls. Users should be aware of API usage.
- **Sample sizes**: Self-improvement phases have minimum sample requirements. New installations start with manual defaults.
- **Single user**: The system is designed for single-user desktop use. No multi-tenancy, no auth.
- **Data sources**: Uses existing yfinance, CBOE, FRED data. No new paid data sources required.

## Design Decisions to Finalize During Epic Work

These are medium-priority items identified during spec review. Resolve during epic implementation, not before parsing:

1. **Tool budget vs UsageLimits redundancy**: `DeskDeps.tool_call_budget` (default 3) and `UsageLimits(tool_calls_limit=N)` serve the same purpose. During Epic 1, decide: remove `tool_call_budget` from `DeskDeps` (rely on `UsageLimits` only), or keep it as informational for prompt injection while `UsageLimits` enforces.

2. **Post-enrichment tool budgets**: After Epics 7-8, Trend/Volatility/Fundamental each have 5 tools but budget of 3. Either increase budget to 4 for enriched desks, or document the rationale explicitly (agents must triage; tight budget prevents cost bloat). Decide during Epic 7.

3. **PromptVersion accuracy metric**: Define precisely how desk prompt "accuracy" is computed. Options: (a) citation density only, (b) citation density + user feedback (requires new `DeskQueryFeedback` model + `/api/agency/query/{id}/feedback` endpoint), (c) outcome correlation (desk query -> trade -> P&L). Decide during Epic 5.

## Out of Scope

- **Autonomous trade execution** — No broker integration or automated order placement
- **Proactive monitoring & alerts** — Watchlist monitoring, alert triggers, alert deduplication. Deferred to future epic; builds on desk + advisor foundation.
- **Real-time streaming** — Polling-based data access, not real-time market data
- **Multi-user / auth** — Single-user desktop tool
- **Mobile app** — Web UI only
- **Custom agent creation** — Users cannot define their own desk agents (V2+ consideration)
- **Cross-session conversation memory** — Queries are independent (GraphRAG/vector DB is V2+)
- **Portfolio tracking** — No position management or P&L dashboard for live holdings
- **LoRA / fine-tuning** — No model fine-tuning, LoRA adapters, or custom model training. Self-improvement is prompt-level only.

## Dependencies

### Internal
- Existing 6 agent modules / 6-agent debate pipeline (`agents/`)
- Outcome tracking system (`data/`, `services/outcome_collector.py`)
- Auto-tune infrastructure (`agents/orchestrator.py :: compute_auto_tune_weights()`)
- WebSocket infrastructure (`api/`)
- Service layer (`services/`)
- **Epic 7 — always available (no optional deps)**:
  - `analysis/valuation.py` — `compute_composite_valuation()`, `FDData` input dataclass
  - `analysis/correlation.py` — `compute_correlation_matrix()`, requires `dict[str, pd.DataFrame]`
  - `analysis/performance.py` — `compute_risk_adjusted_metrics()`, requires outcome return data
  - `analysis/position_sizing.py` — `compute_position_size()`, IV-based vol-regime allocation
  - `indicators/hv_estimators.py` — `compute_hv_yang_zhang()`, OHLC Series input
- **Epic 8 — requires `[ml]` extra (guarded imports)**:
  - `indicators/vol_forecast.py` — `compute_garch_forecast()`, requires `arch` + `statsmodels`
  - `indicators/regime_ml.py` — `compute_markov_regime()`, requires `statsmodels`
- **Epic 8 — pure math (grouped thematically, no optional deps)**:
  - `indicators/macro.py` — `compute_macro_regime()`, pure math from FRED data
  - `indicators/hurst.py` — `hurst_exponent()`, pure math R/S analysis

### External
- PydanticAI `FunctionToolset` + `UsageLimits` support (available in current version)
- `arch >=8.0,<9` (MIT) — GARCH/EGARCH volatility forecasting for Volatility desk tools. Already installed via `[ml]` optional extra (scientific-ml epic, merged 2026-03-15). Agency consumes, does not install.
- `scikit-learn >=1.5,<2` — Random Forest feature importance for indicator weight validation (Epic 4, FR-S5 relocated from scientific-ml PRD). Already installed via `[ml]` optional extra (scientific-ml epic, merged 2026-03-15). Agency consumes, does not install.
- No new external API services required

### Future Integration Candidates (Not for Initial Epics)
- `ib_async` — autonomous execution via IBKR (future broker integration epic)
- `polygon-api-client` — professional chains with native Greeks, historical to 2014 (future, paid)
- `chromadb` + `sentence-transformers` — Memory V2 vector similarity when SQL-based memory proves insufficient (Phase 4+)

## Implementation Phasing

| Epic | Scope | Est. Issues | Dependencies | Parallelizable With |
|------|-------|-------------|-------------|-------------------|
| 1: Desk Foundation | DeskDeps, FunctionToolset for vol + risk desks, base tools, desk prompts | 3-4 | None | — |
| 2: Advisor + Routing | Advisor agent, intent classification, query persistence, API + CLI | 3-4 | Epic 1 | Epic 3 |
| 3: All Desks Online | Remaining 4 desks + Research desk (curated base tools, budget 5) | 4-5 | Epic 1 | Epic 2 |
| 4: Self-Improvement P1 — Weights | Extended auto-tune + indicator weight validation + weight history | 3-4 | Epics 1-2 | Epics 7-8 |
| 5: Self-Improvement P2 — Prompts | Prompt versioning, A/B testing (desk prompts only), accuracy tracking | 3-4 | Epic 4 | Epics 7-8 |
| 6: Self-Improvement P3 — Strategy Mining | Outcome pattern mining (manual trigger), strategy rules, human review | 3-4 | Epic 5 | Epics 7-8 |
| 7: Analysis & HV Desk Tools | Wrap `analysis/` + `indicators/hv_estimators` functions as FunctionToolset tools: valuation (composite 4-model), correlation matrix, risk-adjusted metrics (Sharpe/Sortino/Calmar), position sizing (Kelly/vol-regime), Yang-Zhang HV. Register on Fundamental, Risk, Volatility, Research desks. Pure math — no optional deps. | 3-4 | Epics 1-3 (desks exist) | Epics 4-6 |
| 8: ML Desk Tools | Wrap `indicators/` ML functions as FunctionToolset tools: GARCH forecast, Markov regime, macro regime, Hurst exponent. Conditional registration via guarded imports. Register on Trend, Volatility, Fundamental, Risk, Research desks. Requires `[ml]` extra. | 3-4 | Epics 1-3 (desks exist) | Epics 4-6 |

**Total: ~27-33 issues across 8 epics.**

### Parallelization Strategy

```
Track A (Core Agency):    Epic 1 ──> Epic 2 ──> (done)
                            │          │
                            └──> Epic 3 ┘  (parallel with Epic 2)

Track B (Self-Improvement): ──────────> Epic 4 ──> Epic 5 ──> Epic 6
                                        (after Epics 1-2)

Track C (Tool Enrichment):  ──────────────────> Epic 7 ┐  (after Epics 1-3)
                                                Epic 8 ┘  (parallel with each other)
```

Tracks B and C are **fully independent** — they can run in parallel. Track C enriches desks with analysis/ML tools while Track B adds self-improvement capabilities. Neither depends on the other.

### Epic 7 Details: Analysis Desk Tools

| Tool | Source Function | Target Desks | Input Adaptation |
|------|----------------|-------------|-----------------|
| `compute_composite_valuation_tool` | `analysis/valuation.compute_composite_valuation()` | Fundamental, Research | Ticker + current price from `fetch_quote`; `FDData` fields from service or prompt context |
| `compute_correlation_matrix_tool` | `analysis/correlation.compute_correlation_matrix()` | Risk | Multi-ticker OHLCV from `MarketDataService.fetch_ohlcv()` for each ticker |
| `compute_risk_adjusted_metrics_tool` | `analysis/performance.compute_risk_adjusted_metrics()` | Risk | Historical outcome returns from `Repository` |
| `compute_position_size_tool` | `analysis/position_sizing.compute_position_size()` | Risk, Research | IV from quote/chain data; optional portfolio correlation |
| `compute_hv_yang_zhang_tool` | `indicators/hv_estimators.compute_hv_yang_zhang()` | Volatility, Research | OHLC Series from `MarketDataService.fetch_ohlcv()` |

All 5 tools are pure math wrappers — no optional dependencies, always registered.

### Epic 8 Details: ML Desk Tools

| Tool | Source Function | Target Desks | Optional Dep | Graceful Absence |
|------|----------------|-------------|-------------|-----------------|
| `compute_garch_forecast_tool` | `indicators/vol_forecast.compute_garch_forecast()` | Volatility, Research | `arch`, `statsmodels` | Tool not registered; vol desk works with Yang-Zhang HV only |
| `compute_markov_regime_tool` | `indicators/regime_ml.compute_markov_regime()` | Trend, Risk | `statsmodels` | Tool not registered; trend desk works with Hurst + indicators only |
| `compute_macro_regime_tool` | `indicators/macro.compute_macro_regime()` | Fundamental, Risk, Research | None (pure math) | Always registered (despite being in "ML" epic for thematic grouping) |
| `compute_hurst_exponent_tool` | `indicators/hurst.hurst_exponent()` | Trend, Research | None (pure math) | Always registered (despite being in "ML" epic for thematic grouping) |

Note: `compute_macro_regime` and `hurst_exponent` have no optional deps but are grouped in Epic 8 for thematic coherence (statistical/ML indicators). They are always registered regardless of `[ml]` installation.

## Cross-PRD Coordination

### scientific-ml-integration (MERGED — completed 2026-03-15)

The `scientific-ml-integration` PRD is fully merged into master. No coordination contracts needed — all ML capabilities are stable and available as tool sources:

- **GARCH/EGARCH** (`indicators/vol_forecast.py`): Available for Volatility desk tool wrapping (Epic 8)
- **Markov-switching regime** (`indicators/regime_ml.py`): Available for Trend/Risk desk tool wrapping (Epic 8)
- **FRED macro pipeline** (`indicators/macro.py`): Available for Fundamental/Risk desk tool wrapping (Epic 8)
- **Hurst exponent** (`indicators/hurst.py`): Available for Trend/Research desk tool wrapping (Epic 8)
- **`render_macro_context()`** and vol forecast fields in `render_volatility_context()`: Already in `_parsing.py`, can be referenced by desk prompts
- **`INDICATOR_WEIGHTS`**: ML indicators already wired with static weights (sum == 1.0). Epic 4 auto-tune will make these dynamic.

### Remaining Contracts

**WeightSnapshot Schema (owned by this PRD, Epic 4)**: `WeightSnapshot` extension with `WeightType.INDICATOR` and dynamic tuning loop. No other PRD modifies `WeightSnapshot` or auto-tune infrastructure.

**FR-S5 Relocation Note**: Indicator weight validation via ML (Random Forest feature importance on historical outcomes) was originally FR-S5 in `scientific-ml-integration`. Relocated to this PRD's Epic 4 because its *purpose* is intelligence/learning. The implementation (`tools/validate_indicator_weights.py`) uses scikit-learn but serves the self-improvement loop.

## Competitive Landscape

### What Options Arena Uniquely Provides (No Open Source Competitor)
1. Options-specific AI agency — all competitors target equities only
2. Local American-style pricing (BAW) with computed Greeks — no external Greeks dependency
3. Multi-agent debate on specific option contracts with structured dissent
4. Outcome tracking with P&L at multiple holding periods (T+1/5/10/20)
5. Self-improvement loop from outcome -> weight tuning -> prompt evolution -> strategy mining
6. Desk agents with embedded quantitative tools — DCF valuation, GARCH forecasting, regime detection, position sizing built into agent reasoning (not just prompt context)

### Closest Architectural Analogs to Monitor
- **TradingAgents** (32k stars): If they add options support, they become a direct competitor. Currently stock-only. Monitor their roadmap.
- **optopsy** (1.3k stars): If they add AI/LLM integration, they bridge the gap from backtesting to recommendation. Currently pure backtesting. Active development.

### Ecosystem Gaps Options Arena Fills
- No open source real-time options screener with IV rank + Greeks filtering
- No open source portfolio-level options Greek aggregation tool
- No open source AI-powered options contract recommendation system
- No open source options outcome tracking with agent accuracy analytics
