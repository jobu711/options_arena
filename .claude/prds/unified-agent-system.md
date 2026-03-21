---
name: unified-agent-system
description: Replace dual agent architecture (debate + desk) with unified desk-only system — desk agents gain structured recommendation mode, synthesis agent replaces algorithmic verdict
status: planned
created: 2026-03-21T12:00:00Z
revised: 2026-03-21T14:30:00Z
revision_notes: Gap audit pass — desk enable/disable config, should_recommend threshold, spread passthrough, parallelism for paid providers, citation density spec, analytics forward-only (no legacy debate compat). Prior: vote weight tuning, Context7 verification.
supersedes: Debate portion of ai-agency-evolution PRD (debate agents, orchestrator, DebateDeps, DebateResult)
---

# PRD: Unified Agent System — Desk Agents Replace Debate Agents

## Executive Summary

Merge Options Arena's two parallel AI agent systems (6 debate agents + 7 desk agents) into a single unified architecture where desk agents are the sole agent type. Each desk gains a "recommendation mode" (structured `DomainAssessment` output) alongside existing interactive Q&A mode (`str` output). A new synthesis agent replaces algorithmic verdict computation, producing a richer `PositionRecommendation` with specific contract recommendations, entry/exit criteria, and position sizing. This is a clean break — debate agents, the debate orchestrator, and all debate-specific prompts are deleted.

## Problem Statement

### What problem are we solving?

Options Arena has two parallel agent systems with significant overlap:

1. **6 debate agents** (Trend, Volatility, Flow, Fundamental, Risk, Contrarian) — structured output (`AgentResponse`/`RiskAssessment`), pre-fetched data via `DebateDeps`, no tools, 4-phase pipeline, algorithmic verdict synthesis
2. **7 desk agents** (same 6 + Research) — plain text output (`str`), tool-based data fetching via `DeskDeps`, interactive Q&A

