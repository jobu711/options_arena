---
name: ai-agency-evolution
description: Evolve Options Arena into an AI advisory agency with specialized desks, hybrid routing, monitoring, and self-improving behavior
status: backlog
created: 2026-03-14T03:03:29Z
---

# PRD: ai-agency-evolution

## Executive Summary

Transform Options Arena from a batch analysis tool into an AI advisory agency — a team of specialized "desk" agents (Volatility, Risk, Flow, Fundamental, Trend, Contrarian, Research) coordinated by an Advisor agent that routes queries, synthesizes multi-desk responses, and surfaces proactive alerts. The system is semi-proactive: it monitors watchlists on a schedule and alerts users to opportunities/risks, but never acts without confirmation. A three-phase self-improvement engine progressively tunes weights, evolves prompts, and mines strategy patterns from historical outcomes.

## Problem Statement

### What problem are we solving?

Options Arena currently operates as a **batch pipeline tool**: users trigger scans, launch debates, and read reports. There is no persistent advisory relationship — the system has no memory between sessions, no proactive monitoring, no ability to answer ad-hoc questions, and no mechanism to learn from its own track record. Users must manually connect the dots between scan results, debate outputs, and outcome data.

### Why is this important now?

The foundation is ready. Options Arena already has:
- 8 agent modules (bull, bear, risk, volatility, contrarian, flow, fundamental, trend) running a 6-agent debate pipeline with structured outputs and independent judgment
- Outcome tracking with P&L at T+1/5/10/20 and agent accuracy heatmaps
- Auto-tuning infrastructure (`compute_auto_tune_weights()`) that derives vote weights from accuracy
- Background task infrastructure (operation mutex, WebSocket progress)
- PydanticAI's unused `@agent.tool` capability — agents CAN use tools, we just haven't enabled it

The pieces exist. This PRD assembles them into an agency.

## User Stories

### Advisory Interaction
- **As a trader**, I want to ask "What's the best play on AAPL right now?" and get a synthesized answer from multiple specialist desks, so I don't have to run a full scan + debate just for one question.
  - *Acceptance*: Query returns within 30s, cites specific data points, includes confidence score.

- **As a power user**, I want to directly ask the Volatility Desk "Analyze TSLA's term structure" for deep domain expertise, so I can get focused analysis without routing overhead.
  - *Acceptance*: Direct desk queries bypass Advisor routing, return desk-specific structured output.

### Proactive Monitoring
- **As a watchlist user**, I want the system to monitor my watchlist tickers hourly during market hours and alert me when IV rank spikes above my threshold, so I don't miss vol selling opportunities.
  - *Acceptance*: Alerts delivered via WebSocket within 5 minutes of trigger condition. Alerts are deduplicated (no spam).

- **As a risk-conscious trader**, I want to receive a warning when earnings are approaching for any ticker on my watchlist, so I can adjust positions before the event.
  - *Acceptance*: Earnings alerts surface 7 days before the event, once per ticker per earnings date.

### Self-Improvement
- **As a user who tracks outcomes**, I want the system to automatically tune its indicator and vote weights based on which signals actually predicted profitable trades, so recommendations improve over time.
  - *Acceptance*: Weights update after each outcome collection batch (minimum 50 samples). Weight history is viewable.

- **As a user**, I want the system to discover patterns in its own wins and losses (e.g., "bearish high-IV tech in earnings week has 62% loss rate") and surface them as strategy rules I can approve or reject.
  - *Acceptance*: Rules require human approval before affecting recommendations. Rules show sample size, win rate, avg return.

## Architecture & Design

### Chosen Approach: Evolve-in-Place

Promote existing 8 agent modules (6-agent debate pipeline) into dual-purpose agents (debate mode + interactive desk mode). Add Advisor agent for routing, monitoring module for alerts, and learning module for self-improvement. The debate system becomes one capability of the agency, not a separate thing.

**Why this approach**: Maximizes reuse of existing agent expertise, prompts, and service layer. No duplication — every self-improvement gain benefits both debates and direct queries.

### Module Changes

| Module | Change | Boundary Compliance |
|--------|--------|-------------------|
| `agents/` | Existing agents gain `@agent.tool` + interactive mode. New `advisor.py`, `research_desk.py`, `_routing.py` | Yes — agents access services via DeskDeps |
| `agents/prompts/` | Prompt versioning system (SQLite-backed) | Yes — prompts/ manages prompt text |
| `models/` | New models: `AgencyQuery`, `DeskResponse`, `Alert`, `PromptVersion`, `StrategyRule`, `WeightSnapshot`, enums | Yes — data shapes only |
| `data/` | New migrations for agency tables + new repository mixin (`AgencyMixin`) | Yes — persistence only |
| `monitoring/` | **New module**: scheduler, watchers, triggers, alert generation | Accesses: `models/`, `services/`, `data/`, `scoring/` |
| `learning/` | **New module**: weight tuner, prompt lab, strategy book | Accesses: `models/`, `data/`, `agents/prompts/` |
| `api/` | New route groups: `/api/agency/*`, `/api/alerts/*`, `/api/learning/*` | Yes — top of stack |
| `cli/` | New `agency` subcommand group | Yes — top of stack |
| `services/` | Minor convenience methods for desk tool-use | Yes — external API access |

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

class DeskResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    desk: DeskType
    response: str
    tools_used: list[str]
    confidence: float  # 0.0-1.0, field_validator

class AgencyResponse(BaseModel):
    model_config = ConfigDict(frozen=True)
    query_id: str
    desk_responses: list[DeskResponse]
    synthesis: str
    citations: list[Citation]
    confidence: float  # 0.0-1.0, field_validator
```

#### Monitoring & Alerts

```python
class AlertType(StrEnum):
    IV_RANK_SPIKE = "iv_rank_spike"
    PRICE_THRESHOLD = "price_threshold"
    UNUSUAL_FLOW = "unusual_flow"
    EARNINGS_APPROACHING = "earnings_approaching"
    SCORE_CHANGE = "score_change"

class AlertSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

class Alert(BaseModel):
    model_config = ConfigDict(frozen=True)
    alert_id: str
    alert_type: AlertType
    ticker: str
    message: str
    severity: AlertSeverity
    triggered_at: datetime  # UTC validated
    acknowledged: bool = False
```

#### Self-Improvement

```python
class PromptVersion(BaseModel):
    model_config = ConfigDict(frozen=True)
    version_id: str
    agent_name: str
    prompt_hash: str
    is_active: bool
    sample_count: int = 0
    accuracy: float | None = None

class RuleStatus(StrEnum):
    CANDIDATE = "candidate"
    APPROVED = "approved"
    REJECTED = "rejected"

class StrategyCondition(BaseModel):
    model_config = ConfigDict(frozen=True)
    field: str        # e.g. "sector", "iv_rank_bucket", "dte_bucket", "direction"
    operator: str     # e.g. "eq", "gt", "lt", "in"
    value: str        # string-encoded, parsed per operator

class StrategyRule(BaseModel):
    model_config = ConfigDict(frozen=True)
    rule_id: str
    pattern: str
    conditions: list[StrategyCondition]  # typed model, not raw dict
    win_rate: float
    avg_return: float
    sample_size: int
    status: RuleStatus

class WeightType(StrEnum):
    VOTE = "vote"
    INDICATOR = "indicator"

class WeightEntry(BaseModel):
    model_config = ConfigDict(frozen=True)
    name: str
    value: float  # math.isfinite() validated

class WeightSnapshot(BaseModel):
    model_config = ConfigDict(frozen=True)
    weight_type: WeightType
    weights: list[WeightEntry]  # typed model, not raw dict
    accuracy_at_time: float
    sample_size: int
    created_at: datetime  # UTC validated
```

All models follow project conventions: `frozen=True`, UTC validators on datetimes, `math.isfinite()` on numerics, confidence clamped `[0.0, 1.0]`, `StrEnum` for categoricals.

### Tool Scoping Map

Each desk receives only domain-relevant tools, preventing cross-domain hallucination
(pattern from TradingAgents). Tool call budget: 3 per specialist desk, 5-8 for Research.

```
Desk            Tools                                     Service Source
Trend           fetch_quote, fetch_related_ohlcv,        MarketDataService
                compute_indicator_on_demand               indicators/
Volatility      fetch_quote, fetch_vol_surface_slice,    OptionsDataService,
                compute_iv_for_strike, garch_forecast     analysis/
Flow            fetch_quote, fetch_chain_summary,        OptionsDataService
                fetch_unusual_activity