Both cover the same 6 analytical domains with:
- Separate code files (12 agent files total)
- Separate prompt files (13 prompt files)
- Separate dependency dataclasses (`DebateDeps` vs `DeskDeps`)
- Separate orchestration logic (`orchestrator.py` vs `_routing.py`)
- No shared tool infrastructure (debate agents can't use tools)

**The core limitation**: Debate agents produce structured theses but have no tool access and rely entirely on pre-fetched data. Desk agents have rich tool access but can only produce unstructured text. Neither system alone can produce a structured option position recommendation grounded in real-time tool-fetched data.

### Why is this important now?

The user's goal is to have agents recommend specific option positions based on scan pipeline scores — a capability that requires both structured output AND tool access. Rather than bolt structured output onto desk agents while keeping debate agents alive (creating even more duplication), this is the right time for a clean unification:

1. **All 7 desk agents are fully operational** with domain-specific tools (Epics 1-6 complete)
2. **Tool enrichment** (analysis + ML tools, Epics 7-8) is additive and compatible with either architecture
3. **The debate system's algorithmic verdict** (weighted averaging of agent scores) is a known limitation — an AI synthesis agent can produce richer, more contextual recommendations
4. **Maintenance burden**: 25+ files maintain two parallel systems doing essentially the same analysis

### What does success look like?

A single `run_recommendation(ticker, ...)` call that:
1. Runs 6 desk agents in parallel (recommendation mode) with tool access + pre-fetched scan data
2. Passes all assessments to a synthesis agent that produces a specific position recommendation
3. Returns a `RecommendationResult` with contract specifics, entry/exit criteria, position sizing, and risk assessment
4. Persists results for outcome tracking and learning
5. Falls back gracefully on any failure (never-raises contract preserved)

## User Stories

### Position Recommendation
- **As a trader**, I want the debate command to produce a specific position recommendation (contract, entry price, stop loss, take profit, position size) instead of just a directional thesis, so I can act on it directly.
  - *Acceptance*: `options-arena debate AAPL` returns a `PositionRecommendation` with a named contract, entry criteria, and risk parameters.

### Tool-Grounded Analysis
- **As a user**, I want recommendation agents to verify and supplement pre-fetched data using tools (live quotes, IV lookups, correlation checks), so recommendations are grounded in the freshest available data.
  - *Acceptance*: Each desk's `DomainAssessment` includes `tools_used` showing which tools were called during recommendation mode.

### Richer Risk Assessment
- **As a risk-conscious trader**, I want the synthesis to show me which desks disagreed, what the agreement score is, and what the dissenting view was, so I can gauge conviction.
  - *Acceptance*: `PositionRecommendation` includes `agent_agreement_score`, `dissenting_desks`, and individual `DomainAssessment` results are accessible.

### Backward Compatibility
- **As an existing user**, I want my historical debate results to remain viewable and my outcome tracking / learning pipeline to continue working, so I don't lose historical data.
  - *Acceptance*: `GET /api/debate/{id}` checks both old `ai_theses` and new `recommendation_results` tables. Learning module reads from both.

### Interactive Mode Unchanged
- **As an agency user**, I want `options-arena agency ask "..."` to work exactly as before, so the unification doesn't regress interactive Q&A.
  - *Acceptance*: All existing agency tests pass without modification. Interactive desk agents (`Agent[DeskDeps, str]`) are untouched.

## Architecture & Design

### Chosen Approach: Big Bang Replacement

Delete all 13 debate-specific files. Each desk gains a second agent instance for recommendation mode. A new synthesis agent replaces algorithmic verdict computation.

**Why big bang over gradual migration**:
- The debate system has zero external consumers — it's only called by CLI `debate` and API `POST /api/debate`
- Keeping both systems alive during migration doubles the test surface and creates confusing "which path am I on?" logic
- The desk agents already cover all 6 analytical domains with richer tool access
- Clean break eliminates 13 files of dead code immediately

**Why NOT big bang**:
- Higher risk of regression in a single PR
- Mitigation: Epic decomposition with verification gates between each epic

### Dual-Instance Pattern (Per Desk)

PydanticAI enforces a single `output_type` per Agent instance. Each desk file gains a second agent:

```python
# Existing (UNCHANGED) — interactive Q&A mode
vol_desk: Agent[DeskDeps, str] = Agent(
    model=None, deps_type=DeskDeps, output_type=str,
    tools=build_volatility_toolset(),
)

# NEW — recommendation mode (structured output)
vol_desk_recommend: Agent[DeskDeps, VolatilityAssessment] = Agent(
    model=None, deps_type=DeskDeps, output_type=VolatilityAssessment,
    retries=2, tools=build_volatility_toolset(),
)
```

Both instances share:
- Same `DeskDeps` dependency type (extended with optional scan data)
- Same toolset (domain-specific tools)
- Same service access pattern

They differ in:
- `output_type`: `str` (interactive) vs `DomainAssessment` subclass (recommendation)
- System prompt: conversational vs recommendation-focused
- `@output_validator`: recommendation agents get think-tag stripping + validation

### Extended DeskDeps

**Prerequisite fix**: The current `DeskDeps` has a dataclass field ordering violation —
`fred: FredService | None = None` (with default) precedes `repo: Repository` (no default).
Python dataclasses require all non-default fields before fields with defaults. This must be
fixed first by reordering `repo` before `fred`, or giving `repo` a sentinel default. The
fix is part of Epic B step 1.

```python
@dataclass
class DeskDeps:
    # Existing fields — reordered: non-defaults first, then defaults
    query: str
    ticker: str
    market_data: MarketDataService
    options_data: OptionsDataService
    repo: Repository                                    # moved before fred (no default)
    fred: FredService | None = None
    tools_used: list[str] = field(default_factory=list)
    learned_patterns: str = ""

    # NEW: Pre-fetched context for recommendation mode
    # All None in interactive mode — recommendation orchestrator populates these
    ticker_score: TickerScore | None = None
    contracts: list[OptionContract] = field(default_factory=list)
    market_context: MarketContext | None = None
```

Interactive callers pass `ticker_score=None, contracts=[], market_context=None` (defaults).
Recommendation orchestrator populates all three from scan pipeline data.

**Impact of reorder**: All existing callers that use positional args for `DeskDeps` will
break. Callers must switch to keyword args. Grep for `DeskDeps(` across the codebase and
update all call sites. This is a small change since most callers already use keyword args.

### New Models (`models/recommendation.py`)

#### DomainAssessment Hierarchy

Uses a **discriminated union** on the `desk` field for polymorphic deserialization.
When reading `assessments_json` from SQLite, the `desk` value determines which subclass
to instantiate. Pydantic v2 supports this via `Discriminator` + `Tag` (Context7-verified).

```python
from typing import Annotated
from pydantic import Discriminator, Tag

class DomainAssessment(BaseModel):
    """Base assessment — all desks produce this in recommendation mode."""
    model_config = ConfigDict(frozen=True)
    desk: DeskType                         # discriminator field for union deserialization
    direction: SignalDirection
    confidence: float          # [0.0, 1.0], field_validator + isfinite
    summary: str
    key_factors: list[str]     # 3-5 bullet points
    risks: list[str]
    contracts_referenced: list[str]
    tools_used: list[str]
    model_used: str

# Per-desk subclasses with domain-specific fields
class TrendAssessment(DomainAssessment):
    desk: Literal[DeskType.TREND] = DeskType.TREND  # narrows discriminator
    trend_strength: float | None = None     # ADX-derived, 0-100
    momentum_signal: str | None = None      # "accelerating", "decelerating", "neutral"

class VolatilityAssessment(DomainAssessment):
    desk: Literal[DeskType.VOLATILITY] = DeskType.VOLATILITY
    iv_regime: VolRegime | None = None
    vol_skew_assessment: str | None = None
    term_structure_shape: IVTermStructureShape | None = None

class FlowAssessment(DomainAssessment):
    desk: Literal[DeskType.FLOW] = DeskType.FLOW
    flow_bias: str | None = None            # "call-heavy", "put-heavy", "balanced"
    unusual_activity_noted: bool = False

class FundamentalAssessment(DomainAssessment):
    desk: Literal[DeskType.FUNDAMENTAL] = DeskType.FUNDAMENTAL
    valuation_signal: ValuationSignal | None = None
    catalyst_timeline: str | None = None

class RiskDeskAssessment(DomainAssessment):
    desk: Literal[DeskType.RISK] = DeskType.RISK
    max_position_pct: float | None = None
    hedging_suggestion: str | None = None
    portfolio_correlation_note: str | None = None

class ContrarianAssessment(DomainAssessment):
    desk: Literal[DeskType.CONTRARIAN] = DeskType.CONTRARIAN
    consensus_challenged: str | None = None
    contrarian_thesis: str | None = None

# Discriminated union type alias for deserialization from JSON
AnyAssessment = Annotated[
    Annotated[TrendAssessment, Tag(DeskType.TREND)]
    | Annotated[VolatilityAssessment, Tag(DeskType.VOLATILITY)]
    | Annotated[FlowAssessment, Tag(DeskType.FLOW)]
    | Annotated[FundamentalAssessment, Tag(DeskType.FUNDAMENTAL)]
    | Annotated[RiskDeskAssessment, Tag(DeskType.RISK)]
    | Annotated[ContrarianAssessment, Tag(DeskType.CONTRARIAN)],
    Discriminator("desk"),
]
```

**Deserialization**: Use `TypeAdapter(list[AnyAssessment])` to deserialize
`assessments_json` from SQLite. Each JSON object's `desk` field determines the
correct subclass. This preserves domain-specific fields through the round-trip.

#### PositionRecommendation

```python
class PositionRecommendation(BaseModel):
    """Final synthesis output — replaces TradeThesis."""
    model_config = ConfigDict(frozen=True)

    ticker: str
    direction: SignalDirection
    confidence: float                      # [0.0, 1.0]
    recommended_contract: str              # "AAPL 190C 2026-04-18"
    entry_price: Decimal                   # mid price or specified limit
    entry_criteria: str                    # "Enter on pullback to $188 support"
    exit_criteria: str                     # "Exit at 50% profit or 2 weeks before expiry"
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    position_size_pct: float               # % of portfolio, from Kelly/vol-regime
    position_rationale: str                # Why this size
    risk_reward_ratio: float               # reward/risk
    max_loss_estimate: str                 # "Max loss: $X (Y% of position)"
    recommended_strategy: SpreadType | None = None
    strategy_rationale: str
    summary: str                           # 2-3 sentence synthesis
    key_factors: list[str]                 # Top 5 factors from all desks
    risk_assessment: str                   # Synthesized risk view
    agent_agreement_score: float | None = None  # 0-1, fraction agreeing
    dissenting_desks: list[DeskType] = Field(default_factory=list)
    model_used: str

    # Decimal serializers, confidence validator, isfinite guards
```

#### RecommendationResult

```python
class RecommendationResult(BaseModel):
    """Complete recommendation output — replaces DebateResult.

    ``arbitrary_types_allowed=True`` is required because ``RunUsage`` is a plain
    dataclass from pydantic-ai, not a Pydantic BaseModel (Context7-verified).
    ``RunUsage`` supports ``__add__`` for accumulation across agent runs.
    """
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    context: MarketContext
    assessments: list[AnyAssessment]       # discriminated union preserves subclass types
    recommendation: PositionRecommendation
    total_usage: RunUsage                  # pydantic_ai.usage.RunUsage — plain dataclass
    duration_ms: int
    is_fallback: bool
    citation_density: float = 0.0
```

**Serialization note**: `assessments` uses the `AnyAssessment` discriminated union type.
`model_dump_json()` includes the `desk` discriminator field in each assessment JSON object.
`model_validate_json()` uses `desk` to reconstruct the correct subclass. Test this
round-trip explicitly.

### Synthesis Agent

New `agents/synthesis_agent.py` with dedicated deps:

```python
@dataclass
class SynthesisDeps:
    context: MarketContext
    assessments: list[DomainAssessment]
    contracts: list[OptionContract]
    ticker_score: TickerScore
    learned_patterns: str = ""
    tuned_weights: str = ""  # <<<TUNED_WEIGHTS>>> block from vote weight tuning

synthesis_agent: Agent[SynthesisDeps, PositionRecommendation] = Agent(
    model=None, deps_type=SynthesisDeps,
    output_type=PositionRecommendation, retries=2,
    tools=build_synthesis_toolset(),
)
```

The synthesis agent:
- Receives all 6 domain assessments + scan data + contracts
- Has tool access for additional lookups (synthesis toolset)
- Produces a single `PositionRecommendation`
- Weighs agreement/disagreement across desks
- Selects the specific contract, entry/exit, and position size

### Recommendation Orchestrator (`agents/recommendation_orchestrator.py`)

```
Phase 0: Build MarketContext + inject scan data into DeskDeps
  - Reuse existing build_market_context()
  - Pre-fetch TickerScore, contracts, quote, ticker_info from scan/services

Phase 1 (parallel): 6 domain desks → DomainAssessment each
  - asyncio.gather with return_exceptions=True
  - Each desk gets DeskDeps with ticker_score + contracts + market_context populated
  - Failed desks → fallback DomainAssessment (confidence=0.2, direction=NEUTRAL)
  - Research desk excluded (synthesis replaces its cross-domain role)

Phase 2 (sequential): Synthesis agent → PositionRecommendation
  - Receives all Phase 1 assessments + scan data + contracts
  - Has synthesis toolset for additional lookups
  - Timeout: synthesis_timeout (default 90s)
  - Failure → data-driven fallback PositionRecommendation

Phase 3: Persist + extract predictions
  - Save to recommendation_results table
  - Extract agent_predictions (reuse existing table)

Return: RecommendationResult
```

**Never-raises contract**: Same as current `run_debate()` — on any failure, return data-driven fallback with `is_fallback=True`.

### Persistence (Migration 037)

```sql
-- New table for unified recommendation results
CREATE TABLE IF NOT EXISTS recommendation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_run_id INTEGER,
    ticker TEXT NOT NULL,
    assessments_json TEXT NOT NULL,       -- JSON array of DomainAssessment (discriminated union)
    recommendation_json TEXT NOT NULL,    -- JSON PositionRecommendation
    market_context_json TEXT,             -- JSON MarketContext
    total_tokens INTEGER NOT NULL DEFAULT 0,
    model_name TEXT NOT NULL,
    duration_ms INTEGER NOT NULL DEFAULT 0,
    is_fallback INTEGER NOT NULL DEFAULT 0,
    desks_completed INTEGER NOT NULL DEFAULT 0,
    recommendation_protocol TEXT NOT NULL DEFAULT 'unified_v1',
    citation_density REAL NOT NULL DEFAULT 0.0,
    created_at TEXT NOT NULL,
    FOREIGN KEY (scan_run_id) REFERENCES scan_runs(id)
);

CREATE INDEX IF NOT EXISTS idx_recommendation_results_ticker ON recommendation_results(ticker);
CREATE INDEX IF NOT EXISTS idx_recommendation_results_created_at ON recommendation_results(created_at);

-- Tag existing agent_predictions with protocol for forward-only analytics filtering
ALTER TABLE agent_predictions ADD COLUMN recommendation_protocol TEXT NOT NULL DEFAULT 'debate_v1';
```

Old `ai_theses` table kept read-only for historical viewing. No new writes, no analytics queries.

### Module Changes

#### New Files (12)

| File | Purpose |
|------|---------|
| `models/recommendation.py` | DomainAssessment hierarchy, PositionRecommendation, RecommendationResult |
| `agents/recommendation_orchestrator.py` | `run_recommendation()` — 3-phase orchestrator |
| `agents/synthesis_agent.py` | Synthesis agent + SynthesisDeps |
| `agents/prompts/recommend_trend.py` | Recommendation-mode trend prompt |
| `agents/prompts/recommend_volatility.py` | Recommendation-mode volatility prompt |
| `agents/prompts/recommend_flow.py` | Recommendation-mode flow prompt |
| `agents/prompts/recommend_fundamental.py` | Recommendation-mode fundamental prompt |
| `agents/prompts/recommend_risk.py` | Recommendation-mode risk prompt |
| `agents/prompts/recommend_contrarian.py` | Recommendation-mode contrarian prompt |
| `agents/prompts/synthesis.py` | Synthesis agent prompt |
| `data/_recommendation.py` | RecommendationMixin — save/get/list recommendation results |
| `data/migrations/037_recommendation_results.sql` | New table + indexes |

#### Modified Files (~15)

| File | Changes |
|------|---------|
| `agents/_desk_deps.py` | Fix field ordering (`repo` before `fred`), add `ticker_score`, `contracts`, `market_context` optional fields. Update all `DeskDeps(` call sites to keyword args. |
| `agents/volatility_desk.py` | Add `vol_desk_recommend` agent + `run_vol_desk_recommendation()` |
| `agents/risk_desk.py` | Add `risk_desk_recommend` agent + `run_risk_desk_recommendation()` |
| `agents/trend_desk.py` | Add `trend_desk_recommend` agent + `run_trend_desk_recommendation()` |
| `agents/flow_desk.py` | Add `flow_desk_recommend` agent + `run_flow_desk_recommendation()` |
| `agents/fundamental_desk.py` | Add `fundamental_desk_recommend` agent + `run_fundamental_desk_recommendation()` |
| `agents/contrarian_desk.py` | Add `contrarian_desk_recommend` agent + `run_contrarian_desk_recommendation()` |
| `agents/_toolsets.py` | Add `build_synthesis_toolset()` |
| `agents/_parsing.py` | Add `build_cleaned_domain_assessment()`. Keep render functions + `PROMPT_RULES_APPENDIX`. Remove `DebateDeps`/`DebateResult` after cutover. |
| `agents/__init__.py` | Replace debate exports with recommendation exports |
| `cli/` (debate command) | Rewrite to use `run_recommendation()` |
| `api/routes/` (debate routes) | Rewrite to use `run_recommendation()` |
| `api/schemas.py` | Add recommendation response schemas |
| `data/repository.py` | Add `RecommendationMixin` |
| `models/__init__.py` | Re-export new recommendation models |

#### Deleted Files (13)

| File | Reason |
|------|--------|
| `agents/trend_agent.py` | Debate agent replaced by desk recommendation mode |
| `agents/volatility.py` | Debate agent replaced |
| `agents/flow_agent.py` | Debate agent replaced |
| `agents/fundamental_agent.py` | Debate agent replaced |
| `agents/risk.py` | Debate agent replaced |
| `agents/contrarian_agent.py` | Debate agent replaced |
| `agents/orchestrator.py` | Debate orchestrator replaced by `recommendation_orchestrator.py` |
| `agents/prompts/trend_agent.py` | Debate prompt |
| `agents/prompts/volatility.py` | Debate prompt |
| `agents/prompts/flow_agent.py` | Debate prompt |
| `agents/prompts/fundamental_agent.py` | Debate prompt |
| `agents/prompts/risk.py` | Debate prompt |
| `agents/prompts/contrarian_agent.py` | Debate prompt |

Note: `agents/constraints.py` may also be removable if constraint logic is folded into synthesis agent validation.

### Boundary Table Impact

| Module | Change |
|--------|--------|
| `agents/` | Desk agents now access `models/recommendation.py` for output types. Recommendation orchestrator replaces debate orchestrator. Same boundary rules apply — no inter-agent imports, no pricing imports, no data fetching in agents themselves (tools do that). |
| `models/` | New `recommendation.py` — data shapes only, no logic. |
| `data/` | New `_recommendation.py` mixin — persistence only. |
| All other modules | **No changes** — scan pipeline, scoring, pricing, services, indicators, learning all unchanged. |

Key: The recommendation orchestrator follows the same pattern as the debate orchestrator — it coordinates agents but doesn't fetch data itself. Data comes from the caller (CLI/API) or from desk tools at runtime.

### Config Strategy

Keep `DebateConfig` name for env var backward compatibility (`ARENA_DEBATE__*`). Remove dead
fields from the old debate system. Add new fields for the unified system.

**Dead fields to remove** (consumed only by deleted orchestrator/debate code):
- `enable_volatility_agent` — all 6 desks always run (use `disabled_desks` to skip)
- `enable_rebuttal` — no rebuttal concept in unified system
- `phase1_parallelism` — replaced by `desk_parallelism` (see below)
- `phase1_batch_delay` — replaced by `desk_parallelism` semaphore

**Fields preserved** (still consumed by model_config.py, rate limiting, or general config):
- `provider`, `model`, `anthropic_model`, `api_key`, `anthropic_api_key` — LLM dispatch
- `enable_extended_thinking`, `thinking_budget_tokens` — Anthropic extended thinking
- `agent_timeout`, `num_ctx`, `retries`, `temperature` — per-agent run config
- `fallback_confidence`, `max_total_duration` — fallback and total timeout
- `min_debate_score` — renamed to `min_recommendation_score` (see below)
- `batch_ticker_delay` — batch pacing
- `rate_limit_retries`, `rate_limit_max_wait` — transport-level retry
- `auto_tune_weights` — opt-in weight tuning

**New fields**:

```python
class DebateConfig(BaseModel):
    # ... preserved fields above ...

    # NEW — unified system
    synthesis_timeout: float = 90.0              # synthesis agent timeout (seconds)
    recommendation_protocol: str = "unified_v1"  # version tag for analytics
    min_recommendation_score: float = 30.0       # replaces min_debate_score
    desk_parallelism: int = 6                    # max concurrent desk agents (6=all parallel)
    disabled_desks: list[str] = Field(default_factory=list)  # e.g. ["flow"] to skip flow desk
```

**Desk enable/disable**: Instead of boolean toggles per agent (`enable_volatility_agent`),
the unified system uses `disabled_desks: list[str]` — a list of `DeskType` values to skip.
Empty list (default) = all 6 desks run. This is more flexible than per-agent booleans.

**Parallelism for paid providers**: `desk_parallelism` controls the `asyncio.Semaphore` that
gates concurrent desk agent runs. Default `6` (all parallel) assumes a paid API tier.
Set `desk_parallelism=2` for Groq free tier (30 RPM). The old `phase1_parallelism=2` existed
for the same reason — this is the direct replacement.

**Provider migration note**: This project is moving to Anthropic API and paid Groq tiers.
The default `desk_parallelism=6` reflects this. Groq free tier support is not a priority.

### Recommendation Tool Budget Config

Recommendation-mode agents may need different tool budgets than interactive-mode agents.
Interactive mode uses `AgencyConfig.default_tool_budget` (4). Recommendation agents do
deeper analysis with pre-fetched context — they may need fewer tool calls (context already
available) or more (verification + supplemental lookups).

**Decision**: Reuse `AgencyConfig` budgets for V1. Recommendation agents get the same
per-desk budgets as interactive agents. If experience shows recommendation agents need
different budgets, add `recommendation_tool_budget: int` to `AgencyConfig` later.

Rationale: Starting with the same budgets avoids premature config proliferation. The
recommendation orchestrator can always override via `UsageLimits` at `run()` time.

### Backward Compatibility

| Concern | Resolution |
|---------|-----------|
| Historical `ai_theses` data | Table kept read-only for viewing. `DebateMixin` preserved for `GET /api/debate/{id}` with old IDs. **Excluded from analytics** — no new queries against it. |
| `GET /api/debate/{id}` | Checks both `ai_theses` (old IDs) and `recommendation_results` (new IDs). Returns appropriate schema per table. |
| `agent_predictions` table | Reused. New predictions tagged with `recommendation_protocol='unified_v1'`. Analytics queries filter by protocol. Old predictions tagged `'debate_v1'` via backfill migration. |
| `learning/` module | Indicator tuning + strategy mining unchanged. Vote weight tuning preserved — weights injected into synthesis prompt as advisory context. All learning queries filter `WHERE recommendation_protocol = 'unified_v1'`. |
| Outcome tracking | `RecommendedContract` persistence unchanged. P&L collection reads contract data regardless of source. |
| Interactive desk queries | Completely unchanged — `Agent[DeskDeps, str]` instances not modified. |
| Old analytics data | Archived. Old debate accuracy/calibration viewable but not mixed into new analytics. Clean separation prevents misleading comparisons. |

### Data Flow Comparison

#### Current (Debate)
```
CLI/API → build_market_context() → DebateDeps (pre-fetched)
  → Phase 1: Trend + Vol + [Flow + Fund] parallel → AgentResponse
  → Phase 2: Risk → RiskAssessment
  → Phase 3: Contrarian → AgentResponse
  → Phase 4: synthesize_verdict() (algorithmic) → TradeThesis
  → DebateResult
```

#### New (Recommendation)
```
CLI/API → build_market_context() → DeskDeps (pre-fetched + tools)
  → Phase 1: 6 desks parallel → DomainAssessment (each desk uses tools)
  → Phase 2: Synthesis agent → PositionRecommendation (AI-driven)
  → Phase 3: Persist
  → RecommendationResult
```

Key differences:
- All 6 desks run in parallel (not 3-phase sequential)
- Each desk can use tools to verify/supplement pre-fetched data
- Synthesis is AI-driven (not algorithmic weighted averaging)
- Output is a specific position recommendation (not a directional thesis)

## Relationship to Existing Epics

### ai-agency-evolution PRD

This PRD **supersedes** the debate portion of `ai-agency-evolution`:
- Debate agents, debate orchestrator, `DebateDeps`, `DebateResult` — all replaced
- Interactive desk agents, routing, learning, strategy mining — all **preserved unchanged**

### Epics 7 (Analysis Tools) and 8 (ML Tools)

These are **purely additive** and fully compatible:
- They add tools to `_toolsets.py` — tools are used by both interactive and recommendation modes
- Can proceed independently (before, after, or in parallel with this PRD)
- No coordination needed beyond the existing `_toolsets.py` pattern

### Learning Module

**Partially affected** — indicator weight tuning and strategy mining are unchanged, but
vote weight tuning becomes dead code and must be addressed.

- **Indicator weight tuning** (`tune_indicator_weights()`): Unchanged — correlates scan-time
  indicator values with contract P&L outcomes. No debate/recommendation involvement.
- **Strategy mining** (`run_strategy_mining()`): Unchanged — reads from `contract_outcomes`.
- **Learned patterns**: Unchanged — injected via `DeskDeps.learned_patterns`.
- **Vote weight tuning** (`tune_vote_weights()`): **Broken** — tunes `AGENT_VOTE_WEIGHTS`
  which are consumed by `synthesize_verdict()`. The synthesis agent replaces
  `synthesize_verdict()`, so tuned weights have no consumer. See below.

### Vote Weight Tuning — Impact & Resolution

**Problem**: `AGENT_VOTE_WEIGHTS` are consumed by `synthesize_verdict()` for algorithmic
weighted averaging of agent directions. The synthesis agent replaces this function entirely,
making its own AI-driven judgment about how to weigh assessments. `tune_vote_weights()`
would tune weights that nothing uses.

**Decision**: Inject tuned weights into the synthesis agent prompt as advisory context.
The synthesis agent receives the weights as a `<<<TUNED_WEIGHTS>>>` block showing each
desk's historical accuracy and current weight. This gives the synthesis agent informed
priors while preserving its ability to override based on current assessment content.

**Implementation**:
1. `tune_vote_weights()` continues to function — computes desk accuracy and optimal weights
2. Weights are loaded from DB by the recommendation orchestrator before synthesis
3. Injected into `SynthesisDeps` as a formatted string (same pattern as `learned_patterns`)
4. Synthesis prompt instructs the agent to consider historical accuracy but not be bound by it
5. `AGENT_VOTE_WEIGHTS` constant remains as the default/fallback when no tuned weights exist

**What changes**:
- `SynthesisDeps` gains a `tuned_weights: str = ""` field
- Recommendation orchestrator loads weights via existing `Repository.get_weight_history()`
- Synthesis prompt gains a `<<<TUNED_WEIGHTS>>>` section
- `tune_vote_weights()` output format unchanged — same DB persistence

**What stays the same**:
- `tune_vote_weights()` function — unchanged
- `AGENT_VOTE_WEIGHTS` constant — unchanged (default values)
- `agent_predictions` table — reused, populated from `DomainAssessment` list
- `get_agent_accuracy()` Repository query — unchanged (joins predictions with outcomes)
- CLI `learn tune-votes` / API `/api/learning/tune-votes` — unchanged

## Requirements

### Functional Requirements

1. **FR-1**: Each of the 6 domain desks (Trend, Vol, Flow, Fundamental, Risk, Contrarian) must have a recommendation-mode agent that produces a typed `DomainAssessment` subclass
2. **FR-2**: Recommendation-mode agents must have access to the same toolsets as interactive-mode agents
3. **FR-3**: Recommendation-mode agents receive pre-fetched scan data (TickerScore, contracts, MarketContext) via extended DeskDeps
4. **FR-4**: A synthesis agent must produce a `PositionRecommendation` from all domain assessments
5. **FR-5**: `PositionRecommendation` must include: specific contract, entry/exit criteria, stop loss, take profit, position size, risk/reward ratio
6. **FR-6**: `run_recommendation()` must never raise — data-driven fallback on any failure
7. **FR-7**: Phase 1 (6 desks) runs in parallel via `asyncio.gather(return_exceptions=True)`
8. **FR-8**: Failed desks produce fallback `DomainAssessment` (confidence=0.2, direction=NEUTRAL)
9. **FR-9**: Results persisted to `recommendation_results` table with full JSON
10. **FR-10**: Historical `ai_theses` data remains viewable (read-only) but excluded from analytics. New analytics queries target `recommendation_results` only.
11. **FR-11**: CLI `debate` command uses `run_recommendation()` and renders `PositionRecommendation`
12. **FR-12**: API `POST /api/debate` uses `run_recommendation()` and returns `RecommendationResult`
13. **FR-13**: Interactive desk agents (`Agent[DeskDeps, str]`) are completely unchanged
14. **FR-14**: Agent predictions extracted from `DomainAssessment` list for learning pipeline compatibility

### Non-Functional Requirements

1. **NFR-1**: Recommendation completes within 120s total (6 parallel desks + synthesis)
2. **NFR-2**: Per-desk timeout: `config.agent_timeout` (default 60s)
3. **NFR-3**: Synthesis timeout: `config.synthesis_timeout` (default 90s)
4. **NFR-4**: Fallback computation < 1s (no LLM, pure template)
5. **NFR-5**: Windows compatible (no Unix-only dependencies)
6. **NFR-6**: All deleted debate code has zero remaining importers before deletion
7. **NFR-7**: Test coverage: new code at same level as existing agent tests

## Testing Strategy

### Unit Tests
- **Models**: Construction, frozen, validation, JSON round-trip for all new models
- **DomainAssessment hierarchy**: Each subclass with domain-specific fields
- **PositionRecommendation**: Decimal precision, confidence bounds, all validators
- **RecommendationResult**: Serialization round-trip

### Agent Tests (TestModel)
- Each desk's recommendation-mode agent produces valid `DomainAssessment` subclass
- Synthesis agent produces valid `PositionRecommendation`
- Output validators strip think tags correctly
- `models.ALLOW_MODEL_REQUESTS = False` in every test file

### Orchestrator Tests
- Success path: all 6 desks succeed + synthesis succeeds
- Partial failure: 2 desks fail → fallback assessments → synthesis still runs
- Full failure: all desks fail → data-driven fallback `RecommendationResult`
- Synthesis failure: desks succeed but synthesis fails → fallback from assessments
- Timeout: per-desk and total timeout handling
- Progress callback invocation

### Persistence Tests
- `RecommendationMixin` save/get/list round-trip
- Migration 037 creates table correctly
- Backward compat: `DebateMixin` still reads old `ai_theses`

### Integration Tests
- `run_recommendation()` end-to-end with TestModel
- CLI `debate` command rendering
- API endpoint response schema

### Regression Tests
- All existing agency/routing tests pass unchanged
- All existing learning tests pass unchanged
- Interactive desk query tests pass unchanged

### Estimated Test Count
- ~80-100 new tests across all 4 epics
- ~50-80 existing debate tests to rewrite/remove

## Implementation Phasing

### Epic A: Foundation Models + Synthesis Agent (Issues: 4-5)

**Scope**: New models, synthesis agent, synthesis toolset. No desk modifications yet.

1. Create `models/recommendation.py` — `DomainAssessment` hierarchy (base + 6 subclasses), `PositionRecommendation`, `RecommendationResult`
2. Create `SynthesisDeps` dataclass
3. Create `agents/prompts/synthesis.py` — synthesis agent prompt
4. Create `agents/synthesis_agent.py` — synthesis agent + output validator + runner
5. Add `build_synthesis_toolset()` to `agents/_toolsets.py`
6. Re-export new models from `models/__init__.py`
7. Unit tests for all new models, synthesis agent (TestModel)

**Dependencies**: None
**Verification**: `ruff check`, `pytest`, `mypy --strict`

### Epic B: Desk Recommendation Mode (Issues: 5-6)

**Scope**: Extend DeskDeps, add recommendation agent + runner to each desk, create recommendation prompts.

1. Fix `DeskDeps` field ordering (move `repo` before `fred` to satisfy dataclass non-default-before-default rule). Update all `DeskDeps(` call sites to use keyword args. Then extend with `ticker_score`, `contracts`, `market_context` fields.
2. Create 6 recommendation prompts (`agents/prompts/recommend_*.py`)
3. Add `build_cleaned_domain_assessment()` to `agents/_parsing.py`
4. Add recommendation agent + runner to `volatility_desk.py` (`vol_desk_recommend`, `run_vol_desk_recommendation`)
5. Same for `risk_desk.py`, `trend_desk.py`, `flow_desk.py`, `fundamental_desk.py`, `contrarian_desk.py`
6. Unit tests for each desk's recommendation mode (TestModel)

**Dependencies**: Epic A (DomainAssessment models exist)
**Verification**: `ruff check`, `pytest`, `mypy --strict`, existing interactive tests still pass

### Epic C: Orchestrator + Persistence (Issues: 4-5)

**Scope**: Recommendation orchestrator, migration, persistence mixin, integration tests.

1. Create `data/migrations/037_recommendation_results.sql`
2. Create `data/_recommendation.py` — `RecommendationMixin`
3. Wire `RecommendationMixin` into `data/repository.py`
4. Create `agents/recommendation_orchestrator.py` — `run_recommendation()` (3-phase)
5. Move `build_market_context()`, `extract_agent_predictions()`, and other reusable functions from current `orchestrator.py`
6. Tests: orchestrator (success, partial failure, full fallback, timeout), persistence round-trip

**Dependencies**: Epics A + B (models + desk recommendation agents exist)
**Verification**: `ruff check`, `pytest`, `mypy --strict`

### Epic D: Big Bang Cutover + Cleanup (Issues: 6-8)

**Scope**: Rewire CLI + API, delete debate code, update exports, rewrite tests.

1. Rewrite CLI debate command to use `run_recommendation()`, render `PositionRecommendation`
2. Rewrite API debate routes to use `run_recommendation()`, return `RecommendationResult`
3. Update `api/schemas.py` with recommendation response schemas
4. Update `reporting/debate_export.py` for new model shape
5. Update `agents/__init__.py` — replace debate exports with recommendation exports
6. Delete 13 debate-specific files (6 agents, 1 orchestrator, 6 prompts)
7. Clean up `_parsing.py` — remove `DebateDeps`, `DebateResult`
8. Update/rewrite affected tests
9. Update module CLAUDE.md files (agents/, models/, data/)
10. Full regression suite

**Dependencies**: Epic C (orchestrator works end-to-end)
**Verification**: Full suite — `ruff check`, `pytest tests/ -v`, `mypy --strict`, manual CLI + API + web testing

### Phasing Diagram

```
Epic A (Models + Synthesis)  ──> Epic B (Desk Recommend Mode) ──> Epic C (Orchestrator) ──> Epic D (Cutover)
```

Strictly sequential — each epic depends on the previous.

**Total: ~19-24 issues across 4 epics.**

## Success Criteria

1. `options-arena debate AAPL` produces a `PositionRecommendation` with specific contract, entry/exit, sizing
2. Recommendation uses tool-fetched data (visible in `tools_used` fields)
3. All 6 desks produce typed `DomainAssessment` subclasses with domain-specific fields
4. Synthesis agent weighs agreement/disagreement across desks, informed by tuned weights
5. Fallback path works: LLM unavailable → data-driven recommendation with `is_fallback=True`
6. Historical debate data viewable via API (read-only, excluded from new analytics)
7. Interactive desk queries (`agency ask/chat`) work identically
8. Learning pipeline works with forward-only analytics (`recommendation_protocol` filtering)
9. `disabled_desks` config allows skipping individual desks
10. `desk_parallelism` semaphore controls concurrent LLM calls (default 6 for paid tiers)
11. SpreadAnalysis passes through to MarketContext
12. Citation density computed from DomainAssessment + PositionRecommendation text
13. All tests pass (existing + new)
14. 13 debate files deleted, dead DebateConfig fields removed, net code reduction

## Constraints & Assumptions

- **LLM provider**: Moving to Anthropic API or paid Groq tiers. Groq free tier (30 RPM) is not a design target. `desk_parallelism=6` (all parallel) is the default.
- **LLM cost**: Recommendation mode costs 7 LLM calls (6 desks + synthesis) vs current 6 (debate). ~17% increase per recommendation. Acceptable for paid tiers.
- **Parallel execution**: Phase 1 runs up to `desk_parallelism` desks concurrently via `asyncio.Semaphore`. Default 6 (all parallel). Set lower for rate-limited tiers.
- **Synthesis quality**: The synthesis agent's recommendation quality depends on prompt engineering. Initial prompts will be conservative; iteration expected.
- **No new dependencies**: Uses existing PydanticAI, services, models infrastructure.
- **Migration 037**: Must be the next sequential migration number at time of implementation. Adds `recommendation_results` table + `recommendation_protocol` column on `agent_predictions`.
- **Forward-only analytics**: New analytics queries target `recommendation_results` only. Old `ai_theses` data is viewable but excluded from analytics. No normalization layer between old and new.

## Out of Scope

- **Prompt A/B testing for recommendation prompts** — defer to learning module evolution
- **Frontend DebateResultPage.vue rewrite** — adapt to new data shape but no UX redesign
- **New desk agents** — only existing 6 domain desks get recommendation mode (not Research)
- **Real-time streaming of recommendation progress** — reuse existing WebSocket progress pattern
- **Autonomous execution** — recommendations only, no broker integration

## Resolved Design Decisions

### should_debate() → should_recommend()

The eligibility gate is preserved but renamed. `should_recommend()` checks:
- `composite_score >= config.min_recommendation_score` (default 30.0)
- `direction != SignalDirection.NEUTRAL`

Same logic, new name, reads from `min_recommendation_score` instead of `min_debate_score`.
Called by CLI and API before launching `run_recommendation()`.

### SpreadAnalysis Passthrough

Current `run_debate()` accepts `spread_analysis: SpreadAnalysis | None` and injects spread
fields into `MarketContext`. The new `run_recommendation()` preserves this parameter:

```python
async def run_recommendation(
    ...,
    spread_analysis: SpreadAnalysis | None = None,  # passed through to MarketContext
    ...,
) -> RecommendationResult:
```

Spread data is injected into `MarketContext` by `build_market_context()` (unchanged).
Desks and synthesis agent can reference spread fields in context. No change to spread
computation or persistence — only the passthrough is preserved.

### Citation Density Computation

`compute_citation_density()` extracts text from agent outputs and counts context label
matches. For the new system:

1. **Input**: `render_context_block(market_context)` produces the label set (same as before)
2. **Text extraction**: Concatenate `summary + " ".join(key_factors) + " ".join(risks)` from
   each `DomainAssessment` + `summary + " ".join(key_factors) + risk_assessment` from
   `PositionRecommendation`
3. **Computation**: Same fraction — `labels_cited / total_labels`
4. **Storage**: `citation_density: float` on `RecommendationResult` (already specified)

Add `build_citation_text_from_assessments(assessments, recommendation) -> str` helper in
`_parsing.py` that extracts the concatenated text for citation density computation.

### Analytics — Forward-Only Design

**Decision**: Analytics goes forward-only. No backward compatibility with old `ai_theses`
debate records.

**Rationale**: The old debate system and new recommendation system produce fundamentally
different output shapes. Attempting to normalize them into a single analytics view creates
fragile mapping code and misleading comparisons (a "confidence" from algorithmic verdict
synthesis is not comparable to confidence from an AI synthesis agent).

**What this means**:
- `ai_theses` table: Kept for read-only historical viewing (`GET /api/debate/{id}` with
  old IDs). No new writes. No analytics queries against it.
- `recommendation_results` table: All new analytics queries target this table only.
- `agent_predictions` table: Reused. New predictions written with `recommendation_protocol`
  tag. Analytics queries for accuracy/calibration filter by protocol:
  `WHERE recommendation_protocol = 'unified_v1'`
- Old debate accuracy data is archived — viewable but not mixed into new analytics.
- Learning module (`tune_vote_weights`, `tune_indicator_weights`): Only reads predictions
  tagged with `recommendation_protocol = 'unified_v1'`.
- `debate_mode` column on `ai_theses`: Dead. New system uses `recommendation_protocol` on
  `recommendation_results`. No mapping between old modes and new protocol.

**Migration**: Add `recommendation_protocol TEXT` column to `agent_predictions` table in
migration 037 (alongside the `recommendation_results` table). Backfill existing rows with
`recommendation_protocol = 'debate_v1'` so they can be filtered out.

**Impact on FR-10**: Revised — historical `ai_theses` data remains *viewable* via API
(read-only) but is *excluded from analytics*. This is a simplification, not a regression.

## Open Questions

1. **Research desk in recommendations?** Research desk is excluded from Phase 1 (synthesis replaces its cross-domain role). Should it participate as a 7th assessment? Decision: No for V1 — 6 focused domains + synthesis is cleaner.

2. **Contract selection**: Should the synthesis agent select from pre-computed contracts, or should it have a tool to request additional contracts? Decision: Start with pre-computed contracts from scan pipeline; add tool if needed.

3. **Batch recommendations**: Current batch debate iterates sequentially. Same pattern for recommendations? Decision: Yes — sequential with per-ticker error isolation, same as current.

4. **`constraints.py` fate**: Currently validates contracts before debate. Fold into synthesis agent prompt, keep as pre-check, or remove? Decision: Keep as pre-check — inject `constraint_warnings` into DeskDeps for recommendation agents to reference. Same pattern as current debate system.

## Context7 Verification (2026-03-21)

All external library data shapes verified against Context7 docs. Libraries checked:
`/pydantic/pydantic-ai` (PydanticAI), `/websites/pydantic_dev` (Pydantic v2).

### PydanticAI — All Passed

| Shape | Claim | Context7 | Status |
|-------|-------|----------|--------|
| `Agent(model=None, deps_type=..., output_type=..., retries=2, tools=[...])` | Constructor params | Confirmed: model, deps_type, output_type, retries, tools all valid | PASS |
| `agent.run(query, model=model, deps=deps, usage_limits=limits)` | Run params | Confirmed: model override, deps injection, usage_limits | PASS |
| `@agent.output_validator` | Decorator on recommendation agents | Confirmed: `async def(ctx, output) -> output` or raises `ModelRetry` | PASS |
| `result.usage()` returns `RunUsage` | Token tracking | Confirmed: `RunUsage(input_tokens=N, output_tokens=N, requests=N)` | PASS |
| `RunUsage.__add__` | Accumulation across agents | Already verified in agents/CLAUDE.md:242 | PASS |
| `RunUsage()` empty construction | Fallback path | Existing code: `orchestrator.py:636` | PASS |
| `UsageLimits(request_limit=N, tool_calls_limit=N)` | Tool budget enforcement | Confirmed: raises `UsageLimitExceeded` on excess | PASS |
| `tools=[func1, func2]` in constructor | Toolset pattern | Confirmed: matches existing `build_*_toolset() -> list[object]` | PASS |

### Pydantic v2 — All Passed

| Shape | Claim | Context7 | Status |
|-------|-------|----------|--------|
| `ConfigDict(frozen=True)` | Immutable models | Confirmed: raises `ValidationError` on reassignment | PASS |
| `ConfigDict(arbitrary_types_allowed=True)` | For `RunUsage` on Pydantic model | Confirmed: allows non-Pydantic types as fields | PASS |
| `Field(default_factory=list)` | Default empty lists | Standard Pydantic pattern | PASS |
| `field_validator` with `@classmethod` | Confidence/isfinite guards | Confirmed | PASS |
| `field_serializer` for `Decimal` → `str` | Precision preservation | Project convention; Context7 shows `PlainSerializer` alternative | PASS |
| BaseModel subclass inheritance | `TrendAssessment(DomainAssessment)` | Confirmed: V2 preserves subclass types | PASS |
| Discriminated union via `Discriminator("desk")` | `AnyAssessment` type alias | Pydantic v2 feature for polymorphic deserialization | PASS |

### Corrections Applied from Verification

| Finding | Severity | Correction |
|---------|----------|------------|
| `DeskDeps` field ordering: `fred` (default) before `repo` (no default) violates dataclass rules | **Must fix** | Reordered `repo` before `fred`. Added call site migration note. |
| `DebateConfig.api_key` shown as `str \| None` but actual is `SecretStr \| None` | **Must fix** | Fixed code sample to list all existing fields as comments with correct types. |
| `DebateConfig` partial field listing implies missing fields | **Must fix** | Changed to explicit "all existing fields preserved" with full field list comment. |
| No discriminator for `list[DomainAssessment]` deserialization | **Recommended** | Added `Literal[DeskType.X]` narrowing on each subclass + `AnyAssessment` discriminated union type. |
| No tool budget discussion for recommendation mode | **Recommended** | Added "Recommendation Tool Budget Config" section — reuse `AgencyConfig` budgets for V1. |