Fundamental     fetch_quote, fetch_earnings_history,     MarketDataService,
                fetch_sector_comparison                   IntelligenceService
Risk            fetch_quote, fetch_correlation,          MarketDataService,
                fetch_portfolio_exposure                  Repository
Contrarian      fetch_quote, fetch_debate_history        Repository
Research (new)  All tools from all desks                 All services
```

### Core Logic

#### Dual-Mode Agent Pattern

Each desk agent operates in two modes via the same PydanticAI Agent instance:

1. **Debate Mode** (existing): Called by orchestrator with pre-rendered domain context. Returns structured thesis.
2. **Interactive Mode** (new): Called by Advisor or user. Uses `@agent.tool` to fetch data on demand. Returns conversational response with citations.

```python
# Interactive mode tools (example: Volatility Desk)
@vol_agent.tool
async def fetch_iv_snapshot(ctx: RunContext[DeskDeps], ticker: str) -> IVSnapshot:
    """Fetch current IV rank, percentile, and term structure."""
    return await ctx.deps.market_data.fetch_iv_data(ticker)

@vol_agent.tool
async def fetch_vol_surface(ctx: RunContext[DeskDeps], ticker: str) -> VolSurface:
    """Fetch the volatility surface for a ticker."""
    return await ctx.deps.options_data.fetch_vol_surface(ticker)
```

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

#### Monitoring Flow

```
Scheduler (hourly during market hours, via asyncio.create_task in API lifespan)
  -> For each watchlist ticker:
      Fetch quote + IV data via services
      Evaluate trigger conditions against user config
      If triggered -> create Alert, deduplicate against recent alerts, persist
      Push to WebSocket subscribers
```

#### Self-Improvement (3 Phases)

| Phase | Trigger | Input | Output | Min Samples |
|-------|---------|-------|--------|-------------|
| 1: Weight Tuning | After outcome collection | Historical outcomes | Updated vote + indicator weights | 50 |
| 2: Prompt A/B | Continuous during debates | Debates tagged with prompt version | Promoted prompt variant | 30 per variant |
| 3: Strategy Mining | Weekly batch job | All historical outcomes | StrategyRule candidates | 20 per pattern |

**Phase 1 — Weight Tuning** (FinRL pattern): Extends existing `compute_auto_tune_weights()` to cover indicator weights (not just vote weights). Key insight from FinRL: composite score calibration should be driven by historical returns, not hand-tuned constants. Existing infrastructure that just needs connecting:
- `AgentAccuracyReport` — per-agent direction hit rate + Brier score
- `CalibrationBucket` — confidence calibration curves
- `compute_auto_tune_weights()` — inverse-Brier vote weights
- `WeightSnapshot` — weight history tracking (now with typed `WeightEntry` list)
- `auto_tune_weights()` — full accuracy → weights → persist flow

**Phase 2 — Prompt A/B Testing** (FinGPT evaluation methodology): Tags each debate with the prompt version used. After 30+ samples per variant, compares F1/accuracy metrics and promotes the winner. Rollback if new prompt degrades below baseline. Fine-tuning consideration threshold: after 5,000+ debates with outcomes, consider LoRA on 7B model.

**Phase 3 — Strategy Mining** (FinMem three-tier memory + optopsy metrics):
- **Short-term (working)**: Recent debates for same ticker/sector from `ai_theses` table. Rendered as context in agent prompts.
- **Long-term (patterns)**: `agent_memory` SQLite table, scoped by agent + ticker/sector/regime. Example: "When IV Rank >80 in Technology, bearish puts outperform by 12% (n=67)".
- **Reflective (meta-learning)**: Weekly batch job. Groups outcomes by dimensions (sector × IV bucket × DTE bucket × direction). Chi-squared test for significance, minimum 20 samples per pattern. Generates `StrategyRule` candidates for human approval.
- **Evaluation metrics** (optopsy reference): Sharpe, Sortino, VaR, CVaR, Calmar for evaluating mined strategy performance. Memory injected into prompts as delimited text blocks (`<<<LEARNED_PATTERNS>>>`).

## Open Source Patterns

Patterns cherry-picked from the open source options/trading ecosystem (45 repos evaluated,
research date: 2026-03-13). Full analysis: `docs/architecture/ai-agency-integration-plan.md`.

| Source | Stars | License | Pattern Adopted |
|--------|-------|---------|-----------------|
| **TradingAgents** | 32k | Apache-2.0 | Tool-per-role scoping — each desk gets only domain-relevant tools, preventing cross-domain hallucination. Maps to PydanticAI's `tools=[...]` parameter. |
| **FinRobot** | 6.4k | MIT | API-to-tool wrapping — thin wrapper around existing `services/` methods. Tools return `str` for agent consumption, never-raises contract. |
| **FinRL** | 14.2k | MIT | Reward signal design — `log(portfolio_value_t / portfolio_value_{t-1})`. Applied as Brier score + P&L correlation for indicator weight tuning. |
| **FinGPT** | 18.8k | MIT | Evaluation methodology for prompt A/B testing — F1/accuracy comparison after 30+ samples per variant. Fine-tuning consideration threshold: 5,000+ debates with outcomes. |
| **FinMem** | 856 | MIT | Three-tier memory (working → long-term patterns → reflective meta-learning), implemented via SQLite not vector DB. |
| **optopsy** | 1.3k | AGPL | 38-strategy taxonomy and performance metrics (Sharpe, Sortino, VaR, CVaR, Calmar) — reference only, not a dependency. |

## Architectural Decisions

1. **PydanticAI stays — no LangGraph.** `@agent.tool` + typed deps + `TestModel` already sufficient. TradingAgents uses LangGraph but we get the same capabilities with better type safety.

2. **SQLite memory, not vector DB.** Options Arena's data is structured (sector, IV rank bucket, DTE bucket). SQL WHERE clauses on discrete fields are more reliable than cosine similarity. Vector DB deferred to Phase 4+ when semantic search is needed.

3. **Prompt injection for learning, not RL.** Feedback loop: outcome data → statistical analysis → pattern extraction → prompt text. The LLM is not trained; its prompts are enriched with historical context. FinRL's DRL approach is architecturally wrong for LLM agents.

4. **Service DI through `DeskDeps`.** Runtime injection, not import-time coupling. `agents/` never imports `services/` at module level. Preserves testability and boundary table.

5. **Tool call budgeting.** Cap at 3 per specialist desk, 5-8 for Research desk. Failed tools return error strings, not exceptions. Prevents runaway API costs.

## Requirements

### Functional Requirements

1. Users can submit natural language queries to the Advisor or directly to a specific desk
2. Advisor classifies intent and routes to appropriate desk(s)
3. Desk agents use tools to fetch live data and produce cited responses
4. Monitoring scheduler runs hourly during market hours for watchlist tickers
5. Alerts generated when trigger conditions met (IV spike, price threshold, earnings approaching, unusual flow, score change)
6. Alerts delivered via WebSocket and persisted in SQLite
7. Alert deduplication prevents spam (same alert type + ticker within 24h window)
8. Weight auto-tuning runs after each outcome collection batch (min 50 samples)
9. Prompt versions tracked in SQLite with accuracy metrics
10. A/B testing splits debates between active prompt variants
11. Strategy rules mined weekly from outcome patterns
12. Strategy rules require human approval before affecting recommendations
13. All agency interactions persisted for audit trail

### Non-Functional Requirements

1. Query response time: <30s for single-desk, <60s for multi-desk
2. Monitoring overhead: <5% CPU during market hours
3. Alert latency: <5 minutes from trigger condition to delivery
4. Weight tuning: completes in <30s for 1000 outcomes
5. Windows compatible (no Unix-only dependencies)
6. Graceful degradation: if LLM unreachable, desk queries return data-driven responses (like existing debate fallback)
7. Never-raises contract on monitoring and learning — errors logged, not propagated

## API / CLI Surface

### API Endpoints

```
# Agency interaction
POST   /api/agency/query              # Submit query (advisor or direct desk)
GET    /api/agency/query/{id}         # Get response
WS     /api/agency/ws                 # Streaming interaction

# Alerts
GET    /api/alerts                    # List alerts (filter by type, severity, ticker)
POST   /api/alerts/{id}/ack          # Acknowledge
GET    /api/alerts/config             # Monitoring config
PUT    /api/alerts/config             # Update triggers

# Learning
GET    /api/learning/weights          # Current tuned weights
GET    /api/learning/weights/history  # Weight evolution
GET    /api/learning/prompts          # Prompt versions by agent
POST   /api/learning/prompts/{id}/promote  # Manual promotion
GET    /api/learning/playbook         # Strategy rules
PUT    /api/learning/playbook/{id}    # Approve/reject rule
```

### CLI Commands

```bash
options-arena agency ask "What's the best play on AAPL right now?"
options-arena agency ask --desk volatility "TSLA term structure analysis"
options-arena agency alerts list
options-arena agency alerts config --ticker AAPL --iv-threshold 80
options-arena agency monitor start
options-arena agency monitor stop
options-arena agency learn status
options-arena agency learn weights
options-arena agency learn playbook
```

### Frontend Components

- `AgencyChat.vue` — Chat interface for advisor interaction
- `DeskSelector.vue` — Direct desk access with desk descriptions
- `AlertDashboard.vue` — Alert list with severity indicators, ack buttons
- `LearningDashboard.vue` — Weight evolution charts, prompt comparison, playbook viewer

## Testing Strategy

- **Unit tests**: Desk tool functions (mock services), advisor routing/classification, trigger evaluation, weight tuning algorithm, prompt A/B selection, strategy pattern mining
- **Integration tests**: Full query -> route -> desk -> synthesize flow (PydanticAI TestModel)
- **Integration tests**: Monitoring -> alert generation -> deduplication -> persistence
- **API tests**: All new endpoints with test database
- **E2E Playwright**: Agency chat flow, alert dashboard, learning dashboard
- **Estimated**: ~200+ new tests across all epics

## Success Criteria

1. Users can get a multi-desk synthesized answer to a natural language question within 30 seconds
2. Watchlist monitoring detects IV rank spikes within 5 minutes during market hours
3. Weight auto-tuning produces measurably different weights from manual defaults after 100+ outcomes
4. Prompt A/B testing identifies a statistically significant winner within 60 debates per variant
5. Strategy mining surfaces at least 3 actionable rules from 200+ historical outcomes
6. All existing debate and scan functionality continues to work unchanged (zero regression)

## Constraints & Assumptions

- **LLM cost**: Each desk query costs 1 LLM call (Groq free tier or Anthropic). Multi-desk queries cost N calls. Users should be aware of API usage.
- **Market hours**: Monitoring only runs during US market hours (9:30 AM - 4:00 PM ET). Configurable.
- **Sample sizes**: Self-improvement phases have minimum sample requirements. New installations start with manual defaults.
- **Single user**: The system is designed for single-user desktop use. No multi-tenancy, no auth.
- **Data sources**: Uses existing yfinance, CBOE, FRED data. No new paid data sources required.

## Out of Scope

- **Autonomous trade execution** — No broker integration or automated order placement
- **Real-time streaming** — Monitoring is polling-based (hourly), not real-time market data
- **Multi-user / auth** — Single-user desktop tool
- **Mobile app** — Web UI only
- **Custom agent creation** — Users cannot define their own desk agents (V2+ consideration)
- **Cross-session conversation memory** — Queries are independent (GraphRAG/vector DB is V2+)
- **Portfolio tracking** — No position management or P&L dashboard for live holdings

## Dependencies

### Internal
- Existing 8 agent modules / 6-agent debate pipeline (`agents/`)
- Outcome tracking system (`data/`, `services/outcome_collector.py`)
- Auto-tune infrastructure (`agents/orchestrator.py :: compute_auto_tune_weights()`)
- Watchlist system — **NOT YET BUILT** (requires: `WatchlistItem` model, Repository CRUD, API routes, CLI subcommand)
- WebSocket infrastructure (`api/`)
- Service layer (`services/`)

### External
- PydanticAI `@agent.tool` support (already available, unused)
- `arch >=7.0` (MIT) — GARCH/EGARCH volatility forecasting for Volatility desk tools. Installed by scientific-ml Epic A; agency is a consumer.
- `scikit-learn` — Random Forest feature importance for indicator weight validation (Epic 5, FR-S5 relocated from scientific-ml PRD). Installed by scientific-ml Epic B if sequenced first; otherwise add directly.
- No new external API services required

### Future Integration Candidates (Not for Initial Epics)
- `ib_async` — autonomous execution via IBKR (future broker integration epic)
- `polygon-api-client` — professional chains with native Greeks, historical to 2014 (future, paid)
- `chromadb` + `sentence-transformers` — Memory V2 vector similarity when SQL-based memory proves insufficient (Phase 4+)

## Implementation Phasing

| Epic | Scope | Est. Issues | Dependencies |
|------|-------|-------------|-------------|
| 1: Desk Foundation | DeskDeps, @agent.tool on vol + risk desks, interactive mode | 3-4 | None |
| 2: Advisor + Routing | Advisor agent, intent classification, query persistence, API + CLI | 3-4 | Epic 1 |
| 3: All Desks Online | Remaining 4 desks + Research desk (new, ReACT with tools) | 4-5 | Epic 1 |
| 4: Monitoring & Alerts | Scheduler, watchers, triggers, alert persistence, WebSocket delivery | 4-5 | Epic 2 |
| 5: Self-Improvement P1 — Weights | Extended auto-tune + weight history + dashboard + **offline RF-based indicator weight validation (from scientific-ml FR-S5)** | 3-4 | Epics 1-2 |
| 6: Self-Improvement P2 — Prompts | Prompt versioning, A/B testing, accuracy tracking | 3-4 | Epic 5 |
| 7: Self-Improvement P3 — Strategy | Outcome pattern mining, strategy rules, human review | 3-4 | Epic 6 |
| 8: Agency Frontend | Chat UI, desk selector, alert dashboard, learning dashboard | 5-6 | Epics 2-4 |

**Total: ~28-36 issues across 8 epics.**

Parallelization: Epics 1-3 can partially overlap. Epic 4 can start after Epic 2. Epic 8 can start after Epic 2. Epics 5-7 are sequential.

## Cross-PRD Coordination

This PRD and `scientific-ml-integration` are architecturally distinct (intelligence vs capabilities) but share integration points. These contracts prevent merge conflicts:

### Contract 1: WeightSnapshot Schema (owned by this PRD)

- **ai-agency** Epic 5 owns `WeightSnapshot` with `WeightType.INDICATOR` and builds the dynamic tuning loop
- **scientific-ml** adds new ML indicators to `INDICATOR_WEIGHTS` with static weight redistribution (maintains `sum == 1.0`)
- **Rule**: scientific-ml does NOT modify `WeightSnapshot` or auto-tune infrastructure

### Contract 2: Agent Context Rendering (additive convention)

- Both PRDs append independent `render_*_context()` functions to `agents/_parsing.py`
- Each function is self-contained, returns `str | None`, called by orchestrator
- **ai-agency**: `render_learned_patterns()` for strategy memory injection
- **scientific-ml**: `render_macro_context()`, vol forecast fields in `render_volatility_context()`

### Contract 3: Volatility Agent Dual Modification (non-conflicting sections)

- **ai-agency** modifies tool registration + adds `DeskDeps` for interactive mode
- **scientific-ml** modifies system prompt content + `DebateDeps` fields (vol forecast context)
- Agent operates in one mode at a time (debate vs interactive) — no runtime conflict

### FR-S5 Relocation Note

Indicator weight validation via ML (Random Forest feature importance on historical outcomes) was originally FR-S5 in `scientific-ml-integration`. It has been relocated to this PRD's Epic 5 (Self-Improvement Phase 1 — Weights) because its *purpose* is intelligence/learning, not capability. The implementation (`tools/validate_indicator_weights.py`) uses scikit-learn but serves the self-improvement loop, not the computation layer.

## Competitive Landscape

### What Options Arena Uniquely Provides (No Open Source Competitor)
1. Options-specific AI agency — all competitors target equities only
2. Local American-style pricing (BAW) with computed Greeks — no external Greeks dependency
3. Multi-agent debate on specific option contracts with structured dissent
4. Outcome tracking with P&L at multiple holding periods (T+1/5/10/20)
5. Self-improvement loop from outcome → weight tuning → prompt evolution → strategy mining

### Closest Architectural Analogs to Monitor
- **TradingAgents** (32k stars): If they add options support, they become a direct competitor. Currently stock-only. Monitor their roadmap.
- **optopsy** (1.3k stars): If they add AI/LLM integration, they bridge the gap from backtesting to recommendation. Currently pure backtesting. Active development.

### Ecosystem Gaps Options Arena Fills
- No open source real-time options screener with IV rank + Greeks filtering
- No open source portfolio-level options Greek aggregation tool
- No open source AI-powered options contract recommendation system
- No open source options outcome tracking with agent accuracy analytics
